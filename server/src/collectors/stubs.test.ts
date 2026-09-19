import { test } from "node:test";
import assert from "node:assert/strict";
import { TwitterCollector } from "./twitter";
import { TelegramCollector } from "./telegram";
import { DiscordCollector } from "./discord";
import { CollectorNotImplementedError } from "./types";

test("TwitterCollector always throws CollectorNotImplementedError", async () => {
  await assert.rejects(() => new TwitterCollector().collect(["BTC"]), CollectorNotImplementedError);
});

test("TelegramCollector always throws CollectorNotImplementedError", async () => {
  await assert.rejects(() => new TelegramCollector().collect(["BTC"]), CollectorNotImplementedError);
});

test("DiscordCollector always throws CollectorNotImplementedError", async () => {
  await assert.rejects(() => new DiscordCollector().collect(["BTC"]), CollectorNotImplementedError);
});
