import argparse
import functools
import itertools
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from .config import Config
from .engine import run_backtest
from .exchange import fetch_ohlcv
from .metrics import PerformanceMetrics, compute_metrics
from .portfolio import Portfolio
from .strategy import RsiReversionStrategy, SmaCrossoverStrategy, Strategy


@dataclass
class Candidate:
    name: str
    make_strategy: Callable[[], Strategy]
    min_history: int


@dataclass
class CandidateResult:
    name: str
    metrics: PerformanceMetrics
    final_equity: float


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
    candidates: list[Candidate] = []

    for fast, slow in itertools.product(fast_windows, slow_windows):
        if fast >= slow:
            continue
        candidates.append(
            Candidate(
                name=f"sma(fast={fast},slow={slow})",
                make_strategy=functools.partial(SmaCrossoverStrategy, fast, slow),
                min_history=slow,
            )
        )

    for period, oversold, overbought in itertools.product(rsi_periods, rsi_oversold, rsi_overbought):
        candidates.append(
            Candidate(
                name=f"rsi(period={period},oversold={oversold:g},overbought={overbought:g})",
                make_strategy=functools.partial(RsiReversionStrategy, period, oversold, overbought),
                min_history=period + 1,
            )
        )

    return candidates


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

    candidates = default_candidates()
    ranked = rank_by_total_return(evaluate_candidates(close_prices, candidates, config.starting_balance_usd))

    print(f"{config.symbol} on {config.exchange_id}, {len(close_prices)} candles ({config.timeframe}, {args.days}d)")
    print(f"Evaluated {len(candidates)} strategy configurations — top {min(args.top, len(ranked))} by return:\n")
    print(f"{'strategy':<40} {'return%':>9} {'drawdown%':>10} {'win_rate':>9} {'sharpe':>8} {'trades':>7}")
    for candidate_result in ranked[: args.top]:
        m = candidate_result.metrics
        win_rate_str = f"{m.win_rate * 100:.1f}%" if m.win_rate is not None else "n/a"
        sharpe_str = f"{m.sharpe_ratio:.3f}" if m.sharpe_ratio is not None else "n/a"
        print(
            f"{candidate_result.name:<40} {m.total_return_pct:>8.2f}% {m.max_drawdown_pct:>9.2f}% "
            f"{win_rate_str:>9} {sharpe_str:>8} {m.trade_count:>7}"
        )


if __name__ == "__main__":
    main()
