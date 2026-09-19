# CryptoTrader server

Node 20 + strict TypeScript. Collects social mentions of tracked crypto
tickers, scores their sentiment, stores the results, and serves them over
a small read-only HTTP API. See the root README for the platform-status
table and the hard "informational only" boundary.

## Structure

```
src/
  tickers.ts                Tracked-ticker list + extraction (cashtag-only rules for ambiguous symbols like DOT/LINK/ADA)
  tickers.test.ts
  scoring/
    types.ts                  SentimentScorer interface — pluggable, see CLAUDE.md
    lexicon.ts                 Deterministic lexicon-based baseline scorer, with basic negation handling
    lexicon.test.ts
  collectors/                (every collector below has a matching *.test.ts)
    types.ts                   Collector interface, Mention shape, CollectorNotConfiguredError/CollectorNotImplementedError
    reddit.ts                  Real: OAuth client-credentials flow against Reddit's official API
    twitter.ts                 Stub: needs a paid X API plan
    telegram.ts                Stub: needs a bot token + the bot joined to specific channels
    discord.ts                 Stub: needs a bot token + the bot invited to specific servers
    README.md                  Setup steps and honest cost/access notes per platform
  storage/
    types.ts                   Store interface (add mentions, query time series / top tickers)
    jsonFileStore.ts            JSON-file-backed implementation — fine at this scale, swap before it needs to scale
    jsonFileStore.test.ts
  ingest.ts                    Orchestrates collectors → scorer → store; run directly or on a schedule
  ingest.test.ts
  api/
    server.ts                   Plain node:http JSON API (no framework dependency) serving the dashboard
    server.test.ts               Real HTTP requests against an ephemeral port, fake Store
  trading/                      Paper trading only — see trading/README.md for the full picture
    types.ts, paperExchange.ts, portfolioStore.ts, runTradingCycle.ts
    priceFeed/                   coingecko.ts + coinbase.ts (real, untested against the live API from
                                   this sandbox — see trading/README.md), simulated.ts (for tests/demos)
    strategies/sentimentMomentum.ts   Naive baseline strategy
```

## Checks

```bash
npm install
npm run typecheck   # tsc --noEmit
npm run lint          # eslint src
npm test               # node --test (real temp dirs for storage tests, real HTTP for the API test, mocked fetch for collectors)
npm run build           # tsc -p tsconfig.build.json (excludes test files)
```

## Running it

```bash
cp .env.example .env   # fill in whatever credentials you have — Reddit's are free
npm run ingest           # runs every collector once; unconfigured/unimplemented ones are skipped, not errors
npm run serve             # starts the API on :4000 (or $PORT)
npm run trade              # runs one paper-trading cycle; see src/trading/README.md before assuming this touches real money (it doesn't)
```

`npm run ingest` is meant to run on a schedule (cron, a scheduled Lambda,
whatever you deploy this to eventually) — it's idempotent, since the store
de-duplicates by mention id.
