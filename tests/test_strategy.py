import pytest

from crypto_trader.strategy import RsiReversionStrategy, Signal, SmaCrossoverStrategy


def test_rejects_fast_window_not_smaller_than_slow():
    with pytest.raises(ValueError):
        SmaCrossoverStrategy(fast_window=30, slow_window=10)


def test_rejects_zero_or_negative_windows():
    with pytest.raises(ValueError):
        SmaCrossoverStrategy(fast_window=0, slow_window=30)
    with pytest.raises(ValueError):
        SmaCrossoverStrategy(fast_window=-5, slow_window=30)
    with pytest.raises(ValueError):
        SmaCrossoverStrategy(fast_window=5, slow_window=0)


def test_holds_until_enough_history_for_both_windows():
    strategy = SmaCrossoverStrategy(fast_window=3, slow_window=5)
    for i in range(1, 5):
        assert strategy.next_signal([100.0] * i) is Signal.HOLD


def test_flat_prices_never_signal():
    strategy = SmaCrossoverStrategy(fast_window=3, slow_window=5)
    signals = [strategy.next_signal([100.0] * i) for i in range(1, 20)]
    assert all(signal is Signal.HOLD for signal in signals)


def test_uptrend_then_downtrend_produces_a_buy_then_a_sell(uptrend_then_downtrend):
    strategy = SmaCrossoverStrategy(fast_window=5, slow_window=15)
    signals = [strategy.next_signal(uptrend_then_downtrend[: i + 1]) for i in range(len(uptrend_then_downtrend))]

    assert Signal.BUY in signals
    assert Signal.SELL in signals
    assert signals.index(Signal.BUY) < signals.index(Signal.SELL)


def test_reset_clears_prior_averages():
    strategy = SmaCrossoverStrategy(fast_window=3, slow_window=5)
    strategy.next_signal([100.0, 101.0, 102.0, 103.0, 104.0])
    strategy.reset()
    assert strategy._prev_fast is None
    assert strategy._prev_slow is None


def test_rsi_rejects_non_positive_period():
    with pytest.raises(ValueError):
        RsiReversionStrategy(period=0)
    with pytest.raises(ValueError):
        RsiReversionStrategy(period=-3)


def test_rsi_rejects_invalid_threshold_ordering():
    with pytest.raises(ValueError):
        RsiReversionStrategy(oversold=70, overbought=30)
    with pytest.raises(ValueError):
        RsiReversionStrategy(oversold=0, overbought=70)
    with pytest.raises(ValueError):
        RsiReversionStrategy(oversold=30, overbought=100)


def test_rsi_holds_until_enough_history():
    strategy = RsiReversionStrategy(period=3)
    for i in range(1, 3):
        assert strategy.next_signal([100.0] * i) is Signal.HOLD


def test_rsi_buys_when_strictly_declining():
    strategy = RsiReversionStrategy(period=3, oversold=30, overbought=70)
    prices = [100.0, 99.0, 98.0, 97.0]  # 3 consecutive losses, no gains -> RSI == 0
    assert strategy.next_signal(prices) is Signal.BUY


def test_rsi_sells_when_strictly_rising():
    strategy = RsiReversionStrategy(period=3, oversold=30, overbought=70)
    prices = [100.0, 101.0, 102.0, 103.0]  # 3 consecutive gains, no losses -> RSI == 100
    assert strategy.next_signal(prices) is Signal.SELL


def test_rsi_holds_when_gains_and_losses_balance():
    strategy = RsiReversionStrategy(period=4, oversold=30, overbought=70)
    prices = [100.0, 101.0, 100.0, 101.0, 100.0]  # alternating +1/-1 -> RSI == 50
    assert strategy.next_signal(prices) is Signal.HOLD
