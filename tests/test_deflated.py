import pytest

from crypto_trader.deflated import deflated_sharpe_ratio, expected_max_sharpe


def test_expected_max_sharpe_needs_at_least_two_trials():
    assert expected_max_sharpe([]) == 0.0
    assert expected_max_sharpe([0.5]) == 0.0


def test_expected_max_sharpe_is_zero_when_every_trial_scored_the_same():
    # No spread means no luck to correct for.
    assert expected_max_sharpe([0.4] * 20) == 0.0


def test_expected_max_sharpe_rises_with_the_number_of_trials():
    # The core property: the more configurations you try, the higher a
    # Sharpe a no-skill search is expected to turn up, so the higher the bar
    # a real result must clear.
    few = expected_max_sharpe([0.0, 0.1, -0.1, 0.05] * 3)
    many = expected_max_sharpe([0.0, 0.1, -0.1, 0.05] * 50)

    assert many > few


def test_expected_max_sharpe_rises_with_the_spread_of_trials():
    tight = expected_max_sharpe([0.00, 0.01, -0.01, 0.005] * 10)
    wide = expected_max_sharpe([0.0, 0.5, -0.5, 0.25] * 10)

    assert wide > tight


def test_returns_none_without_enough_to_compute():
    assert deflated_sharpe_ratio(0.5, [0.1, 0.2], return_count=1) is None
    assert deflated_sharpe_ratio(0.5, [0.1], return_count=500) is None
    assert deflated_sharpe_ratio(0.5, [], return_count=500) is None


def test_a_standout_result_from_a_small_search_survives():
    # One clearly strong result among a handful of mediocre ones, over a
    # long history: the search doesn't explain it.
    trials = [0.02, -0.01, 0.03, 0.00, 0.01, 0.40]

    deflated = deflated_sharpe_ratio(0.40, trials, return_count=2000)

    assert deflated is not None
    assert deflated.probability > 0.95
    assert deflated.trials == 6


def test_the_same_result_stops_surviving_once_the_search_is_large_enough():
    # Identical winning Sharpe, identical history length — only the number
    # of things tried changes. This is the whole point of the correction.
    small_search = [0.02, -0.01, 0.03, 0.00, 0.01, 0.20]
    large_search = [0.20] + [0.02, -0.06, 0.08, -0.04, 0.05, -0.07] * 200

    from_small = deflated_sharpe_ratio(0.20, small_search, return_count=500)
    from_large = deflated_sharpe_ratio(0.20, large_search, return_count=500)

    assert from_small is not None and from_large is not None
    assert from_large.benchmark_sharpe > from_small.benchmark_sharpe
    assert from_large.probability < from_small.probability


def test_a_winner_drawn_from_wide_scatter_does_not_survive():
    # The real selection-bias case: results all over the map, and the
    # "winner" only just tops them. That scatter is the noise level, and a
    # winner inside it is explained by the search.
    trials = [0.30, -0.28, 0.22, -0.31, 0.19, -0.25, 0.27, -0.20, 0.33]

    deflated = deflated_sharpe_ratio(0.33, trials, return_count=200)

    assert deflated is not None
    assert deflated.probability < 0.95


def test_tightly_clustered_positive_trials_are_not_penalised():
    # Counterpart to the above, and worth pinning down: when every
    # configuration agrees on a modest positive Sharpe, there is little
    # scatter for luck to hide in, so the correction should NOT reject it.
    # Deflation punishes selection from noise, not consistency.
    trials = [0.09, 0.10, 0.11, 0.10, 0.09, 0.12, 0.10, 0.11]

    deflated = deflated_sharpe_ratio(0.12, trials, return_count=500)

    assert deflated is not None
    assert deflated.benchmark_sharpe < 0.05  # barely any bar to clear
    assert deflated.probability > 0.95


def test_fat_tails_and_negative_skew_lower_the_verdict():
    # Same Sharpe, same trials, same history — but returns that are
    # left-skewed and fat-tailed are less trustworthy than normal ones, and
    # the correction should say so.
    trials = [0.02, -0.01, 0.03, 0.00, 0.01, 0.25]

    normal_shaped = deflated_sharpe_ratio(0.25, trials, return_count=800, skewness=0.0, kurtosis=3.0)
    ugly_shaped = deflated_sharpe_ratio(0.25, trials, return_count=800, skewness=-1.5, kurtosis=12.0)

    assert normal_shaped is not None and ugly_shaped is not None
    assert ugly_shaped.probability < normal_shaped.probability


def test_longer_history_raises_confidence_in_the_same_sharpe():
    trials = [0.02, -0.01, 0.03, 0.00, 0.01, 0.15]

    short = deflated_sharpe_ratio(0.15, trials, return_count=50)
    long = deflated_sharpe_ratio(0.15, trials, return_count=5000)

    assert short is not None and long is not None
    assert long.probability > short.probability


def test_a_winner_below_the_no_skill_benchmark_scores_under_half():
    # If the best result is worse than what luck alone would be expected to
    # produce, the probability must fall below even odds.
    trials = [0.0, 0.5, -0.5, 0.45, -0.45, 0.3]

    deflated = deflated_sharpe_ratio(0.05, trials, return_count=500)

    assert deflated is not None
    assert deflated.observed_sharpe < deflated.benchmark_sharpe
    assert deflated.probability < 0.5


def test_probability_stays_a_probability():
    trials = [0.0, 0.1, -0.1, 0.05, 0.2, 0.9]
    for count in (10, 100, 10_000):
        deflated = deflated_sharpe_ratio(0.9, trials, return_count=count)
        assert deflated is not None
        assert 0.0 <= deflated.probability <= 1.0


def test_degenerate_variance_returns_none():
    # A large negative skew with a large Sharpe can drive the variance term
    # non-positive; that's unknown, not a pass.
    assert deflated_sharpe_ratio(3.0, [0.1, 0.2, 3.0], return_count=500, skewness=20.0, kurtosis=1.0) is None


def test_deflate_best_integrates_with_optimizer_results(uptrend_then_downtrend):
    from crypto_trader.optimize import default_candidates, deflate_best, evaluate_candidates

    results = evaluate_candidates(uptrend_then_downtrend, default_candidates(), starting_balance_usd=10000.0)
    deflated = deflate_best(results)

    assert deflated is not None
    assert deflated.trials > 1
    assert 0.0 <= deflated.probability <= 1.0


def test_deflate_best_returns_none_for_a_single_candidate(uptrend_then_downtrend):
    from crypto_trader.optimize import deflate_best, evaluate_candidates, make_candidate

    only = [c for c in [make_candidate("sma", {"fast": 5, "slow": 15})] if c is not None]
    results = evaluate_candidates(uptrend_then_downtrend, only, starting_balance_usd=10000.0)

    assert deflate_best(results) is None


def test_metrics_expose_the_distribution_shape(uptrend_then_downtrend):
    from crypto_trader.engine import run_backtest
    from crypto_trader.metrics import compute_metrics
    from crypto_trader.portfolio import Portfolio
    from crypto_trader.strategy import SmaCrossoverStrategy

    portfolio = Portfolio(cash_usd=10000.0)
    result = run_backtest(uptrend_then_downtrend, SmaCrossoverStrategy(5, 15), portfolio, min_history=15)

    metrics = compute_metrics(result, starting_balance_usd=10000.0)

    assert metrics.return_count == len(uptrend_then_downtrend) - 1
    assert metrics.skewness is not None
    assert metrics.kurtosis is not None


def test_kurtosis_of_a_flat_curve_is_undefined(flat_prices):
    from crypto_trader.engine import run_backtest
    from crypto_trader.metrics import compute_metrics
    from crypto_trader.portfolio import Portfolio
    from crypto_trader.strategy import SmaCrossoverStrategy

    portfolio = Portfolio(cash_usd=10000.0)
    result = run_backtest(flat_prices, SmaCrossoverStrategy(5, 15), portfolio, min_history=15)

    metrics = compute_metrics(result, starting_balance_usd=10000.0)

    assert metrics.skewness is None  # zero variance: no shape to report
    assert metrics.kurtosis is None


def test_deflate_best_needs_two_scorable_candidates():
    from crypto_trader.metrics import PerformanceMetrics
    from crypto_trader.optimize import CandidateResult, deflate_best

    def unscorable(name: str) -> CandidateResult:
        return CandidateResult(
            name=name,
            metrics=PerformanceMetrics(
                total_return_pct=0.0,
                max_drawdown_pct=0.0,
                win_rate=None,
                trade_count=0,
                sharpe_ratio=None,  # flat curve — nothing to score
            ),
            final_equity=10000.0,
        )

    assert deflate_best([unscorable("a"), unscorable("b")]) is None


@pytest.mark.parametrize("trials", [2, 10, 100, 1000])
def test_benchmark_is_finite_and_positive_across_search_sizes(trials):
    sharpes = [0.1 * ((i % 7) - 3) for i in range(trials)]
    benchmark = expected_max_sharpe(sharpes)

    assert benchmark > 0
    assert benchmark == pytest.approx(benchmark)  # not NaN
