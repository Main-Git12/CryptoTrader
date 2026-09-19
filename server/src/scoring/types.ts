export type SentimentLabel = "positive" | "neutral" | "negative";

export interface SentimentResult {
  label: SentimentLabel;
  /** Normalized to roughly [-1, 1]; not a probability, just a comparable magnitude. */
  score: number;
}

/**
 * Deliberately swappable: the initial implementation (LexiconSentimentScorer)
 * is a transparent, deterministic baseline. A future trained/ML-based
 * scorer implements this same interface and drops in without touching
 * collectors, storage, or the API — see CLAUDE.md.
 */
export interface SentimentScorer {
  score(text: string): SentimentResult;
}
