import { test, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { runIngest } from "./ingest";
import { CollectorNotConfiguredError, CollectorNotImplementedError, type Collector, type Mention } from "./collectors/types";
import { JsonFileStore } from "./storage/jsonFileStore";
import { LexiconSentimentScorer } from "./scoring/lexicon";

let dataDir: string;

beforeEach(async () => {
  dataDir = await mkdtemp(join(tmpdir(), "cryptotrader-ingest-"));
});

afterEach(async () => {
  await rm(dataDir, { recursive: true, force: true });
});

class FakeWorkingCollector implements Collector {
  readonly platform = "reddit" as const;
  async collect(): Promise<Mention[]> {
    return [
      {
        platform: "reddit",
        id: "reddit:1:BTC",
        ticker: "BTC",
        text: "BTC is mooning today",
        postedAt: new Date().toISOString(),
        url: "https://reddit.com/r/CryptoCurrency/1",
      },
    ];
  }
}

class FakeUnconfiguredCollector implements Collector {
  readonly platform = "twitter" as const;
  async collect(): Promise<Mention[]> {
    throw new CollectorNotConfiguredError("twitter", ["TWITTER_BEARER_TOKEN"]);
  }
}

class FakeUnimplementedCollector implements Collector {
  readonly platform = "discord" as const;
  async collect(): Promise<Mention[]> {
    throw new CollectorNotImplementedError("discord", "not built yet");
  }
}

class FakeBrokenCollector implements Collector {
  readonly platform = "telegram" as const;
  async collect(): Promise<Mention[]> {
    throw new Error("network is down");
  }
}

test("runs all collectors, skipping unconfigured/unimplemented ones without treating them as failures", async () => {
  const store = new JsonFileStore(dataDir);
  const summaries = await runIngest(
    [new FakeWorkingCollector(), new FakeUnconfiguredCollector(), new FakeUnimplementedCollector()],
    new LexiconSentimentScorer(),
    store
  );

  assert.equal(summaries.length, 3);
  assert.deepEqual(summaries[0], { platform: "reddit", status: "ok", mentionsFound: 1, added: 1, duplicates: 0 });
  assert.equal(summaries[1]?.status, "skipped");
  assert.match(summaries[1]?.reason ?? "", /TWITTER_BEARER_TOKEN/);
  assert.equal(summaries[2]?.status, "skipped");
});

test("scores and persists what a working collector finds", async () => {
  const store = new JsonFileStore(dataDir);
  await runIngest([new FakeWorkingCollector()], new LexiconSentimentScorer(), store);

  const top = await store.getTopTickers("2000-01-01T00:00:00.000Z");
  assert.equal(top.length, 1);
  assert.equal(top[0]?.ticker, "BTC");
  assert.ok((top[0]?.averageSentiment ?? 0) > 0, "expected positive sentiment for a mooning post");
});

test("an unexpected error from a collector is not swallowed", async () => {
  const store = new JsonFileStore(dataDir);
  await assert.rejects(
    () => runIngest([new FakeBrokenCollector()], new LexiconSentimentScorer(), store),
    /network is down/
  );
});
