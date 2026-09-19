import { test, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { PaperExchange } from "./paperExchange";
import { JsonPortfolioStore } from "./portfolioStore";
import { SimulatedPriceFeed } from "./priceFeed/simulated";
import { InsufficientFundsError, NoPositionToSellError } from "./types";

let dataDir: string;

beforeEach(async () => {
  dataDir = await mkdtemp(join(tmpdir(), "cryptotrader-portfolio-"));
});

afterEach(async () => {
  await rm(dataDir, { recursive: true, force: true });
});

test("hold decisions execute to null and don't touch the portfolio", async () => {
  const store = new JsonPortfolioStore(dataDir, 1000);
  const exchange = new PaperExchange(new SimulatedPriceFeed({ BTC: [50_000] }), store, 100);

  const trade = await exchange.execute({ action: "hold", ticker: "BTC", reason: "test" });

  assert.equal(trade, null);
  const state = await store.load();
  assert.equal(state.cashUsd, 1000);
});

test("a buy spends exactly the position size and credits the correct quantity", async () => {
  const store = new JsonPortfolioStore(dataDir, 1000);
  const exchange = new PaperExchange(new SimulatedPriceFeed({ BTC: [50_000] }), store, 100);

  const trade = await exchange.execute({ action: "buy", ticker: "BTC", reason: "test" });

  assert.equal(trade?.action, "buy");
  assert.equal(trade?.usdValue, 100);
  assert.equal(trade?.quantity, 100 / 50_000);

  const state = await store.load();
  assert.equal(state.cashUsd, 900);
  assert.equal(state.holdings.BTC, 100 / 50_000);
  assert.equal(state.trades.length, 1);
});

test("buying without enough cash throws InsufficientFundsError and doesn't mutate the portfolio", async () => {
  const store = new JsonPortfolioStore(dataDir, 50);
  const exchange = new PaperExchange(new SimulatedPriceFeed({ BTC: [50_000] }), store, 100);

  await assert.rejects(() => exchange.execute({ action: "buy", ticker: "BTC", reason: "test" }), InsufficientFundsError);

  const state = await store.load();
  assert.equal(state.cashUsd, 50);
  assert.deepEqual(state.trades, []);
});

test("a sell liquidates the entire position and credits proceeds at the current price", async () => {
  const store = new JsonPortfolioStore(dataDir, 1000);
  const priceFeed = new SimulatedPriceFeed({ BTC: [50_000] });
  const exchange = new PaperExchange(priceFeed, store, 100);

  await exchange.execute({ action: "buy", ticker: "BTC", reason: "buy in" });

  priceFeed.setPrice("BTC", 60_000); // price rose 20% since the buy
  const sellTrade = await exchange.execute({ action: "sell", ticker: "BTC", reason: "cash out" });

  const expectedQuantity = 100 / 50_000;
  assert.equal(sellTrade?.action, "sell");
  assert.equal(sellTrade?.quantity, expectedQuantity);
  assert.equal(sellTrade?.usdValue, expectedQuantity * 60_000);

  const state = await store.load();
  assert.equal(state.holdings.BTC, 0);
  // Started with 1000, spent 100 to buy, got back quantity*60000 (~120) on sell.
  assert.equal(state.cashUsd, 1000 - 100 + expectedQuantity * 60_000);
  assert.ok(state.cashUsd > 1000, "a 20% price rise on the held position should show a net profit");
});

test("selling with no open position throws NoPositionToSellError", async () => {
  const store = new JsonPortfolioStore(dataDir, 1000);
  const exchange = new PaperExchange(new SimulatedPriceFeed({ BTC: [50_000] }), store, 100);

  await assert.rejects(() => exchange.execute({ action: "sell", ticker: "BTC", reason: "test" }), NoPositionToSellError);
});

test("a losing trade is reflected honestly as a net loss", async () => {
  const store = new JsonPortfolioStore(dataDir, 1000);
  const priceFeed = new SimulatedPriceFeed({ BTC: [50_000] });
  const exchange = new PaperExchange(priceFeed, store, 100);

  await exchange.execute({ action: "buy", ticker: "BTC", reason: "buy in" });
  priceFeed.setPrice("BTC", 40_000); // price fell 20%
  await exchange.execute({ action: "sell", ticker: "BTC", reason: "cut losses" });

  const state = await store.load();
  assert.ok(state.cashUsd < 1000, "a 20% price drop on the held position should show a net loss");
});
