from typing import Any

from .config import Config


class LiveOrderPlacementNotConfigured(Exception):
    """Raised when order placement is attempted without a fully configured,
    explicit live-trading setup. This is a deliberate guard, not a bug."""


def _ccxt_exchange(config: Config) -> Any:
    import ccxt  # imported lazily so tests/backtests never need it installed as a hard dep of import time

    exchange_class = getattr(ccxt, config.exchange_id)
    kwargs: dict[str, str | None] = {}
    if config.live_trading:
        kwargs["apiKey"] = config.api_key
        kwargs["secret"] = config.api_secret
    return exchange_class(kwargs)


def fetch_ohlcv(
    config: Config, since_ms: int | None = None, limit: int | None = None
) -> list[list[float]]:
    """Public market data — never requires credentials, live_trading or not."""
    exchange = _ccxt_exchange(config)
    return exchange.fetch_ohlcv(config.symbol, timeframe=config.timeframe, since=since_ms, limit=limit)


def place_order(config: Config, side: str, quantity: float) -> None:
    """Deliberately not implemented yet. Config already refuses to construct
    with live_trading=True unless real credentials are set (see config.py) —
    this is a second, independent gate at the point orders would actually be
    sent, so a future caller can't reach real order placement by accident
    while this is still a stub."""
    if not config.live_trading:
        raise LiveOrderPlacementNotConfigured("live_trading is off — this is paper/backtest mode")
    raise LiveOrderPlacementNotConfigured(
        "Real order placement isn't implemented yet — position sizing and risk "
        "limits need to be designed first. Nothing has been sent to the exchange."
    )
