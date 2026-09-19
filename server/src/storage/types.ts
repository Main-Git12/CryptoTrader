import type { TrackedTicker } from "../tickers";
import type { Mention } from "../collectors/types";
import type { SentimentResult } from "../scoring/types";

export interface ScoredMention extends Mention {
  sentiment: SentimentResult;
}

export interface TimeSeriesPoint {
  /** ISO 8601, start of the hour this point aggregates. */
  bucketStart: string;
  mentionCount: number;
  /** Average of each mention's sentiment score in this bucket; 0 if none. */
  averageSentiment: number;
}

export interface TickerSummary {
  ticker: TrackedTicker;
  mentionCount: number;
  averageSentiment: number;
}

export interface AddResult {
  added: number;
  duplicates: number;
}

export interface Store {
  addMentions(mentions: ScoredMention[]): Promise<AddResult>;
  getTimeSeries(ticker: TrackedTicker, sinceIso: string): Promise<TimeSeriesPoint[]>;
  getTopTickers(sinceIso: string, limit?: number): Promise<TickerSummary[]>;
}
