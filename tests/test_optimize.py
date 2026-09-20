from crypto_trader.optimize import Candidate, default_candidates, evaluate_candidates, rank_by_total_return
from crypto_trader.strategy import SmaCrossoverStrategy


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
