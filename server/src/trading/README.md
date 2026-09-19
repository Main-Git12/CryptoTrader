# Trading

**Paper trading only. No real order is ever placed by anything in this
directory.** Everything here simulates a portfolio and computes real P&L
against real (or simulated) prices, entirely in a local JSON file — no
exchange account, no real money, ever, unless you deliberately build and
wire up real order execution later, which does not exist yet.

## Why paper trading first

The sentiment scorer (`../scoring/lexicon.ts`) is a transparent, deterministic
keyword-based baseline — not a validated trading signal. A small sample of
Reddit posts scored by keyword-matching is a well-known-to-be-weak
predictor of price movement; institutional desks with far more data and
compute struggle to extract reliable edge from social sentiment alone.
Paper trading exists so you can see, with real (or simulated) price data
and zero financial risk, whether a given strategy would have made or lost
money — before ever considering real money.

**A real, honest finding from testing this**: the baseline strategy
(`strategies/sentimentMomentum.ts`) computes average sentiment over a
rolling 24h window. When sentiment reverses partway through that window,
the reversal gets diluted by older mentions still inside it — a batch of
strongly negative mentions right after a batch of strongly positive ones
can average out to "neutral," missing the reversal entirely. This isn't a
bug; it's a real characteristic of a rolling-average signal, and a
legitimate thing to tune (a shorter window, or weighting recent mentions
more heavily) if you iterate on the strategy.

## Structure

```
types.ts                    TradingStrategy/PortfolioStore interfaces, Trade/PortfolioState shapes,
                              InsufficientFundsError/NoPositionToSellError
priceFeed/
  types.ts                    PriceFeed interface — just getPrice(ticker)
  coingecko.ts                 Real implementation (CoinGecko's free API, no credentials needed)
  coinbase.ts                   Real implementation (Coinbase Developer Platform / Advanced Trade,
                                  ES256-signed JWT auth) — price lookups only, no order placement
  simulated.ts                   Deterministic in-memory feed for tests and demos
strategies/
  sentimentMomentum.ts            Naive baseline: buy on strong positive sentiment, sell on strong
                                    negative sentiment, hold otherwise
portfolioStore.ts             JSON-file-backed portfolio persistence (cash, holdings, trade log)
paperExchange.ts               Simulates order execution: fixed position sizing, full-exit sells
runTradingCycle.ts              Orchestrates: pull sentiment summaries -> strategy -> paper exchange
```

## A note on the Coinbase and CoinGecko feeds

Both are real, correctly-implemented code, tested against mocked HTTP
responses (and, for Coinbase, a real generated test key pair that proves
the ES256 JWT signing is cryptographically correct). Neither has been
exercised against the live API — the sandbox this was built in has no
network access to any external price/exchange API (confirmed: CoinGecko,
Binance, Kraken, and Coinbase are all blocked by that environment's egress
policy). Run `npm run trade` somewhere with real internet access to
actually exercise them.

## Configuration

- `COINBASE_CDP_API_KEY_NAME`, `COINBASE_CDP_PRIVATE_KEY` — if both are
  set, `runTradingCycle`'s default price feed is Coinbase; otherwise it
  falls back to CoinGecko (no credentials needed).
- Position sizing and the strategy's thresholds are constructor
  parameters, not env vars yet — pass them explicitly if you're calling
  `runTradingCycle` outside its CLI default.

## Running it

```bash
npm run trade   # runs one cycle against all tracked tickers, prints each decision + the final portfolio
```

## What it would take to go from "paper" to "real"

This is a bigger, separate decision — not something to flip on casually:

1. **Validate the strategy first.** Run paper trading for a meaningful
   stretch of real time against real market data and look honestly at the
   result — profitable, unprofitable, or inconclusive.
2. **A real exchange integration for order placement** — everything here
   only reads prices; placing an order is a different, unbuilt code path
   that would need the exchange's trade-execution API, not just its price
   endpoint.
3. **Hard risk limits before any real money moves**: a maximum position
   size, a daily/total loss limit that halts trading, and a manual kill
   switch — none of which exist yet because there's no real execution path
   to protect.
4. **Your own funded exchange account and API keys with trading
   permission** — not something that can be created or funded on your
   behalf.
