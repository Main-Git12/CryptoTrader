import type { TickerSummary, TimeSeriesPoint, TrackedTicker } from "../types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:4000";

async function request<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`);
  if (!response.ok) throw new Error(`Request failed: ${response.status} ${path}`);
  return response.json() as Promise<T>;
}

export const api = {
  getTopTickers: (since: string, limit = 8) =>
    request<{ since: string; tickers: TickerSummary[] }>(`/api/tickers?since=${encodeURIComponent(since)}&limit=${limit}`),
  getTimeSeries: (ticker: TrackedTicker, since: string) =>
    request<{ ticker: string; since: string; points: TimeSeriesPoint[] }>(
      `/api/tickers/${ticker}/timeseries?since=${encodeURIComponent(since)}`
    ),
};
