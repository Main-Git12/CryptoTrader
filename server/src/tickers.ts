/**
 * A deliberately small, curated set of tickers to start with — precision
 * over recall. Symbols that double as common English words (DOT, LINK,
 * ADA) are split into a separate list: those only count as a mention when
 * written as a cashtag ("$DOT"), never as a bare word, or nearly every
 * sentence ending in a period would register as a Polkadot mention.
 */
export const UNAMBIGUOUS_TICKERS = ["BTC", "ETH", "SOL", "XRP", "DOGE", "AVAX", "MATIC"] as const;

/** Common-word collisions — only matched as a cashtag ($DOT), never a bare word. */
export const CASHTAG_ONLY_TICKERS = ["DOT", "LINK", "ADA"] as const;

export const TRACKED_TICKERS = [...UNAMBIGUOUS_TICKERS, ...CASHTAG_ONLY_TICKERS] as const;

export type TrackedTicker = (typeof TRACKED_TICKERS)[number];

const UNAMBIGUOUS_PATTERN = new RegExp(`\\$?\\b(${UNAMBIGUOUS_TICKERS.join("|")})\\b`, "gi");
const CASHTAG_PATTERN = new RegExp(`\\$(${CASHTAG_ONLY_TICKERS.join("|")})\\b`, "gi");

/**
 * Extracts tracked-ticker mentions from free text, e.g. "$BTC" or "eth".
 * Case-insensitive, de-duplicated per call. Ambiguous symbols (see
 * CASHTAG_ONLY_TICKERS) only count with an explicit "$" prefix.
 */
export function extractTickers(text: string): TrackedTicker[] {
  const found = new Set<TrackedTicker>();

  for (const match of text.matchAll(UNAMBIGUOUS_PATTERN)) {
    const symbol = match[1]?.toUpperCase();
    if (symbol) found.add(symbol as TrackedTicker);
  }

  for (const match of text.matchAll(CASHTAG_PATTERN)) {
    const symbol = match[1]?.toUpperCase();
    if (symbol) found.add(symbol as TrackedTicker);
  }

  return [...found];
}
