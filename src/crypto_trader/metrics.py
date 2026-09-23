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


def _sharpe_ratio(equity_curve: list[float]) -> float | None:
    returns = [
        (curr - prev) / prev for prev, curr in zip(equity_curve, equity_curve[1:], strict=False) if prev > 0
    ]
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    stdev = math.sqrt(variance)
    if stdev == 0:
        return None
    return mean / stdev


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

    return PerformanceMetrics(
        total_return_pct=total_return_pct,
        max_drawdown_pct=max_drawdown_pct,
        win_rate=_win_rate(result.portfolio.fills),
        trade_count=result.trade_count,
        sharpe_ratio=_sharpe_ratio(equity_curve),
    )
