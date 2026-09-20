import pytest

from crypto_trader import exchange as exchange_module
from crypto_trader.config import Config
from crypto_trader.exchange import DEFAULT_PAGE_LIMIT, LiveOrderPlacementNotConfigured, fetch_ohlcv, place_order


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


TIMEFRAME_MS = 3_600_000  # matches FakeExchange.parse_timeframe below, for a "1h" config


class FakeExchange:
    """Stands in for a ccxt exchange instance: parse_timeframe plus a scripted
    sequence of fetch_ohlcv pages, so pagination can be tested without a real
    network call."""

    def __init__(self, pages):
        self._pages = list(pages)
        self.since_values: list[int | None] = []

    def parse_timeframe(self, timeframe: str) -> int:
        return TIMEFRAME_MS // 1000

    def fetch_ohlcv(self, symbol, timeframe=None, since=None, limit=None):
        self.since_values.append(since)
        if not self._pages:
            return []
        return self._pages.pop(0)


def _candle(ts_ms: int, close: float = 100.0) -> list[float]:
    return [ts_ms, close, close, close, close, 1.0]


def test_fetch_ohlcv_paginates_past_a_single_page(monkeypatch):
    page1 = [_candle(i * TIMEFRAME_MS) for i in range(DEFAULT_PAGE_LIMIT)]
    page2_start = DEFAULT_PAGE_LIMIT * TIMEFRAME_MS
    page2 = [_candle(page2_start + i * TIMEFRAME_MS) for i in range(5)]
    fake = FakeExchange([page1, page2])
    monkeypatch.setattr(exchange_module, "_ccxt_exchange", lambda config: fake)

    now_ms = page2[-1][0] + TIMEFRAME_MS * 10  # well after every candle closes
    candles = fetch_ohlcv(_paper_config(), since_ms=0, now_ms=now_ms)

    assert len(candles) == DEFAULT_PAGE_LIMIT + 5  # not silently truncated to one page
    assert len(fake.since_values) == 2  # had to make a second request to get past the cap
    assert candles == sorted(candles, key=lambda candle: candle[0])


def test_fetch_ohlcv_excludes_the_still_open_candle(monkeypatch):
    closed = _candle(0)
    still_open = _candle(TIMEFRAME_MS)  # its interval doesn't end until 2 * TIMEFRAME_MS
    fake = FakeExchange([[closed, still_open]])
    monkeypatch.setattr(exchange_module, "_ccxt_exchange", lambda config: fake)

    now_ms = TIMEFRAME_MS + 1  # inside the still-open candle's interval
    candles = fetch_ohlcv(_paper_config(), since_ms=0, now_ms=now_ms)

    assert candles == [closed]


def test_fetch_ohlcv_with_explicit_limit_makes_a_single_request(monkeypatch):
    page = [_candle(i * TIMEFRAME_MS) for i in range(10)]
    fake = FakeExchange([page])
    monkeypatch.setattr(exchange_module, "_ccxt_exchange", lambda config: fake)

    now_ms = page[-1][0] + TIMEFRAME_MS * 10
    candles = fetch_ohlcv(_paper_config(), since_ms=0, limit=10, now_ms=now_ms)

    assert len(fake.since_values) == 1  # explicit limit means one page, no pagination loop
    assert len(candles) == 10
