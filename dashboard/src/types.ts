// Mirrors server/src/storage/types.ts and server/src/tickers.ts.

export const TRACKED_TICKERS = ["BTC", "ETH", "SOL", "XRP", "DOGE", "AVAX", "MATIC", "DOT", "LINK", "ADA"] as const;
export type TrackedTicker = (typeof TRACKED_TICKERS)[number];

export interface TickerSummary {
  ticker: TrackedTicker;
  mentionCount: number;
  averageSentiment: number;
}

export interface TimeSeriesPoint {
  bucketStart: string;
  mentionCount: number;
  averageSentiment: number;
}
