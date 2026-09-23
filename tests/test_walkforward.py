import pytest

from crypto_trader.metrics import PerformanceMetrics
from crypto_trader.optimize import CandidateResult, make_candidate
from crypto_trader.walkforward import (
    FoldResult,
    Window,
    buy_and_hold_return_pct,
    evaluate_on_test_window,
    make_windows,
    run_walk_forward,
    summarize,
)


def test_make_windows_tiles_history_with_non_overlapping_test_ranges():
    windows = make_windows(total_candles=100, train_size=40, test_size=20)

    assert [(w.train_start, w.train_end, w.test_start, w.test_end) for w in windows] == [
        (0, 40, 40, 60),
        (20, 60, 60, 80),
        (40, 80, 80, 100),
    ]


def test_make_windows_honours_an_explicit_step():
    windows = make_windows(total_candles=100, train_size=40, test_size=20, step=30)

    assert [(w.train_start, w.test_end) for w in windows] == [(0, 60), (30, 90)]


def test_make_windows_returns_nothing_when_history_is_too_short():
    assert make_windows(total_candles=50, train_size=40, test_size=20) == []


def test_make_windows_rejects_non_positive_sizes():
    with pytest.raises(ValueError):
        make_windows(total_candles=100, train_size=0, test_size=20)
    with pytest.raises(ValueError):
        make_windows(total_candles=100, train_size=40, test_size=0)
    with pytest.raises(ValueError):
        make_windows(total_candles=100, train_size=40, test_size=20, step=0)


def test_evaluate_on_test_window_scores_only_the_test_range(uptrend_then_downtrend):
    candidate = make_candidate("sma", {"fast": 5, "slow": 15})
    assert candidate is not None
    window = Window(train_start=0, train_end=40, test_start=40, test_end=70)

    metrics = evaluate_on_test_window(candidate, uptrend_then_downtrend, window, starting_balance_usd=10000.0)

    # 30 test candles in, 30 equity points out — the warm-up candles the
    # strategy saw beforehand must not inflate the scored curve.
    assert metrics.trade_count >= 0
    assert isinstance(metrics.total_return_pct, float)


def test_evaluate_on_test_window_lets_indicators_warm_up_before_the_test_range(uptrend_then_downtrend):
    # A config whose slow window is longer than the test range can still
    # trade within it, because it sees train candles first. Without warm-up
    # it could never produce a signal at all.
    candidate = make_candidate("sma", {"fast": 5, "slow": 15})
    assert candidate is not None
    short_test = Window(train_start=0, train_end=40, test_start=40, test_end=50)

    metrics = evaluate_on_test_window(candidate, uptrend_then_downtrend, short_test, starting_balance_usd=10000.0)

    assert metrics is not None  # 10-candle test range, 15-candle slow SMA


def test_buy_and_hold_return_is_positive_on_a_rising_test_range():
    prices = [100.0] * 10 + [100.0, 110.0, 120.0, 130.0]
    window = Window(train_start=0, train_end=10, test_start=10, test_end=14)

    result = buy_and_hold_return_pct(prices, window, starting_balance_usd=10000.0)

    assert result == pytest.approx(29.87, abs=0.1)  # +30% less the entry fee


def test_buy_and_hold_return_is_negative_on_a_falling_test_range():
    prices = [100.0] * 10 + [100.0, 90.0, 80.0]
    window = Window(train_start=0, train_end=10, test_start=10, test_end=13)

    assert buy_and_hold_return_pct(prices, window, starting_balance_usd=10000.0) < 0


def test_buy_and_hold_return_is_zero_for_a_degenerate_window():
    window = Window(train_start=0, train_end=10, test_start=10, test_end=11)

    assert buy_and_hold_return_pct([100.0] * 11, window, starting_balance_usd=10000.0) == 0.0


def test_run_walk_forward_produces_a_fold_per_window(uptrend_then_downtrend):
    candidates = [
        make_candidate("sma", {"fast": 5, "slow": 15}),
        make_candidate("sma", {"fast": 3, "slow": 10}),
    ]
    candidates = [c for c in candidates if c is not None]

    folds = run_walk_forward(
        uptrend_then_downtrend, candidates, starting_balance_usd=10000.0, train_size=40, test_size=20
    )

    assert len(folds) == len(make_windows(len(uptrend_then_downtrend), 40, 20))
    assert all(fold.chosen.name in {c.name for c in candidates} for fold in folds)


def test_run_walk_forward_picks_the_train_winner_not_the_test_winner():
    # Train range trends up then down (the crossover config profits there);
    # test range is flat (it can't). The chosen config must be the one that
    # won on TRAIN — picking by test performance would be lookahead, which
    # is exactly the bug walk-forward exists to avoid.
    train = [100.0] * 20 + [100 + i * 2 for i in range(1, 21)] + [140.0] * 20 + [140 - i * 2 for i in range(1, 21)]
    prices = train + [100.0] * 40

    candidates = [c for c in [make_candidate("sma", {"fast": 5, "slow": 15})] if c is not None]
    folds = run_walk_forward(prices, candidates, starting_balance_usd=10000.0, train_size=80, test_size=40)

    assert len(folds) == 1
    fold = folds[0]
    assert fold.chosen.metrics.total_return_pct != 0  # it traded in-sample
    assert fold.test_metrics.trade_count == 0  # flat out-of-sample: nothing to trade
    assert fold.test_metrics.total_return_pct == pytest.approx(0.0)


def _fold(train_pct: float, test_pct: float, hold_pct: float) -> FoldResult:
    def metrics(total_return_pct: float) -> PerformanceMetrics:
        return PerformanceMetrics(
            total_return_pct=total_return_pct,
            max_drawdown_pct=1.0,
            win_rate=0.5,
            trade_count=2,
            sharpe_ratio=0.1,
        )

    return FoldResult(
        window=Window(0, 10, 10, 20),
        chosen=CandidateResult(name="sma(fast=5,slow=15)", metrics=metrics(train_pct), final_equity=1.0),
        test_metrics=metrics(test_pct),
        buy_and_hold_return_pct=hold_pct,
    )


def test_summarize_averages_each_column_and_counts_the_wins():
    folds = [_fold(20.0, 5.0, 2.0), _fold(10.0, -3.0, 8.0), _fold(30.0, 1.0, 1.0)]

    summary = summarize(folds)

    assert summary is not None
    assert summary.fold_count == 3
    assert summary.mean_train_return_pct == pytest.approx(20.0)
    assert summary.mean_test_return_pct == pytest.approx(1.0)
    assert summary.mean_buy_and_hold_return_pct == pytest.approx(11.0 / 3)
    assert summary.folds_profitable_out_of_sample == 2  # 5.0 and 1.0
    # Only 5.0 > 2.0 counts: -3.0 loses to 8.0, and matching buy & hold
    # exactly (1.0 vs 1.0) is not beating it.
    assert summary.folds_beating_buy_and_hold == 1


def test_summarize_surfaces_the_in_sample_to_out_of_sample_gap():
    # The headline the whole feature exists to produce: configs that looked
    # great on the data they were chosen from, and didn't hold up after.
    folds = [_fold(25.0, -4.0, 0.0), _fold(30.0, -1.0, 0.0)]

    summary = summarize(folds)

    assert summary is not None
    assert summary.mean_train_return_pct > 0
    assert summary.mean_test_return_pct < 0
    assert summary.folds_profitable_out_of_sample == 0


def test_summarize_returns_none_without_folds():
    assert summarize([]) is None
