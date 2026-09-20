# crypto-trader

A crypto trading bot that starts in **backtest/paper mode** — it trades against
historical or simulated prices with a simulated wallet, never a real exchange
account. Live trading is a separate, explicit opt-in (see below), not the
default.

## Why paper mode is the default

There is no live exchange API key configured anywhere in this repo, and none
will be fabricated — you provide your own if and when you decide to go live.
Until then, `LIVE_TRADING` defaults to `false` and the engine only ever
simulates fills against market data.

## Structure

```
src/crypto_trader/
  config.py       Env-driven config; refuses to start in live mode without real API credentials
  exchange.py     Thin ccxt wrapper — public market data always, order placement gated on live mode
  portfolio.py    Simulated wallet: cash + position, fills with fees, equity tracking
  strategy.py     Strategy interface + an example SMA-crossover strategy
  engine.py       Backtest engine: replays OHLCV candles through a strategy and a portfolio
tests/            pytest unit tests for portfolio math, strategy signals, config safety, and a full backtest run
```

## Getting started

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt

ruff check src tests   # lint
mypy                    # type check
pytest                  # unit tests (synthetic data, no network needed)

python -m crypto_trader.backtest --exchange kraken --symbol BTC/USD --timeframe 1h --days 30
```

CI (`.github/workflows/ci.yml`) runs lint, type check, and tests on every push
and pull request against `main`, on Python 3.11 and 3.12.

Default exchange is `kraken`, not `binance`: Binance's public API returns
HTTP 451 ("restricted location") for most cloud/datacenter egress IPs,
which includes most CI runners and PaaS hosts (e.g. Railway) — kraken,
coinbase, and bitstamp all work fine from those. If you're running this
somewhere Binance isn't blocked, `--exchange binance --symbol BTC/USDT`
works the same way.

## Going live (not yet wired up beyond the config guard)

Real trading needs real infrastructure decisions first — position sizing,
max-loss limits, which exchange, and your own API key/secret in
`EXCHANGE_API_KEY` / `EXCHANGE_API_SECRET` (never committed, never generated
for you). `Config` raises on startup if `LIVE_TRADING=true` without both set.
Order placement in `exchange.py` is intentionally unimplemented beyond that
guard until those decisions are made.
