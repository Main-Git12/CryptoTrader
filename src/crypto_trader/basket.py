import argparse
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

from .config import Config
from .engine import BacktestResult, run_backtest
from .exchange import fetch_ohlcv
from .metrics import PerformanceMetrics, compute_metrics
from .portfolio import Portfolio
from .risk import RiskLimits, RiskManager
from .strategy import Strategy, TimeSeriesMomentumStrategy

DEFAULT_SYMBOLS = ("BTC/USD", "ETH/USD", "SOL/USD", "LTC/USD", "XRP/USD")


@dataclass
class Sleeve:
    """One asset's independent slice of the account."""

    symbol: str
    result: BacktestResult
    metrics: PerformanceMetrics


@dataclass
class BasketResult:
    sleeves: list[Sleeve] = field(default_factory=list)
    equity_curve: list[float] = field(default_factory=list)
    metrics: PerformanceMetrics | None = None
    buy_and_hold_return_pct: float | None = None


def _aggregate_equity(sleeves: Sequence[Sleeve]) -> list[float]:
    """Sums the sleeves' equity curves point by point, truncated to the
    shortest. Exchanges return different amounts of history per symbol, and
    summing past the shortest would silently compare a full basket against a
    partial one."""
    curves = [sleeve.result.equity_curve for sleeve in sleeves if sleeve.result.equity_curve]
    if not curves:
        return []

    length = min(len(curve) for curve in curves)
    return [sum(curve[i] for curve in curves) for i in range(length)]


def equal_weight_buy_and_hold_pct(
    price_series: Mapping[str, Sequence[float]], starting_balance_usd: float
) -> float | None:
    """Equal-weight buy and hold across the same symbols, each paying one
    entry fee — the benchmark the basket has to beat to justify trading."""
    usable = {symbol: prices for symbol, prices in price_series.items() if len(prices) >= 2}
    if not usable:
        return None

    per_sleeve = starting_balance_usd / len(usable)
    final = 0.0
    for prices in usable.values():
        portfolio = Portfolio(cash_usd=per_sleeve)
        portfolio.buy(prices[0], (per_sleeve / prices[0]) * 0.999)
        final += portfolio.equity(prices[-1])
    return (final - starting_balance_usd) / starting_balance_usd * 100


def run_basket_backtest(
    price_series: Mapping[str, Sequence[float]],
    make_strategy: Callable[[], Strategy],
    starting_balance_usd: float,
    min_history: int,
    limits: RiskLimits | None = None,
) -> BasketResult:
    """Runs the same strategy independently on each symbol, each with its own
    equal slice of capital and its own wallet, then sums the sleeves into one
    portfolio equity curve.

    Independent sleeves rather than one shared wallet: it keeps the accounting
    simple and honest (no sleeve can spend another's cash), and it is what the
    breadth argument actually assumes — the same signal applied across many
    assets, so that one asset's noise doesn't decide the whole result.
    """
    usable = {symbol: list(prices) for symbol, prices in price_series.items() if len(prices) > min_history}
    if not usable:
        return BasketResult()

    per_sleeve = starting_balance_usd / len(usable)
    sleeves = []
    for symbol, prices in sorted(usable.items()):
        portfolio = Portfolio(cash_usd=per_sleeve)
        risk = RiskManager(limits, starting_equity=per_sleeve) if limits is not None else None
        result = run_backtest(prices, make_strategy(), portfolio, min_history=min_history, risk=risk)
        sleeves.append(Sleeve(symbol=symbol, result=result, metrics=compute_metrics(result, per_sleeve)))

    equity_curve = _aggregate_equity(sleeves)
    basket = BacktestResult(
        portfolio=Portfolio(cash_usd=0.0),  # placeholder: per-sleeve wallets hold the real fills
        equity_curve=equity_curve,
        trade_count=sum(sleeve.result.trade_count for sleeve in sleeves),
    )
    return BasketResult(
        sleeves=sleeves,
        equity_curve=equity_curve,
        metrics=compute_metrics(basket, starting_balance_usd),
        buy_and_hold_return_pct=equal_weight_buy_and_hold_pct(usable, starting_balance_usd),
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Backtest a time-series-momentum basket across several assets on daily candles, "
            "with volatility-targeted sizing. Backtests only — no exchange account, no real trading."
        )
    )
    parser.add_argument("--exchange", default="kraken")
    parser.add_argument("--symbols", nargs="+", default=list(DEFAULT_SYMBOLS))
    parser.add_argument("--timeframe", default="1d")
    parser.add_argument("--days", type=int, default=730)
    parser.add_argument("--lookback", type=int, default=28, help="Momentum lookback in candles (28d ≈ 4 weeks).")
    parser.add_argument("--starting-balance-usd", type=float, default=10000.0)
    parser.add_argument("--max-position-fraction", type=float, default=1.0)
    parser.add_argument(
        "--target-volatility-pct",
        type=float,
        default=0.40,
        help="Annualized volatility target per sleeve, as a fraction (0.40 = 40%%). Scales positions down only.",
    )
    parser.add_argument("--max-drawdown-pct", type=float, default=None)
    args = parser.parse_args()

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
        except Exception as error:  # noqa: BLE001 — one dead symbol shouldn't sink the basket
            print(f"{symbol}: skipped ({type(error).__name__}: {error})")
            continue
        price_series[symbol] = [candle[4] for candle in candles]

    if not price_series:
        print("No symbols returned usable data — nothing to backtest.")
        return

    periods_per_year = {"1d": 365.0, "4h": 365.0 * 6, "1h": 365.0 * 24}.get(args.timeframe, 365.0)
    limits = RiskLimits(
        max_position_fraction=args.max_position_fraction,
        max_drawdown_pct=args.max_drawdown_pct,
        target_volatility_pct=args.target_volatility_pct,
        periods_per_year=periods_per_year,
    )

    basket = run_basket_backtest(
        price_series,
        lambda: TimeSeriesMomentumStrategy(lookback=args.lookback),
        starting_balance_usd=args.starting_balance_usd,
        min_history=args.lookback + 1,
        limits=limits,
    )
    if basket.metrics is None:
        print(f"Not enough history for a {args.lookback}-candle lookback on any symbol.")
        return

    counts = ", ".join(f"{s.symbol} {len(s.result.equity_curve)}" for s in basket.sleeves)
    print(f"Momentum({args.lookback}) basket on {args.exchange}, {args.timeframe} candles — {counts}")
    print(
        f"Volatility target {args.target_volatility_pct:.0%} annualized, "
        f"position cap {args.max_position_fraction:.0%}\n"
    )

    print(f"{'sleeve':<12} {'return%':>9} {'drawdown%':>10} {'sharpe':>8} {'trades':>7}")
    for sleeve in basket.sleeves:
        sharpe = f"{sleeve.metrics.sharpe_ratio:.3f}" if sleeve.metrics.sharpe_ratio is not None else "n/a"
        print(
            f"{sleeve.symbol:<12} {sleeve.metrics.total_return_pct:>8.2f}% "
            f"{sleeve.metrics.max_drawdown_pct:>9.2f}% {sharpe:>8} {sleeve.metrics.trade_count:>7}"
        )

    metrics = basket.metrics
    sharpe = f"{metrics.sharpe_ratio:.3f}" if metrics.sharpe_ratio is not None else "n/a"
    print(
        f"\n{'BASKET':<12} {metrics.total_return_pct:>8.2f}% "
        f"{metrics.max_drawdown_pct:>9.2f}% {sharpe:>8} {metrics.trade_count:>7}"
    )
    if basket.buy_and_hold_return_pct is not None:
        print(f"{'buy & hold':<12} {basket.buy_and_hold_return_pct:>8.2f}%")
        verdict = "beat" if metrics.total_return_pct > basket.buy_and_hold_return_pct else "did NOT beat"
        print(f"\nThe basket {verdict} equal-weight buy & hold over this period.")
    print(
        "\nThis is in-sample. Run walkforward before believing it — a basket backtest "
        "is still a backtest, and this one chose its own lookback."
    )


if __name__ == "__main__":
    main()
