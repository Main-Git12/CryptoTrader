"""Is a backtest result distinguishable from luck?

`deflated.py` answers a related question — what a search result is worth
given how many configurations were tried. This module answers two others,
both of which apply even when nothing was searched at all:

1. **Did the signal do anything?** A strategy that is long half the time
   will look different from buy & hold whether or not its timing means
   anything. `random_signal_test` replaces the signal with coin flips that
   have the same exposure and the same trading rhythm, runs that many times,
   and reports where the real result lands in that distribution.

2. **Is the margin over a benchmark bigger than the noise?** Financial
   returns are autocorrelated and fat-tailed, so the usual t-test overstates
   its own confidence. `block_bootstrap_test` resamples the paired
   difference series in blocks, preserving that structure, and reports how
   often the resampled advantage disappears.

Neither test can make a strategy good. Both can show that a number which
looked good is inside the range that nothing-in-particular produces, which
is the more common outcome and the more useful thing to know.
"""

import argparse
import itertools
import math
import random
import statistics
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

from .basket import DEFAULT_SYMBOLS, equal_weight_buy_and_hold_pct, run_basket_backtest
from .config import Config
from .engine import run_backtest
from .exchange import fetch_ohlcv
from .metrics import step_returns
from .portfolio import Portfolio
from .risk import RiskLimits
from .strategy import RandomSignalStrategy, Strategy, TimeSeriesMomentumStrategy


@dataclass
class TransitionRates:
    """How often a position series flips state, and what that implies.

    `p_enter` is the share of flat candles followed by a long one, `p_exit`
    the share of long candles followed by a flat one. Together they pin down
    both how much of the time a strategy is exposed and how long it stays
    put once it commits — the two things a fair control has to match.
    """

    p_enter: float
    p_exit: float
    time_in_market: float
    candles: int


def transition_rates(positions: Sequence[bool]) -> TransitionRates | None:
    """None when the series is too short to have a transition to measure."""
    if len(positions) < 2:
        return None

    flat_to_long = sum(1 for a, b in zip(positions, positions[1:], strict=False) if not a and b)
    flat_total = sum(1 for a in positions[:-1] if not a)
    long_to_flat = sum(1 for a, b in zip(positions, positions[1:], strict=False) if a and not b)
    long_total = sum(1 for a in positions[:-1] if a)

    return TransitionRates(
        # A state never visited has no observed exit rate. 0.0 is the honest
        # stand-in: the control is then simply never seen leaving a state the
        # real strategy was never seen leaving either.
        p_enter=flat_to_long / flat_total if flat_total else 0.0,
        p_exit=long_to_flat / long_total if long_total else 0.0,
        time_in_market=sum(1 for p in positions if p) / len(positions),
        candles=len(positions),
    )


def pooled_transition_rates(position_series: Sequence[Sequence[bool]]) -> TransitionRates | None:
    """One rhythm summarizing several sleeves, weighted by their lengths.

    The basket runs one strategy across many assets, so the thing being
    tested is the strategy's rhythm, not any single sleeve's. Pooling keeps
    the control matched to that.
    """
    rates = [(series, transition_rates(series)) for series in position_series]
    usable = [(series, rate) for series, rate in rates if rate is not None]
    if not usable:
        return None

    total = sum(len(series) for series, _ in usable)
    return TransitionRates(
        p_enter=sum(rate.p_enter * len(series) for series, rate in usable) / total,
        p_exit=sum(rate.p_exit * len(series) for series, rate in usable) / total,
        time_in_market=sum(rate.time_in_market * len(series) for series, rate in usable) / total,
        candles=total,
    )


@dataclass
class RandomSignalResult:
    """Where a real result sits among controls that share its rhythm."""

    actual_return_pct: float
    trial_returns_pct: list[float] = field(default_factory=list)
    rates: TransitionRates | None = None

    @property
    def trials(self) -> int:
        return len(self.trial_returns_pct)

    @property
    def mean_trial_return_pct(self) -> float | None:
        return statistics.fmean(self.trial_returns_pct) if self.trial_returns_pct else None

    @property
    def median_trial_return_pct(self) -> float | None:
        return statistics.median(self.trial_returns_pct) if self.trial_returns_pct else None

    @property
    def p_value(self) -> float | None:
        """Share of random controls that did at least as well as the real
        strategy.

        Read it as: the probability a signal with no information would have
        looked this good by chance. The real result is counted in both the
        numerator and denominator — the standard small-sample correction,
        which keeps the p-value from ever being exactly 0 and claiming more
        certainty than N trials can support.
        """
        if not self.trial_returns_pct:
            return None
        at_least_as_good = sum(1 for r in self.trial_returns_pct if r >= self.actual_return_pct)
        return (at_least_as_good + 1) / (self.trials + 1)

    @property
    def survives(self) -> bool:
        """True when fewer than 5% of no-information controls matched it."""
        p_value = self.p_value
        return p_value is not None and p_value < 0.05


def random_signal_test(
    close_prices: Sequence[float],
    strategy: Strategy,
    starting_balance_usd: float,
    min_history: int,
    trials: int = 200,
    seed: int = 0,
) -> RandomSignalResult | None:
    """Runs `strategy`, then re-runs the same prices `trials` times with
    coin-flip strategies matched to its exposure and holding period."""
    prices = list(close_prices)
    actual = run_backtest(prices, strategy, Portfolio(cash_usd=starting_balance_usd), min_history=min_history)
    rates = transition_rates(actual.positions)
    if rates is None:
        return None

    actual_return_pct = _return_pct(actual.equity_curve, starting_balance_usd)
    trial_returns = []
    for trial in range(trials):
        control = RandomSignalStrategy(rates.p_enter, rates.p_exit, seed=seed + trial)
        run = run_backtest(prices, control, Portfolio(cash_usd=starting_balance_usd), min_history=min_history)
        trial_returns.append(_return_pct(run.equity_curve, starting_balance_usd))

    return RandomSignalResult(actual_return_pct=actual_return_pct, trial_returns_pct=trial_returns, rates=rates)


def random_signal_test_basket(
    price_series: Mapping[str, Sequence[float]],
    make_strategy: Callable[[], Strategy],
    starting_balance_usd: float,
    min_history: int,
    trials: int = 200,
    seed: int = 0,
    limits: RiskLimits | None = None,
) -> RandomSignalResult | None:
    """The same test applied to the whole basket.

    Each sleeve gets its own independently-seeded control, so a trial is a
    basket of unrelated coin flips — not one coin flip applied five times,
    which would understate the diversification the real basket gets.
    """
    actual = run_basket_backtest(price_series, make_strategy, starting_balance_usd, min_history, limits)
    if actual.metrics is None:
        return None

    rates = pooled_transition_rates([sleeve.result.positions for sleeve in actual.sleeves])
    if rates is None:
        return None

    sleeve_seeds = itertools.count(seed)
    trial_returns = []
    for _ in range(trials):
        run = run_basket_backtest(
            price_series,
            lambda: RandomSignalStrategy(rates.p_enter, rates.p_exit, seed=next(sleeve_seeds)),
            starting_balance_usd,
            min_history,
            limits,
        )
        if run.metrics is not None:
            trial_returns.append(run.metrics.total_return_pct)

    return RandomSignalResult(
        actual_return_pct=actual.metrics.total_return_pct, trial_returns_pct=trial_returns, rates=rates
    )


@dataclass
class BlockBootstrapResult:
    """A resampled distribution for a strategy's margin over a benchmark,
    measured in log growth per candle.

    Log growth, not the plain arithmetic difference, because the two answer
    different questions and only one of them is the question here. Summed
    over the period, mean log difference *is* the ratio of final balances —
    so a positive value means the strategy ended ahead, which is what anyone
    comparing to buy & hold actually wants to know.

    The distinction is not academic for this repo. A strategy that sits in
    cash half the time has much lower variance, and therefore much less
    compounding drag, so it can end well ahead of a benchmark while earning
    *less* on the average candle. Testing the arithmetic difference would
    call that a failure; it is simply a different way of winning.
    """

    observed_mean_log_difference: float
    return_count: int
    resampled_means: list[float] = field(default_factory=list)
    block_size: int = 0

    @property
    def trials(self) -> int:
        return len(self.resampled_means)

    @property
    def compounded_difference_pct(self) -> float:
        """The observed edge compounded over the whole period, as a percent —
        how much more (or less) the strategy ended up with per dollar."""
        return (math.exp(self.observed_mean_log_difference * self.return_count) - 1) * 100

    @property
    def p_value(self) -> float | None:
        """Share of resamples in which the advantage vanished.

        The difference series is resampled in blocks, so each resample is a
        plausible reordering of the same history with its autocorrelation
        intact. If the margin survives that reshuffling it is coming from
        the whole period; if it disappears in a third of resamples, it was
        resting on a handful of candles that happened to fall well.
        """
        if not self.resampled_means:
            return None
        return (sum(1 for mean in self.resampled_means if mean <= 0) + 1) / (self.trials + 1)

    @property
    def survives(self) -> bool:
        p_value = self.p_value
        return p_value is not None and p_value < 0.05


def block_bootstrap_test(
    strategy_returns: Sequence[float],
    benchmark_returns: Sequence[float],
    block_size: int = 10,
    trials: int = 2000,
    seed: int = 0,
) -> BlockBootstrapResult | None:
    """Moving-block bootstrap on the paired per-candle difference in log
    growth (see `BlockBootstrapResult` for why log).

    Resampling individual candles would destroy the autocorrelation that
    makes financial returns what they are, and would report far more
    confidence than the data supports. Resampling contiguous blocks keeps
    the local structure — momentum, volatility clustering — and only
    reshuffles which stretches of history show up.
    """
    if block_size <= 0:
        raise ValueError(f"block_size must be positive, got {block_size}")

    paired = list(zip(strategy_returns, benchmark_returns, strict=False))
    differences = [
        math.log1p(strategy) - math.log1p(benchmark)
        for strategy, benchmark in paired
        # A candle that wipes a series out has no finite log growth. In
        # practice neither series reaches -100%, but the guard keeps one bad
        # candle from taking the whole test with it.
        if strategy > -1 and benchmark > -1
    ]
    if len(differences) < 2 or len(differences) < block_size:
        return None

    starts = len(differences) - block_size + 1
    blocks_needed = -(-len(differences) // block_size)  # ceil
    rng = random.Random(seed)

    resampled_means = []
    for _ in range(trials):
        sample: list[float] = []
        for _ in range(blocks_needed):
            start = rng.randrange(starts)
            sample.extend(differences[start : start + block_size])
        resampled_means.append(statistics.fmean(sample[: len(differences)]))

    return BlockBootstrapResult(
        observed_mean_log_difference=statistics.fmean(differences),
        return_count=len(differences),
        resampled_means=resampled_means,
        block_size=block_size,
    )


def verdict(p_value: float, survived: str, borderline: str, failed: str) -> str:
    """Three bands, not two.

    A p-value of 0.06 is not the same finding as one of 0.60, and collapsing
    both into "not significant" throws away the difference. The middle band
    says what it is: suggestive, short of the threshold, and a reason to get
    more data rather than to believe it or dismiss it.
    """
    if p_value < 0.05:
        return survived
    return borderline if p_value < 0.15 else failed


def _return_pct(equity_curve: Sequence[float], starting_balance_usd: float) -> float:
    final = equity_curve[-1] if equity_curve else starting_balance_usd
    return (final - starting_balance_usd) / starting_balance_usd * 100


def buy_and_hold_equity_curve(close_prices: Sequence[float], starting_balance_usd: float) -> list[float]:
    """The benchmark's equity candle by candle, paying the one entry fee a
    real buyer would — so its returns line up with a strategy's for pairing."""
    if len(close_prices) < 2:
        return [starting_balance_usd] * len(close_prices)

    portfolio = Portfolio(cash_usd=starting_balance_usd)
    portfolio.buy(close_prices[0], (starting_balance_usd / close_prices[0]) * 0.999)
    return [portfolio.equity(price) for price in close_prices]


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Significance tests for a backtest result: does the signal beat coin flips with the "
            "same exposure and rhythm, and does its margin over buy & hold survive block "
            "resampling? Backtests only — no exchange account, no real trading."
        )
    )
    parser.add_argument("--exchange", default="kraken")
    parser.add_argument("--symbols", nargs="+", default=list(DEFAULT_SYMBOLS))
    parser.add_argument("--timeframe", default="1d")
    parser.add_argument("--days", type=int, default=730)
    parser.add_argument("--lookback", type=int, default=28)
    parser.add_argument("--starting-balance-usd", type=float, default=10000.0)
    parser.add_argument("--trials", type=int, default=200, help="Random-signal controls to run.")
    parser.add_argument("--bootstrap-trials", type=int, default=2000)
    parser.add_argument("--block-size", type=int, default=10, help="Bootstrap block length, in candles.")
    parser.add_argument("--target-volatility-pct", type=float, default=0.40)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    since_ms = int((time.time() - args.days * 86400) * 1000)
    price_series: dict[str, list[float]] = {}
    for symbol in args.symbols:
        config = Config(
            exchange_id=args.exchange,
            symbol=symbol,
            timeframe=args.timeframe,
            starting_balance_usd=args.starting_balance_usd,
            live_trading=False,
            api_key=None,
            api_secret=None,
        )
        try:
            candles = fetch_ohlcv(config, since_ms=since_ms)
        except Exception as error:  # noqa: BLE001 — one dead symbol shouldn't sink the run
            print(f"{symbol}: skipped ({type(error).__name__}: {error})")
            continue
        price_series[symbol] = [candle[4] for candle in candles]

    if not price_series:
        print("No symbols returned usable data — nothing to test.")
        return

    periods_per_year = {"1d": 365.0, "4h": 365.0 * 6, "1h": 365.0 * 24}.get(args.timeframe, 365.0)
    limits = RiskLimits(target_volatility_pct=args.target_volatility_pct, periods_per_year=periods_per_year)

    print(f"Momentum({args.lookback}) basket on {args.exchange}, {args.timeframe} candles")
    print(f"Symbols: {', '.join(sorted(price_series))}\n")

    _report_random_signal(args, price_series, limits)
    _report_block_bootstrap(args, price_series, limits)


def _report_random_signal(
    args: argparse.Namespace, price_series: Mapping[str, Sequence[float]], limits: RiskLimits
) -> None:
    result = random_signal_test_basket(
        price_series,
        lambda: TimeSeriesMomentumStrategy(lookback=args.lookback),
        starting_balance_usd=args.starting_balance_usd,
        min_history=args.lookback + 1,
        trials=args.trials,
        seed=args.seed,
        limits=limits,
    )
    print("--- Random-signal test: is the timing worth anything? ---")
    if result is None or result.p_value is None or result.rates is None:
        print("Not enough history to run it.\n")
        return

    rates = result.rates
    print(
        f"Control rhythm: long {rates.time_in_market:.0%} of candles, "
        f"entry rate {rates.p_enter:.1%}/candle, exit rate {rates.p_exit:.1%}/candle"
    )
    print(f"Momentum basket:              {result.actual_return_pct:>8.2f}%")
    for label, value in (("mean", result.mean_trial_return_pct), ("median", result.median_trial_return_pct)):
        if value is not None:
            print(f"{result.trials} random controls, {label:<6} {value:>8.2f}%")
    beaten = sum(1 for r in result.trial_returns_pct if r < result.actual_return_pct)
    print(f"Beat {beaten}/{result.trials} of them (p = {result.p_value:.3f})")
    print(
        verdict(
            result.p_value,
            survived="The signal beats coin flips of the same rhythm.",
            borderline=(
                "Suggestive but short of the 5% threshold: the signal is near the top of the "
                "control distribution without clearing it. More data, not more belief."
            ),
            failed="Coin flips with the same exposure do as well — no evidence the timing means anything.",
        )
        + "\n"
    )


def _report_block_bootstrap(
    args: argparse.Namespace, price_series: Mapping[str, Sequence[float]], limits: RiskLimits
) -> None:
    basket = run_basket_backtest(
        price_series,
        lambda: TimeSeriesMomentumStrategy(lookback=args.lookback),
        starting_balance_usd=args.starting_balance_usd,
        min_history=args.lookback + 1,
        limits=limits,
    )
    print("--- Block bootstrap: is the margin over buy & hold bigger than the noise? ---")
    if basket.metrics is None or not basket.equity_curve:
        print("Not enough history to run it.\n")
        return

    length = len(basket.equity_curve)
    benchmark = _basket_benchmark_curve(price_series, args.starting_balance_usd, length)
    result = block_bootstrap_test(
        step_returns(basket.equity_curve),
        step_returns(benchmark),
        block_size=args.block_size,
        trials=args.bootstrap_trials,
        seed=args.seed,
    )
    if result is None or result.p_value is None:
        print("Not enough history to run it.\n")
        return

    hold_pct = equal_weight_buy_and_hold_pct(price_series, args.starting_balance_usd)
    print(f"Momentum basket:              {basket.metrics.total_return_pct:>8.2f}%")
    if hold_pct is not None:
        print(f"Equal-weight buy & hold:      {hold_pct:>8.2f}%")
    print(
        f"Compounded edge over the period: {result.compounded_difference_pct:+.2f}% "
        f"({result.observed_mean_log_difference * 100:+.4f}% log growth per candle)"
    )
    print(f"{result.trials} resamples of {result.block_size}-candle blocks")
    vanished = sum(1 for m in result.resampled_means if m <= 0)
    print(f"Edge vanished in {vanished}/{result.trials} resamples (p = {result.p_value:.3f})")
    print(
        verdict(
            result.p_value,
            survived="The margin survives block resampling.",
            borderline="The margin nearly survives resampling, but not at the 5% threshold.",
            failed="The margin does not survive resampling — it is inside the range noise produces.",
        )
        + "\n"
    )


def _basket_benchmark_curve(
    price_series: Mapping[str, Sequence[float]], starting_balance_usd: float, length: int
) -> list[float]:
    """Equal-weight buy & hold as a curve, trimmed to the basket's own length
    so the two series pair candle for candle."""
    usable = {symbol: list(prices) for symbol, prices in price_series.items() if len(prices) >= 2}
    if not usable:
        return []

    per_sleeve = starting_balance_usd / len(usable)
    curves = [buy_and_hold_equity_curve(prices[-length:], per_sleeve) for prices in usable.values()]
    shortest = min(len(curve) for curve in curves)
    return [sum(curve[i] for curve in curves) for i in range(shortest)]


if __name__ == "__main__":
    main()
