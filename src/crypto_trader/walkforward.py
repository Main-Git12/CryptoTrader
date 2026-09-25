import argparse
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import partial

from .basket import DEFAULT_SYMBOLS, equal_weight_buy_and_hold_pct, run_basket_backtest
from .config import Config
from .engine import BacktestResult, run_backtest
from .exchange import fetch_ohlcv
from .metrics import PerformanceMetrics, compute_metrics
from .optimize import Candidate, CandidateResult, default_candidates, evaluate_candidates, rank_by_total_return
from .portfolio import Portfolio
from .risk import RiskLimits
from .strategy import TimeSeriesMomentumStrategy


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


@dataclass
class BasketFoldResult:
    window: Window
    chosen_lookback: int
    train_return_pct: float  # in-sample, on the range the lookback was chosen from
    test_metrics: PerformanceMetrics  # the same lookback on data it never saw
    buy_and_hold_return_pct: float


@dataclass
class BasketWalkForwardSummary:
    fold_count: int
    mean_train_return_pct: float
    mean_test_return_pct: float
    mean_buy_and_hold_return_pct: float
    folds_profitable_out_of_sample: int
    folds_beating_buy_and_hold: int
    chosen_lookbacks: list[int]


def align_price_series(price_series: Mapping[str, Sequence[float]]) -> dict[str, list[float]]:
    """Trims every symbol to the shortest series, keeping the most recent
    candles.

    Window indices have to mean the same date in every sleeve, or a fold
    would train on one symbol's January against another's March. All fetches
    end at roughly now, so aligning on the tail lines them up.
    """
    usable = {symbol: list(prices) for symbol, prices in price_series.items() if prices}
    if not usable:
        return {}

    length = min(len(prices) for prices in usable.values())
    return {symbol: prices[-length:] for symbol, prices in usable.items()}


def _slice_series(price_series: Mapping[str, Sequence[float]], start: int, end: int) -> dict[str, list[float]]:
    return {symbol: list(prices[start:end]) for symbol, prices in price_series.items()}


def evaluate_basket_on_test_window(
    price_series: Mapping[str, Sequence[float]],
    window: Window,
    lookback: int,
    starting_balance_usd: float,
    limits: RiskLimits | None = None,
) -> PerformanceMetrics | None:
    """Scores one lookback over a window's test range only.

    Like the single-asset version, the strategies first see `lookback`
    candles of the preceding train data so their momentum signal is already
    formed when the test range opens — otherwise every fold would start
    blind. Those warm-up candles are then cut from the scored equity curve,
    so the metrics describe the test range and nothing else.
    """
    warmup = min(lookback, window.test_start)
    windowed = _slice_series(price_series, window.test_start - warmup, window.test_end)

    basket = run_basket_backtest(
        windowed,
        partial(TimeSeriesMomentumStrategy, lookback=lookback),
        starting_balance_usd=starting_balance_usd,
        min_history=warmup + 1,
        limits=limits,
    )
    if basket.metrics is None or len(basket.equity_curve) <= warmup:
        return None

    scored = BacktestResult(
        portfolio=Portfolio(cash_usd=0.0),  # the sleeves hold the real fills
        equity_curve=basket.equity_curve[warmup:],
        trade_count=basket.metrics.trade_count,
    )
    return compute_metrics(scored, starting_balance_usd)


def run_basket_walk_forward(
    price_series: Mapping[str, Sequence[float]],
    lookbacks: Sequence[int],
    starting_balance_usd: float,
    train_size: int,
    test_size: int,
    step: int | None = None,
    limits: RiskLimits | None = None,
) -> list[BasketFoldResult]:
    """Walk-forward for the multi-asset momentum basket.

    Same discipline as the single-asset version, with the lookback as the
    thing being selected: each fold picks the lookback that did best across
    the whole basket over the train range, then scores that one lookback
    over the test range it never saw, against equal-weight buy & hold on the
    same range.

    This is the test that matters for the basket. Its in-sample result used
    a lookback taken from published evidence rather than fitted here, which
    is a better starting position than a parameter search — but "better
    starting position" is not evidence, and only out-of-sample scoring can
    tell the difference.
    """
    aligned = align_price_series(price_series)
    if not aligned or not lookbacks:
        return []

    length = min(len(prices) for prices in aligned.values())
    folds = []
    for window in make_windows(length, train_size, test_size, step):
        train_slices = _slice_series(aligned, window.train_start, window.train_end)

        scored_lookbacks = []
        for lookback in lookbacks:
            trained = run_basket_backtest(
                train_slices,
                partial(TimeSeriesMomentumStrategy, lookback=lookback),
                starting_balance_usd=starting_balance_usd,
                min_history=lookback + 1,
                limits=limits,
            )
            if trained.metrics is not None:
                scored_lookbacks.append((lookback, trained.metrics.total_return_pct))

        if not scored_lookbacks:
            continue

        chosen_lookback, train_return_pct = max(scored_lookbacks, key=lambda pair: pair[1])
        test_metrics = evaluate_basket_on_test_window(
            aligned, window, chosen_lookback, starting_balance_usd, limits
        )
        if test_metrics is None:
            continue

        test_slices = _slice_series(aligned, window.test_start, window.test_end)
        folds.append(
            BasketFoldResult(
                window=window,
                chosen_lookback=chosen_lookback,
                train_return_pct=train_return_pct,
                test_metrics=test_metrics,
                buy_and_hold_return_pct=equal_weight_buy_and_hold_pct(test_slices, starting_balance_usd) or 0.0,
            )
        )
    return folds


def summarize_basket(folds: Sequence[BasketFoldResult]) -> BasketWalkForwardSummary | None:
    if not folds:
        return None

    return BasketWalkForwardSummary(
        fold_count=len(folds),
        mean_train_return_pct=sum(f.train_return_pct for f in folds) / len(folds),
        mean_test_return_pct=sum(f.test_metrics.total_return_pct for f in folds) / len(folds),
        mean_buy_and_hold_return_pct=sum(f.buy_and_hold_return_pct for f in folds) / len(folds),
        folds_profitable_out_of_sample=sum(1 for f in folds if f.test_metrics.total_return_pct > 0),
        folds_beating_buy_and_hold=sum(
            1 for f in folds if f.test_metrics.total_return_pct > f.buy_and_hold_return_pct
        ),
        chosen_lookbacks=[f.chosen_lookback for f in folds],
    )


def _run_basket_cli(args: argparse.Namespace) -> None:
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

    aligned = align_price_series(price_series)
    if not aligned:
        print("No symbols returned usable data — nothing to validate.")
        return

    periods_per_year = {"1d": 365.0, "4h": 365.0 * 6, "1h": 365.0 * 24}.get(args.timeframe, 365.0)
    limits = RiskLimits(
        target_volatility_pct=args.target_volatility_pct,
        periods_per_year=periods_per_year,
    )

    length = min(len(prices) for prices in aligned.values())
    folds = run_basket_walk_forward(
        aligned,
        lookbacks=args.lookbacks,
        starting_balance_usd=args.starting_balance_usd,
        train_size=args.train_candles,
        test_size=args.test_candles,
        step=args.step_candles,
        limits=limits,
    )

    print(f"Basket walk-forward on {args.exchange}, {args.timeframe} candles, {length} aligned per symbol")
    print(f"Symbols: {', '.join(sorted(aligned))}")
    summary = summarize_basket(folds)
    if summary is None:
        needed = args.train_candles + args.test_candles
        print(
            f"Not enough aligned history for a single fold: need {needed} candles "
            f"({args.train_candles} train + {args.test_candles} test), have {length}."
        )
        return

    print(f"Lookbacks searched per fold: {args.lookbacks}\n")
    print(f"{'fold':<6} {'chosen':>8} {'train%':>9} {'test%':>9} {'buy&hold%':>11} {'drawdown%':>11}")
    for index, fold in enumerate(folds, start=1):
        print(
            f"{index:<6} {fold.chosen_lookback:>8} {fold.train_return_pct:>8.2f}% "
            f"{fold.test_metrics.total_return_pct:>8.2f}% {fold.buy_and_hold_return_pct:>10.2f}% "
            f"{fold.test_metrics.max_drawdown_pct:>10.2f}%"
        )

    print(
        f"\nMean in-sample (train):    {summary.mean_train_return_pct:>8.2f}%"
        f"\nMean out-of-sample (test): {summary.mean_test_return_pct:>8.2f}%"
        f"\nMean buy & hold:           {summary.mean_buy_and_hold_return_pct:>8.2f}%"
        f"\nProfitable out-of-sample:  {summary.folds_profitable_out_of_sample}/{summary.fold_count} folds"
        f"\nBeat buy & hold:           {summary.folds_beating_buy_and_hold}/{summary.fold_count} folds"
    )
    if len(set(summary.chosen_lookbacks)) > 1:
        print(
            f"\nThe chosen lookback moved between folds ({summary.chosen_lookbacks}), which is "
            "itself a warning: a parameter that won't sit still is being fitted to each window."
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
    parser.add_argument(
        "--basket",
        action="store_true",
        help="Walk-forward the multi-asset momentum basket instead of the single-symbol indicator grid.",
    )
    parser.add_argument("--symbols", nargs="+", default=list(DEFAULT_SYMBOLS), help="Symbols for --basket.")
    parser.add_argument(
        "--lookbacks",
        nargs="+",
        type=int,
        default=[7, 14, 21, 28, 42, 56],
        help="Momentum lookbacks each fold chooses between, in candles.",
    )
    parser.add_argument("--target-volatility-pct", type=float, default=0.40)
    args = parser.parse_args()

    if args.basket:
        _run_basket_cli(args)
        return

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
