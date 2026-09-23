from crypto_trader.leaderboard import LeaderboardEntry
from crypto_trader.metrics import PerformanceMetrics
from crypto_trader.optimize import (
    Candidate,
    dedupe_candidates,
    default_candidates,
    evaluate_candidates,
    make_candidate,
    neighbors,
    rank_by_total_return,
    refine_from_leaderboard,
)
from crypto_trader.strategy import RsiReversionStrategy, SmaCrossoverStrategy


def test_default_candidates_only_include_valid_sma_pairs():
    candidates = default_candidates(fast_windows=(10, 20), slow_windows=(20, 30), rsi_periods=())
    names = {c.name for c in candidates}

    assert "sma(fast=10,slow=20)" in names
    assert "sma(fast=20,slow=30)" in names
    assert "sma(fast=20,slow=20)" not in names  # fast must be strictly smaller than slow


def test_default_candidates_includes_rsi_configurations():
    candidates = default_candidates(
        fast_windows=(), slow_windows=(), rsi_periods=(14,), rsi_oversold=(30.0,), rsi_overbought=(70.0,)
    )

    assert [c.name for c in candidates] == ["rsi(period=14,oversold=30,overbought=70)"]


def test_evaluate_candidates_runs_an_independent_backtest_per_candidate(uptrend_then_downtrend):
    candidates = [
        Candidate(name="active", make_strategy=lambda: SmaCrossoverStrategy(5, 15), min_history=15),
        Candidate(name="idle", make_strategy=lambda: SmaCrossoverStrategy(40, 45), min_history=45),
    ]

    results = evaluate_candidates(uptrend_then_downtrend, candidates, starting_balance_usd=10000.0)

    assert {r.name for r in results} == {"active", "idle"}
    active = next(r for r in results if r.name == "active")
    idle = next(r for r in results if r.name == "idle")
    assert active.metrics.trade_count == 2
    assert idle.metrics.trade_count == 0
    assert idle.final_equity == 10000.0  # never traded, so equity never moved


def test_rank_by_total_return_sorts_best_first(uptrend_then_downtrend):
    candidates = [
        Candidate(name="active", make_strategy=lambda: SmaCrossoverStrategy(5, 15), min_history=15),
        Candidate(name="idle", make_strategy=lambda: SmaCrossoverStrategy(40, 45), min_history=45),
    ]
    results = evaluate_candidates(uptrend_then_downtrend, candidates, starting_balance_usd=10000.0)

    ranked = rank_by_total_return(results)

    assert ranked[0].metrics.total_return_pct >= ranked[-1].metrics.total_return_pct
    returns = [r.metrics.total_return_pct for r in ranked]
    assert returns == sorted(returns, reverse=True)


def test_make_candidate_rejects_parameters_the_strategy_would_refuse():
    assert make_candidate("sma", {"fast": 20, "slow": 10}) is None  # fast must be < slow
    assert make_candidate("sma", {"fast": 0, "slow": 10}) is None
    assert make_candidate("rsi", {"period": 0, "oversold": 30, "overbought": 70}) is None
    assert make_candidate("rsi", {"period": 14, "oversold": 80, "overbought": 20}) is None
    assert make_candidate("unknown-family", {}) is None


def test_make_candidate_builds_a_working_strategy_factory():
    sma = make_candidate("sma", {"fast": 5, "slow": 20})
    rsi = make_candidate("rsi", {"period": 14, "oversold": 30, "overbought": 70})

    assert sma is not None and rsi is not None
    assert isinstance(sma.make_strategy(), SmaCrossoverStrategy)
    assert isinstance(rsi.make_strategy(), RsiReversionStrategy)
    assert sma.min_history == 20
    assert rsi.min_history == 15


def test_neighbors_vary_one_parameter_at_a_time_and_drop_invalid_ones():
    varied = neighbors("sma", {"fast": 10, "slow": 30})
    names = {c.name for c in varied}

    assert "sma(fast=5,slow=30)" in names  # fast stepped down
    assert "sma(fast=10,slow=35)" in names  # slow stepped up
    assert all(c.params["fast"] < c.params["slow"] for c in varied)


def test_neighbors_of_a_tight_sma_pair_drop_the_invalid_variations():
    # fast=18/slow=20: stepping fast up by 5 would cross slow, so that
    # variation must be dropped rather than blowing up.
    varied = neighbors("sma", {"fast": 18, "slow": 20})

    assert "sma(fast=23,slow=20)" not in {c.name for c in varied}
    assert all(c.params["fast"] < c.params["slow"] for c in varied)


def test_neighbors_of_rsi_stay_inside_valid_thresholds():
    varied = neighbors("rsi", {"period": 14, "oversold": 30, "overbought": 70})

    assert varied  # produced something
    for candidate in varied:
        assert 0 < candidate.params["oversold"] < candidate.params["overbought"] < 100
        assert candidate.params["period"] > 0


def test_dedupe_candidates_drops_repeats_of_the_same_configuration():
    first = make_candidate("sma", {"fast": 10, "slow": 30})
    duplicate = make_candidate("sma", {"fast": 10, "slow": 30})
    other = make_candidate("sma", {"fast": 5, "slow": 30})
    assert first is not None and duplicate is not None and other is not None

    unique = dedupe_candidates([first, duplicate, other])

    assert [c.name for c in unique] == [first.name, other.name]


def _leaderboard_entry(name, kind, params, total_return_pct, symbol="BTC/USD", timeframe="1h"):
    return LeaderboardEntry(
        name=name,
        kind=kind,
        params=params,
        symbol=symbol,
        timeframe=timeframe,
        metrics=PerformanceMetrics(
            total_return_pct=total_return_pct,
            max_drawdown_pct=1.0,
            win_rate=0.5,
            trade_count=2,
            sharpe_ratio=0.1,
        ),
    )


def test_refine_from_leaderboard_searches_around_previous_winners():
    entries = [_leaderboard_entry("sma(fast=10,slow=30)", "sma", {"fast": 10, "slow": 30}, 12.0)]

    refined = refine_from_leaderboard(entries, symbol="BTC/USD", timeframe="1h")

    names = {c.name for c in refined}
    assert "sma(fast=12,slow=30)" in names
    assert "sma(fast=10,slow=32)" in names


def test_refine_from_leaderboard_ignores_other_markets_and_timeframes():
    # Parameters that worked on one market/timeframe say nothing about
    # another, so they must not seed this run's local search.
    entries = [
        _leaderboard_entry("sma(fast=10,slow=30)", "sma", {"fast": 10, "slow": 30}, 50.0, symbol="ETH/USD"),
        _leaderboard_entry("sma(fast=7,slow=21)", "sma", {"fast": 7, "slow": 21}, 40.0, timeframe="4h"),
    ]

    refined = refine_from_leaderboard(entries, symbol="BTC/USD", timeframe="1h")

    assert refined == []
