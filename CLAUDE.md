# CryptoTrader — project conventions

## Purpose and hard boundary

This tracks social mention volume and sentiment for crypto tickers, and
can paper-trade a strategy against that data. **No real order has ever
been placed by anything here, and it stays that way without a separate,
explicit decision.** `server/src/trading/` simulates a portfolio — real
math, zero real money. Placing a real order needs: a validated strategy
(paper-traded for a meaningful stretch, results looked at honestly), a
real exchange execution API (not the price-only feeds that exist today),
hard position-size/loss limits, and the user's own funded, trading-enabled
exchange credentials. Don't build any part of that without being asked,
and flag it plainly if a request implies it.

## Architecture

- `/server` — Node 20 + strict TypeScript. `collectors/` (one module per
  platform, all implementing `Collector`), `scoring/` (pluggable
  `SentimentScorer`), `storage/` (aggregate store), `api/` (serves the
  dashboard), `ingest.ts` (orchestrates collector → scorer → store, run as
  a scheduled job).
- `/dashboard` — React + Vite + TypeScript + Tailwind, charts via
  `recharts`. Read-only; it displays what `/server`'s API returns and
  computes nothing itself.
- `server/src/trading/` — paper trading. `priceFeed/` (pluggable
  `PriceFeed`: real CoinGecko/Coinbase implementations, a deterministic
  `SimulatedPriceFeed` for tests), `strategies/` (pluggable
  `TradingStrategy`), `portfolioStore.ts` + `paperExchange.ts` (simulated
  order execution against a JSON-file-backed portfolio),
  `runTradingCycle.ts` (orchestrates sentiment → strategy → paper
  exchange). See `server/src/trading/README.md`.

## Working conventions (carried over from the sibling YouEnjoyMyFamily repo — they held up)

- **Strict typing everywhere:** `strict: true` + `noUncheckedIndexedAccess`
  in both subprojects. Run `npm run typecheck` after any change.
- **Validate at the boundary:** zod schemas for anything crossing a
  process boundary (collector → external API responses, API → dashboard).
- **Test what you write, for real:** `node:test` in `/server`, Vitest +
  `@testing-library/react` in `/dashboard`. Run `npm test` — don't assume
  a change works because it typechecks.
- **New external SDK/API → inject it, don't mock the module.** Define a
  minimal interface for the calls actually made, pass a factory with a
  real default, fake it in tests. See `server/src/collectors/reddit.ts`.
- **Check `npm audit` after adding or bumping a dependency**, and prefer a
  same-major patched version over a reflexive `--force` major bump —
  check what the advisory's fixed-version range actually requires.
- **Run the checks before considering a change done:** `npm run
  typecheck`, `npm run lint`, `npm test`, `npm run build` in both
  `/server` and `/dashboard`. Both have registry access in this
  environment — there's no excuse to skip actually running them.

## Collectors specifically

- A collector that isn't wired to real credentials is a stub that
  **throws a clear "not configured" error**, not one that silently
  returns empty/fake data — a caller (or the ingest job) needs to be able
  to tell "no data because nothing to report" apart from "not set up yet."
- Never hardcode API keys/tokens. Read them from `process.env`, document
  the required variable in that collector's section of
  `server/src/collectors/README.md` and in `.env.example`.
- Respect each platform's actual rate limits and ToS — this means using
  their real API (OAuth where required), not scraping public pages
  unofficially, even when scraping would be technically easier.
