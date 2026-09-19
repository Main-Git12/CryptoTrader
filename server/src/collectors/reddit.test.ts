import { test } from "node:test";
import assert from "node:assert/strict";
import { RedditCollector } from "./reddit";
import { CollectorNotConfiguredError } from "./types";

function fakePost(overrides: Partial<{ id: string; title: string; selftext: string; permalink: string }> = {}) {
  return {
    id: overrides.id ?? "abc123",
    title: overrides.title ?? "",
    selftext: overrides.selftext ?? "",
    created_utc: 1_700_000_000,
    permalink: overrides.permalink ?? "/r/CryptoCurrency/comments/abc123/",
  };
}

function makeFakeFetch(posts: ReturnType<typeof fakePost>[]) {
  let call = 0;
  return (async (url: string | URL) => {
    call++;
    const urlString = url.toString();

    if (urlString.includes("access_token")) {
      return new Response(JSON.stringify({ access_token: "fake-token", expires_in: 3600 }), { status: 200 });
    }

    if (urlString.includes("oauth.reddit.com")) {
      return new Response(JSON.stringify({ data: { children: posts.map((data) => ({ data })) } }), { status: 200 });
    }

    throw new Error(`Unexpected fetch call #${call} to ${urlString}`);
  }) as typeof fetch;
}

test("throws CollectorNotConfiguredError when credentials are missing", async () => {
  const originalClientId = process.env.REDDIT_CLIENT_ID;
  const originalClientSecret = process.env.REDDIT_CLIENT_SECRET;
  delete process.env.REDDIT_CLIENT_ID;
  delete process.env.REDDIT_CLIENT_SECRET;

  try {
    const collector = new RedditCollector({ fetchImpl: makeFakeFetch([]) });
    await assert.rejects(() => collector.collect(["BTC"]), CollectorNotConfiguredError);
  } finally {
    if (originalClientId !== undefined) process.env.REDDIT_CLIENT_ID = originalClientId;
    if (originalClientSecret !== undefined) process.env.REDDIT_CLIENT_SECRET = originalClientSecret;
  }
});

test("collects a mention for a ticker found in a post's title", async () => {
  const collector = new RedditCollector({
    clientId: "id",
    clientSecret: "secret",
    subreddits: ["CryptoCurrency"],
    fetchImpl: makeFakeFetch([fakePost({ title: "BTC just broke $100k, absolutely mooning" })]),
  });

  const mentions = await collector.collect(["BTC"]);

  assert.equal(mentions.length, 1);
  assert.equal(mentions[0]?.ticker, "BTC");
  assert.equal(mentions[0]?.platform, "reddit");
  assert.match(mentions[0]?.url ?? "", /reddit\.com\/r\/CryptoCurrency/);
});

test("ignores tickers mentioned but not in the requested list", async () => {
  const collector = new RedditCollector({
    clientId: "id",
    clientSecret: "secret",
    subreddits: ["CryptoCurrency"],
    fetchImpl: makeFakeFetch([fakePost({ title: "ETH and BTC both up today" })]),
  });

  const mentions = await collector.collect(["BTC"]);

  assert.equal(mentions.length, 1);
  assert.equal(mentions[0]?.ticker, "BTC");
});

test("produces one mention per distinct ticker found in the same post", async () => {
  const collector = new RedditCollector({
    clientId: "id",
    clientSecret: "secret",
    subreddits: ["CryptoCurrency"],
    fetchImpl: makeFakeFetch([fakePost({ title: "BTC and ETH both up today" })]),
  });

  const mentions = await collector.collect(["BTC", "ETH"]);

  assert.equal(mentions.length, 2);
  assert.deepEqual(
    mentions.map((m) => m.ticker).sort(),
    ["BTC", "ETH"]
  );
});

test("returns no mentions when no posts match the requested tickers", async () => {
  const collector = new RedditCollector({
    clientId: "id",
    clientSecret: "secret",
    fetchImpl: makeFakeFetch([fakePost({ title: "just a regular post about wallets" })]),
  });

  const mentions = await collector.collect(["BTC"]);
  assert.deepEqual(mentions, []);
});

test("surfaces a clear error when the token request fails", async () => {
  const collector = new RedditCollector({
    clientId: "id",
    clientSecret: "secret",
    fetchImpl: (async () => new Response("unauthorized", { status: 401 })) as typeof fetch,
  });

  await assert.rejects(() => collector.collect(["BTC"]), /token request failed: 401/);
});
