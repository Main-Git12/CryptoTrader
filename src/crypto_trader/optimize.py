import argparse
import functools
import itertools
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from .config import Config
from .deflated import DeflatedSharpe, deflated_sharpe_ratio
from .engine import run_backtest
from .exchange import fetch_ohlcv
from .leaderboard import LeaderboardEntry, load_leaderboard, merge_leaderboard, save_leaderboard
from .metrics import PerformanceMetrics, compute_metrics
from .portfolio import Portfolio
from .strategy import RsiReversionStrategy, SmaCrossoverStrategy, Strategy


@dataclass
class Candidate:
    name: str
    make_strategy: Callable[[], Strategy]
    min_history: int
    kind: str = "custom"  # "sma" | "rsi" — which family, so a later run knows how to vary it
    params: dict[str, float] = field(default_factory=dict)


@dataclass
class CandidateResult:
    name: str
    metrics: PerformanceMetrics
    final_equity: float
    kind: str = "custom"
    params: dict[str, float] = field(default_factory=dict)


SMA_WINDOW_STEPS = (-5, -2, 2, 5)
RSI_PERIOD_STEPS = (-5, -2, 2, 5)
RSI_THRESHOLD_STEPS = (-5.0, 5.0)


def make_candidate(kind: str, params: dict[str, float]) -> Candidate | None:
    """Builds a Candidate from a strategy family and its parameters, or None
    when those parameters are invalid for that family (an SMA pair with
    `fast >= slow`, an out-of-range RSI threshold). Returning None rather
    than raising is what keeps `neighbors()` simple: variations that fall
    outside a strategy's valid range are just dropped."""
    if kind == "sma":
        fast, slow = int(params["fast"]), int(params["slow"])
        if fast <= 0 or slow <= 0 or fast >= slow:
            return None
        return Candidate(
            name=f"sma(fast={fast},slow={slow})",
            make_strategy=functools.partial(SmaCrossoverStrategy, fast, slow),
            min_history=slow,
            kind="sma",
            params={"fast": fast, "slow": slow},
        )

    if kind == "rsi":
        period = int(params["period"])
        oversold, overbought = float(params["oversold"]), float(params["overbought"])
        if period <= 0 or not (0 < oversold < overbought < 100):
            return None
        return Candidate(
            name=f"rsi(period={period},oversold={oversold:g},overbought={overbought:g})",
            make_strategy=functools.partial(RsiReversionStrategy, period, oversold, overbought),
            min_history=period + 1,
            kind="rsi",
            params={"period": period, "oversold": oversold, "overbought": overbought},
        )

    return None


def neighbors(kind: str, params: dict[str, float]) -> list[Candidate]:
    """Nearby variations of one configuration — the local search a run does
    around the best configurations previous runs found, so repeated runs
    hill-climb toward better parameters instead of re-scanning one fixed
    grid forever. Variations invalid for the strategy are dropped."""
    variations: list[Candidate | None] = []

    if kind == "sma":
        fast, slow = params["fast"], params["slow"]
        for delta in SMA_WINDOW_STEPS:
            variations.append(make_candidate("sma", {"fast": fast + delta, "slow": slow}))
            variations.append(make_candidate("sma", {"fast": fast, "slow": slow + delta}))
    elif kind == "rsi":
        period, oversold, overbought = params["period"], params["oversold"], params["overbought"]
        for delta in RSI_PERIOD_STEPS:
            variations.append(
                make_candidate("rsi", {"period": period + delta, "oversold": oversold, "overbought": overbought})
            )
        for threshold_delta in RSI_THRESHOLD_STEPS:
            variations.append(
                make_candidate(
                    "rsi", {"period": period, "oversold": oversold + threshold_delta, "overbought": overbought}
                )
            )
            variations.append(
                make_candidate(
                    "rsi", {"period": period, "oversold": oversold, "overbought": overbought + threshold_delta}
                )
            )

    return [candidate for candidate in variations if candidate is not None]


def dedupe_candidates(candidates: Sequence[Candidate]) -> list[Candidate]:
    """Keeps the first candidate per name — the refined set from a previous
    run's winners routinely overlaps the baseline grid, and backtesting the
    same configuration twice just wastes time."""
    seen: set[str] = set()
    unique = []
    for candidate in candidates:
        if candidate.name in seen:
            continue
        seen.add(candidate.name)
        unique.append(candidate)
    return unique


def evaluate_candidates(
    close_prices: list[float],
    candidates: Sequence[Candidate],
    starting_balance_usd: float,
) -> list[CandidateResult]:
    """Backtests every candidate against the same `close_prices`, each with
    its own fresh Portfolio so results can't leak between candidates."""
    results = []
    for candidate in candidates:
        portfolio = Portfolio(cash_usd=starting_balance_usd)
        result = run_backtest(close_prices, candidate.make_strategy(), portfolio, min_history=candidate.min_history)
        final_equity = result.equity_curve[-1] if result.equity_curve else starting_balance_usd
        results.append(
            CandidateResult(
                name=candidate.name,
                metrics=compute_metrics(result, starting_balance_usd),
                final_equity=final_equity,
                kind=candidate.kind,
                params=candidate.params,
            )
        )
    return results


def rank_by_total_return(results: Sequence[CandidateResult]) -> list[CandidateResult]:
    return sorted(results, key=lambda r: r.metrics.total_return_pct, reverse=True)


def default_candidates(
    fast_windows: Sequence[int] = (5, 10, 20),
    slow_windows: Sequence[int] = (20, 30, 50, 100),
    rsi_periods: Sequence[int] = (7, 14, 21),
    rsi_oversold: Sequence[float] = (20.0, 30.0),
    rsi_overbought: Sequence[float] = (70.0, 80.0),
) -> list[Candidate]:
    """A grid of SMA-crossover and RSI-reversion configurations — the search
    space `optimize`'s CLI backtests and ranks. `fast >= slow` SMA pairs are
    skipped since `SmaCrossoverStrategy` itself rejects them."""
    built = [
        make_candidate("sma", {"fast": fast, "slow": slow})
        for fast, slow in itertools.product(fast_windows, slow_windows)
    ] + [
        make_candidate("rsi", {"period": period, "oversold": oversold, "overbought": overbought})
        for period, oversold, overbought in itertools.product(rsi_periods, rsi_oversold, rsi_overbought)
    ]
    return [candidate for candidate in built if candidate is not None]


def refine_from_leaderboard(
    entries: Sequence[LeaderboardEntry],
    symbol: str,
    timeframe: str,
    top: int = 5,
) -> list[Candidate]:
    """Turns the best configurations previous runs found (for this same
    symbol and timeframe — parameters don't transfer across markets) into a
    set of nearby variations to test this run. This is what makes repeated
    runs compound: each one searches around the current best instead of
    re-testing one fixed grid forever."""
    relevant = [entry for entry in entries if entry.symbol == symbol and entry.timeframe == timeframe]
    best_first = sorted(relevant, key=lambda entry: entry.metrics.total_return_pct, reverse=True)

    refined: list[Candidate] = []
    for entry in best_first[:top]:
        refined.extend(neighbors(entry.kind, entry.params))
    return refined


def deflate_best(results: Sequence[CandidateResult]) -> DeflatedSharpe | None:
    """Scores the best-by-Sharpe candidate against the whole set it was
    picked from. Returns None when the search is too small or too degenerate
    to say anything — which is itself worth reporting, rather than passing
    off silence as a pass."""
    scored = [r for r in results if r.metrics.sharpe_ratio is not None]
    if len(scored) < 2:
        return None

    best = max(scored, key=lambda r: r.metrics.sharpe_ratio or 0.0)
    return deflated_sharpe_ratio(
        observed_sharpe=best.metrics.sharpe_ratio or 0.0,
        trial_sharpes=[r.metrics.sharpe_ratio or 0.0 for r in scored],
        return_count=best.metrics.return_count,
        skewness=best.metrics.skewness,
        kurtosis=best.metrics.kurtosis,
    )


def _print_deflated_verdict(results: Sequence[CandidateResult]) -> None:
    """The headline number is the best of many tries, so on its own it
    overstates what was found. This says what it's worth after accounting
    for the size of the search."""
    deflated = deflate_best(results)
    if deflated is None:
        print("\nDeflated Sharpe: not computable (too few scorable candidates or too short a history).")
        return

    print(
        f"\nBest Sharpe {deflated.observed_sharpe:.3f} vs {deflated.benchmark_sharpe:.3f} expected "
        f"from {deflated.trials} no-skill trials"
    )
    print(f"Deflated Sharpe (P[true Sharpe > 0]): {deflated.probability:.1%}")
    if deflated.probability >= 0.95:
        print("Survives the multiple-testing correction — worth testing out-of-sample.")
    else:
        print(
            "Does NOT survive the multiple-testing correction: searching this many "
            "configurations would be expected to turn up a result this good by luck alone."
        )


def _print_table(rows: Sequence[tuple[str, PerformanceMetrics]]) -> None:
    print(f"{'strategy':<40} {'return%':>9} {'drawdown%':>10} {'win_rate':>9} {'sharpe':>8} {'trades':>7}")
    for name, m in rows:
        win_rate_str = f"{m.win_rate * 100:.1f}%" if m.win_rate is not None else "n/a"
        sharpe_str = f"{m.sharpe_ratio:.3f}" if m.sharpe_ratio is not None else "n/a"
        print(
            f"{name:<40} {m.total_return_pct:>8.2f}% {m.max_drawdown_pct:>9.2f}% "
            f"{win_rate_str:>9} {sharpe_str:>8} {m.trade_count:>7}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Grid-search SMA-crossover and RSI-reversion parameters against real historical "
            "OHLCV data and rank them by performance. No exchange account, no real trading — "
            "this only ever runs backtests against a simulated wallet."
        )
    )
    parser.add_argument("--exchange", default="kraken")
    parser.add_argument("--symbol", default="BTC/USD")
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--starting-balance-usd", type=float, default=10000.0)
    parser.add_argument("--top", type=int, default=15, help="How many ranked candidates to print.")
    parser.add_argument(
        "--leaderboard-file",
        default=None,
        help=(
            "Accumulate results here across runs. Each run also searches around the best "
            "configurations previous runs found for this symbol/timeframe, so repeated runs "
            "refine toward better parameters instead of re-testing the same fixed grid."
        ),
    )
    args = parser.parse_args()

    config = Config(
        exchange_id=args.exchange,
        symbol=args.symbol,
        timeframe=args.timeframe,
        starting_balance_usd=args.starting_balance_usd,
        live_trading=False,
        api_key=None,
        api_secret=None,
    )

    since_ms = int((time.time() - args.days * 86400) * 1000)
    candles = fetch_ohlcv(config, since_ms=since_ms)
    close_prices = [candle[4] for candle in candles]

    previous = load_leaderboard(args.leaderboard_file) if args.leaderboard_file else []
    refined = refine_from_leaderboard(previous, config.symbol, config.timeframe)
    candidates = dedupe_candidates([*default_candidates(), *refined])
    ranked = rank_by_total_return(evaluate_candidates(close_prices, candidates, config.starting_balance_usd))

    print(f"{config.symbol} on {config.exchange_id}, {len(close_prices)} candles ({config.timeframe}, {args.days}d)")
    if refined:
        print(f"Refining around {len(previous)} previously-recorded results ({len(refined)} nearby variations tried)")
    print(f"Evaluated {len(candidates)} strategy configurations — top {min(args.top, len(ranked))} by return:\n")
    _print_table([(r.name, r.metrics) for r in ranked[: args.top]])
    _print_deflated_verdict(ranked)

    if args.leaderboard_file:
        new_entries = [
            LeaderboardEntry(
                name=r.name,
                kind=r.kind,
                params=r.params,
                symbol=config.symbol,
                timeframe=config.timeframe,
                metrics=r.metrics,
            )
            for r in ranked
        ]
        merged = merge_leaderboard(previous, new_entries)
        save_leaderboard(args.leaderboard_file, merged)

        print(f"\nAll-time leaderboard ({args.leaderboard_file}), top {min(args.top, len(merged))}:\n")
        _print_table([(f"{e.name} [{e.symbol} {e.timeframe}]", e.metrics) for e in merged[: args.top]])


if __name__ == "__main__":
    main()
