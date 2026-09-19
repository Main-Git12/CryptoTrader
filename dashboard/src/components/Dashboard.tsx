import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { TickerSummary, TimeSeriesPoint, TrackedTicker } from "../types";
import Disclaimer from "./Disclaimer";
import TopTickersChart from "./TopTickersChart";
import SentimentTrendChart from "./SentimentTrendChart";

const WINDOW_MS = 24 * 60 * 60 * 1000;

function sinceIso(): string {
  return new Date(Date.now() - WINDOW_MS).toISOString();
}

export default function Dashboard() {
  const [topTickers, setTopTickers] = useState<TickerSummary[]>([]);
  const [selectedTicker, setSelectedTicker] = useState<TrackedTicker>("BTC");
  const [points, setPoints] = useState<TimeSeriesPoint[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getTopTickers(sinceIso())
      .then((res) => setTopTickers(res.tickers))
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
  }, []);

  useEffect(() => {
    api
      .getTimeSeries(selectedTicker, sinceIso())
      .then((res) => setPoints(res.points))
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
  }, [selectedTicker]);

  return (
    <main style={{ maxWidth: 960, margin: "0 auto", padding: 32 }}>
      <header style={{ marginBottom: 8 }}>
        <h1 style={{ fontSize: 28, margin: 0 }}>CryptoTrader Sentiment Monitor</h1>
        <p style={{ color: "var(--text-secondary)", marginTop: 4 }}>Mentions and sentiment over the last 24 hours</p>
      </header>

      <Disclaimer />

      {error && (
        <p style={{ color: "var(--diverging-negative)", background: "var(--diverging-neutral)", padding: "8px 12px", borderRadius: 8 }}>
          Couldn&apos;t reach the API: {error}
        </p>
      )}

      <section style={{ marginBottom: 32 }}>
        <h2 style={{ fontSize: 18 }}>Top tickers by mention volume</h2>
        <TopTickersChart tickers={topTickers} />
      </section>

      <section>
        <h2 style={{ fontSize: 18 }}>Sentiment trend by ticker</h2>
        <SentimentTrendChart selectedTicker={selectedTicker} onSelectTicker={setSelectedTicker} points={points} />
      </section>
    </main>
  );
}
