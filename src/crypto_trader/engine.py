from dataclasses import dataclass, field

from .portfolio import Portfolio
from .strategy import Signal, Strategy


@dataclass
class BacktestResult:
    portfolio: Portfolio
    equity_curve: list[float] = field(default_factory=list)
    trade_count: int = 0


def run_backtest(
    close_prices: list[float],
    strategy: Strategy,
    portfolio: Portfolio,
    min_history: int = 1,
) -> BacktestResult:
    """Replays `close_prices` candle by candle: the strategy sees the prices
    up to and including the current candle, and any resulting buy/sell is
    filled at that candle's close (all-in/all-out sizing — position sizing
    beyond that is a live-trading design question, not a backtest one)."""
    strategy.reset()
    equity_curve: list[float] = []
    trade_count = 0

    for i in range(len(close_prices)):
        if i + 1 < min_history:
            equity_curve.append(portfolio.equity(close_prices[i]))
            continue

        price = close_prices[i]
        history = close_prices[: i + 1]
        signal = strategy.next_signal(history)

        if signal is Signal.BUY and portfolio.position_qty == 0 and portfolio.cash_usd > 0:
            quantity = (portfolio.cash_usd / price) * 0.999  # leave room for the taker fee
            if quantity > 0:
                portfolio.buy(price, quantity)
                trade_count += 1
        elif signal is Signal.SELL and portfolio.position_qty > 0:
            portfolio.sell(price, portfolio.position_qty)
            trade_count += 1

        equity_curve.append(portfolio.equity(price))

    return BacktestResult(portfolio=portfolio, equity_curve=equity_curve, trade_count=trade_count)
