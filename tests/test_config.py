import pytest

from crypto_trader.config import Config, LiveTradingMisconfigured


def _base_kwargs(**overrides):
    kwargs = dict(
        exchange_id="binance",
        symbol="BTC/USDT",
        timeframe="1h",
        starting_balance_usd=10000.0,
        live_trading=False,
        api_key=None,
        api_secret=None,
    )
    kwargs.update(overrides)
    return kwargs


def test_paper_mode_needs_no_credentials():
    config = Config(**_base_kwargs())
    assert config.live_trading is False


def test_live_trading_without_credentials_is_refused():
    with pytest.raises(LiveTradingMisconfigured):
        Config(**_base_kwargs(live_trading=True))


def test_live_trading_with_partial_credentials_is_refused():
    with pytest.raises(LiveTradingMisconfigured):
        Config(**_base_kwargs(live_trading=True, api_key="k"))


def test_live_trading_with_both_credentials_is_accepted():
    config = Config(**_base_kwargs(live_trading=True, api_key="k", api_secret="s"))
    assert config.live_trading is True


def test_from_env_defaults_to_paper_mode(monkeypatch):
    for var in ("LIVE_TRADING", "EXCHANGE_API_KEY", "EXCHANGE_API_SECRET"):
        monkeypatch.delenv(var, raising=False)
    config = Config.from_env()
    assert config.live_trading is False
    assert config.api_key is None
