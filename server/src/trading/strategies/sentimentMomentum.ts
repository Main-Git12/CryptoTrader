import type { StrategyInput, TradeDecision, TradingStrategy } from "../types";

export interface SentimentMomentumConfig {
  /** Average sentiment score (roughly -1..1) at or above which an unheld ticker gets bought. */
  buyThreshold?: number;
  /** Average sentiment score at or below which an open position gets fully sold. */
  sellThreshold?: number;
  /** Minimum mention count in the lookback window before acting at all — ignores thin/noisy samples. */
  minMentions?: number;
}

const DEFAULTS: Required<SentimentMomentumConfig> = {
  buyThreshold: 0.3,
  sellThreshold: -0.3,
  minMentions: 3,
};

/**
 * A naive, fully transparent baseline: buy when mention sentiment is
 * clearly positive and there's no existing position, sell when it turns
 * clearly negative. This is NOT a validated trading signal — it exists so
 * the paper-trading machinery (portfolio math, order execution) has
 * something concrete to exercise. See server/src/trading/README.md for
 * why "sentiment from a few hundred Reddit posts" is a weak signal on its
 * own, and what it would take to validate this (or any) strategy before
 * trusting it with real money.
 */
export class SentimentMomentumStrategy implements TradingStrategy {
  private readonly config: Required<SentimentMomentumConfig>;

  constructor(config: SentimentMomentumConfig = {}) {
    this.config = { ...DEFAULTS, ...config };
  }

  decide(input: StrategyInput): TradeDecision {
    const { buyThreshold, sellThreshold, minMentions } = this.config;
    const summary = input.sentimentSummary;

    if (!summary || summary.mentionCount < minMentions) {
      return { action: "hold", ticker: input.ticker, reason: `fewer than ${minMentions} mentions in the window` };
    }

    if (!input.hasOpenPosition && summary.averageSentiment >= buyThreshold) {
      return {
        action: "buy",
        ticker: input.ticker,
        reason: `average sentiment ${summary.averageSentiment.toFixed(2)} >= buy threshold ${buyThreshold}`,
      };
    }

    if (input.hasOpenPosition && summary.averageSentiment <= sellThreshold) {
      return {
        action: "sell",
        ticker: input.ticker,
        reason: `average sentiment ${summary.averageSentiment.toFixed(2)} <= sell threshold ${sellThreshold}`,
      };
    }

    return { action: "hold", ticker: input.ticker, reason: "no threshold crossed" };
  }
}
