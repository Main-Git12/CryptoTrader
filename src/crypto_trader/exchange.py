import time
from typing import Any

from .config import Config

DEFAULT_PAGE_LIMIT = 1000


class LiveOrderPlacementNotConfigured(Exception):
    """Raised when order placement is attempted without a fully configured,
    explicit live-trading setup. This is a deliberate guard, not a bug."""


def _ccxt_exchange(config: Config) -> Any:
    import ccxt  # imported lazily so tests/backtests never need it installed as a hard dep of import time

    exchange_class = getattr(ccxt, config.exchange_id)
    kwargs: dict[str, str] = {}
    if config.live_trading:
        kwargs["apiKey"] = config.api_key
        kwargs["secret"] = config.api_secret
    return exchange_class(kwargs)


def fetch_ohlcv(
    config: Config,
    since_ms: int | None = None,
    limit: int | None = None,
    now_ms: int | None = None,
) -> list[list[float]]:
    """Public market data — never requires credentials, live_trading or not.

    When `limit` is omitted, paginates past the exchange's per-request candle
    cap so a long requested range (many days of a short timeframe) isn't
    silently truncated to a single page. Either way, drops the still-forming
    candle at the end of the range: its close is provisional and would change
    on a later call, so including it makes repeated runs over "the same"
    period produce different final signals.
    """
    exchange = _ccxt_exchange(config)
    timeframe_ms = exchange.parse_timeframe(config.timeframe) * 1000
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms

    if limit is not None:
        candles = exchange.fetch_ohlcv(config.symbol, timeframe=config.timeframe, since=since_ms, limit=limit)
    else:
        candles = _fetch_ohlcv_paginated(exchange, config, since_ms, timeframe_ms, now_ms)

    return [candle for candle in candles if candle[0] + timeframe_ms <= now_ms]


def _fetch_ohlcv_paginated(
    exchange: Any, config: Config, since_ms: int | None, timeframe_ms: int, now_ms: int
) -> list[list[float]]:
    candles: list[list[float]] = []
    seen_timestamps: set[float] = set()
    cursor = since_ms

    while True:
        page = exchange.fetch_ohlcv(
            config.symbol, timeframe=config.timeframe, since=cursor, limit=DEFAULT_PAGE_LIMIT
        )
        if not page:
            break

        new_candles = [candle for candle in page if candle[0] not in seen_timestamps]
        seen_timestamps.update(candle[0] for candle in new_candles)
        candles.extend(new_candles)

        next_cursor = page[-1][0] + timeframe_ms
        if not new_candles or next_cursor <= (cursor if cursor is not None else page[-1][0]):
            break  # exchange isn't advancing — stop rather than loop forever
        cursor = next_cursor
        if cursor >= now_ms or len(page) < DEFAULT_PAGE_LIMIT:
            break

    candles.sort(key=lambda candle: candle[0])
    return candles


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
