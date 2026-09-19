import type { SentimentScorer, SentimentResult } from "./types";

// General sentiment words plus common crypto-community slang. Not
// exhaustive — extend these sets as false negatives show up in review,
// rather than reaching for a heavier NLP dependency prematurely.
const POSITIVE_WORDS = new Set([
  "good",
  "great",
  "love",
  "amazing",
  "excellent",
  "bullish",
  "moon",
  "mooning",
  "pump",
  "pumping",
  "rally",
  "rallying",
  "gain",
  "gains",
  "profit",
  "profits",
  "ath",
  "hodl",
  "buy",
  "buying",
  "strong",
  "up",
  "win",
  "winning",
]);

const NEGATIVE_WORDS = new Set([
  "bad",
  "terrible",
  "hate",
  "awful",
  "bearish",
  "dump",
  "dumping",
  "crash",
  "crashing",
  "tank",
  "tanking",
  "rug",
  "rugpull",
  "scam",
  "loss",
  "losses",
  "sell",
  "selling",
  "weak",
  "down",
  "worst",
  "fear",
  "panic",
]);

const NEGATIONS = new Set(["not", "no", "never", "n't", "isn't", "wasn't", "don't", "doesn't", "won't"]);
const NEGATION_WINDOW = 2;

function tokenize(text: string): string[] {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9'\s]/g, " ")
    .split(/\s+/)
    .filter(Boolean);
}

function isNegatedAt(tokens: string[], index: number): boolean {
  const start = Math.max(0, index - NEGATION_WINDOW);
  for (let i = start; i < index; i++) {
    if (NEGATIONS.has(tokens[i] ?? "")) return true;
  }
  return false;
}

// Thresholds chosen to require a clear lean before labeling non-neutral —
// a single positive word in a long neutral post shouldn't flip the label.
const POSITIVE_THRESHOLD = 0.15;
const NEGATIVE_THRESHOLD = -0.15;

export class LexiconSentimentScorer implements SentimentScorer {
  score(text: string): SentimentResult {
    const tokens = tokenize(text);
    if (tokens.length === 0) return { label: "neutral", score: 0 };

    let polarity = 0;
    let sentimentWordCount = 0;

    tokens.forEach((token, index) => {
      const negated = isNegatedAt(tokens, index);
      if (POSITIVE_WORDS.has(token)) {
        polarity += negated ? -1 : 1;
        sentimentWordCount++;
      } else if (NEGATIVE_WORDS.has(token)) {
        polarity += negated ? 1 : -1;
        sentimentWordCount++;
      }
    });

    if (sentimentWordCount === 0) return { label: "neutral", score: 0 };

    const score = polarity / sentimentWordCount;
    const label = score > POSITIVE_THRESHOLD ? "positive" : score < NEGATIVE_THRESHOLD ? "negative" : "neutral";
    return { label, score };
  }
}
