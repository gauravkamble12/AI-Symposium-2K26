import { useEffect, useRef, useState } from 'react';
import { AnalyticsPanel } from './components/AnalyticsPanel';
import { DetectionFeed } from './components/DetectionFeed';
import { PulseGraph } from './components/PulseGraph';
import { VerdictPanel } from './components/VerdictPanel';
import type { DetectionResult, ScanLog } from './types';

const API_BASE = (import.meta.env.VITE_API_BASE ?? '').replace(/\/$/, '');
const WS_ENDPOINT = import.meta.env.VITE_WS_BASE?.replace(/\/$/, '')
  ?? `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws/live`;

export default function App() {
  const [activeMode, setActiveMode] = useState<'upload' | 'screen' | 'webcam'>('upload');
  const [isStreaming, setIsStreaming] = useState(false);
  const [uploadBusy, setUploadBusy] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewType, setPreviewType] = useState<'image' | 'video' | null>(null);
  const [mediaSize, setMediaSize] = useState({ width: 1280, height: 720 });
  const [detection, setDetection] = useState<DetectionResult | null>(null);
  const [pulseSeries, setPulseSeries] = useState<Array<{ index: number; value: number }>>([]);
  const [logs, setLogs] = useState<ScanLog[]>([]);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [runtimeError, setRuntimeError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const imageRef = useRef<HTMLImageElement>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  useEffect(() => {
    return () => {
      stopStream();
      if (previewUrl) {
        URL.revokeObjectURL(previewUrl);
      }
    };
  }, [previewUrl]);

  useEffect(() => {
    if (!isStreaming) {
      return undefined;
    }

    setRuntimeError(null);
    const socket = new WebSocket(WS_ENDPOINT);
    wsRef.current = socket;

    socket.onopen = () => {
      setRuntimeError(null);
    };

    socket.onmessage = (event) => {
      const payload = JSON.parse(event.data) as DetectionResult | { error: string } | { ok: boolean; stream_id: string };
      if ('ok' in payload) {
        return;
      }
      if ('error' in payload) {
        setRuntimeError(payload.error);
        return;
      }
      setRuntimeError(null);
      setDetection(payload);
      setPulseSeries((current) => {
        const nextPoint = {
          index: current.length === 0 ? 0 : current[current.length - 1].index + 1,
          value: payload.pulse_value,
        };
        return [...current.slice(-47), nextPoint];
      });
      setLogs((current) => {
        const nextLog: ScanLog = {
          id: `${payload.timestamp}`,
          label: payload.is_fake ? 'Synthetic anomaly detected' : 'Biometric coherence confirmed',
          confidence: payload.confidence,
          threat: payload.threat_level,
          timestamp: new Date(payload.timestamp * 1000).toLocaleTimeString(),
        };
        return [nextLog, ...current].slice(0, 6);
      });
    };

    socket.onerror = () => {
      setRuntimeError('Live analysis socket failed to connect to the backend.');
    };

    socket.onclose = (event) => {
      if (!event.wasClean) {
        setRuntimeError('Live analysis socket closed unexpectedly.');
      }
    };

    return () => {
      if (socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ action: 'reset', stream_id: activeMode }));
      }
      socket.close();
      wsRef.current = null;
    };
  }, [activeMode, isStreaming]);

  useEffect(() => {
    if (!isStreaming) {
      return undefined;
    }

    const timer = window.setInterval(() => {
      const socket = wsRef.current;
      const video = videoRef.current;
      if (!socket || socket.readyState !== WebSocket.OPEN || !video || video.videoWidth === 0) {
        return;
      }
      if (!canvasRef.current) {
        canvasRef.current = document.createElement('canvas');
      }
      canvasRef.current.width = video.videoWidth;
      canvasRef.current.height = video.videoHeight;
      const context = canvasRef.current.getContext('2d');
      if (!context) {
        return;
      }
      context.drawImage(video, 0, 0, canvasRef.current.width, canvasRef.current.height);
      const frame = canvasRef.current.toDataURL('image/jpeg', 0.82);
      socket.send(JSON.stringify({ frame, source: activeMode, stream_id: activeMode }));
    }, 650);

    return () => {
      window.clearInterval(timer);
    };
  }, [activeMode, isStreaming]);

  async function attachStream(stream: MediaStream, mode: 'screen' | 'webcam') {
    stopStream();
    setActiveMode(mode);
    streamRef.current = stream;
    setPreviewUrl(null);
    setPreviewType('video');
    if (videoRef.current) {
      videoRef.current.srcObject = stream;
      await videoRef.current.play();
    }
    stream.getTracks().forEach((track) => {
      track.onended = () => stopStream();
    });
    setIsStreaming(true);
  }

  async function startWebcam() {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: 'user' },
      audio: false,
    });
    await attachStream(stream, 'webcam');
  }

  async function startScreen() {
    const stream = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: false });
    await attachStream(stream, 'screen');
  }

  function stopStream() {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    setIsStreaming(false);
    if (videoRef.current && activeMode !== 'upload') {
      videoRef.current.srcObject = null;
    }
  }

  async function analyzeUpload() {
    if (!selectedFile) {
      return;
    }
    setUploadBusy(true);
    setActiveMode('upload');
    setRuntimeError(null);
    stopStream();

    try {
      const formData = new FormData();
      formData.append('file', selectedFile);
      const response = await fetch(`${API_BASE}/api/analyze/upload`, {
        method: 'POST',
        body: formData,
      });
      if (!response.ok) {
        throw new Error(`Upload analysis failed with status ${response.status}`);
      }
      const result = (await response.json()) as DetectionResult;
      setRuntimeError(null);
      setDetection(result);
      setLogs((current) => [
        {
          id: `${Date.now()}`,
          label: `Upload scan: ${selectedFile.type || 'unknown media'}`,
          confidence: result.confidence,
          threat: result.threat_level,
          timestamp: new Date().toLocaleTimeString(),
        },
        ...current,
      ].slice(0, 6));
      setPulseSeries((current) => [
        ...current.slice(-47),
        { index: current.length === 0 ? 0 : current[current.length - 1].index + 1, value: result.pulse_value },
      ]);
    } catch (error) {
      setRuntimeError(error instanceof Error ? error.message : 'Upload analysis failed.');
    } finally {
      setUploadBusy(false);
    }
  }

  function onFilePicked(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null;
    if (!file) {
      return;
    }
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
    }
    const nextPreviewUrl = URL.createObjectURL(file);
    setSelectedFile(file);
    setPreviewUrl(nextPreviewUrl);
    setPreviewType(file.type.startsWith('image/') ? 'image' : file.type.startsWith('video/') ? 'video' : null);
    setActiveMode('upload');
    setDetection(null);
    setRuntimeError(null);
  }

  function onVideoReady() {
    const video = videoRef.current;
    if (!video) {
      return;
    }
    setMediaSize({ width: video.videoWidth || 1280, height: video.videoHeight || 720 });
  }

  function onImageReady() {
    const image = imageRef.current;
    if (!image) {
      return;
    }
    setMediaSize({ width: image.naturalWidth || 1280, height: image.naturalHeight || 720 });
  }

  return (
    <main className="app-shell">
      <div className="ambient ambient--left" />
      <div className="ambient ambient--right" />

      <header className="hero reveal-up">
        <div>
          <p className="eyebrow">Bio-VeriSync DeepWatch</p>
          <h1>Real-time deepfake detection fused with biological verification.</h1>
        </div>
        <div className="hero-stat-strip">
          <div>
            <span>Modes</span>
            <strong>Upload / Screen / Webcam</strong>
          </div>
          <div>
            <span>Signals</span>
            <strong>Artifacts + rPPG + Blink + Motion</strong>
          </div>
        </div>
      </header>

      <div className="dashboard-grid">
        <DetectionFeed
          activeMode={activeMode}
          isStreaming={isStreaming}
          previewUrl={previewUrl}
          previewType={previewType}
          detection={detection}
          runtimeError={runtimeError}
          mediaSize={mediaSize}
          videoRef={videoRef}
          imageRef={imageRef}
          fileInputRef={fileInputRef}
          uploadBusy={uploadBusy}
          onSelectMode={setActiveMode}
          onStartWebcam={startWebcam}
          onStartScreen={startScreen}
          onStopStream={stopStream}
          onFilePicked={onFilePicked}
          onAnalyzeUpload={analyzeUpload}
          onVideoReady={onVideoReady}
          onImageReady={onImageReady}
        />
        <VerdictPanel detection={detection} />
        <PulseGraph series={pulseSeries} />
        <AnalyticsPanel detection={detection} logs={logs} />
      </div>
    </main>
  );
}
