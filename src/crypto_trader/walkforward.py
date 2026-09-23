import argparse
import time
from collections.abc import Sequence
from dataclasses import dataclass

from .config import Config
from .engine import BacktestResult, run_backtest
from .exchange import fetch_ohlcv
from .metrics import PerformanceMetrics, compute_metrics
from .optimize import Candidate, CandidateResult, default_candidates, evaluate_candidates, rank_by_total_return
from .portfolio import Portfolio


@dataclass
class Window:
    """Index ranges into a close-price series. `train_end` and `test_end` are
    exclusive, and the test range always starts where the train range ends."""

    train_start: int
    train_end: int
    test_start: int
    test_end: int


@dataclass
class FoldResult:
    window: Window
    chosen: CandidateResult  # metrics on this are in-sample (the train range)
    test_metrics: PerformanceMetrics  # the same config on data it never saw
    buy_and_hold_return_pct: float


@dataclass
class WalkForwardSummary:
    fold_count: int
    mean_train_return_pct: float
    mean_test_return_pct: float
    mean_buy_and_hold_return_pct: float
    folds_profitable_out_of_sample: int
    folds_beating_buy_and_hold: int


def make_windows(total_candles: int, train_size: int, test_size: int, step: int | None = None) -> list[Window]:
    """Sequential train→test windows rolling forward through the series.
    `step` defaults to `test_size`, which tiles the history with
    non-overlapping test ranges so no candle is ever scored twice."""
    if train_size <= 0 or test_size <= 0:
        raise ValueError("train_size and test_size must both be positive")
    step = test_size if step is None else step
    if step <= 0:
        raise ValueError("step must be positive")

    windows = []
    train_start = 0
    while train_start + train_size + test_size <= total_candles:
        train_end = train_start + train_size
        windows.append(
            Window(
                train_start=train_start,
                train_end=train_end,
                test_start=train_end,
                test_end=train_end + test_size,
            )
        )
        train_start += step
    return windows


def evaluate_on_test_window(
    candidate: Candidate,
    close_prices: Sequence[float],
    window: Window,
    starting_balance_usd: float,
) -> PerformanceMetrics:
    """Backtests one candidate over a window's test range only.

    The strategy first sees `candidate.min_history` candles of the preceding
    train data so its indicators are already warm when the test range opens —
    the position it would be in running live, rather than blind for the first
    N candles of every test window. Those warm-up candles are excluded from
    the returned metrics; only the test range is scored.
    """
    warmup = min(candidate.min_history, window.test_start)
    prices = list(close_prices[window.test_start - warmup : window.test_end])

    portfolio = Portfolio(cash_usd=starting_balance_usd)
    result = run_backtest(prices, candidate.make_strategy(), portfolio, min_history=warmup + 1)

    scored = BacktestResult(
        portfolio=result.portfolio,
        equity_curve=result.equity_curve[warmup:],
        trade_count=result.trade_count,
    )
    return compute_metrics(scored, starting_balance_usd)


def buy_and_hold_return_pct(
    close_prices: Sequence[float],
    window: Window,
    starting_balance_usd: float,
) -> float:
    """Buying at the test range's first close and holding to its last — the
    benchmark a strategy has to beat to be worth running at all. Pays the
    one taker fee that entering the position costs, so it's compared on the
    same terms as a strategy's own fills."""
    prices = close_prices[window.test_start : window.test_end]
    if len(prices) < 2:
        return 0.0

    portfolio = Portfolio(cash_usd=starting_balance_usd)
    portfolio.buy(prices[0], (portfolio.cash_usd / prices[0]) * 0.999)
    final_equity = portfolio.equity(prices[-1])
    return (final_equity - starting_balance_usd) / starting_balance_usd * 100


def run_walk_forward(
    close_prices: Sequence[float],
    candidates: Sequence[Candidate],
    starting_balance_usd: float,
    train_size: int,
    test_size: int,
    step: int | None = None,
) -> list[FoldResult]:
    """For each window: pick the best candidate by return over the train
    range, then measure that one config over the test range it has never
    seen.

    The gap between those two numbers is the honest cost of having searched.
    A config that looks good in-sample and falls apart out-of-sample didn't
    find an edge, it fit noise — and no amount of further searching over the
    same history will tell you which of those happened. This will.
    """
    folds = []
    for window in make_windows(len(close_prices), train_size, test_size, step):
        train_prices = list(close_prices[window.train_start : window.train_end])
        ranked = rank_by_total_return(evaluate_candidates(train_prices, candidates, starting_balance_usd))
        if not ranked:
            continue

        best = ranked[0]
        chosen = next(candidate for candidate in candidates if candidate.name == best.name)
        folds.append(
            FoldResult(
                window=window,
                chosen=best,
                test_metrics=evaluate_on_test_window(chosen, close_prices, window, starting_balance_usd),
                buy_and_hold_return_pct=buy_and_hold_return_pct(close_prices, window, starting_balance_usd),
            )
        )
    return folds


def summarize(folds: Sequence[FoldResult]) -> WalkForwardSummary | None:
    """None when there were no folds — not enough history for even one
    train+test window, which is a input problem to report, not a result."""
    if not folds:
        return None

    return WalkForwardSummary(
        fold_count=len(folds),
        mean_train_return_pct=sum(f.chosen.metrics.total_return_pct for f in folds) / len(folds),
        mean_test_return_pct=sum(f.test_metrics.total_return_pct for f in folds) / len(folds),
        mean_buy_and_hold_return_pct=sum(f.buy_and_hold_return_pct for f in folds) / len(folds),
        folds_profitable_out_of_sample=sum(1 for f in folds if f.test_metrics.total_return_pct > 0),
        folds_beating_buy_and_hold=sum(
            1 for f in folds if f.test_metrics.total_return_pct > f.buy_and_hold_return_pct
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Walk-forward validation: repeatedly pick the best strategy configuration on one "
            "slice of history, then score it on the slice that follows, which it never saw. "
            "Backtests only — no exchange account, no real trading."
        )
    )
    parser.add_argument("--exchange", default="kraken")
    parser.add_argument("--symbol", default="BTC/USD")
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--days", type=int, default=180)
    parser.add_argument("--train-candles", type=int, default=500)
    parser.add_argument("--test-candles", type=int, default=250)
    parser.add_argument(
        "--step-candles",
        type=int,
        default=None,
        help="How far each window rolls forward. Defaults to --test-candles (non-overlapping test ranges).",
    )
    parser.add_argument("--starting-balance-usd", type=float, default=10000.0)
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

    folds = run_walk_forward(
        close_prices,
        default_candidates(),
        config.starting_balance_usd,
        train_size=args.train_candles,
        test_size=args.test_candles,
        step=args.step_candles,
    )

    print(f"{config.symbol} on {config.exchange_id}, {len(close_prices)} candles ({config.timeframe}, {args.days}d)")
    summary = summarize(folds)
    if summary is None:
        needed = args.train_candles + args.test_candles
        print(
            f"Not enough history for a single fold: need at least {needed} candles "
            f"({args.train_candles} train + {args.test_candles} test), have {len(close_prices)}. "
            "Ask for more --days, a shorter --timeframe, or smaller windows."
        )
        return

    print(f"{summary.fold_count} folds of {args.train_candles} train / {args.test_candles} test candles\n")
    print(f"{'fold':<6} {'chosen on train':<40} {'train%':>9} {'test%':>9} {'buy&hold%':>11}")
    for index, fold in enumerate(folds, start=1):
        print(
            f"{index:<6} {fold.chosen.name:<40} "
            f"{fold.chosen.metrics.total_return_pct:>8.2f}% "
            f"{fold.test_metrics.total_return_pct:>8.2f}% "
            f"{fold.buy_and_hold_return_pct:>10.2f}%"
        )

    print(
        f"\nMean in-sample (train):   {summary.mean_train_return_pct:>8.2f}%"
        f"\nMean out-of-sample (test): {summary.mean_test_return_pct:>8.2f}%"
        f"\nMean buy & hold:           {summary.mean_buy_and_hold_return_pct:>8.2f}%"
        f"\nProfitable out-of-sample:  {summary.folds_profitable_out_of_sample}/{summary.fold_count} folds"
        f"\nBeat buy & hold:           {summary.folds_beating_buy_and_hold}/{summary.fold_count} folds"
    )
    print(
        "\nThe train-vs-test gap is what searching cost you. A large drop means the "
        "winning configs fit that slice of history rather than finding something that "
        "persists — the usual outcome, and worth knowing before risking anything."
    )


if __name__ == "__main__":
    main()
