import { test, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { runTradingCycle } from "./runTradingCycle";
import { JsonPortfolioStore } from "./portfolioStore";
import { SimulatedPriceFeed } from "./priceFeed/simulated";
import { SentimentMomentumStrategy } from "./strategies/sentimentMomentum";
import type { Store, TickerSummary } from "../storage/types";

let dataDir: string;

beforeEach(async () => {
  dataDir = await mkdtemp(join(tmpdir(), "cryptotrader-trading-cycle-"));
});

afterEach(async () => {
  await rm(dataDir, { recursive: true, force: true });
});

class FakeMentionStore implements Store {
  constructor(private readonly summaries: TickerSummary[]) {}
  async addMentions(): Promise<{ added: number; duplicates: number }> {
    throw new Error("not used by these tests");
  }
  async getTimeSeries(): Promise<[]> {
    return [];
  }
  async getTopTickers(): Promise<TickerSummary[]> {
    return this.summaries;
  }
}

test("tickers with no mention data all hold, and the portfolio is untouched", async () => {
  const portfolioStore = new JsonPortfolioStore(dataDir, 1000);
  const results = await runTradingCycle(
    new FakeMentionStore([]),
    new SimulatedPriceFeed({ BTC: [50_000] }),
    new SentimentMomentumStrategy(),
    portfolioStore
  );

  assert.ok(results.every((r) => r.decision.action === "hold"));
  const state = await portfolioStore.load();
  assert.equal(state.cashUsd, 1000);
});

test("end-to-end: buys on positive sentiment, sells on negative sentiment, produces a real profit when price rose in between", async () => {
  const portfolioStore = new JsonPortfolioStore(dataDir, 1000);
  const priceFeed = new SimulatedPriceFeed({ BTC: [50_000] });

  const buyResults = await runTradingCycle(
    new FakeMentionStore([{ ticker: "BTC", mentionCount: 10, averageSentiment: 0.8 }]),
    priceFeed,
    new SentimentMomentumStrategy(),
    portfolioStore,
    100
  );
  const buyResult = buyResults.find((r) => r.ticker === "BTC");
  assert.equal(buyResult?.decision.action, "buy");
  assert.equal(buyResult?.trade?.action, "buy");

  priceFeed.setPrice("BTC", 60_000); // +20% while held

  const sellResults = await runTradingCycle(
    new FakeMentionStore([{ ticker: "BTC", mentionCount: 10, averageSentiment: -0.8 }]),
    priceFeed,
    new SentimentMomentumStrategy(),
    portfolioStore,
    100
  );
  const sellResult = sellResults.find((r) => r.ticker === "BTC");
  assert.equal(sellResult?.decision.action, "sell");
  assert.equal(sellResult?.trade?.action, "sell");

  const finalState = await portfolioStore.load();
  assert.equal(finalState.holdings.BTC, 0);
  assert.ok(finalState.cashUsd > 1000, "buying before a rise and selling after should show a real, computed profit");
});

test("end-to-end: buying before a price drop produces a real, computed loss", async () => {
  const portfolioStore = new JsonPortfolioStore(dataDir, 1000);
  const priceFeed = new SimulatedPriceFeed({ ETH: [3000] });

  await runTradingCycle(
    new FakeMentionStore([{ ticker: "ETH", mentionCount: 10, averageSentiment: 0.8 }]),
    priceFeed,
    new SentimentMomentumStrategy(),
    portfolioStore,
    100
  );

  priceFeed.setPrice("ETH", 2400); // -20% while held

  await runTradingCycle(
    new FakeMentionStore([{ ticker: "ETH", mentionCount: 10, averageSentiment: -0.8 }]),
    priceFeed,
    new SentimentMomentumStrategy(),
    portfolioStore,
    100
  );

  const finalState = await portfolioStore.load();
  assert.ok(finalState.cashUsd < 1000, "buying before a drop and selling after should show a real, computed loss");
});

test("insufficient funds on one ticker is reported as a skip, not thrown out of the cycle", async () => {
  const portfolioStore = new JsonPortfolioStore(dataDir, 50); // less than the $100 position size
  const results = await runTradingCycle(
    new FakeMentionStore([{ ticker: "BTC", mentionCount: 10, averageSentiment: 0.8 }]),
    new SimulatedPriceFeed({ BTC: [50_000] }),
    new SentimentMomentumStrategy(),
    portfolioStore,
    100
  );

  const btcResult = results.find((r) => r.ticker === "BTC");
  assert.equal(btcResult?.trade, null);
  assert.match(btcResult?.skippedReason ?? "", /Cannot buy BTC/);
});
