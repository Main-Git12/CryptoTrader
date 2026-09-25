import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass


def annualized_volatility(prices: Sequence[float], periods_per_year: float) -> float | None:
    """Realized volatility of `prices`, as an annualized fraction (0.8 = 80%).
    None when there aren't enough points or the series doesn't move."""
    returns = [(b - a) / a for a, b in zip(prices, prices[1:], strict=False) if a > 0]
    if len(returns) < 2:
        return None

    per_period = statistics.stdev(returns)
    if per_period <= 0:
        return None
    return per_period * math.sqrt(periods_per_year)


@dataclass(frozen=True)
class RiskLimits:
    """Caps on what a strategy is allowed to do, independent of what it
    signals. A strategy decides *when* to trade; this decides *how much* and
    *whether trading is still allowed at all*.

    `max_position_fraction` is the share of current equity a single position
    may use — 1.0 is the all-in sizing backtests have always used, 0.25 puts
    at most a quarter of the account at risk at once.

    `max_drawdown_pct` is a kill switch, not a stop-loss: once equity falls
    that far below its high-water mark, trading stops for good rather than
    resizing. It exists so a strategy that stops working can't keep trading
    the account down while nobody is watching.
    """

    max_position_fraction: float = 1.0
    max_drawdown_pct: float | None = None
    target_volatility_pct: float | None = None  # annualized
    periods_per_year: float = 365.0  # daily crypto candles; 24*365 for hourly
    volatility_lookback: int = 30

    def __post_init__(self) -> None:
        if not (0 < self.max_position_fraction <= 1):
            raise ValueError(f"max_position_fraction must be in (0, 1], got {self.max_position_fraction}")
        if self.max_drawdown_pct is not None and not (0 < self.max_drawdown_pct <= 100):
            raise ValueError(f"max_drawdown_pct must be in (0, 100], got {self.max_drawdown_pct}")
        if self.target_volatility_pct is not None and self.target_volatility_pct <= 0:
            raise ValueError(f"target_volatility_pct must be positive, got {self.target_volatility_pct}")
        if self.periods_per_year <= 0:
            raise ValueError(f"periods_per_year must be positive, got {self.periods_per_year}")
        if self.volatility_lookback < 2:
            raise ValueError(f"volatility_lookback must be at least 2, got {self.volatility_lookback}")


# Leaves room for the taker fee, so a full-size buy can't cost more cash than
# the account holds.
_FEE_HEADROOM = 0.999


class RiskManager:
    """Tracks equity against its high-water mark and answers two questions:
    how much may be bought right now, and is trading still permitted.

    Halting is deliberately one-way. A kill switch that re-arms itself the
    moment equity ticks back up isn't a kill switch — restarting is a
    decision for whoever is running this, so it takes constructing a new
    manager (or `reset()`) rather than happening on its own.
    """

    def __init__(self, limits: RiskLimits, starting_equity: float):
        if starting_equity <= 0:
            raise ValueError(f"starting_equity must be positive, got {starting_equity}")
        self.limits = limits
        self.starting_equity = starting_equity
        self.peak_equity = starting_equity
        self.halted = False
        self.halt_reason: str | None = None

    def reset(self) -> None:
        self.peak_equity = self.starting_equity
        self.halted = False
        self.halt_reason = None

    def observe(self, equity: float) -> None:
        """Feed every mark-to-market equity value through here. Raises the
        high-water mark, and trips the kill switch the first time drawdown
        from that mark breaches the limit."""
        if not math.isfinite(equity):
            return
        self.peak_equity = max(self.peak_equity, equity)

        if self.halted or self.limits.max_drawdown_pct is None or self.peak_equity <= 0:
            return

        drawdown_pct = (self.peak_equity - equity) / self.peak_equity * 100
        if drawdown_pct >= self.limits.max_drawdown_pct:
            self.halted = True
            self.halt_reason = (
                f"drawdown {drawdown_pct:.2f}% from peak ${self.peak_equity:,.2f} "
                f"reached the {self.limits.max_drawdown_pct:.2f}% limit"
            )

    def buy_quantity(
        self,
        cash_usd: float,
        equity: float,
        price: float,
        recent_prices: Sequence[float] | None = None,
    ) -> float:
        """How much to buy at `price`: the position-fraction cap applied to
        equity, never more cash than is actually on hand. Returns 0 when
        halted or when there's nothing meaningful to buy.

        With `target_volatility_pct` set and `recent_prices` supplied, the
        position is also scaled down when the asset has been more volatile
        than the target, so a fixed fraction of equity doesn't mean wildly
        different amounts of risk between calm and turbulent markets. Note
        it only ever scales *down*: sizing up in quiet markets would need
        leverage, which this wallet doesn't have, so the fraction cap stays
        the ceiling. Expect steadier drawdowns from this, not higher returns.
        """
        if self.halted or price <= 0 or cash_usd <= 0:
            return 0.0

        fraction = self.limits.max_position_fraction
        if self.limits.target_volatility_pct is not None and recent_prices:
            realized = annualized_volatility(recent_prices, self.limits.periods_per_year)
            if realized is not None and realized > 0:
                fraction = min(fraction, fraction * self.limits.target_volatility_pct / realized)

        budget = min(equity * fraction, cash_usd)
        if budget <= 0:
            return 0.0
        return (budget / price) * _FEE_HEADROOM
