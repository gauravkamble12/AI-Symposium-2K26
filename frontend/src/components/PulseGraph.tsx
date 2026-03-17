import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

type PulseGraphProps = {
  series: Array<{ index: number; value: number }>;
};

export function PulseGraph({ series }: PulseGraphProps) {
  return (
    <section className="panel pulse-panel reveal-up delay-2">
      <div className="panel-header compact">
        <div>
          <p className="eyebrow">Biological Verification</p>
          <h2>Live rPPG Signal</h2>
        </div>
      </div>

      <div className="chart-wrap">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={series}>
            <CartesianGrid stroke="rgba(255,255,255,0.08)" vertical={false} />
            <XAxis dataKey="index" hide />
            <YAxis domain={[0, 1]} tick={{ fill: '#9cb7b1', fontSize: 11 }} width={28} />
            <Tooltip
              contentStyle={{
                background: '#12211d',
                border: '1px solid rgba(255,255,255,0.08)',
                borderRadius: 14,
                color: '#ecf8f1',
              }}
            />
            <Line type="monotone" dataKey="value" stroke="#83f6c8" dot={false} strokeWidth={2.4} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
