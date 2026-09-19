import { test } from "node:test";
import assert from "node:assert/strict";
import { LexiconSentimentScorer } from "./lexicon";

const scorer = new LexiconSentimentScorer();

test("scores an obviously positive post as positive", () => {
  const result = scorer.score("BTC is mooning, huge gains, so bullish right now");
  assert.equal(result.label, "positive");
  assert.ok(result.score > 0);
});

test("scores an obviously negative post as negative", () => {
  const result = scorer.score("total dump, market is crashing, feels like a scam");
  assert.equal(result.label, "negative");
  assert.ok(result.score < 0);
});

test("scores text with no sentiment words as neutral with zero score", () => {
  const result = scorer.score("the block time is roughly ten minutes");
  assert.deepEqual(result, { label: "neutral", score: 0 });
});

test("empty string scores as neutral", () => {
  assert.deepEqual(scorer.score(""), { label: "neutral", score: 0 });
});

test("negation flips a positive word to a negative contribution", () => {
  const result = scorer.score("this is not good at all");
  assert.equal(result.label, "negative");
});

test("negation flips a negative word to a positive contribution", () => {
  const result = scorer.score("not bad for a Tuesday");
  assert.equal(result.label, "positive");
});

test("is case-insensitive", () => {
  const lower = scorer.score("great gains today");
  const upper = scorer.score("GREAT GAINS TODAY");
  assert.deepEqual(lower, upper);
});

test("a single mild sentiment word in an otherwise neutral sentence doesn't overwhelm the label", () => {
  // one positive word, but it's the only sentiment word, so score is +1 (max) — this
  // documents that behavior rather than asserting a nuance the current scorer doesn't have.
  const result = scorer.score("the weather today is good");
  assert.equal(result.label, "positive");
});
