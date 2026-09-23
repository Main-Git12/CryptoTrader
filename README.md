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
  strategy.py     Strategy interface + SMA-crossover and RSI-reversion strategies
  engine.py       Backtest + live paper-trading loops: run a strategy against a portfolio, one candle at a time
  paper_trade.py  CLI: paper-trade against live market data with a simulated wallet
  state.py        Save/resume a paper-trading run's wallet, price history, and polling cursor
  metrics.py      Performance metrics for a backtest: return, max drawdown, win rate, Sharpe ratio
  optimize.py     CLI: grid-search strategy parameters against real historical data, ranked by performance
  leaderboard.py  Accumulate optimizer results across runs so each run can refine around the best found so far
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

python -m crypto_trader.optimize --exchange kraken --symbol BTC/USD --timeframe 1h --days 90
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

Pass `--state-file PATH` to persist the wallet, recent price history, and
polling cursor after each run and resume from them on the next one — without
it, every run starts over from `--starting-balance-usd` and re-fetches from
scratch, which isn't useful for anything meant to keep running across
restarts (a crash, a redeploy, a manual stop and start).

`optimize` backtests a grid of SMA-crossover and RSI-reversion parameter
combinations against the same historical data and ranks them by total
return, printing each one's max drawdown, win rate, Sharpe ratio (per-candle,
not annualized), and trade count alongside it — a way to compare strategies
and parameters against real market history before deciding what, if
anything, is worth paper-trading live. Like everything else here, it only
ever runs backtests against a simulated wallet.

Pass `--leaderboard-file PATH` to accumulate results across runs. Each run
then also searches *around* the best configurations previous runs found for
that same symbol and timeframe — stepping their parameters up and down — so
repeated runs hill-climb toward better parameters instead of re-testing one
fixed grid forever, and can land on values the original grid never
contained.

**A caveat worth taking seriously:** searching harder for parameters that
scored well on one slice of past data is a good way to find parameters that
*fit that slice*, which is not the same as finding parameters that will make
money next month. The more configurations you try, the more likely the
winner is just the luckiest fit to that history rather than a real edge. Use
the leaderboard to narrow down what's worth testing forward on unseen data
(that's what `paper_trade` is for), not as a list of settings that are
"proven" to profit.

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
