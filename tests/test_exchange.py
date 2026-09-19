import pytest

from crypto_trader.config import Config
from crypto_trader.exchange import LiveOrderPlacementNotConfigured, place_order


def _paper_config() -> Config:
    return Config(
        exchange_id="binance",
        symbol="BTC/USDT",
        timeframe="1h",
        starting_balance_usd=10000.0,
        live_trading=False,
        api_key=None,
        api_secret=None,
    )


def _live_config() -> Config:
    return Config(
        exchange_id="binance",
        symbol="BTC/USDT",
        timeframe="1h",
        starting_balance_usd=10000.0,
        live_trading=True,
        api_key="k",
        api_secret="s",
    )


def test_place_order_refused_in_paper_mode():
    with pytest.raises(LiveOrderPlacementNotConfigured):
        place_order(_paper_config(), side="buy", quantity=1.0)


def test_place_order_refused_even_when_live_because_unimplemented():
    # Order placement logic doesn't exist yet on purpose (see exchange.py) —
    # this must keep failing closed, not silently start sending real orders.
    with pytest.raises(LiveOrderPlacementNotConfigured):
        place_order(_live_config(), side="buy", quantity=1.0)
