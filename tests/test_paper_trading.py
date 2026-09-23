import pytest

from crypto_trader.config import Config
from crypto_trader.engine import run_paper_trading
from crypto_trader.portfolio import Fill, Portfolio
from crypto_trader.risk import RiskLimits, RiskManager
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


def test_paper_trading_resume_replay_rebuilds_indicators_without_reexecuting_trades(uptrend_then_downtrend):
    # Replaying resume_close_prices must rebuild the strategy's internal
    # averages so it can react correctly to new candles, without re-firing
    # trades against the portfolio for candles a prior run already acted on.
    portfolio = Portfolio(cash_usd=10000.0)

    def fetch_nothing_new(config: Config, since_ms: int | None = None, limit: int | None = None) -> list[list[float]]:
        return []

    result = run_paper_trading(
        _config(),
        SmaCrossoverStrategy(fast_window=5, slow_window=15),
        portfolio,
        iterations=1,
        fetch=fetch_nothing_new,
        sleep=lambda _seconds: None,
        resume_close_prices=uptrend_then_downtrend,
        resume_since_ms=999,
    )

    assert result.trade_count == 0
    assert portfolio.fills == []
    assert portfolio.cash_usd == 10000.0
    assert result.last_price == uptrend_then_downtrend[-1]


def test_paper_trading_resume_skips_the_initial_lookback_fetch():
    calls: list[dict[str, int | None]] = []

    def fetch(config: Config, since_ms: int | None = None, limit: int | None = None) -> list[list[float]]:
        calls.append({"since_ms": since_ms, "limit": limit})
        return []

    run_paper_trading(
        _config(),
        SmaCrossoverStrategy(fast_window=1, slow_window=2),
        Portfolio(cash_usd=10000.0),
        iterations=1,
        fetch=fetch,
        sleep=lambda _seconds: None,
        resume_close_prices=[100.0, 101.0, 102.0],
        resume_since_ms=999,
    )

    assert calls == [{"since_ms": 999, "limit": None}]


def test_paper_trading_resume_continues_as_if_it_never_stopped(uptrend_then_downtrend):
    split = 30
    first_half, second_half = uptrend_then_downtrend[:split], uptrend_then_downtrend[split:]

    continuous_portfolio = Portfolio(cash_usd=10000.0)
    continuous_feed = FakeFeed(_candles_from_closes(uptrend_then_downtrend))
    continuous_result = run_paper_trading(
        _config(),
        SmaCrossoverStrategy(fast_window=5, slow_window=15),
        continuous_portfolio,
        iterations=len(uptrend_then_downtrend),
        lookback_candles=1,
        fetch=continuous_feed.fetch,
        sleep=FakeClock().sleep,
    )

    # Same portfolio object carries across the "restart" (as state.py would
    # reload it), but a brand-new Strategy instance stands in for the one
    # that only existed in the previous process's memory.
    resumed_portfolio = Portfolio(cash_usd=10000.0)
    first_run = run_paper_trading(
        _config(),
        SmaCrossoverStrategy(fast_window=5, slow_window=15),
        resumed_portfolio,
        iterations=len(first_half),
        lookback_candles=1,
        fetch=FakeFeed(_candles_from_closes(first_half)).fetch,
        sleep=FakeClock().sleep,
    )
    second_run = run_paper_trading(
        _config(),
        SmaCrossoverStrategy(fast_window=5, slow_window=15),  # fresh instance, no memory of first_run
        resumed_portfolio,
        iterations=len(second_half),
        lookback_candles=1,
        fetch=FakeFeed(_candles_from_closes(second_half)).fetch,
        sleep=FakeClock().sleep,
        resume_close_prices=first_run.close_prices,
        resume_since_ms=first_run.since_ms,
    )

    assert first_run.trade_count + second_run.trade_count == continuous_result.trade_count
    assert resumed_portfolio.position_qty == continuous_result.portfolio.position_qty
    assert resumed_portfolio.cash_usd == pytest.approx(continuous_result.portfolio.cash_usd)


def test_paper_trading_survives_a_failed_poll_and_keeps_going(flat_prices):
    # A process meant to run for weeks can't exit the first time an exchange
    # times out or rate-limits.
    feed = FakeFeed(_candles_from_closes(flat_prices))
    clock = FakeClock()
    errors: list[Exception] = []
    calls = {"n": 0}

    def flaky_fetch(config: Config, since_ms: int | None = None, limit: int | None = None) -> list[list[float]]:
        calls["n"] += 1
        if calls["n"] == 2:
            raise ConnectionError("exchange timed out")
        return feed.fetch(config, since_ms=since_ms, limit=limit)

    result = run_paper_trading(
        _config(),
        SmaCrossoverStrategy(fast_window=5, slow_window=15),
        Portfolio(cash_usd=10000.0),
        iterations=4,
        lookback_candles=1,
        fetch=flaky_fetch,
        sleep=clock.sleep,
        on_error=errors.append,
    )

    assert calls["n"] == 4  # kept polling after the failure
    assert [type(e) for e in errors] == [ConnectionError]
    assert result.last_price is not None


def test_paper_trading_resumes_from_the_same_cursor_after_a_failure(flat_prices):
    # A failed poll must not advance the cursor: the candles it missed are
    # still waiting on the next one.
    seen_since: list[int | None] = []

    def failing_fetch(config: Config, since_ms: int | None = None, limit: int | None = None) -> list[list[float]]:
        seen_since.append(since_ms)
        raise TimeoutError("still down")

    run_paper_trading(
        _config(),
        SmaCrossoverStrategy(fast_window=5, slow_window=15),
        Portfolio(cash_usd=10000.0),
        iterations=3,
        fetch=failing_fetch,
        sleep=lambda _seconds: None,
        resume_since_ms=4242,
        on_error=lambda _error: None,
    )

    assert seen_since == [4242, 4242, 4242]


def test_paper_trading_without_an_error_handler_still_survives_a_failure():
    def always_fails(config: Config, since_ms: int | None = None, limit: int | None = None) -> list[list[float]]:
        raise ConnectionError("down")

    result = run_paper_trading(
        _config(),
        SmaCrossoverStrategy(fast_window=5, slow_window=15),
        Portfolio(cash_usd=10000.0),
        iterations=2,
        fetch=always_fails,
        sleep=lambda _seconds: None,
    )

    assert result.trade_count == 0


def test_interrupt_returns_the_history_accumulated_so_far(flat_prices):
    # Stopping must not strand the caller with no result: the price history
    # and cursor built up during the run are exactly what has to be
    # persisted, and losing them would silently reset a long-running
    # deployment to its starting state.
    feed = FakeFeed(_candles_from_closes(flat_prices))
    calls = {"n": 0}

    def fetch_then_interrupt(
        config: Config, since_ms: int | None = None, limit: int | None = None
    ) -> list[list[float]]:
        calls["n"] += 1
        if calls["n"] > 3:
            raise KeyboardInterrupt
        return feed.fetch(config, since_ms=since_ms, limit=limit)

    result = run_paper_trading(
        _config(),
        SmaCrossoverStrategy(fast_window=5, slow_window=15),
        Portfolio(cash_usd=10000.0),
        iterations=None,  # would otherwise run forever
        lookback_candles=1,
        fetch=fetch_then_interrupt,
        sleep=lambda _seconds: None,
    )

    assert len(result.close_prices) == 3
    assert result.since_ms is not None
    assert result.last_price == flat_prices[2]


def test_interrupt_during_the_wait_also_returns_progress(flat_prices):
    feed = FakeFeed(_candles_from_closes(flat_prices))

    def interrupting_sleep(_seconds: float) -> None:
        raise KeyboardInterrupt

    result = run_paper_trading(
        _config(),
        SmaCrossoverStrategy(fast_window=5, slow_window=15),
        Portfolio(cash_usd=10000.0),
        iterations=None,
        lookback_candles=1,
        fetch=feed.fetch,
        sleep=interrupting_sleep,
    )

    assert len(result.close_prices) == 1  # one poll landed before the wait was cut short


def test_paper_trading_honours_a_risk_manager(uptrend_then_downtrend):
    feed = FakeFeed(_candles_from_closes(uptrend_then_downtrend))
    portfolio = Portfolio(cash_usd=10000.0)
    risk = RiskManager(RiskLimits(max_position_fraction=0.25), starting_equity=10000.0)

    run_paper_trading(
        _config(),
        SmaCrossoverStrategy(fast_window=5, slow_window=15),
        portfolio,
        iterations=len(uptrend_then_downtrend),
        lookback_candles=1,
        fetch=feed.fetch,
        sleep=FakeClock().sleep,
        risk=risk,
    )

    buys = [fill for fill in portfolio.fills if fill.side == "buy"]
    assert buys, "expected the crossover to fire at least one buy"
    # A quarter-sized buy costs about a quarter of the account.
    assert buys[0].price * buys[0].quantity == pytest.approx(2500.0, rel=0.01)


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
