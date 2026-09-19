import { test } from "node:test";
import assert from "node:assert/strict";
import { CoinGeckoPriceFeed } from "./coingecko";

test("getPrice returns the USD price for a tracked ticker", async () => {
  const fetchImpl = (async (url: string | URL) => {
    assert.match(url.toString(), /ids=bitcoin/);
    return new Response(JSON.stringify({ bitcoin: { usd: 65000.5 } }), { status: 200 });
  }) as typeof fetch;

  const feed = new CoinGeckoPriceFeed({ fetchImpl });
  const price = await feed.getPrice("BTC");

  assert.equal(price, 65000.5);
});

test("throws a clear error on a non-ok response", async () => {
  const feed = new CoinGeckoPriceFeed({
    fetchImpl: (async () => new Response("rate limited", { status: 429 })) as typeof fetch,
  });

  await assert.rejects(() => feed.getPrice("ETH"), /429/);
});

test("throws a clear error when the response is missing the expected coin id", async () => {
  const feed = new CoinGeckoPriceFeed({
    fetchImpl: (async () => new Response(JSON.stringify({}), { status: 200 })) as typeof fetch,
  });

  await assert.rejects(() => feed.getPrice("SOL"), /missing a USD price/);
});
