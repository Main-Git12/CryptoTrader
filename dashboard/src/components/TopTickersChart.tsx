import { Bar, BarChart, CartesianGrid, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { TickerSummary } from "../types";
import { useChartPalette } from "../hooks/useChartPalette";

interface TopTickersChartProps {
  tickers: TickerSummary[];
}

function formatSentiment(score: number): string {
  const sign = score > 0 ? "+" : "";
  return `${sign}${score.toFixed(2)}`;
}

export default function TopTickersChart({ tickers }: TopTickersChartProps) {
  const palette = useChartPalette();

  if (tickers.length === 0) {
    return <p style={{ color: "var(--text-secondary)" }}>No mentions collected yet.</p>;
  }

  return (
    <div>
      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={tickers} margin={{ top: 24, right: 16, left: 0, bottom: 0 }} barCategoryGap="20%">
          <CartesianGrid stroke={palette.gridline} vertical={false} />
          <XAxis dataKey="ticker" tick={{ fill: palette.textMuted, fontSize: 13 }} axisLine={{ stroke: palette.baseline }} tickLine={false} />
          <YAxis tick={{ fill: palette.textMuted, fontSize: 12 }} axisLine={false} tickLine={false} width={40} allowDecimals={false} />
          <Tooltip
            contentStyle={{ background: palette.surface1, border: `1px solid ${palette.gridline}`, borderRadius: 8, fontSize: 13 }}
            formatter={(value: number) => [value, "Mentions"]}
          />
          <Bar dataKey="mentionCount" fill={palette.series[0]} radius={[4, 4, 0, 0]} maxBarSize={24}>
            <LabelList dataKey="mentionCount" position="top" fill="var(--text-secondary)" fontSize={12} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      <table style={{ width: "100%", borderCollapse: "collapse", marginTop: 16, fontSize: 13 }}>
        <caption style={{ textAlign: "left", color: "var(--text-secondary)", marginBottom: 8 }}>
          Table view of the chart above
        </caption>
        <thead>
          <tr style={{ textAlign: "left", color: "var(--text-muted)", borderBottom: "1px solid var(--gridline)" }}>
            <th style={{ padding: "6px 8px" }}>Ticker</th>
            <th style={{ padding: "6px 8px" }}>Mentions</th>
            <th style={{ padding: "6px 8px" }}>Avg. sentiment</th>
          </tr>
        </thead>
        <tbody>
          {tickers.map((t) => (
            <tr key={t.ticker} style={{ borderBottom: "1px solid var(--gridline)" }}>
              <td style={{ padding: "6px 8px", color: "var(--text-primary)", fontWeight: 600 }}>{t.ticker}</td>
              <td style={{ padding: "6px 8px", fontVariantNumeric: "tabular-nums" }}>{t.mentionCount}</td>
              <td
                style={{
                  padding: "6px 8px",
                  fontVariantNumeric: "tabular-nums",
                  color: t.averageSentiment > 0 ? "var(--diverging-positive)" : t.averageSentiment < 0 ? "var(--diverging-negative)" : "var(--text-secondary)",
                }}
              >
                {formatSentiment(t.averageSentiment)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
