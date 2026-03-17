from __future__ import annotations

import asyncio
import base64
import io
import json
import math
import tempfile
import time
import wave
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import FastAPI, File, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None

try:
    import mediapipe as mp
except ImportError:  # pragma: no cover
    mp = None


class DetectionResponse(BaseModel):
    is_fake: bool
    confidence: float = Field(ge=0.0, le=1.0)
    pulse_value: float
    landmarks: list[dict[str, float]]
    reasons: list[str]
    signal_breakdown: dict[str, float]
    mode: str
    threat_level: str
    timestamp: float


@dataclass
class StreamState:
    green_history: deque[float] = field(default_factory=lambda: deque(maxlen=180))
    motion_history: deque[float] = field(default_factory=lambda: deque(maxlen=120))
    blink_history: deque[float] = field(default_factory=lambda: deque(maxlen=60))
    center_history: deque[tuple[float, float]] = field(default_factory=lambda: deque(maxlen=120))
    verdict_history: deque[bool] = field(default_factory=lambda: deque(maxlen=30))


FACE_MESH = (
    mp.solutions.face_mesh.FaceMesh(
        static_image_mode=False,
        max_num_faces=1,
        refine_landmarks=True,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    if mp is not None
    else None
)

FOREHEAD_INDEXES = [10, 67, 103, 109, 151, 338, 297, 332]
LEFT_EYE = [33, 160, 158, 133, 153, 144]
RIGHT_EYE = [362, 385, 387, 263, 373, 380]

app = FastAPI(title="Bio-VeriSync DeepWatch", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STREAMS: dict[str, StreamState] = {}


def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def decode_base64_image(data: str) -> np.ndarray:
    encoded = data.split(",", 1)[1] if "," in data else data
    raw = base64.b64decode(encoded)
    if cv2 is None:
        raise RuntimeError("opencv-python is required for image decoding")
    array = np.frombuffer(raw, dtype=np.uint8)
    frame = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError("Unable to decode frame")
    return frame


def bytes_to_image(payload: bytes) -> np.ndarray:
    if cv2 is None:
        raise RuntimeError("opencv-python is required for image decoding")
    array = np.frombuffer(payload, dtype=np.uint8)
    frame = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError("Unable to decode image upload")
    return frame


def ensure_stream(stream_id: str) -> StreamState:
    if stream_id not in STREAMS:
        STREAMS[stream_id] = StreamState()
    return STREAMS[stream_id]


def normalized_landmarks(face_landmarks: Any, width: int, height: int) -> list[dict[str, float]]:
    return [
        {
            "x": float(point.x * width),
            "y": float(point.y * height),
            "z": float(point.z),
        }
        for point in face_landmarks.landmark
    ]


def fallback_landmarks(width: int, height: int) -> list[dict[str, float]]:
    cx = width / 2
    cy = height / 2
    rx = width * 0.18
    ry = height * 0.25
    samples: list[dict[str, float]] = []
    for angle in np.linspace(0, 2 * math.pi, num=24, endpoint=False):
        samples.append({"x": cx + math.cos(angle) * rx, "y": cy + math.sin(angle) * ry, "z": 0.0})
    return samples


def crop_box(frame: np.ndarray, x0: int, y0: int, x1: int, y1: int) -> np.ndarray:
    height, width = frame.shape[:2]
    x0 = max(0, min(x0, width - 1))
    x1 = max(x0 + 1, min(x1, width))
    y0 = max(0, min(y0, height - 1))
    y1 = max(y0 + 1, min(y1, height))
    return frame[y0:y1, x0:x1]


def bounding_box(points: list[dict[str, float]], width: int, height: int) -> tuple[int, int, int, int]:
    if not points:
        margin_x = int(width * 0.2)
        margin_y = int(height * 0.18)
        return margin_x, margin_y, width - margin_x, height - margin_y
    xs = [point["x"] for point in points]
    ys = [point["y"] for point in points]
    return (
        max(0, int(min(xs))),
        max(0, int(min(ys))),
        min(width, int(max(xs))),
        min(height, int(max(ys))),
    )


def get_forehead_region(frame: np.ndarray, landmarks: list[dict[str, float]]) -> np.ndarray:
    height, width = frame.shape[:2]
    if landmarks and max(FOREHEAD_INDEXES) < len(landmarks):
        forehead_points = [landmarks[index] for index in FOREHEAD_INDEXES]
        x0, y0, x1, y1 = bounding_box(forehead_points, width, height)
        pad_x = max(4, (x1 - x0) // 10)
        pad_y = max(4, (y1 - y0) // 3)
        return crop_box(frame, x0 - pad_x, y0 - pad_y, x1 + pad_x, y1 + pad_y)
    return crop_box(
        frame,
        int(width * 0.35),
        int(height * 0.12),
        int(width * 0.65),
        int(height * 0.28),
    )


def eye_aspect_ratio(landmarks: list[dict[str, float]], indexes: list[int]) -> float:
    if not landmarks or max(indexes) >= len(landmarks):
        return 0.3
    p1, p2, p3, p4, p5, p6 = [landmarks[index] for index in indexes]
    vertical_a = math.dist((p2["x"], p2["y"]), (p6["x"], p6["y"]))
    vertical_b = math.dist((p3["x"], p3["y"]), (p5["x"], p5["y"]))
    horizontal = math.dist((p1["x"], p1["y"]), (p4["x"], p4["y"]))
    if horizontal == 0:
        return 0.0
    return (vertical_a + vertical_b) / (2.0 * horizontal)


def extract_landmarks(frame: np.ndarray) -> list[dict[str, float]]:
    height, width = frame.shape[:2]
    if FACE_MESH is None or cv2 is None:
        return fallback_landmarks(width, height)
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    result = FACE_MESH.process(rgb)
    if not result.multi_face_landmarks:
        return fallback_landmarks(width, height)
    return normalized_landmarks(result.multi_face_landmarks[0], width, height)


def compute_motion_score(state: StreamState, face_box: tuple[int, int, int, int]) -> float:
    x0, y0, x1, y1 = face_box
    center = ((x0 + x1) / 2.0, (y0 + y1) / 2.0)
    if state.center_history:
        prev_center = state.center_history[-1]
        motion = math.dist(center, prev_center)
        state.motion_history.append(motion)
    state.center_history.append(center)
    if len(state.motion_history) < 5:
        return 0.25
    movements = np.array(state.motion_history, dtype=float)
    stability = float(np.std(movements) / (np.mean(movements) + 1e-6))
    return clamp(stability / 1.5)


def compute_pulse_signal(state: StreamState, forehead: np.ndarray) -> tuple[float, float]:
    if forehead.size == 0:
        return 0.0, 1.0
    green_mean = float(np.mean(forehead[:, :, 1]) / 255.0)
    state.green_history.append(green_mean)
    values = np.array(state.green_history, dtype=float)
    if len(values) < 12:
        return green_mean, 0.5
    detrended = values - np.mean(values)
    variation = float(np.std(detrended))
    if len(values) > 1:
        spectrum = np.fft.rfft(detrended)
        freqs = np.fft.rfftfreq(len(detrended), d=1 / 12.0)
        band_mask = (freqs >= 0.8) & (freqs <= 3.0)
        band_power = float(np.mean(np.abs(spectrum[band_mask]))) if np.any(band_mask) else 0.0
    else:
        band_power = 0.0
    pulse_score = clamp((variation * 10.0) + (band_power * 0.02))
    fake_penalty = clamp(1.0 - pulse_score)
    return green_mean, fake_penalty


def compute_blink_score(state: StreamState, landmarks: list[dict[str, float]]) -> float:
    left_ratio = eye_aspect_ratio(landmarks, LEFT_EYE)
    right_ratio = eye_aspect_ratio(landmarks, RIGHT_EYE)
    mean_ratio = (left_ratio + right_ratio) / 2.0
    state.blink_history.append(mean_ratio)
    if len(state.blink_history) < 8:
        return 0.25
    blink_values = np.array(state.blink_history, dtype=float)
    blink_variation = float(np.std(blink_values))
    return clamp(1.0 - min(blink_variation * 20.0, 1.0))


def compute_artifact_score(frame: np.ndarray, face_box: tuple[int, int, int, int]) -> float:
    if cv2 is None:
        return 0.35
    face_crop = crop_box(frame, *face_box)
    if face_crop.size == 0:
        return 0.5
    gray = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
    laplacian = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    edges = cv2.Canny(gray, 80, 180)
    edge_density = float(np.mean(edges > 0))
    blur_score = clamp(1.0 - min(laplacian / 400.0, 1.0))
    edge_score = clamp(abs(edge_density - 0.12) / 0.12)
    return clamp((blur_score * 0.55) + (edge_score * 0.45))


def compute_frame_quality(frame: np.ndarray, face_box: tuple[int, int, int, int]) -> float:
    if cv2 is None:
        return 0.5
    region = crop_box(frame, *face_box)
    if region.size == 0:
        region = frame
    gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
    brightness = float(np.mean(gray) / 255.0)
    contrast = float(np.std(gray) / 64.0)
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var() / 350.0)

    brightness_score = 1.0 - min(abs(brightness - 0.52) / 0.52, 1.0)
    contrast_score = min(contrast, 1.0)
    sharpness_score = min(sharpness, 1.0)
    return clamp((brightness_score * 0.35) + (contrast_score * 0.3) + (sharpness_score * 0.35))


def mode_weights(mode: str) -> dict[str, float]:
    weights_by_mode: dict[str, dict[str, float]] = {
        "webcam": {"artifacts": 0.2, "pulse": 0.4, "blink": 0.2, "motion": 0.2},
        "screen": {"artifacts": 0.5, "pulse": 0.15, "blink": 0.1, "motion": 0.25},
        "upload-video": {"artifacts": 0.45, "pulse": 0.2, "blink": 0.15, "motion": 0.2},
        "upload-image": {"artifacts": 0.7, "pulse": 0.1, "blink": 0.1, "motion": 0.1},
        "upload-audio": {"artifacts": 1.0, "pulse": 0.0, "blink": 0.0, "motion": 0.0},
    }
    return weights_by_mode.get(mode, {"artifacts": 0.36, "pulse": 0.32, "blink": 0.17, "motion": 0.15})


def adaptive_threshold(mode: str, quality_score: float) -> float:
    base = 0.58
    if mode in {"screen", "upload-image"}:
        base += 0.03
    if quality_score < 0.32:
        base += 0.08
    elif quality_score < 0.45:
        base += 0.04
    return clamp(base, 0.52, 0.76)


def build_reasons(scores: dict[str, float], quality_score: float) -> list[str]:
    reasons: list[str] = []
    if scores["pulse"] > 0.6:
        reasons.append("Irregular Pulse")
    if scores["artifacts"] > 0.55:
        reasons.append("Visual Artifact Pattern")
    if scores["blink"] > 0.6:
        reasons.append("Blink Rhythm Anomaly")
    if scores["motion"] > 0.6:
        reasons.append("Micro Motion Instability")
    if quality_score < 0.4:
        reasons.append("Low visual quality reduced confidence")
    if not reasons:
        reasons.append("Biological and visual signals appear coherent")
    return reasons


def threat_label(confidence: float) -> str:
    if confidence >= 0.8:
        return "critical"
    if confidence >= 0.6:
        return "high"
    if confidence >= 0.35:
        return "elevated"
    return "low"


def analyze_frame(frame: np.ndarray, mode: str, stream_id: str = "default") -> DetectionResponse:
    state = ensure_stream(stream_id)
    landmarks = extract_landmarks(frame)
    face_box = bounding_box(landmarks, frame.shape[1], frame.shape[0])
    forehead = get_forehead_region(frame, landmarks)
    pulse_value, pulse_penalty = compute_pulse_signal(state, forehead)
    blink_penalty = compute_blink_score(state, landmarks)
    motion_penalty = compute_motion_score(state, face_box)
    artifact_penalty = compute_artifact_score(frame, face_box)
    quality_score = compute_frame_quality(frame, face_box)
    quality_penalty = clamp(1.0 - quality_score)

    # With weak camera/screen inputs, artifact detectors become noisy.
    quality_compensation = 1.0 - (0.35 * quality_penalty)
    artifact_penalty = clamp(artifact_penalty * quality_compensation)
    pulse_penalty = clamp(pulse_penalty * (1.0 - 0.2 * quality_penalty))

    scores = {
        "artifacts": artifact_penalty,
        "pulse": pulse_penalty,
        "blink": blink_penalty,
        "motion": motion_penalty,
        "quality": quality_score,
    }
    weights = mode_weights(mode)
    confidence = clamp(
        (scores["artifacts"] * weights["artifacts"])
        + (scores["pulse"] * weights["pulse"])
        + (scores["blink"] * weights["blink"])
        + (scores["motion"] * weights["motion"])
    )
    threshold = adaptive_threshold(mode, quality_score)
    is_fake = confidence >= threshold
    state.verdict_history.append(is_fake)
    smoothed_confidence = confidence
    if len(state.verdict_history) > 3:
        fake_ratio = sum(state.verdict_history) / len(state.verdict_history)
        smoothed_confidence = clamp((confidence * 0.7) + (fake_ratio * 0.3))

    return DetectionResponse(
        is_fake=smoothed_confidence >= threshold,
        confidence=smoothed_confidence,
        pulse_value=pulse_value,
        landmarks=landmarks,
        reasons=build_reasons(scores, quality_score),
        signal_breakdown=scores,
        mode=mode,
        threat_level=threat_label(smoothed_confidence),
        timestamp=time.time(),
    )


def aggregate_video_results(results: list[DetectionResponse], mode: str) -> DetectionResponse:
    if not results:
        return DetectionResponse(
            is_fake=False,
            confidence=0.0,
            pulse_value=0.0,
            landmarks=[],
            reasons=["No readable frames detected"],
            signal_breakdown={"artifacts": 0.0, "pulse": 0.0, "blink": 0.0, "motion": 0.0},
            mode=mode,
            threat_level="low",
            timestamp=time.time(),
        )

    frame_weights = np.array(
        [max(0.25, result.signal_breakdown.get("quality", 0.5)) for result in results],
        dtype=float,
    )
    frame_weights /= np.sum(frame_weights)

    mean_confidence = float(np.sum(np.array([result.confidence for result in results]) * frame_weights))
    mean_pulse = float(np.sum(np.array([result.pulse_value for result in results]) * frame_weights))
    breakdown_keys = results[0].signal_breakdown.keys()
    mean_breakdown = {
        key: float(np.sum(np.array([result.signal_breakdown[key] for result in results]) * frame_weights))
        for key in breakdown_keys
    }
    all_reasons = [reason for result in results for reason in result.reasons]
    unique_reasons = list(dict.fromkeys(all_reasons))[:4]
    return DetectionResponse(
        is_fake=mean_confidence >= 0.58,
        confidence=mean_confidence,
        pulse_value=mean_pulse,
        landmarks=results[-1].landmarks,
        reasons=unique_reasons,
        signal_breakdown=mean_breakdown,
        mode=mode,
        threat_level=threat_label(mean_confidence),
        timestamp=time.time(),
    )


def analyze_video_upload(payload: bytes) -> DetectionResponse:
    if cv2 is None:
        return DetectionResponse(
            is_fake=True,
            confidence=0.64,
            pulse_value=0.0,
            landmarks=[],
            reasons=["Video analysis requires opencv-python to be installed"],
            signal_breakdown={"artifacts": 0.8, "pulse": 0.7, "blink": 0.5, "motion": 0.5},
            mode="upload-video",
            threat_level="high",
            timestamp=time.time(),
        )

    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as handle:
        temp_path = Path(handle.name)
        handle.write(payload)

    try:
        capture = cv2.VideoCapture(str(temp_path))
        results: list[DetectionResponse] = []
        frame_index = 0
        while capture.isOpened() and len(results) < 36:
            success, frame = capture.read()
            if not success:
                break
            if frame_index % 4 == 0:
                results.append(analyze_frame(frame, mode="upload-video", stream_id="upload-video"))
            frame_index += 1
        capture.release()
        return aggregate_video_results(results, mode="upload-video")
    finally:
        temp_path.unlink(missing_ok=True)


def analyze_audio_upload(payload: bytes) -> DetectionResponse:
    try:
        with wave.open(io.BytesIO(payload), "rb") as wav_file:
            frames = wav_file.readframes(wav_file.getnframes())
            sample_width = wav_file.getsampwidth()
            channels = wav_file.getnchannels()
            if sample_width == 2:
                audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32)
            else:
                audio = np.frombuffer(frames, dtype=np.uint8).astype(np.float32) - 128.0
            if channels > 1:
                audio = audio.reshape(-1, channels).mean(axis=1)
            if audio.size == 0:
                raise ValueError("Empty audio")
            audio /= np.max(np.abs(audio)) + 1e-6
            amplitude_variation = float(np.std(audio))
            zero_crossings = float(np.mean(np.abs(np.diff(np.sign(audio))) > 0))
            spectral_flatness = clamp(zero_crossings * 2.2)
            confidence = clamp((0.7 - amplitude_variation) * 0.75 + spectral_flatness * 0.25)
            reasons = ["Audio cadence irregularity"] if confidence >= 0.58 else ["Audio dynamics appear natural"]
    except Exception:
        entropy = float(len(set(payload[:4096])) / max(1, min(256, len(payload[:4096]))))
        confidence = clamp(0.75 - entropy * 0.35)
        reasons = ["Fallback byte-pattern audio analysis used"]

    return DetectionResponse(
        is_fake=confidence >= 0.58,
        confidence=confidence,
        pulse_value=0.0,
        landmarks=[],
        reasons=reasons,
        signal_breakdown={
            "artifacts": confidence,
            "pulse": 0.0,
            "blink": 0.0,
            "motion": 0.0,
        },
        mode="upload-audio",
        threat_level=threat_label(confidence),
        timestamp=time.time(),
    )


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "bio-verisync-deepwatch"}


@app.post("/api/analyze/upload", response_model=DetectionResponse)
async def analyze_upload(file: UploadFile = File(...)) -> DetectionResponse:
    payload = await file.read()
    content_type = file.content_type or ""

    if content_type.startswith("image/"):
        frame = bytes_to_image(payload)
        return analyze_frame(frame, mode="upload-image", stream_id="upload-image")
    if content_type.startswith("video/"):
        return analyze_video_upload(payload)
    if content_type.startswith("audio/"):
        return analyze_audio_upload(payload)

    raise ValueError(f"Unsupported upload type: {content_type or 'unknown'}")


@app.websocket("/ws/live")
async def live_detection_socket(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            raw_message = await websocket.receive_text()
            message = json.loads(raw_message)
            stream_id = message.get("stream_id", "default")
            if message.get("action") == "reset":
                STREAMS.pop(stream_id, None)
                await websocket.send_json({"ok": True, "stream_id": stream_id})
                continue

            frame_payload = message.get("frame")
            if not frame_payload:
                await websocket.send_json({"error": "Missing frame payload"})
                continue

            try:
                frame = decode_base64_image(frame_payload)
                result = analyze_frame(frame, mode=message.get("source", "live"), stream_id=stream_id)
                await websocket.send_json(result.model_dump())
            except Exception as exc:  # pragma: no cover
                await websocket.send_json({"error": str(exc)})
            await asyncio.sleep(0.01)
    except WebSocketDisconnect:
        return
