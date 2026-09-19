import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import type { AddressInfo } from "node:net";
import { createServer } from "./server";
import type { Store, TickerSummary, TimeSeriesPoint } from "../storage/types";
import type { TrackedTicker } from "../tickers";

class FakeStore implements Store {
  async addMentions(): Promise<{ added: number; duplicates: number }> {
    throw new Error("not used by these tests");
  }

  async getTimeSeries(ticker: TrackedTicker, sinceIso: string): Promise<TimeSeriesPoint[]> {
    if (ticker !== "BTC") return [];
    return [{ bucketStart: sinceIso, mentionCount: 3, averageSentiment: 0.4 }];
  }

  async getTopTickers(_sinceIso: string, limit = 5): Promise<TickerSummary[]> {
    const all: TickerSummary[] = [
      { ticker: "BTC", mentionCount: 10, averageSentiment: 0.3 },
      { ticker: "ETH", mentionCount: 5, averageSentiment: -0.1 },
    ];
    return all.slice(0, limit);
  }
}

let baseUrl: string;
let server: ReturnType<typeof createServer>;

before(async () => {
  server = createServer(new FakeStore());
  await new Promise<void>((resolve) => server.listen(0, resolve));
  const { port } = server.address() as AddressInfo;
  baseUrl = `http://127.0.0.1:${port}`;
});

after(() => {
  server.close();
});

test("GET /api/tickers returns top ticker summaries", async () => {
  const response = await fetch(`${baseUrl}/api/tickers`);
  assert.equal(response.status, 200);
  const body = (await response.json()) as { tickers: TickerSummary[] };
  assert.equal(body.tickers.length, 2);
  assert.equal(body.tickers[0]?.ticker, "BTC");
});

test("GET /api/tickers respects the limit query param", async () => {
  const response = await fetch(`${baseUrl}/api/tickers?limit=1`);
  const body = (await response.json()) as { tickers: TickerSummary[] };
  assert.equal(body.tickers.length, 1);
});

test("GET /api/tickers/:symbol/timeseries returns points for a known ticker", async () => {
  const response = await fetch(`${baseUrl}/api/tickers/btc/timeseries?since=2025-01-01T00:00:00.000Z`);
  assert.equal(response.status, 200);
  const body = (await response.json()) as { ticker: string; points: TimeSeriesPoint[] };
  assert.equal(body.ticker, "BTC");
  assert.equal(body.points.length, 1);
});

test("GET /api/tickers/:symbol/timeseries 404s for an untracked ticker", async () => {
  const response = await fetch(`${baseUrl}/api/tickers/NOTATICKER/timeseries`);
  assert.equal(response.status, 404);
});

test("an unknown route 404s", async () => {
  const response = await fetch(`${baseUrl}/api/nonsense`);
  assert.equal(response.status, 404);
});

test("a non-GET method is rejected", async () => {
  const response = await fetch(`${baseUrl}/api/tickers`, { method: "POST" });
  assert.equal(response.status, 405);
});

test("responses include a permissive CORS header for the dashboard's dev server", async () => {
  const response = await fetch(`${baseUrl}/api/tickers`);
  assert.equal(response.headers.get("access-control-allow-origin"), "*");
});
