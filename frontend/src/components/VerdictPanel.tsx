import type { DetectionResult } from '../types';

type VerdictPanelProps = {
  detection: DetectionResult | null;
};

export function VerdictPanel({ detection }: VerdictPanelProps) {
  const confidence = Math.round((detection?.confidence ?? 0) * 100);
  const state = detection?.is_fake ? 'DEEPFAKE' : 'REAL';

  return (
    <section className="panel verdict-panel reveal-up delay-1">
      <div className="panel-header compact">
        <div>
          <p className="eyebrow">Fusion Verdict</p>
          <h2>{state}</h2>
        </div>
        <div className={detection?.is_fake ? 'verdict-orb danger' : 'verdict-orb safe'} />
      </div>

      <div className="confidence-ring">
        <div className="confidence-ring__inner">
          <span>{confidence}%</span>
          <p>confidence</p>
        </div>
      </div>

      <div className="reason-list">
        {(detection?.reasons ?? ['Awaiting scan results']).map((reason) => (
          <div key={reason} className="reason-item">
            {reason}
          </div>
        ))}
      </div>

      <div className="signal-bars">
        {Object.entries(detection?.signal_breakdown ?? {}).map(([label, value]) => (
          <div key={label} className="signal-bar">
            <div className="signal-bar__meta">
              <span>{label}</span>
              <span>{Math.round(value * 100)}%</span>
            </div>
            <div className="signal-bar__track">
              <div className="signal-bar__fill" style={{ width: `${Math.max(4, value * 100)}%` }} />
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
