import type { DetectionResult, ScanLog } from '../types';

type AnalyticsPanelProps = {
  detection: DetectionResult | null;
  logs: ScanLog[];
};

export function AnalyticsPanel({ detection, logs }: AnalyticsPanelProps) {
  const threatPercent = Math.round((detection?.confidence ?? 0) * 100);

  return (
    <section className="panel analytics-panel reveal-up delay-3">
      <div className="panel-header compact">
        <div>
          <p className="eyebrow">Threat Telemetry</p>
          <h2>Recent Scans</h2>
        </div>
      </div>

      <div className="meter">
        <div className="meter__header">
          <span>Threat level</span>
          <span>{detection?.threat_level ?? 'standby'}</span>
        </div>
        <div className="meter__track">
          <div className="meter__fill" style={{ width: `${threatPercent}%` }} />
        </div>
      </div>

      <div className="telemetry-grid">
        <div>
          <span>Mode</span>
          <strong>{detection?.mode ?? 'idle'}</strong>
        </div>
        <div>
          <span>Pulse value</span>
          <strong>{(detection?.pulse_value ?? 0).toFixed(3)}</strong>
        </div>
      </div>

      <div className="log-list">
        {logs.length === 0 ? (
          <div className="log-item muted">No scan activity yet.</div>
        ) : (
          logs.map((log) => (
            <div key={log.id} className="log-item">
              <div>
                <strong>{log.label}</strong>
                <p>{log.timestamp}</p>
              </div>
              <div className="log-pill">{Math.round(log.confidence * 100)}%</div>
            </div>
          ))
        )}
      </div>
    </section>
  );
}
