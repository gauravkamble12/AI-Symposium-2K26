# AI-Symposium-2K26

Bio-VeriSync DeepWatch is a hackathon MVP for deepfake detection that combines visual artifact analysis with lightweight biological verification.

## What It Includes

- Upload analysis for image, video, and audio files.
- Live screen capture detection through a FastAPI WebSocket stream.
- Webcam monitoring with face mesh overlays and rPPG-inspired pulse tracking.
- Fusion scoring that explains verdicts with artifact, pulse, blink, and motion signals.
- A React dashboard styled like a security command center.

## Architecture

- Frontend: React + Vite + Recharts
- Backend: FastAPI + WebSocket streaming
- Vision stack: OpenCV and optional MediaPipe Face Mesh
- Fusion engine: heuristic artifact detection + biological consistency scoring

## Project Structure

```text
.
├── backend
│   ├── app
│   │   └── main.py
│   └── requirements.txt
├── frontend
│   ├── package.json
│   ├── src
│   │   ├── components
│   │   ├── App.tsx
│   │   └── styles.css
│   └── vite.config.ts
└── main.py
```

## Backend Setup

```bash
cd backend
/workspaces/AI-Symposium-2K26/.venv/bin/pip install -r requirements.txt
/workspaces/AI-Symposium-2K26/.venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Optional:

```bash
/workspaces/AI-Symposium-2K26/.venv/bin/pip install mediapipe
```

If MediaPipe is unavailable, the backend falls back to a synthetic facial region model so the demo still runs.

This backend uses the headless OpenCV build so it works correctly inside containers without desktop OpenGL libraries.

## Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

If the API is not running on `http://localhost:8000`, set `VITE_API_BASE` before starting Vite.

By default, the frontend now proxies `/api` and `/ws` through the Vite dev server, which avoids `localhost:8000` issues when the app is opened from a forwarded dev-container port.

## API Surface

- `GET /api/health`
- `POST /api/analyze/upload`
- `WS /ws/live`

Live WebSocket payload:

```json
{
	"frame": "data:image/jpeg;base64,...",
	"source": "webcam",
	"stream_id": "webcam"
}
```

Response shape:

```json
{
	"is_fake": true,
	"confidence": 0.87,
	"pulse_value": 0.45,
	"landmarks": [{ "x": 120, "y": 94, "z": -0.03 }],
	"reasons": ["Irregular Pulse", "Visual Artifact Pattern"],
	"signal_breakdown": {
		"artifacts": 0.82,
		"pulse": 0.74,
		"blink": 0.48,
		"motion": 0.63
	},
	"mode": "webcam",
	"threat_level": "critical",
	"timestamp": 1710672000.0
}
```

## Important Note

This repository is an explainable MVP, not a production-grade forensic detector. The current backend uses heuristic fusion to simulate the full concept while keeping the code hackathon-friendly and easy to demo.
