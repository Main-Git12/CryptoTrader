# Handoff: where this project stands

A one-page orientation for anyone picking this repo up. The README has the
detail and the commands; this is the map.

## What it is

A crypto backtesting and paper-trading engine, plus four instruments for
telling a real edge from a lucky fit. It never touches a real exchange account:
there are no credentials anywhere in the repo, and live order placement is
unimplemented behind two independent guards (`Config` and `place_order`).

## What's been built

| Module | Does |
|---|---|
| `engine.py`, `portfolio.py` | Candle-by-candle backtest and live paper trading against a fee-aware simulated wallet |
| `strategy.py` | SMA crossover, RSI reversion, time-series momentum, and a coin-flip null strategy |
| `risk.py` | Position cap, one-way drawdown kill switch, volatility targeting |
| `basket.py` | One strategy across several assets, each with an independent wallet |
| `optimize.py`, `leaderboard.py` | Parameter search that refines around previous runs' best results |
| `walkforward.py` | Choose on a train range, score on the unseen test range that follows |
| `deflated.py` | Deflated Sharpe: corrects a search winner for how many configs were tried |
| `significance.py` | Coin-flip controls matched on exposure and rhythm; block bootstrap on log growth |
| `paper_trade.py`, `state.py` | 24/7 paper trading that survives restarts and redeploys |

All six analyses install as commands (`crypto-trader-walkforward`, etc.).
`pytest`, `ruff check src tests` and `mypy` must pass; CI runs them on 3.11 and 3.12.

## What's been proven

Every strategy has been measured, and none has an established edge:

| Test | Result |
|---|---|
| Walk-forward, hourly SMA/RSI (BTC) | +4.02% in-sample, **+0.38%** out-of-sample, profitable in 1 of 4 folds |
| Deflated Sharpe, optimizer winner | Sharpe 0.069 against **0.077 expected from zero skill**; P = 40.9% |
| Walk-forward, momentum basket (daily, 5 assets) | +60.52% in-sample, **−1.78%** out-of-sample |
| Block bootstrap, basket vs buy & hold | +11.63% compounded edge, but **p = 0.398** |
| Coin-flip controls, basket | Beat 467 of 500 controls with the same rhythm, **p = 0.068** |

Two things did hold up, and they should be stated precisely:

- **The basket is defensive.** Out of sample it fell far less than buy & hold
  through a falling market (−1.8% against −10.0%), with shallower drawdowns.
  That is a real property, and it is not an edge.
- **The basket's timing is suggestive.** It beat 93% of controls sharing its
  exact exposure and holding period. That is the best result here, and it still
  misses the 5% threshold.

## What failed, and why it matters

- Hourly indicators on one pair trade too often to clear fees.
- Searching harder makes in-sample numbers better and out-of-sample numbers no
  better. Searching the basket's lookback tripled its in-sample return and left
  the out-of-sample result unchanged.
- Small wallets can't trade at all: Kraken's minimum order is about $2.50 for
  the cheapest pair and $4–7 for most of the basket.

## The one open lead

The p = 0.068 result fell short for lack of data, not lack of signal. Kraken
returns at most ~720 candles per timeframe, so every daily test covers about
two years. **A loader that stitches history across exchanges**, for 3–5× the
sample, would push that result under 0.05 or kill it. Either answer is worth
more than another strategy, and nothing else here could honestly end in "this
makes money."

## Ground rules (from `CLAUDE.md`)

- Never fabricate API keys, wallet addresses or tokens anywhere.
- Paper mode is the default. Anything that makes live trading easier to reach
  needs explicit sign-off, not just a passing test.
- Tests use deterministic synthetic data, with no network and no credentials.
- A result counts only after it survives walk-forward **and** the significance
  tests, and then forward paper trading.
