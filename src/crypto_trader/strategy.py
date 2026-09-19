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
