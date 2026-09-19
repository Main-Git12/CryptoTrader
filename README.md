# CryptoTrader — social sentiment monitor + paper trading

Tracks mentions and sentiment of crypto tickers across social platforms,
surfaces them on a read-only dashboard, and can paper-trade a strategy
against them — with real portfolio math and zero real money at risk. **No
real order has ever been placed by anything in this repo; that would be a
separate, much bigger, explicit step.** See `server/src/trading/README.md`
before assuming otherwise.

## Status

Real and tested: Reddit collection, sentiment scoring, the dashboard, and
the paper-trading engine (portfolio math, order simulation, a baseline
strategy). Real code, not-yet-verified-live: the Coinbase and CoinGecko
price feeds — correct and tested against mocked responses, but this
sandbox's network policy blocks every external market-data API, so
they've never made a real request. Stubs pending your credentials: X,
Telegram, Discord collectors. See [Platform status](#platform-status)
before assuming everything is live.

## Repository layout

```
/server        Node/TypeScript backend: collectors, sentiment scoring, storage, ingest pipeline,
                 API, paper trading (strategy, portfolio, order simulation)
/dashboard     React/TypeScript frontend: charts for mention volume, sentiment trend, top tickers
```

## Platform status

| Platform  | Status | What's needed to go live |
|-----------|--------|---------------------------|
| Reddit    | **Real** — OAuth client-credentials flow against Reddit's official API | A free script-type app at reddit.com/prefs/apps → `REDDIT_CLIENT_ID`/`REDDIT_CLIENT_SECRET` in `.env` |
| X/Twitter | Stub — interface implemented, throws until configured | A **paid** X API plan (current pricing starts well above free tier for meaningful read volume) → bearer token |
| Telegram  | Stub | A bot token (free) **and** the bot added to the specific channels/groups you want monitored — public channel monitoring, not private DMs |
| Discord   | Stub | A bot token (free) **and** the bot invited to specific servers with read permissions on the channels you want monitored |

None of the stubs are wired to real network calls — they exist so the
pipeline's shape (collector → scorer → store → API → dashboard) doesn't
need to change when you're ready to add a platform. See
`server/src/collectors/README.md` for exactly what each one needs.

## Design

- **Pluggable collectors:** every platform implements the same
  `Collector` interface (`server/src/collectors/types.ts`) — fetch raw
  mentions for a set of tracked tickers over a time window. Adding a
  platform means implementing that interface, not touching the scoring,
  storage, or API layers.
- **Pluggable scoring:** sentiment scoring is a `SentimentScorer`
  interface (`server/src/scoring/types.ts`). The current implementation is
  a deterministic lexicon-based scorer — transparent, testable, and a
  reasonable baseline. It's designed to be swapped for a trained/ML-based
  scorer later without touching collectors, storage, or the API; "the
  model keeps improving" is a real upgrade path here, not a marketing claim.
- **Paper trading, never real trading, without a separate explicit
  decision.** `server/src/trading/` simulates a portfolio against a
  `PriceFeed` (real: CoinGecko, Coinbase; simulated: for tests/demos) —
  see `server/src/trading/README.md` for exactly what it would take to
  ever place a real order, and why that's not a small step.

## Getting started

- [`server/README.md`](server/README.md)
- [`server/src/trading/README.md`](server/src/trading/README.md)
- [`dashboard/README.md`](dashboard/README.md)
