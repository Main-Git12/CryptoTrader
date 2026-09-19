import { test } from "node:test";
import assert from "node:assert/strict";
import { SentimentMomentumStrategy } from "./sentimentMomentum";
import type { TickerSummary } from "../../storage/types";

function summary(overrides: Partial<TickerSummary> = {}): TickerSummary {
  return { ticker: "BTC", mentionCount: 10, averageSentiment: 0, ...overrides };
}

test("holds when there's no sentiment data for the ticker", () => {
  const strategy = new SentimentMomentumStrategy();
  const decision = strategy.decide({ ticker: "BTC", sentimentSummary: null, hasOpenPosition: false });
  assert.equal(decision.action, "hold");
});

test("holds when mention volume is below the minimum", () => {
  const strategy = new SentimentMomentumStrategy({ minMentions: 5 });
  const decision = strategy.decide({
    ticker: "BTC",
    sentimentSummary: summary({ mentionCount: 2, averageSentiment: 0.9 }),
    hasOpenPosition: false,
  });
  assert.equal(decision.action, "hold");
});

test("buys when sentiment clears the buy threshold and there's no open position", () => {
  const strategy = new SentimentMomentumStrategy({ buyThreshold: 0.3 });
  const decision = strategy.decide({
    ticker: "BTC",
    sentimentSummary: summary({ averageSentiment: 0.5 }),
    hasOpenPosition: false,
  });
  assert.equal(decision.action, "buy");
});

test("does not buy again when a position is already open", () => {
  const strategy = new SentimentMomentumStrategy({ buyThreshold: 0.3 });
  const decision = strategy.decide({
    ticker: "BTC",
    sentimentSummary: summary({ averageSentiment: 0.9 }),
    hasOpenPosition: true,
  });
  assert.equal(decision.action, "hold");
});

test("sells when sentiment drops to the sell threshold and a position is open", () => {
  const strategy = new SentimentMomentumStrategy({ sellThreshold: -0.3 });
  const decision = strategy.decide({
    ticker: "BTC",
    sentimentSummary: summary({ averageSentiment: -0.5 }),
    hasOpenPosition: true,
  });
  assert.equal(decision.action, "sell");
});

test("does not sell when there's no position to sell, regardless of sentiment", () => {
  const strategy = new SentimentMomentumStrategy({ sellThreshold: -0.3 });
  const decision = strategy.decide({
    ticker: "BTC",
    sentimentSummary: summary({ averageSentiment: -0.9 }),
    hasOpenPosition: false,
  });
  assert.equal(decision.action, "hold");
});

test("holds in the neutral zone between thresholds", () => {
  const strategy = new SentimentMomentumStrategy({ buyThreshold: 0.3, sellThreshold: -0.3 });
  const decision = strategy.decide({
    ticker: "BTC",
    sentimentSummary: summary({ averageSentiment: 0.1 }),
    hasOpenPosition: false,
  });
  assert.equal(decision.action, "hold");
});
