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
  engine.py       Backtest + live paper-trading loops: run a strategy against a portfolio, one candle at a time
  paper_trade.py  CLI: paper-trade against live market data with a simulated wallet
tests/            pytest unit tests for portfolio math, strategy signals, config safety, and a full backtest run
```

## Getting started

```bash
pip install -e .
pip install -r requirements-dev.txt

ruff check src tests   # lint
mypy                    # type check
pytest                  # unit tests (synthetic data, no network needed)

python -m crypto_trader.backtest --exchange kraken --symbol BTC/USD --timeframe 1h --days 30

python -m crypto_trader.paper_trade --exchange kraken --symbol BTC/USD --timeframe 1h
```

`pip install -e .` installs this `src`-layout package (and its `ccxt` dependency, per
`pyproject.toml`) in editable mode — without it, `crypto_trader` isn't importable and
both `pytest` and the commands above fail with `ModuleNotFoundError`.

`backtest` replays historical candles all at once and reports a final P&L.
`paper_trade` runs the same strategy/portfolio machinery against live market
data instead: it polls for newly-closed candles (once per timeframe by
default) and simulates a fill whenever the strategy signals, printing each
trade as it happens. Like `backtest`, it never reads `LIVE_TRADING` or
touches `place_order` — it's a simulated wallet regardless of `Config`. Runs
until interrupted (Ctrl-C), or pass `--iterations N` to stop after N polls.

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
