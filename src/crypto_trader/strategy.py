import random
from abc import ABC, abstractmethod
from enum import Enum


class Signal(Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


class Strategy(ABC):
    """A strategy sees the full close-price history up to and including "now"
    and returns one signal. Implementations should be pure functions of the
    history they're given — no hidden state that isn't reset by `reset()`."""

    @abstractmethod
    def next_signal(self, close_prices: list[float]) -> Signal: ...

    def reset(self) -> None:
        pass


def _sma(prices: list[float], window: int) -> float | None:
    if len(prices) < window:
        return None
    return sum(prices[-window:]) / window


class SmaCrossoverStrategy(Strategy):
    """Classic fast/slow simple-moving-average crossover: buy when the fast
    SMA crosses above the slow SMA, sell on the opposite cross, otherwise hold."""

    def __init__(self, fast_window: int = 10, slow_window: int = 30):
        if fast_window <= 0 or slow_window <= 0:
            raise ValueError("fast_window and slow_window must be positive")
        if fast_window >= slow_window:
            raise ValueError("fast_window must be smaller than slow_window")
        self.fast_window = fast_window
        self.slow_window = slow_window
        self._prev_fast: float | None = None
        self._prev_slow: float | None = None

    def reset(self) -> None:
        self._prev_fast = None
        self._prev_slow = None

    def next_signal(self, close_prices: list[float]) -> Signal:
        fast = _sma(close_prices, self.fast_window)
        slow = _sma(close_prices, self.slow_window)

        signal = Signal.HOLD
        if fast is not None and slow is not None and self._prev_fast is not None and self._prev_slow is not None:
            crossed_up = self._prev_fast <= self._prev_slow and fast > slow
            crossed_down = self._prev_fast >= self._prev_slow and fast < slow
            if crossed_up:
                signal = Signal.BUY
            elif crossed_down:
                signal = Signal.SELL

        self._prev_fast = fast
        self._prev_slow = slow
        return signal


class TimeSeriesMomentumStrategy(Strategy):
    """Long while the trailing return over `lookback` periods is positive,
    flat otherwise.

    This is the plainest form of time-series momentum, and unlike the
    indicator crossovers in this file it is the one price-based family with
    durable cross-market evidence behind it — strongest at roughly 1-4 week
    horizons, which on daily candles means a lookback around 7-28. It is
    deliberately boring: no thresholds to tune, one parameter, and it trades
    rarely enough that costs don't eat the result.

    Stateless — the trailing return is recomputed each call, so `reset()`
    has nothing to clear.
    """

    def __init__(self, lookback: int = 28):
        if lookback <= 0:
            raise ValueError(f"lookback must be positive, got {lookback}")
        self.lookback = lookback

    def next_signal(self, close_prices: list[float]) -> Signal:
        if len(close_prices) < self.lookback + 1:
            return Signal.HOLD

        earlier = close_prices[-(self.lookback + 1)]
        latest = close_prices[-1]
        if earlier <= 0:
            return Signal.HOLD
        return Signal.BUY if latest > earlier else Signal.SELL


def _rsi(prices: list[float], period: int) -> float | None:
    if len(prices) < period + 1:
        return None
    window = prices[-(period + 1) :]
    gains = 0.0
    losses = 0.0
    for previous, current in zip(window, window[1:], strict=False):
        change = current - previous
        gains += max(change, 0.0)
        losses += max(-change, 0.0)
    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss == 0:
        return 100.0
    return 100 - (100 / (1 + avg_gain / avg_loss))


class RsiReversionStrategy(Strategy):
    """Classic RSI mean-reversion: buy when RSI drops below `oversold`
    (the asset looks over-sold), sell when it rises above `overbought`,
    otherwise hold. Stateless — unlike the SMA crossover, RSI itself is
    recomputed from scratch each call, so `reset()` has nothing to clear."""

    def __init__(self, period: int = 14, oversold: float = 30.0, overbought: float = 70.0):
        if period <= 0:
            raise ValueError("period must be positive")
        if not (0 < oversold < overbought < 100):
            raise ValueError("must have 0 < oversold < overbought < 100")
        self.period = period
        self.oversold = oversold
        self.overbought = overbought

    def next_signal(self, close_prices: list[float]) -> Signal:
        rsi = _rsi(close_prices, self.period)
        if rsi is None:
            return Signal.HOLD
        if rsi < self.oversold:
            return Signal.BUY
        if rsi > self.overbought:
            return Signal.SELL
        return Signal.HOLD


class RandomSignalStrategy(Strategy):
    """A strategy that ignores price entirely and moves in and out of the
    market at random, at a chosen rhythm.

    This exists to be a null hypothesis, not to be traded. Given the rate at
    which a real strategy enters (`p_enter`, the chance of going long after a
    flat candle) and exits (`p_exit`, the chance of going flat after a long
    one), it produces a position series with the *same* expected time in
    market and the *same* average holding period — and therefore the same
    exposure and roughly the same fee bill — while having no relationship to
    price whatsoever.

    That is what makes it a fair control. Comparing a strategy against "always
    in the market" conflates two claims: that its timing is informative, and
    that being out of the market sometimes helped. Comparing it against this
    isolates the first. If a coin flip with the same rhythm does just as well,
    the signal contributed nothing and the result came from exposure alone.
    """

    def __init__(self, p_enter: float, p_exit: float, seed: int | None = None):
        if not 0.0 <= p_enter <= 1.0:
            raise ValueError(f"p_enter must be a probability, got {p_enter}")
        if not 0.0 <= p_exit <= 1.0:
            raise ValueError(f"p_exit must be a probability, got {p_exit}")
        self.p_enter = p_enter
        self.p_exit = p_exit
        self.seed = seed
        self._random = random.Random(seed)
        self._long = False

    def reset(self) -> None:
        """Rewinds to the same coin flips, not new ones — a seeded trial has
        to replay identically or the significance test isn't reproducible."""
        self._random = random.Random(self.seed)
        self._long = False

    def next_signal(self, close_prices: list[float]) -> Signal:
        roll = self._random.random()
        self._long = roll >= self.p_exit if self._long else roll < self.p_enter
        return Signal.BUY if self._long else Signal.SELL
