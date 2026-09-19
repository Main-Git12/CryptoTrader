import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { TimeSeriesPoint, TrackedTicker } from "../types";
import { TRACKED_TICKERS } from "../types";
import { useChartPalette } from "../hooks/useChartPalette";

interface SentimentTrendChartProps {
  selectedTicker: TrackedTicker;
  onSelectTicker: (ticker: TrackedTicker) => void;
  points: TimeSeriesPoint[];
}

function formatHour(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric" });
}

export default function SentimentTrendChart({ selectedTicker, onSelectTicker, points }: SentimentTrendChartProps) {
  const palette = useChartPalette();
  const chartData = points.map((p) => ({ ...p, label: formatHour(p.bucketStart) }));

  return (
    <div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
        {TRACKED_TICKERS.map((ticker) => (
          <button
            key={ticker}
            type="button"
            onClick={() => onSelectTicker(ticker)}
            aria-pressed={ticker === selectedTicker}
            style={{
              padding: "6px 12px",
              borderRadius: 999,
              border: `1px solid ${ticker === selectedTicker ? palette.series[0] : "var(--gridline)"}`,
              background: ticker === selectedTicker ? palette.series[0] : "var(--surface-1)",
              color: ticker === selectedTicker ? "#ffffff" : "var(--text-secondary)",
              fontSize: 13,
              cursor: "pointer",
            }}
          >
            {ticker}
          </button>
        ))}
      </div>

      {chartData.length === 0 ? (
        <p style={{ color: "var(--text-secondary)" }}>No {selectedTicker} mentions collected yet.</p>
      ) : (
        <>
          <h3 style={{ fontSize: 13, color: "var(--text-secondary)", margin: "0 0 8px" }}>Mention volume</h3>
          <ResponsiveContainer width="100%" height={160}>
            <BarChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
              <CartesianGrid stroke={palette.gridline} vertical={false} />
              <XAxis dataKey="label" tick={{ fill: palette.textMuted, fontSize: 11 }} axisLine={{ stroke: palette.baseline }} tickLine={false} />
              <YAxis tick={{ fill: palette.textMuted, fontSize: 12 }} axisLine={false} tickLine={false} width={32} allowDecimals={false} />
              <Tooltip
                contentStyle={{ background: palette.surface1, border: `1px solid ${palette.gridline}`, borderRadius: 8, fontSize: 13 }}
                formatter={(value: number) => [value, "Mentions"]}
              />
              <Bar dataKey="mentionCount" fill={palette.series[0]} radius={[4, 4, 0, 0]} maxBarSize={20} />
            </BarChart>
          </ResponsiveContainer>

          <h3 style={{ fontSize: 13, color: "var(--text-secondary)", margin: "20px 0 8px" }}>Sentiment trend</h3>
          <ResponsiveContainer width="100%" height={160}>
            <LineChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
              <CartesianGrid stroke={palette.gridline} vertical={false} />
              <XAxis dataKey="label" tick={{ fill: palette.textMuted, fontSize: 11 }} axisLine={{ stroke: palette.baseline }} tickLine={false} />
              <YAxis domain={[-1, 1]} tick={{ fill: palette.textMuted, fontSize: 12 }} axisLine={false} tickLine={false} width={32} />
              <ReferenceLine y={0} stroke={palette.baseline} strokeWidth={1} />
              <Tooltip
                contentStyle={{ background: palette.surface1, border: `1px solid ${palette.gridline}`, borderRadius: 8, fontSize: 13 }}
                formatter={(value: number) => [value.toFixed(2), "Avg. sentiment"]}
              />
              <Line
                type="monotone"
                dataKey="averageSentiment"
                stroke={palette.textSecondary}
                strokeWidth={2}
                isAnimationActive={false}
                dot={(props: { cx?: number; cy?: number; payload?: { averageSentiment: number } }) => {
                  const { cx, cy, payload } = props;
                  if (cx === undefined || cy === undefined || !payload) return <g key={`${cx}-${cy}`} />;
                  const score = payload.averageSentiment;
                  const fill = score > 0 ? palette.divergingPositive : score < 0 ? palette.divergingNegative : palette.divergingNeutral;
                  return <circle key={`${cx}-${cy}`} cx={cx} cy={cy} r={4} fill={fill} stroke={palette.surface1} strokeWidth={2} />;
                }}
              />
            </LineChart>
          </ResponsiveContainer>
        </>
      )}

      {chartData.length > 0 && (
        <table style={{ width: "100%", borderCollapse: "collapse", marginTop: 16, fontSize: 13 }}>
          <caption style={{ textAlign: "left", color: "var(--text-secondary)", marginBottom: 8 }}>
            Table view of {selectedTicker}&apos;s hourly mentions and sentiment
          </caption>
          <thead>
            <tr style={{ textAlign: "left", color: "var(--text-muted)", borderBottom: "1px solid var(--gridline)" }}>
              <th style={{ padding: "6px 8px" }}>Hour</th>
              <th style={{ padding: "6px 8px" }}>Mentions</th>
              <th style={{ padding: "6px 8px" }}>Avg. sentiment</th>
            </tr>
          </thead>
          <tbody>
            {chartData.map((point) => (
              <tr key={point.bucketStart} style={{ borderBottom: "1px solid var(--gridline)" }}>
                <td style={{ padding: "6px 8px" }}>{point.label}</td>
                <td style={{ padding: "6px 8px", fontVariantNumeric: "tabular-nums" }}>{point.mentionCount}</td>
                <td style={{ padding: "6px 8px", fontVariantNumeric: "tabular-nums" }}>{point.averageSentiment.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
