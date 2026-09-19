import type { TrackedTicker } from "../tickers";
import type { TickerSummary } from "../storage/types";

export type TradeAction = "buy" | "sell" | "hold";

export interface TradeDecision {
  action: TradeAction;
  ticker: TrackedTicker;
  reason: string;
}

export interface StrategyInput {
  ticker: TrackedTicker;
  /** null when there's been no mention volume for this ticker in the lookback window. */
  sentimentSummary: TickerSummary | null;
  hasOpenPosition: boolean;
}

/**
 * Deliberately swappable, same pattern as SentimentScorer/Collector
 * elsewhere in this repo: a naive rule-based baseline now, replaceable
 * with something more sophisticated later without touching the exchange,
 * portfolio, or orchestration code.
 */
export interface TradingStrategy {
  decide(input: StrategyInput): TradeDecision;
}

export interface Trade {
  timestamp: string;
  ticker: TrackedTicker;
  action: "buy" | "sell";
  quantity: number;
  price: number;
  usdValue: number;
  reason: string;
}

export interface PortfolioState {
  cashUsd: number;
  holdings: Partial<Record<TrackedTicker, number>>;
  trades: Trade[];
}

export interface PortfolioStore {
  load(): Promise<PortfolioState>;
  save(state: PortfolioState): Promise<void>;
}

export class InsufficientFundsError extends Error {
  constructor(ticker: string, requiredUsd: number, availableUsd: number) {
    super(`Cannot buy ${ticker}: need $${requiredUsd.toFixed(2)}, have $${availableUsd.toFixed(2)}`);
    this.name = "InsufficientFundsError";
  }
}

export class NoPositionToSellError extends Error {
  constructor(ticker: string) {
    super(`Cannot sell ${ticker}: no open position`);
    this.name = "NoPositionToSellError";
  }
}
