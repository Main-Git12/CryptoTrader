import { test } from "node:test";
import assert from "node:assert/strict";
import { extractTickers } from "./tickers";

test("extracts an unambiguous ticker as a bare word", () => {
  assert.deepEqual(extractTickers("btc is pumping today"), ["BTC"]);
});

test("extracts an unambiguous ticker with a cashtag prefix", () => {
  assert.deepEqual(extractTickers("just bought some $ETH"), ["ETH"]);
});

test("de-duplicates repeated mentions of the same ticker", () => {
  assert.deepEqual(extractTickers("BTC BTC btc $BTC"), ["BTC"]);
});

test("does not match a common-word ticker as a bare word", () => {
  assert.deepEqual(extractTickers("I'll wrap up with one final dot."), []);
});

test("does match a common-word ticker when written as a cashtag", () => {
  assert.deepEqual(extractTickers("loading up on $DOT and $LINK"), ["DOT", "LINK"]);
});

test("does not match a substring inside an unrelated word", () => {
  assert.deepEqual(extractTickers("check the docs at example.com"), []);
});

test("returns an empty array for text with no tracked tickers", () => {
  assert.deepEqual(extractTickers("just a regular sentence about the weather"), []);
});

test("extracts multiple distinct tickers from one text", () => {
  assert.deepEqual(extractTickers("BTC and ETH both up, $SOL lagging").sort(), ["BTC", "ETH", "SOL"]);
});
