import pytest


@pytest.fixture
def uptrend_then_downtrend() -> list[float]:
    """Flat, then a ramp up, then flat, then a ramp down, then flat again.
    The flat stretches matter: a ramp starting immediately (with no flat lead-in)
    makes the fast/slow SMA gap already nonzero the moment both windows are
    filled, so a 5/15 crossover never actually crosses through zero. Starting
    and settling at flat baselines gives it a real zero-crossing to detect in
    each direction (one BUY on the way up, one SELL on the way down)."""
    flat_start = [100.0] * 20
    up = [100 + (i + 1) * 2 for i in range(20)]  # 102..140
    flat_peak = [140.0] * 20
    down = [140 - (i + 1) * 2 for i in range(20)]  # 138..100
    flat_end = [100.0] * 20
    return flat_start + up + flat_peak + down + flat_end


@pytest.fixture
def flat_prices() -> list[float]:
    return [100.0] * 50
