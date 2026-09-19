# CryptoTrader — social sentiment monitor

Tracks mentions and sentiment of crypto tickers across social platforms and
surfaces them on a read-only dashboard. **This is an informational tool,
not financial advice, and does not place trades or generate buy/sell
signals.** It scores publicly available text data; it has no opinion on
what you should do with that information.

## Status

This is an early scaffold. One collector is real and working end-to-end;
the rest are stubs pending credentials only you can provide — see
[Platform status](#platform-status) below before assuming everything is live.

## Repository layout

```
/server        Node/TypeScript backend: collectors, sentiment scoring, storage, ingest pipeline, API
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
- **No trading logic.** The system stops at aggregated, timestamped
  mention/sentiment data. Anything resembling a "buy/sell signal" is a
  deliberate non-goal right now — see the dashboard's own disclaimer.

## Getting started

- [`server/README.md`](server/README.md)
- [`dashboard/README.md`](dashboard/README.md)
