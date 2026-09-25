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
  strategy.py     Strategy interface + SMA-crossover, RSI-reversion and time-series-momentum strategies
  engine.py       Backtest + live paper-trading loops: run a strategy against a portfolio, one candle at a time
  paper_trade.py  CLI: paper-trade against live market data with a simulated wallet
  state.py        Save/resume a paper-trading run's wallet, price history, and polling cursor
  metrics.py      Performance metrics for a backtest: return, max drawdown, win rate, Sharpe ratio
  optimize.py     CLI: grid-search strategy parameters against real historical data, ranked by performance
  leaderboard.py  Accumulate optimizer results across runs so each run can refine around the best found so far
  deflated.py     Deflated Sharpe ratio — what a search result is worth after correcting for how many configs were tried
  significance.py CLI: does the signal beat coin flips of the same rhythm, and does its margin survive block resampling?
  basket.py       CLI: multi-asset time-series-momentum basket on daily candles, volatility-targeted
  walkforward.py  CLI: pick the best config on one slice of history, score it on the next slice it never saw
                  (--basket does the same for the multi-asset momentum basket)
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

python -m crypto_trader.walkforward --symbol BTC/USD --timeframe 1h --train-candles 300 --test-candles 100

python -m crypto_trader.significance --timeframe 1d --days 730 --trials 500
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

Every run also reports a **deflated Sharpe ratio** (`deflated.py`, after
Bailey & López de Prado 2014), which is the honest version of the headline
number. An ordinary Sharpe asks "is this good?"; the deflated one asks "is
this good *given how hard we looked*?" — because the winner of a large
search is partly selected for luck. It computes the highest Sharpe you'd
expect from that many strategies with **zero** real skill, then reports the
probability the winner's true Sharpe is above zero. Above ~95% the result
survives the correction; below it, the search itself plausibly explains the
result.

On a real 30-day BTC/USD 1h run this is what it says about our own
optimizer's output:

```
Best Sharpe 0.069 vs 0.077 expected from 23 no-skill trials
Deflated Sharpe (P[true Sharpe > 0]): 40.9%
Does NOT survive the multiple-testing correction.
```

The top line of that same run showed +12.03% return. The two numbers are
both true, and the second one is the one that matters.

**A caveat worth taking seriously:** searching harder for parameters that
scored well on one slice of past data is a good way to find parameters that
*fit that slice*, which is not the same as finding parameters that will make
money next month. The more configurations you try, the more likely the
winner is just the luckiest fit to that history rather than a real edge. Use
the leaderboard to narrow down what's worth testing forward on unseen data
(that's what `walkforward` and `paper_trade` are for), not as a list of
settings that are "proven" to profit.

## The momentum basket: daily candles, many assets, volatility-targeted

`basket` is the deliberate opposite of hourly SMA/RSI on one pair, and it
exists because that shape is well documented to fail. It runs
`TimeSeriesMomentumStrategy` — long while the trailing N-candle return is
positive, flat otherwise — independently across several assets on daily
candles, each with its own equal slice of capital and its own wallet, then
sums the sleeves into one portfolio.

```bash
python -m crypto_trader.basket --timeframe 1d --days 730 --lookback 28
```

Three changes from the old approach, each for a reason:

- **Daily candles.** The single biggest lever. Hourly crossovers trade far
  too often to clear realistic round-trip costs; daily amortizes them, and
  1-4 weeks is the horizon where time-series momentum evidence actually
  exists. `--lookback 28` is ~4 weeks.
- **Several assets.** The same signal across many markets, so one asset's
  noise doesn't decide the result. Sleeves are independent wallets — no
  sleeve can spend another's cash.
- **Volatility targeting.** `--target-volatility-pct` scales a position down
  when the asset has been more volatile than the target. It only ever scales
  *down*, since sizing up would need leverage this wallet doesn't have.
  Expect steadier drawdowns from it, not higher returns.

A real run, 720 daily candles (~2 years) on Kraken, 28-day lookback:

```
BASKET          60.52%     33.72% drawdown    319 trades
buy & hold      49.11%
```

Excluding the one outlier sleeve (XRP, +200%), the remaining four still beat
the benchmark — 25.52% against 11.12% — so the result is not one asset
wearing a trench coat. Annualized, the basket's Sharpe lands around 0.6-1.0,
which is where the trend-following literature says to expect it.

**All of that is in-sample.** The lookback was taken from published evidence
rather than fitted to this data, which is a meaningfully better starting
position than a parameter search — but it is still a backtest over one
two-year stretch of one market regime. The section below is what happened
when it was scored out-of-sample, and the headline number did not survive.

## Walk-forward validation: does any of it hold up?

`optimize` tells you what fit the past best. `walkforward` tells you whether
that means anything. It repeatedly picks the best configuration on one slice
of history (the *train* range), then scores that single configuration on the
slice immediately after it (the *test* range), which it never saw — rolling
forward through the data. It reports both numbers per fold, plus buy & hold
over the same test range as a benchmark.

The gap between the train and test columns is what searching cost you. Here
is a real run on BTC/USD 1h data, 300 train / 100 test candles, 4 folds:

```
Mean in-sample (train):       4.02%
Mean out-of-sample (test):    0.38%
Mean buy & hold:              1.73%
Profitable out-of-sample:  1/4 folds
```

Read that honestly: configurations that averaged +4% on the data they were
chosen from returned +0.38% on data they hadn't seen, underperformed simply
holding the asset, and lost money in 3 of 4 periods. That is the normal
result for this kind of search, and it is the reason the live-trading gate
in this repo stays shut. A strategy earns real money only after it survives
this test *and* forward paper trading — not because it topped a leaderboard.

### The basket, walked forward

`--basket` applies the same discipline to the multi-asset momentum basket.
Each fold searches a set of lookbacks across the whole basket on the train
range, picks the one with the best total return, then scores *that single
lookback* on the test range it never saw, against equal-weight buy & hold
over the same range. Series are first trimmed to a common length (keeping
the most recent candles) so a fold's indices mean the same dates in every
sleeve, and each test window is warmed up on the train candles immediately
before it so the momentum signal is already formed when scoring starts.

```bash
python -m crypto_trader.walkforward --basket --timeframe 1d --days 730 \
  --train-candles 300 --test-candles 100
```

720 daily Kraken candles, 5 symbols, 4 folds — first with the lookback
searched per fold, then with it pinned at 28 so no search happens at all:

```
                          searched    fixed(28)
Mean in-sample (train):     29.75%      13.04%
Mean out-of-sample (test):  -1.78%      -3.14%
Mean buy & hold:            -9.96%      -9.96%
Profitable out-of-sample:   1/4          1/4
Beat buy & hold:            2/4          2/4
```

**The in-sample +60.52% did not survive.** Out-of-sample the basket lost
money in both configurations, and searching the lookback bought nothing:
it tripled the in-sample number (13% → 30%) and left the out-of-sample
number where it was. The lookback it picked also refused to sit still
across folds (21, 21, 7, 56), which is what fitting each window looks like.

What *did* show up is worth stating precisely, because it is the only
positive finding here: the basket beat buy & hold in 2 of 4 folds and lost
far less than it over the period as a whole (-1.8% against -10.0%), with
noticeably shallower drawdowns (5-15% against holding through a 42% fall
in one fold). The test ranges happen to cover a falling market, and being
flat rather than long during a fall is exactly what a trend filter is
supposed to do. That is a real property, and it is *not* the same as an
edge: losing less than a losing benchmark still loses money. Nothing here
justifies putting capital behind it, and the live-trading gate stays shut.

**Note on available history:** exchanges cap how many candles they'll return
regardless of `--days`. Kraken returns about 720 per timeframe (so 4h covers
~120 days, 1d covers ~1 year); Coinbase returns 300. Walk-forward needs
`train + test` candles for even one fold, so for longer calendar coverage,
use a longer `--timeframe` rather than a bigger `--days`.

CI (`.github/workflows/ci.yml`) runs lint, type check, and tests on every push
and pull request against `main`, on Python 3.11 and 3.12.

Default exchange is `kraken`, not `binance`: Binance's public API returns
HTTP 451 ("restricted location") for most cloud/datacenter egress IPs,
which includes most CI runners and PaaS hosts (e.g. Railway) — kraken,
coinbase, and bitstamp all work fine from those. If you're running this
somewhere Binance isn't blocked, `--exchange binance --symbol BTC/USDT`
works the same way.

## Is any of it distinguishable from luck?

`significance.py` runs two tests that apply even when nothing was searched.
Both exist because of a specific weakness in the basket result above: it
rests on four folds, and "beat buy & hold in 2 of 4" is not a claim four
folds can carry on their own.

```bash
python -m crypto_trader.significance --timeframe 1d --days 730 --trials 500
```

### 1. Did the timing do anything, or was it just being in cash?

A strategy that is long half the time looks different from buy & hold
whether or not its timing means anything. So the control isn't buy & hold —
it's `RandomSignalStrategy`, a coin flip that **ignores price entirely** and
is given the real strategy's own entry and exit rates. That matches its
exposure *and* its average holding period, so fees and time-in-market line
up, and the only thing destroyed is the relationship to price.

Why the rhythm has to match: comparing against "always in the market"
conflates two claims — that the timing is informative, and that being out
sometimes helped. This separates them.

The test is sharp enough to fail a result that looks excellent. On a
straight-line rising series, momentum returns **+171%** and does *not*
survive: it never exits, so its controls never exit either, which makes them
"buy on a random early candle and hold" — and they score about the same. The
return is real; the timing contributed almost nothing to it.

### 2. Is the margin bigger than the noise?

A moving-block bootstrap resamples the paired difference in contiguous
blocks, preserving the autocorrelation and volatility clustering that make a
plain t-test overconfident on financial returns.

It measures **log growth**, not the arithmetic difference, and that choice
matters here: a strategy sitting in cash half the time has far less
compounding drag, so it can finish well ahead while earning *less* on the
average candle. Our own basket does exactly that — its mean per-candle edge
is negative and it still ends ahead. An arithmetic test would call that a
failure. It's just a different way of winning.

### What it says about our basket

720 daily Kraken candles, 5 symbols, 28-day lookback:

```
--- Random-signal test: is the timing worth anything? ---
Control rhythm: long 47% of candles, entry 8.5%/candle, exit 9.3%/candle
Momentum basket:                 62.41%
500 random controls, mean        18.13%
500 random controls, median      12.14%
Beat 467/500 of them (p = 0.068)

--- Block bootstrap: is the margin over buy & hold bigger than the noise? ---
Momentum basket:                 62.41%
Equal-weight buy & hold:         45.35%
Compounded edge over the period: +11.63%
Edge vanished in 1988/5000 resamples (p = 0.398)
```

Read both honestly. The basket beat 93% of controls that share its exact
trading rhythm — genuinely suggestive, and the best sign this repo has
produced — but p = 0.068 does not clear the 5% bar, so it stays a reason to
gather more data rather than a reason to believe. And its margin over buy &
hold is well inside what block resampling produces by chance.

Verdicts are reported in three bands rather than two, because a p-value of
0.068 and one of 0.398 are not the same finding, and calling both "not
significant" discards the difference.

## Risk limits

`risk.py` caps what a strategy is allowed to do, independent of what it
signals. A strategy decides *when* to trade; `RiskLimits` decides *how much*
and *whether trading is still allowed at all*:

- `max_position_fraction` — the share of equity a single position may use.
  `1.0` is the all-in sizing backtests default to; `0.25` risks at most a
  quarter of the account at once.
- `max_drawdown_pct` — a kill switch, not a stop-loss. Once equity falls
  that far below its high-water mark, trading stops for good and any open
  position is flattened. Halting is one-way on purpose: a switch that
  re-arms itself when equity ticks back up isn't a kill switch, and
  restarting should be a decision someone makes, not something that happens
  while nobody is watching.

Both apply to backtests and paper trading through the same code path, so you
can backtest what a given set of limits would have done to the same signals:

```bash
python -m crypto_trader.paper_trade --max-position-fraction 0.25 --max-drawdown-pct 20
```

## Running it continuously

`paper_trade` is built to survive being left alone:

- A failed poll doesn't end the run. Exchanges time out, rate-limit, and have
  outages; the error is logged to stderr and the next cycle picks up from the
  same cursor, so missed candles arrive late rather than being lost.
- `SIGTERM` (what a platform sends on redeploy) unwinds the same way Ctrl-C
  does, so state is saved instead of dropped.
- `--state-file` on a persistent volume means a restart resumes the wallet,
  price history, and cursor instead of starting over.

The `Procfile` runs it as a worker, configured by environment variables
(`STATE_FILE`, `EXCHANGE_ID`, `SYMBOL`, `TIMEFRAME`, `MAX_POSITION_FRACTION`,
`MAX_DRAWDOWN_PCT`). Point `STATE_FILE` at a mounted volume — on ephemeral
disk a redeploy silently resets the run to its starting balance.

**What this is for:** accumulating out-of-sample evidence on data that didn't
exist when a configuration was chosen. Walk-forward tests against history the
strategy never saw; this tests against history that hasn't happened yet,
which is the only test that can't be gamed by searching harder. It is still a
simulated wallet — no credentials, no real orders.

## Going live (not yet wired up beyond the config guard)

Real trading needs real infrastructure decisions first — position sizing,
max-loss limits, which exchange, and your own API key/secret in
`EXCHANGE_API_KEY` / `EXCHANGE_API_SECRET` (never committed, never generated
for you). `Config` raises on startup if `LIVE_TRADING=true` without both set.
Order placement in `exchange.py` is intentionally unimplemented beyond that
guard until those decisions are made.
