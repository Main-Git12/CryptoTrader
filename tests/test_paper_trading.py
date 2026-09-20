import pytest

from crypto_trader.config import Config
from crypto_trader.engine import run_paper_trading
from crypto_trader.portfolio import Fill, Portfolio
from crypto_trader.strategy import SmaCrossoverStrategy

ONE_HOUR_MS = 3_600_000


def _candles_from_closes(closes: list[float]) -> list[list[float]]:
    return [[i * ONE_HOUR_MS, c, c, c, c, 0.0] for i, c in enumerate(closes)]


class FakeFeed:
    """A fake `fetch` that reveals `chunk_size` new candles per call, like an
    exchange trickling in one freshly-closed candle per poll. Ignores
    `since_ms`/`limit` beyond using `limit` to size the very first delivery,
    matching how `run_paper_trading` calls it."""

    def __init__(self, candles: list[list[float]], chunk_size: int = 1):
        self.candles = candles
        self.chunk_size = chunk_size
        self.cursor = 0
        self.calls = 0

    def fetch(self, config: Config, since_ms: int | None = None, limit: int | None = None) -> list[list[float]]:
        self.calls += 1
        take = limit if limit is not None else self.chunk_size
        end = min(self.cursor + take, len(self.candles))
        batch = self.candles[self.cursor : end]
        self.cursor = end
        return batch


class FakeClock:
    def __init__(self) -> None:
        self.sleeps: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)


def _config(**overrides) -> Config:
    kwargs = {
        "exchange_id": "kraken",
        "symbol": "BTC/USD",
        "timeframe": "1h",
        "starting_balance_usd": 10000.0,
        "live_trading": False,
        "api_key": None,
        "api_secret": None,
    }
    kwargs.update(overrides)
    return Config(**kwargs)


def test_paper_trading_buys_on_uptrend_and_sells_on_downtrend(uptrend_then_downtrend):
    feed = FakeFeed(_candles_from_closes(uptrend_then_downtrend))
    clock = FakeClock()
    strategy = SmaCrossoverStrategy(fast_window=5, slow_window=15)
    portfolio = Portfolio(cash_usd=10000.0)

    result = run_paper_trading(
        _config(),
        strategy,
        portfolio,
        iterations=len(uptrend_then_downtrend),
        lookback_candles=1,
        fetch=feed.fetch,
        sleep=clock.sleep,
    )

    assert result.trade_count == 2  # one buy, one sell
    assert result.portfolio.position_qty == 0.0
    assert result.last_price == uptrend_then_downtrend[-1]


def test_paper_trading_on_flat_prices_never_trades(flat_prices):
    feed = FakeFeed(_candles_from_closes(flat_prices))
    clock = FakeClock()
    strategy = SmaCrossoverStrategy(fast_window=5, slow_window=15)
    portfolio = Portfolio(cash_usd=10000.0)

    result = run_paper_trading(
        _config(),
        strategy,
        portfolio,
        iterations=len(flat_prices),
        lookback_candles=1,
        fetch=feed.fetch,
        sleep=clock.sleep,
    )

    assert result.trade_count == 0
    assert result.portfolio.cash_usd == pytest.approx(10000.0)


def test_paper_trading_stops_after_requested_iterations(flat_prices):
    feed = FakeFeed(_candles_from_closes(flat_prices))
    clock = FakeClock()
    strategy = SmaCrossoverStrategy(fast_window=5, slow_window=15)
    portfolio = Portfolio(cash_usd=10000.0)

    result = run_paper_trading(
        _config(),
        strategy,
        portfolio,
        iterations=3,
        lookback_candles=1,
        fetch=feed.fetch,
        sleep=clock.sleep,
    )

    assert feed.calls == 3
    assert feed.cursor == 3  # exactly 3 candles processed, not the whole feed
    assert result.last_price == flat_prices[2]
    assert clock.sleeps == [ONE_HOUR_MS / 1000] * 2  # no sleep after the final iteration


def test_paper_trading_never_reprocesses_a_candle(uptrend_then_downtrend):
    feed = FakeFeed(_candles_from_closes(uptrend_then_downtrend), chunk_size=7)
    clock = FakeClock()
    strategy = SmaCrossoverStrategy(fast_window=5, slow_window=15)
    portfolio = Portfolio(cash_usd=10000.0)

    result = run_paper_trading(
        _config(),
        strategy,
        portfolio,
        iterations=len(uptrend_then_downtrend),  # far more polls than needed
        lookback_candles=1,
        fetch=feed.fetch,
        sleep=clock.sleep,
    )

    assert feed.cursor == len(uptrend_then_downtrend)  # never asked to re-deliver what's already seen
    assert result.trade_count == 2


def test_paper_trading_reports_fills_via_on_fill_callback(uptrend_then_downtrend):
    feed = FakeFeed(_candles_from_closes(uptrend_then_downtrend))
    clock = FakeClock()
    strategy = SmaCrossoverStrategy(fast_window=5, slow_window=15)
    portfolio = Portfolio(cash_usd=10000.0)
    reported: list[tuple[Fill, float]] = []

    run_paper_trading(
        _config(),
        strategy,
        portfolio,
        iterations=len(uptrend_then_downtrend),
        lookback_candles=1,
        fetch=feed.fetch,
        sleep=clock.sleep,
        on_fill=lambda fill, equity: reported.append((fill, equity)),
    )

    assert [fill.side for fill, _equity in reported] == ["buy", "sell"]


def test_paper_trading_never_places_a_real_order(uptrend_then_downtrend):
    # live_trading=True would normally require real credentials via Config,
    # but paper trading must stay simulated-only regardless — it should
    # never call place_order or otherwise reach for real credentials.
    feed = FakeFeed(_candles_from_closes(uptrend_then_downtrend))
    clock = FakeClock()
    strategy = SmaCrossoverStrategy(fast_window=5, slow_window=15)
    portfolio = Portfolio(cash_usd=10000.0)

    result = run_paper_trading(
        _config(live_trading=True, api_key="k", api_secret="s"),
        strategy,
        portfolio,
        iterations=len(uptrend_then_downtrend),
        lookback_candles=1,
        fetch=feed.fetch,
        sleep=clock.sleep,
    )

    assert result.trade_count == 2
    assert all(fill.side in ("buy", "sell") for fill in portfolio.fills)


def test_paper_trading_requires_explicit_poll_seconds_for_unparseable_timeframe():
    feed = FakeFeed(_candles_from_closes([100.0]))
    with pytest.raises(ValueError):
        run_paper_trading(
            _config(timeframe="weird"),
            SmaCrossoverStrategy(fast_window=1, slow_window=2),
            Portfolio(cash_usd=10000.0),
            iterations=1,
            fetch=feed.fetch,
            sleep=lambda _seconds: None,
        )
