import math
from dataclasses import dataclass

from .engine import BacktestResult
from .portfolio import Fill


@dataclass
class PerformanceMetrics:
    total_return_pct: float
    max_drawdown_pct: float
    win_rate: float | None  # None when there were no closed (buy-then-sell) trades to grade
    trade_count: int
    sharpe_ratio: float | None  # per-candle, not annualized; None with too little variance to compute one
    # The shape of the return distribution behind that Sharpe. A Sharpe ratio
    # alone assumes normality; these say how far off that assumption is, and
    # the deflated Sharpe (see deflated.py) needs them to correct for it.
    return_count: int = 0
    skewness: float | None = None
    kurtosis: float | None = None  # non-excess: a normal distribution scores 3.0


def _round_trip_pnls(fills: list[Fill]) -> list[float]:
    """Pairs each buy with the sell that closes it (the engine always buys
    all-in and sells all-out, so fills alternate buy/sell) and returns each
    round trip's profit after both fees."""
    pnls = []
    open_buy: Fill | None = None
    for fill in fills:
        if fill.side == "buy":
            open_buy = fill
        elif fill.side == "sell" and open_buy is not None:
            cost = open_buy.price * open_buy.quantity + open_buy.fee
            proceeds = fill.price * fill.quantity - fill.fee
            pnls.append(proceeds - cost)
            open_buy = None
    return pnls


def _win_rate(fills: list[Fill]) -> float | None:
    pnls = _round_trip_pnls(fills)
    if not pnls:
        return None
    return sum(1 for pnl in pnls if pnl > 0) / len(pnls)


def step_returns(equity_curve: list[float]) -> list[float]:
    """Per-candle fractional returns of the equity curve."""
    return [(curr - prev) / prev for prev, curr in zip(equity_curve, equity_curve[1:], strict=False) if prev > 0]


def _sharpe_ratio(returns: list[float]) -> float | None:
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    stdev = math.sqrt(variance)
    if stdev == 0:
        return None
    return mean / stdev


def _skewness(returns: list[float]) -> float | None:
    """Population skewness. Negative means the left tail is fatter — the
    losses are the surprises, which is the usual shape for a strategy that
    grinds out small gains and occasionally gives a lot back."""
    if len(returns) < 3:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / len(returns)
    if variance <= 0:
        return None
    return sum((r - mean) ** 3 for r in returns) / len(returns) / variance**1.5


def _kurtosis(returns: list[float]) -> float | None:
    """Population kurtosis, not excess: a normal distribution scores 3.0, and
    anything well above that means fat tails — big moves are more common than
    a Sharpe ratio's normality assumption credits."""
    if len(returns) < 4:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / len(returns)
    if variance <= 0:
        return None
    return sum((r - mean) ** 4 for r in returns) / len(returns) / variance**2


def compute_metrics(result: BacktestResult, starting_balance_usd: float) -> PerformanceMetrics:
    """Summarizes a backtest run beyond raw P&L: total return, the worst
    peak-to-trough drop the equity curve ever took (not just where it ended
    up), the fraction of round-trip trades that were profitable, and a
    per-candle Sharpe ratio (mean/stdev of step returns — not annualized,
    since that needs the timeframe's period-per-year count, which the
    caller knows and this function doesn't)."""
    equity_curve = result.equity_curve
    final_equity = equity_curve[-1] if equity_curve else starting_balance_usd
    total_return_pct = (final_equity - starting_balance_usd) / starting_balance_usd * 100

    peak = starting_balance_usd
    max_drawdown_pct = 0.0
    for equity in equity_curve:
        peak = max(peak, equity)
        if peak > 0:
            max_drawdown_pct = max(max_drawdown_pct, (peak - equity) / peak * 100)

    returns = step_returns(equity_curve)
    return PerformanceMetrics(
        total_return_pct=total_return_pct,
        max_drawdown_pct=max_drawdown_pct,
        win_rate=_win_rate(result.portfolio.fills),
        trade_count=result.trade_count,
        sharpe_ratio=_sharpe_ratio(returns),
        return_count=len(returns),
        skewness=_skewness(returns),
        kurtosis=_kurtosis(returns),
    )
