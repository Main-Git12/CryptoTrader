# Collectors

Every platform implements the `Collector` interface in `types.ts`:
`collect(tickers)` returns raw `Mention[]` for the requested tickers over
whatever window that platform's API gives you. The ingest pipeline
(`../ingest.ts`) doesn't know or care which platforms are real.

## Reddit — real, working

Uses Reddit's official OAuth "application only" (client-credentials) flow
— free, read-only, no user login. Setup:

1. Go to <https://www.reddit.com/prefs/apps>, click "create app", choose
   type **script**.
2. Set the following in `.env` (see `.env.example`):
   - `REDDIT_CLIENT_ID` — the string under the app name
   - `REDDIT_CLIENT_SECRET` — the "secret" field
   - `REDDIT_USER_AGENT` — optional, defaults to a generic one; Reddit
     recommends `platform:app_id:version (by /u/yourusername)`
   - `REDDIT_SUBREDDITS` — optional, comma-separated, defaults to
     `CryptoCurrency,CryptoMarkets`

Without credentials, `collect()` throws `CollectorNotConfiguredError`
naming the missing env vars — it does not silently return `[]`.

## X/Twitter, Telegram, Discord — structural stubs

These implement `Collector` and always throw `CollectorNotImplementedError`
right now. They exist so the rest of the pipeline (scoring, storage, API,
dashboard) never has to change shape when one of these goes live — only
the collector's internals need writing, plus real credentials:

- **X/Twitter**: needs a **paid** API plan (current tiers price real read
  volume well above free) and a bearer token. Not something I can
  provision — you'd need to sign up and share the token.
- **Telegram**: needs a free bot token from [@BotFather](https://t.me/botfather)
  **and** the bot added to each specific public channel/group you want
  monitored. It cannot see private DMs or channels it hasn't joined.
- **Discord**: needs a free bot token from the
  [Discord Developer Portal](https://discord.com/developers/applications)
  **and** the bot invited into each specific server, with read permission
  on the channels you want monitored.

If you want one of these live, the fastest path is: get the credentials,
tell me, and I'll wire up the real implementation the same way Reddit's is
built — OAuth/token handling, response parsing, ticker extraction, unit
tests with a mocked `fetch`, no real network calls required to verify it
works.
