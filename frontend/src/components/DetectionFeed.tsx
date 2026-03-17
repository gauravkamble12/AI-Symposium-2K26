import type { ChangeEvent, MutableRefObject, RefObject } from 'react';
import type { DetectionResult } from '../types';

type DetectionFeedProps = {
  activeMode: 'upload' | 'screen' | 'webcam';
  isStreaming: boolean;
  previewUrl: string | null;
  previewType: 'image' | 'video' | null;
  detection: DetectionResult | null;
  runtimeError: string | null;
  mediaSize: { width: number; height: number };
  videoRef: RefObject<HTMLVideoElement>;
  imageRef: RefObject<HTMLImageElement>;
  fileInputRef: MutableRefObject<HTMLInputElement | null>;
  uploadBusy: boolean;
  onSelectMode: (mode: 'upload' | 'screen' | 'webcam') => void;
  onStartWebcam: () => Promise<void>;
  onStartScreen: () => Promise<void>;
  onStopStream: () => void;
  onFilePicked: (event: ChangeEvent<HTMLInputElement>) => void;
  onAnalyzeUpload: () => Promise<void>;
  onVideoReady: () => void;
  onImageReady: () => void;
};

const networkEdges: Array<[number, number]> = [
  [10, 67],
  [67, 103],
  [103, 109],
  [109, 151],
  [151, 338],
  [338, 297],
  [297, 332],
  [33, 133],
  [362, 263],
  [61, 291],
];

export function DetectionFeed({
  activeMode,
  isStreaming,
  previewUrl,
  previewType,
  detection,
  runtimeError,
  mediaSize,
  videoRef,
  imageRef,
  fileInputRef,
  uploadBusy,
  onSelectMode,
  onStartWebcam,
  onStartScreen,
  onStopStream,
  onFilePicked,
  onAnalyzeUpload,
  onVideoReady,
  onImageReady,
}: DetectionFeedProps) {
  const width = mediaSize.width || 1280;
  const height = mediaSize.height || 720;
  const showVideo = activeMode !== 'upload' || previewType === 'video';

  return (
    <section className="panel feed-panel reveal-up">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Security Command Center</p>
          <h2>DeepWatch Visual Stream</h2>
        </div>
        <div className="mode-switcher">
          <button className={activeMode === 'upload' ? 'mode-pill active' : 'mode-pill'} onClick={() => onSelectMode('upload')}>
            Upload Mode
          </button>
          <button className={activeMode === 'screen' ? 'mode-pill active' : 'mode-pill'} onClick={() => onSelectMode('screen')}>
            Live Screen
          </button>
          <button className={activeMode === 'webcam' ? 'mode-pill active' : 'mode-pill'} onClick={() => onSelectMode('webcam')}>
            Webcam BioSync
          </button>
        </div>
      </div>

      <div className="feed-stage">
        <div className="feed-stage__grid" />
        <div className="scan-line" />

        {showVideo ? (
          <video
            ref={videoRef}
            className="feed-media"
            autoPlay
            playsInline
            muted
            controls={activeMode === 'upload' && previewType === 'video'}
            src={activeMode === 'upload' ? previewUrl ?? undefined : undefined}
            onLoadedMetadata={onVideoReady}
          />
        ) : previewUrl ? (
          <img ref={imageRef} className="feed-media" src={previewUrl} alt="Uploaded preview" onLoad={onImageReady} />
        ) : (
          <div className="feed-placeholder">
            <span>Awaiting media input</span>
            <p>Upload content or start a live source to begin AI artifact and biological verification.</p>
          </div>
        )}

        <svg className="mesh-overlay" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
          {detection?.landmarks?.map((point, index) => (
            <circle key={`${point.x}-${point.y}-${index}`} cx={point.x} cy={point.y} r={2.4} />
          ))}
          {detection?.landmarks &&
            networkEdges
              .filter(([from, to]) => detection.landmarks[from] && detection.landmarks[to])
              .map(([from, to]) => {
                const first = detection.landmarks[from];
                const second = detection.landmarks[to];
                return <line key={`${from}-${to}`} x1={first.x} y1={first.y} x2={second.x} y2={second.y} />;
              })}
        </svg>

        <div className="feed-badge-row">
          <span className="status-chip">{isStreaming ? 'LIVE ANALYSIS' : 'READY'}</span>
          <span className="status-chip muted">{detection?.threat_level ?? 'standby'} threat level</span>
        </div>
      </div>

      <div className="control-row">
        <label className="action-button action-button--ghost">
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*,video/*,audio/*"
            hidden
            onChange={onFilePicked}
          />
          Choose Upload
        </label>

        <button className="action-button" onClick={() => void onAnalyzeUpload()} disabled={!previewUrl || uploadBusy}>
          {uploadBusy ? 'Analyzing...' : 'Analyze Upload'}
        </button>

        <button className="action-button" onClick={() => void onStartScreen()}>
          Capture Screen
        </button>

        <button className="action-button" onClick={() => void onStartWebcam()}>
          Start Webcam
        </button>

        <button className="action-button action-button--ghost" onClick={onStopStream}>
          Stop Stream
        </button>
      </div>

      {runtimeError ? <div className="runtime-error">{runtimeError}</div> : null}
    </section>
  );
}
