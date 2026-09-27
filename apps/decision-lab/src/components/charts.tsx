/** Small SVG charts, each accompanied by a data table. No charting library. */
import { useId, useState } from 'react';
import { fmtNum, fmtRatio } from '../lib/format';

export interface BarDatum {
  label: string;
  value: number | null;
  method?: string;
  text: string;
}

const METHOD_FILL: Record<string, string> = { exact_v1: 'var(--exact)', rules_v1: 'var(--rules)', learned_v1: 'var(--learned)' };

export function BarChart({ title, data, max = 1 }: { title: string; data: BarDatum[]; max?: number }) {
  const [showTable, setShowTable] = useState(false);
  const id = useId();
  const rowH = 22;
  const labelW = 110;
  const W = 420;
  const H = data.length * rowH + 8;
  const plotW = W - labelW - 60;
  return (
    <figure style={{ margin: 0 }}>
      <figcaption className="small muted" id={`${id}-cap`}>
        {title}
      </figcaption>
      <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-labelledby={`${id}-cap`} aria-describedby={`${id}-tbl`}>
        {data.map((d, i) => {
          const y = 4 + i * rowH;
          const w = d.value === null ? 0 : Math.max(0, Math.min(1, d.value / max)) * plotW;
          return (
            <g key={d.label}>
              <text x={labelW - 6} y={y + 15} textAnchor="end" fontSize="12" fill="var(--ink)">
                {d.label}
              </text>
              <rect x={labelW} y={y + 3} width={plotW} height={rowH - 8} fill="var(--panel-2)" />
              {d.value !== null ? <rect x={labelW} y={y + 3} width={w} height={rowH - 8} fill={d.method ? METHOD_FILL[d.method] ?? 'var(--ref)' : 'var(--ref)'} /> : null}
              <text x={labelW + plotW + 6} y={y + 15} fontSize="12" fill="var(--muted)">
                {d.text}
              </text>
            </g>
          );
        })}
      </svg>
      <button type="button" className="small" aria-expanded={showTable} onClick={() => setShowTable((s) => !s)}>
        {showTable ? 'hide data table' : 'show data table'}
      </button>
      <table id={`${id}-tbl`} className={showTable ? '' : 'sr-only'}>
        <caption className="sr-only">{title}</caption>
        <thead>
          <tr>
            <th>series</th>
            <th>value</th>
          </tr>
        </thead>
        <tbody>
          {data.map((d) => (
            <tr key={d.label}>
              <td>{d.label}</td>
              <td>{d.text}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}

export interface LinePoint {
  x: number;
  y: number | null;
}
export interface LineSeries {
  name: string;
  method?: string;
  points: LinePoint[];
}

export function LineChart({
  title,
  series,
  xLabel,
  yLabel,
  xFormat = fmtNum,
  yFormat = (v: number) => fmtRatio(v, 3),
}: {
  title: string;
  series: LineSeries[];
  xLabel: string;
  yLabel: string;
  xFormat?: (v: number) => string;
  yFormat?: (v: number) => string;
}) {
  const id = useId();
  const [showTable, setShowTable] = useState(false);
  const W = 560;
  const H = 300;
  const m = { l: 64, r: 16, t: 12, b: 44 };
  const pw = W - m.l - m.r;
  const ph = H - m.t - m.b;
  const all = series.flatMap((s) => s.points.filter((p) => p.y !== null));
  const xs = all.map((p) => p.x);
  const ys = all.map((p) => p.y as number);
  const xMin = xs.length ? Math.min(...xs) : 0;
  const xMax = xs.length ? Math.max(...xs) : 1;
  const yMax = ys.length ? Math.max(...ys) : 1;
  const yTop = yMax <= 0 ? 1 : yMax;
  const sx = (x: number) => m.l + (xMax === xMin ? pw / 2 : ((x - xMin) / (xMax - xMin)) * pw);
  const sy = (y: number) => m.t + ph - (y / yTop) * ph;
  const ticks = 4;
  return (
    <figure style={{ margin: 0 }}>
      <figcaption className="small muted" id={`${id}-cap`}>
        {title}
      </figcaption>
      <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-labelledby={`${id}-cap`} aria-describedby={`${id}-tbl`}>
        <rect x={m.l} y={m.t} width={pw} height={ph} fill="none" stroke="var(--line)" />
        {Array.from({ length: ticks + 1 }, (_, i) => {
          const xv = xMin + ((xMax - xMin) * i) / ticks;
          const yv = (yTop * i) / ticks;
          return (
            <g key={i}>
              <text x={sx(xv)} y={m.t + ph + 16} textAnchor="middle" fontSize="11" fill="var(--muted)">
                {xFormat(xv)}
              </text>
              <text x={m.l - 6} y={sy(yv) + 4} textAnchor="end" fontSize="11" fill="var(--muted)">
                {yFormat(yv)}
              </text>
            </g>
          );
        })}
        <text x={m.l + pw / 2} y={H - 6} textAnchor="middle" fontSize="12" fill="var(--muted)">
          {xLabel}
        </text>
        <text x={14} y={m.t + ph / 2} textAnchor="middle" fontSize="12" fill="var(--muted)" transform={`rotate(-90 14 ${m.t + ph / 2})`}>
          {yLabel}
        </text>
        {series.map((s) => {
          const pts = s.points.filter((p) => p.y !== null).sort((a, b) => a.x - b.x);
          const d = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${sx(p.x).toFixed(1)} ${sy(p.y as number).toFixed(1)}`).join('');
          const color = s.method ? METHOD_FILL[s.method] ?? 'var(--ref)' : 'var(--exact)';
          return (
            <g key={s.name}>
              {d ? <path d={d} fill="none" stroke={color} strokeWidth="2" /> : null}
              {pts.map((p) => (
                <circle key={p.x} cx={sx(p.x)} cy={sy(p.y as number)} r="3" fill={color} />
              ))}
            </g>
          );
        })}
      </svg>
      <button type="button" className="small" aria-expanded={showTable} onClick={() => setShowTable((s) => !s)}>
        {showTable ? 'hide data table' : 'show data table'}
      </button>
      <table id={`${id}-tbl`} className={showTable ? '' : 'sr-only'}>
        <caption className="sr-only">{title}</caption>
        <thead>
          <tr>
            <th>series</th>
            <th>{xLabel}</th>
            <th>{yLabel}</th>
          </tr>
        </thead>
        <tbody>
          {series.flatMap((s) =>
            s.points.map((p) => (
              <tr key={`${s.name}-${p.x}`}>
                <td>{s.name}</td>
                <td>{xFormat(p.x)}</td>
                <td>{p.y === null ? 'unavailable' : yFormat(p.y)}</td>
              </tr>
            )),
          )}
        </tbody>
      </table>
    </figure>
  );
}
