import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from .config import Config
from .exchange import fetch_ohlcv
from .portfolio import Fill, Portfolio
from .strategy import Signal, Strategy

_TIMEFRAME_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}


def _timeframe_seconds(timeframe: str) -> float:
    match = re.fullmatch(r"(\d+)([smhdw])", timeframe)
    if not match:
        raise ValueError(f"Can't infer a poll interval from timeframe {timeframe!r} — pass poll_seconds explicitly.")
    amount, unit = match.groups()
    return int(amount) * _TIMEFRAME_UNIT_SECONDS[unit]


def execute_signal(signal: Signal, portfolio: Portfolio, price: float) -> Fill | None:
    """Applies a signal to `portfolio` at `price`: all-in on BUY, all-out on
    SELL (position sizing beyond that is a live-trading design question, not
    one for backtests or paper trading). Returns the resulting Fill, or None
    if the signal didn't produce a trade (HOLD, already in/out of position,
    or no cash left to buy anything after fees)."""
    if signal is Signal.BUY and portfolio.position_qty == 0 and portfolio.cash_usd > 0:
        quantity = (portfolio.cash_usd / price) * 0.999  # leave room for the taker fee
        if quantity > 0:
            return portfolio.buy(price, quantity)
    elif signal is Signal.SELL and portfolio.position_qty > 0:
        return portfolio.sell(price, portfolio.position_qty)
    return None


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
        if execute_signal(signal, portfolio, price) is not None:
            trade_count += 1

        equity_curve.append(portfolio.equity(price))

    return BacktestResult(portfolio=portfolio, equity_curve=equity_curve, trade_count=trade_count)


@dataclass
class PaperTradingResult:
    portfolio: Portfolio
    close_prices: list[float] = field(default_factory=list)
    since_ms: int | None = None
    last_price: float | None = None
    trade_count: int = 0


def run_paper_trading(
    config: Config,
    strategy: Strategy,
    portfolio: Portfolio,
    *,
    iterations: int | None = None,
    poll_seconds: float | None = None,
    lookback_candles: int = 2,
    fetch: Callable[..., list[list[float]]] = fetch_ohlcv,
    sleep: Callable[[float], None] = time.sleep,
    on_fill: Callable[[Fill, float], None] | None = None,
    resume_close_prices: list[float] | None = None,
    resume_since_ms: int | None = None,
) -> PaperTradingResult:
    """Paper-trades `strategy` against live market data: each poll fetches
    newly-closed candles and feeds them through the same buy/sell logic as
    `run_backtest`, one candle at a time, as they arrive instead of all at
    once. Never touches `place_order` or reads `config.live_trading` — this
    is a simulated wallet regardless of how `config` is set up.

    `iterations` bounds how many polls to make (None polls forever — the
    caller stops it, e.g. on Ctrl-C). `poll_seconds` sets the wait between
    polls; it defaults to `config.timeframe`'s own duration, since polling
    faster than a new candle can close just repeats the same data. The
    first poll asks for only `lookback_candles` recent candles rather than
    the exchange's full history; every poll after that asks for whatever
    closed since the last candle it saw.

    `resume_close_prices` and `resume_since_ms` pick up a previous run
    (see `state.py`): `portfolio` should already reflect whatever trades
    that run made, and `resume_close_prices` is replayed through
    `strategy.next_signal` here — without executing any trades — purely to
    rebuild its internal indicator state (e.g. `SmaCrossoverStrategy`'s
    running averages) before live polling resumes from `resume_since_ms`.
    """
    strategy.reset()
    close_prices = list(resume_close_prices) if resume_close_prices else []
    since_ms = resume_since_ms
    for i in range(len(close_prices)):
        strategy.next_signal(close_prices[: i + 1])

    wait_seconds = poll_seconds if poll_seconds is not None else _timeframe_seconds(config.timeframe)
    result = PaperTradingResult(
        portfolio=portfolio,
        close_prices=close_prices,
        since_ms=since_ms,
        last_price=close_prices[-1] if close_prices else None,
    )

    completed = 0
    while iterations is None or completed < iterations:
        candles = fetch(config, limit=lookback_candles) if since_ms is None else fetch(config, since_ms=since_ms)

        for candle in candles:
            timestamp, _open, _high, _low, close, _volume = candle
            since_ms = int(timestamp) + 1
            close_prices.append(close)
            result.since_ms = since_ms
            result.last_price = close

            signal = strategy.next_signal(close_prices)
            fill = execute_signal(signal, portfolio, close)
            if fill is not None:
                result.trade_count += 1
                if on_fill is not None:
                    on_fill(fill, portfolio.equity(close))

        completed += 1
        if iterations is None or completed < iterations:
            sleep(wait_seconds)

    return result
