from crypto_trader.strategy import Signal, SmaCrossoverStrategy


def test_rejects_fast_window_not_smaller_than_slow():
    import pytest

    with pytest.raises(ValueError):
        SmaCrossoverStrategy(fast_window=30, slow_window=10)


def test_rejects_zero_or_negative_windows():
    import pytest

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
