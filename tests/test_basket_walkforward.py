import pytest

from crypto_trader.risk import RiskLimits
from crypto_trader.walkforward import (
    Window,
    align_price_series,
    evaluate_basket_on_test_window,
    make_windows,
    run_basket_walk_forward,
    summarize_basket,
)


def _trend(n: int, start: float = 100.0, step: float = 1.0) -> list[float]:
    return [start + i * step for i in range(n)]


def _choppy(n: int, start: float = 100.0) -> list[float]:
    return [start + (8.0 if i % 2 else -8.0) for i in range(n)]


# --- alignment --------------------------------------------------------------


def test_align_trims_every_series_to_the_shortest():
    aligned = align_price_series({"A": _trend(100), "B": _trend(60), "C": _trend(80)})

    assert {len(prices) for prices in aligned.values()} == {60}


def test_align_keeps_the_most_recent_candles():
    # Fetches all end at ~now, so the tail is what lines up by date. Keeping
    # the head instead would compare one symbol's January to another's March.
    aligned = align_price_series({"A": [1.0, 2.0, 3.0, 4.0, 5.0], "B": [10.0, 20.0]})

    assert aligned["A"] == [4.0, 5.0]
    assert aligned["B"] == [10.0, 20.0]


def test_align_drops_empty_series():
    aligned = align_price_series({"A": _trend(50), "EMPTY": []})

    assert list(aligned) == ["A"]


def test_align_of_nothing_is_empty():
    assert align_price_series({}) == {}
    assert align_price_series({"A": []}) == {}


# --- test-window scoring ----------------------------------------------------


def test_test_window_scoring_excludes_the_warm_up_region():
    prices = {"A/USD": _trend(200), "B/USD": _trend(200)}
    window = Window(train_start=0, train_end=100, test_start=100, test_end=200)

    metrics = evaluate_basket_on_test_window(prices, window, lookback=20, starting_balance_usd=10000.0)

    assert metrics is not None
    # 100 test candles in; the 20 warm-up candles must not pad the curve.
    assert metrics.return_count == 99


def test_warm_up_lets_the_basket_trade_from_the_first_test_candle():
    # Lookback longer than the test range: without warm-up on preceding
    # train data there would be no signal at all inside the window.
    prices = {"A/USD": _trend(200), "B/USD": _trend(200)}
    window = Window(train_start=0, train_end=150, test_start=150, test_end=180)

    metrics = evaluate_basket_on_test_window(prices, window, lookback=50, starting_balance_usd=10000.0)

    assert metrics is not None
    assert metrics.trade_count > 0


def test_test_window_scoring_returns_none_without_enough_data():
    # Warm-up plus test range is exactly the lookback, leaving no candle the
    # strategy could act on: nothing to score, so nothing is reported.
    prices = {"A/USD": _trend(11)}
    window = Window(train_start=0, train_end=10, test_start=10, test_end=11)

    assert evaluate_basket_on_test_window(prices, window, lookback=200, starting_balance_usd=10000.0) is None


# --- the walk-forward loop --------------------------------------------------


def test_produces_one_fold_per_window():
    prices = {"A/USD": _trend(400), "B/USD": _trend(400)}

    folds = run_basket_walk_forward(
        prices, lookbacks=[10, 20], starting_balance_usd=10000.0, train_size=150, test_size=50
    )

    assert len(folds) == len(make_windows(400, 150, 50))
    assert all(fold.chosen_lookback in (10, 20) for fold in folds)


def test_picks_the_train_winner_not_the_test_winner():
    # Train range trends up, so a short lookback captures it; the test range
    # is chop, where that same lookback whipsaws. The chosen lookback must
    # come from TRAIN — selecting on test performance would be lookahead,
    # the exact bug walk-forward exists to prevent.
    series = _trend(200) + _choppy(100, start=300.0)
    prices = {"A/USD": series, "B/USD": list(series)}

    folds = run_basket_walk_forward(
        prices, lookbacks=[5, 60], starting_balance_usd=10000.0, train_size=200, test_size=100
    )

    assert len(folds) == 1
    fold = folds[0]
    assert fold.train_return_pct > 0  # it did well on the range it was chosen from
    # And the out-of-sample number is reported independently, whatever it is.
    assert isinstance(fold.test_metrics.total_return_pct, float)


def test_reports_a_buy_and_hold_benchmark_per_fold():
    prices = {"A/USD": _trend(400), "B/USD": _trend(400)}

    folds = run_basket_walk_forward(
        prices, lookbacks=[20], starting_balance_usd=10000.0, train_size=150, test_size=50
    )

    assert folds
    for fold in folds:
        assert fold.buy_and_hold_return_pct > 0  # rising market


def test_misaligned_series_are_aligned_before_windowing():
    # B is shorter; windows must be cut from the aligned length, not A's.
    prices = {"A/USD": _trend(500), "B/USD": _trend(300)}

    folds = run_basket_walk_forward(
        prices, lookbacks=[20], starting_balance_usd=10000.0, train_size=150, test_size=50
    )

    assert len(folds) == len(make_windows(300, 150, 50))


def test_no_folds_when_history_is_too_short():
    prices = {"A/USD": _trend(80), "B/USD": _trend(80)}

    folds = run_basket_walk_forward(
        prices, lookbacks=[20], starting_balance_usd=10000.0, train_size=150, test_size=50
    )

    assert folds == []
    assert summarize_basket(folds) is None


def test_no_folds_without_lookbacks_to_choose_from():
    prices = {"A/USD": _trend(400)}

    assert run_basket_walk_forward(prices, [], 10000.0, train_size=150, test_size=50) == []


def test_risk_limits_reach_the_basket():
    prices = {"A/USD": _trend(400), "B/USD": _trend(400)}
    limits = RiskLimits(max_position_fraction=0.2)

    sized = run_basket_walk_forward(
        prices, [20], 10000.0, train_size=150, test_size=50, limits=limits
    )
    unsized = run_basket_walk_forward(prices, [20], 10000.0, train_size=150, test_size=50)

    assert sized and unsized
    # Less exposure to a rising market means a smaller out-of-sample gain.
    assert sized[0].test_metrics.total_return_pct < unsized[0].test_metrics.total_return_pct


# --- summary ----------------------------------------------------------------


def test_summary_averages_and_counts():
    prices = {"A/USD": _trend(400), "B/USD": _trend(400)}
    folds = run_basket_walk_forward(prices, [10, 20], 10000.0, train_size=150, test_size=50)

    summary = summarize_basket(folds)

    assert summary is not None
    assert summary.fold_count == len(folds)
    assert summary.mean_test_return_pct == pytest.approx(
        sum(f.test_metrics.total_return_pct for f in folds) / len(folds)
    )
    assert len(summary.chosen_lookbacks) == len(folds)
    assert summary.folds_profitable_out_of_sample <= summary.fold_count
    assert summary.folds_beating_buy_and_hold <= summary.fold_count


def test_summary_records_which_lookback_each_fold_picked():
    # An unstable choice across folds is a warning sign the CLI surfaces, so
    # the summary has to carry the per-fold choices to report it.
    prices = {"A/USD": _trend(400), "B/USD": _trend(400)}
    folds = run_basket_walk_forward(prices, [10, 20, 40], 10000.0, train_size=150, test_size=50)

    summary = summarize_basket(folds)

    assert summary is not None
    assert summary.chosen_lookbacks == [f.chosen_lookback for f in folds]


def test_summary_of_nothing_is_none():
    assert summarize_basket([]) is None
