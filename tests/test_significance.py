import math
import statistics

import pytest

from crypto_trader.engine import run_backtest
from crypto_trader.portfolio import Portfolio
from crypto_trader.significance import (
    BlockBootstrapResult,
    RandomSignalResult,
    block_bootstrap_test,
    buy_and_hold_equity_curve,
    pooled_transition_rates,
    random_signal_test,
    random_signal_test_basket,
    transition_rates,
    verdict,
)
from crypto_trader.strategy import RandomSignalStrategy, Signal, TimeSeriesMomentumStrategy


def _rising(n: int = 200, start: float = 100.0, step: float = 1.0) -> list[float]:
    return [start + i * step for i in range(n)]


def _sawtooth(n: int = 200, start: float = 100.0) -> list[float]:
    """Alternating up/down legs — a strategy is in and out repeatedly."""
    return [start + (10.0 if (i // 10) % 2 else 0.0) + (i % 10) for i in range(n)]


def _square_wave(cycles: int = 6, leg: int = 30, start: float = 100.0) -> list[float]:
    """Sustained 2%-a-candle rises alternating with equal falls — a series
    where being in or out at the right time is worth a great deal."""
    prices, price = [], start
    for cycle in range(cycles):
        for _ in range(leg):
            price *= 1.02 if cycle % 2 == 0 else 0.98
            prices.append(price)
    return prices


# --- the null-hypothesis strategy -------------------------------------------


def test_random_strategy_rejects_impossible_probabilities():
    with pytest.raises(ValueError):
        RandomSignalStrategy(p_enter=1.5, p_exit=0.1)
    with pytest.raises(ValueError):
        RandomSignalStrategy(p_enter=0.1, p_exit=-0.2)


def test_random_strategy_ignores_price_entirely():
    # The same seed on wildly different price histories must produce the same
    # signals. If prices leaked in, it wouldn't be a null hypothesis.
    rising = RandomSignalStrategy(0.3, 0.3, seed=7)
    falling = RandomSignalStrategy(0.3, 0.3, seed=7)

    from_rising = [rising.next_signal(_rising(i)) for i in range(1, 60)]
    from_falling = [falling.next_signal([1000.0 - j for j in range(i)]) for i in range(1, 60)]

    assert from_rising == from_falling


def test_random_strategy_always_stays_in_when_it_never_exits():
    strategy = RandomSignalStrategy(p_enter=1.0, p_exit=0.0, seed=1)
    signals = [strategy.next_signal(_rising(i + 1)) for i in range(50)]

    assert signals == [Signal.BUY] * 50


def test_random_strategy_never_enters_when_entry_is_impossible():
    strategy = RandomSignalStrategy(p_enter=0.0, p_exit=1.0, seed=1)
    signals = [strategy.next_signal(_rising(i + 1)) for i in range(50)]

    assert signals == [Signal.SELL] * 50


def test_random_strategy_reset_replays_the_same_flips():
    strategy = RandomSignalStrategy(0.4, 0.4, seed=3)
    first = [strategy.next_signal(_rising(i + 1)) for i in range(40)]
    strategy.reset()
    second = [strategy.next_signal(_rising(i + 1)) for i in range(40)]

    assert first == second


def test_different_seeds_give_different_paths():
    a = RandomSignalStrategy(0.4, 0.4, seed=1)
    b = RandomSignalStrategy(0.4, 0.4, seed=2)

    assert [a.next_signal([1.0]) for _ in range(40)] != [b.next_signal([1.0]) for _ in range(40)]


# --- transition rates -------------------------------------------------------


def test_transition_rates_measures_entries_and_exits():
    # flat, flat, long, long, flat -> one entry out of 2 flat candles that
    # had a successor, one exit out of 2 long ones.
    rates = transition_rates([False, False, True, True, False])

    assert rates is not None
    assert rates.p_enter == pytest.approx(0.5)
    assert rates.p_exit == pytest.approx(0.5)
    assert rates.time_in_market == pytest.approx(0.4)
    assert rates.candles == 5


def test_transition_rates_of_a_permanent_position():
    rates = transition_rates([True] * 10)

    assert rates is not None
    assert rates.p_exit == 0.0
    assert rates.time_in_market == pytest.approx(1.0)
    # Never flat, so no entry rate was ever observed — reported as 0, not
    # invented.
    assert rates.p_enter == 0.0


def test_transition_rates_needs_a_transition_to_measure():
    assert transition_rates([]) is None
    assert transition_rates([True]) is None


def test_pooled_rates_weight_by_series_length():
    # A long always-in series and a short never-in one: pooled exposure has
    # to lean toward the longer one, not average 50/50.
    pooled = pooled_transition_rates([[True] * 90, [False] * 10])

    assert pooled is not None
    assert pooled.time_in_market == pytest.approx(0.9)
    assert pooled.candles == 100


def test_pooled_rates_of_nothing_is_none():
    assert pooled_transition_rates([]) is None
    assert pooled_transition_rates([[True], []]) is None


# --- the engine records what the strategy did -------------------------------


def test_backtest_records_a_position_for_every_candle():
    prices = _rising(60)
    result = run_backtest(prices, TimeSeriesMomentumStrategy(lookback=10), Portfolio(cash_usd=10000.0), 11)

    assert len(result.positions) == len(result.equity_curve) == len(prices)


def test_recorded_positions_match_what_the_strategy_did():
    # Rising the whole way: momentum goes long once warmed up and stays there.
    result = run_backtest(_rising(60), TimeSeriesMomentumStrategy(lookback=10), Portfolio(cash_usd=10000.0), 11)

    assert not any(result.positions[:10])  # flat through warm-up
    assert all(result.positions[11:])  # long afterwards


# --- random-signal test -----------------------------------------------------


def test_random_signal_test_reports_the_real_result_and_a_distribution():
    result = random_signal_test(
        _sawtooth(200), TimeSeriesMomentumStrategy(lookback=10), 10000.0, min_history=11, trials=25, seed=0
    )

    assert result is not None
    assert result.trials == 25
    assert result.rates is not None
    assert result.p_value is not None and 0 < result.p_value <= 1


def test_random_signal_test_is_reproducible():
    def run():
        return random_signal_test(
            _sawtooth(200), TimeSeriesMomentumStrategy(lookback=10), 10000.0, min_history=11, trials=20, seed=42
        )

    first, second = run(), run()

    assert first is not None and second is not None
    assert first.trial_returns_pct == second.trial_returns_pct


def test_informative_timing_beats_the_controls():
    # Alternating 2%-a-candle rises and falls: when to be out is the whole
    # game, and momentum catches most of each leg. Controls with the same
    # exposure and rhythm but random timing get chopped up.
    result = random_signal_test(
        _square_wave(), TimeSeriesMomentumStrategy(lookback=10), 10000.0, min_history=11, trials=200, seed=0
    )

    assert result is not None
    assert result.mean_trial_return_pct is not None
    assert result.actual_return_pct > 100 > result.mean_trial_return_pct
    assert result.survives


def test_a_big_return_with_nothing_to_time_does_not_survive():
    # This is the case the whole test exists for. On a monotonic rise
    # momentum returns +171%, which looks superb — but it never exits, so
    # its controls never exit either, and they are simply "buy on a random
    # early candle and hold". They score nearly the same. The return is real
    # and the timing contributed almost nothing to it; only a control that
    # matches the strategy's rhythm can tell those apart.
    result = random_signal_test(
        _rising(200), TimeSeriesMomentumStrategy(lookback=10), 10000.0, min_history=11, trials=200, seed=0
    )

    assert result is not None
    assert result.actual_return_pct > 150  # a headline number that looks great
    assert result.rates is not None and result.rates.p_exit == 0.0  # it never sells
    assert not result.survives  # and it is indistinguishable from a coin flip


def test_p_value_is_never_zero():
    # Even a clean sweep reports 1/(N+1), not 0: 50 trials cannot establish
    # that something happens less than never.
    result = RandomSignalResult(actual_return_pct=100.0, trial_returns_pct=[1.0] * 50)

    assert result.p_value == pytest.approx(1 / 51)
    assert result.survives


def test_a_result_inside_the_control_distribution_does_not_survive():
    result = RandomSignalResult(actual_return_pct=5.0, trial_returns_pct=[float(i) for i in range(20)])

    assert result.p_value is not None and result.p_value > 0.05
    assert not result.survives


def test_random_signal_test_without_enough_history_is_none():
    assert random_signal_test([100.0], TimeSeriesMomentumStrategy(lookback=5), 10000.0, 6, trials=5) is None


def test_random_signal_test_on_the_basket():
    prices = {"A/USD": _sawtooth(200), "B/USD": _sawtooth(200, start=50.0)}

    result = random_signal_test_basket(
        prices, lambda: TimeSeriesMomentumStrategy(lookback=10), 10000.0, min_history=11, trials=10, seed=0
    )

    assert result is not None
    assert result.trials == 10
    assert result.rates is not None


def test_basket_sleeves_get_independent_controls():
    # Identical price series in both sleeves: if the two sleeves shared one
    # seed they'd trade in lockstep and every trial's sleeves would match.
    # Distinct trial outcomes are the evidence they don't.
    prices = {"A/USD": _sawtooth(200), "B/USD": _sawtooth(200)}

    result = random_signal_test_basket(
        prices, lambda: TimeSeriesMomentumStrategy(lookback=10), 10000.0, min_history=11, trials=15, seed=0
    )

    assert result is not None
    assert len(set(result.trial_returns_pct)) > 1


def test_basket_random_signal_test_with_no_usable_symbols_is_none():
    assert (
        random_signal_test_basket(
            {"A/USD": [1.0, 2.0]}, lambda: TimeSeriesMomentumStrategy(lookback=50), 10000.0, min_history=51
        )
        is None
    )


# --- block bootstrap --------------------------------------------------------


def test_bootstrap_rejects_a_non_positive_block_size():
    with pytest.raises(ValueError):
        block_bootstrap_test([0.1, 0.2], [0.0, 0.0], block_size=0)


def test_a_consistent_edge_survives_resampling():
    # The strategy beats the benchmark on every single candle, so no
    # reshuffling of blocks can make the advantage disappear.
    strategy = [0.01] * 100
    benchmark = [0.0] * 100

    result = block_bootstrap_test(strategy, benchmark, block_size=10, trials=200, seed=0)

    assert result is not None
    assert result.observed_mean_log_difference == pytest.approx(math.log1p(0.01))
    assert result.compounded_difference_pct > 0
    assert result.p_value == pytest.approx(1 / 201)
    assert result.survives


def test_an_edge_resting_on_one_lucky_stretch_does_not_survive():
    # Flat against the benchmark everywhere except one big winning block.
    # The mean difference is positive, but most resamples miss that block.
    strategy = [0.0] * 95 + [0.5] * 5
    benchmark = [0.0] * 100

    result = block_bootstrap_test(strategy, benchmark, block_size=10, trials=300, seed=0)

    assert result is not None
    assert result.observed_mean_log_difference > 0
    assert not result.survives


def test_bootstrap_is_reproducible():
    strategy = [0.01, -0.02, 0.03] * 40
    benchmark = [0.0, 0.01, -0.01] * 40

    first = block_bootstrap_test(strategy, benchmark, block_size=8, trials=100, seed=5)
    second = block_bootstrap_test(strategy, benchmark, block_size=8, trials=100, seed=5)

    assert first is not None and second is not None
    assert first.resampled_means == second.resampled_means


def test_bootstrap_pairs_the_two_series_candle_for_candle():
    # Unequal lengths are truncated to the shorter, not zipped past the end.
    result = block_bootstrap_test([0.01] * 100, [0.0] * 40, block_size=5, trials=50, seed=0)

    assert result is not None
    assert result.observed_mean_log_difference == pytest.approx(math.log1p(0.01))
    assert result.return_count == 40


def test_bootstrap_needs_more_candles_than_a_block():
    assert block_bootstrap_test([0.01] * 5, [0.0] * 5, block_size=10, trials=10) is None
    assert block_bootstrap_test([], [], block_size=1, trials=10) is None


def test_bootstrap_p_value_is_never_zero():
    result = BlockBootstrapResult(observed_mean_log_difference=1.0, return_count=100, resampled_means=[1.0] * 100)

    assert result.p_value == pytest.approx(1 / 101)


# --- benchmark curve --------------------------------------------------------


def test_buy_and_hold_curve_tracks_the_price_after_one_entry_fee():
    curve = buy_and_hold_equity_curve([100.0, 110.0, 120.0], 10000.0)

    assert len(curve) == 3
    assert curve[0] == pytest.approx(10000.0 * 0.999, rel=1e-3)
    assert curve[-1] > curve[0]  # price rose


def test_buy_and_hold_curve_of_too_little_data():
    assert buy_and_hold_equity_curve([], 10000.0) == []
    assert buy_and_hold_equity_curve([100.0], 10000.0) == [10000.0]


def test_the_bootstrap_credits_winning_by_being_less_volatile():
    # The exact case that made log growth the right measure. The benchmark
    # earns MORE on the average candle (+1.0% vs +0.5%) but swings wildly,
    # and volatility drag means it ends BEHIND. An arithmetic-difference test
    # would call the steady series a loser; compounding is what pays out, so
    # the log-growth test correctly finds it ahead.
    steady = [0.005] * 120
    swingy = [0.30 if i % 2 else -0.28 for i in range(120)]

    assert statistics.fmean(swingy) > statistics.fmean(steady)  # higher average...
    assert math.prod(1 + r for r in steady) > math.prod(1 + r for r in swingy)  # ...lower finish

    result = block_bootstrap_test(steady, swingy, block_size=10, trials=300, seed=0)

    assert result is not None
    assert result.observed_mean_log_difference > 0
    assert result.compounded_difference_pct > 0
    assert result.survives


# --- verdict bands ----------------------------------------------------------


def test_verdict_distinguishes_borderline_from_hopeless():
    bands = {"survived": "yes", "borderline": "maybe", "failed": "no"}

    assert verdict(0.01, **bands) == "yes"
    assert verdict(0.068, **bands) == "maybe"  # the basket's actual result
    assert verdict(0.398, **bands) == "no"


def test_verdict_boundaries_are_exclusive():
    bands = {"survived": "yes", "borderline": "maybe", "failed": "no"}

    assert verdict(0.05, **bands) == "maybe"  # 0.05 itself does not survive
    assert verdict(0.15, **bands) == "no"
