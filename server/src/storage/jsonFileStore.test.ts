import { test, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { JsonFileStore } from "./jsonFileStore";
import type { ScoredMention } from "./types";

let dataDir: string;

beforeEach(async () => {
  dataDir = await mkdtemp(join(tmpdir(), "cryptotrader-store-"));
});

afterEach(async () => {
  await rm(dataDir, { recursive: true, force: true });
});

function mention(overrides: Partial<ScoredMention> = {}): ScoredMention {
  return {
    platform: "reddit",
    id: overrides.id ?? "reddit:1:BTC",
    ticker: overrides.ticker ?? "BTC",
    text: overrides.text ?? "BTC is mooning",
    postedAt: overrides.postedAt ?? "2025-01-15T10:30:00.000Z",
    url: overrides.url ?? "https://reddit.com/r/CryptoCurrency/1",
    sentiment: overrides.sentiment ?? { label: "positive", score: 0.8 },
  };
}

test("addMentions reports added count and persists to disk", async () => {
  const store = new JsonFileStore(dataDir);
  const result = await store.addMentions([mention()]);
  assert.deepEqual(result, { added: 1, duplicates: 0 });
});

test("addMentions de-duplicates by mention id, including across store instances", async () => {
  const store1 = new JsonFileStore(dataDir);
  await store1.addMentions([mention({ id: "reddit:1:BTC" })]);

  // A fresh instance pointed at the same directory should see the persisted data.
  const store2 = new JsonFileStore(dataDir);
  const result = await store2.addMentions([mention({ id: "reddit:1:BTC" })]);

  assert.deepEqual(result, { added: 0, duplicates: 1 });
});

test("getTimeSeries buckets mentions by hour and averages sentiment", async () => {
  const store = new JsonFileStore(dataDir);
  await store.addMentions([
    mention({ id: "1", postedAt: "2025-01-15T10:05:00.000Z", sentiment: { label: "positive", score: 1 } }),
    mention({ id: "2", postedAt: "2025-01-15T10:45:00.000Z", sentiment: { label: "negative", score: -0.5 } }),
    mention({ id: "3", postedAt: "2025-01-15T11:10:00.000Z", sentiment: { label: "positive", score: 0.5 } }),
  ]);

  const series = await store.getTimeSeries("BTC", "2025-01-15T00:00:00.000Z");

  assert.equal(series.length, 2);
  assert.equal(series[0]?.bucketStart, "2025-01-15T10:00:00.000Z");
  assert.equal(series[0]?.mentionCount, 2);
  assert.equal(series[0]?.averageSentiment, 0.25);
  assert.equal(series[1]?.bucketStart, "2025-01-15T11:00:00.000Z");
  assert.equal(series[1]?.mentionCount, 1);
});

test("getTimeSeries excludes mentions before the cutoff and for other tickers", async () => {
  const store = new JsonFileStore(dataDir);
  await store.addMentions([
    mention({ id: "1", ticker: "BTC", postedAt: "2025-01-01T00:00:00.000Z" }),
    mention({ id: "2", ticker: "ETH", postedAt: "2025-01-15T10:00:00.000Z" }),
  ]);

  const series = await store.getTimeSeries("BTC", "2025-01-10T00:00:00.000Z");
  assert.deepEqual(series, []);
});

test("getTopTickers ranks by mention count and respects the limit", async () => {
  const store = new JsonFileStore(dataDir);
  await store.addMentions([
    mention({ id: "1", ticker: "BTC", sentiment: { label: "positive", score: 1 } }),
    mention({ id: "2", ticker: "BTC", sentiment: { label: "positive", score: 0.5 } }),
    mention({ id: "3", ticker: "ETH", sentiment: { label: "negative", score: -1 } }),
    mention({ id: "4", ticker: "SOL", sentiment: { label: "neutral", score: 0 } }),
  ]);

  const top = await store.getTopTickers("2025-01-01T00:00:00.000Z", 2);

  assert.equal(top.length, 2);
  assert.equal(top[0]?.ticker, "BTC");
  assert.equal(top[0]?.mentionCount, 2);
  assert.equal(top[0]?.averageSentiment, 0.75);
});
