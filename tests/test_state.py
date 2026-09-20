from crypto_trader.portfolio import Fill, Portfolio
from crypto_trader.state import MAX_PERSISTED_CANDLES, load_paper_trading_state, save_paper_trading_state


def test_load_returns_none_when_file_is_missing(tmp_path):
    assert load_paper_trading_state(str(tmp_path / "does-not-exist.json")) is None


def test_save_then_load_round_trips_portfolio_and_history(tmp_path):
    path = str(tmp_path / "state.json")
    fill = Fill(side="buy", price=100.0, quantity=0.5, fee=0.05)
    portfolio = Portfolio(cash_usd=4000.0, position_qty=0.5, fills=[fill])
    close_prices = [100.0, 101.0, 102.0]

    save_paper_trading_state(path, portfolio, close_prices, since_ms=123456)
    loaded = load_paper_trading_state(path)

    assert loaded is not None
    assert loaded.portfolio.cash_usd == 4000.0
    assert loaded.portfolio.position_qty == 0.5
    assert loaded.portfolio.fills == [fill]
    assert loaded.close_prices == close_prices
    assert loaded.since_ms == 123456


def test_save_truncates_history_to_max_persisted_candles(tmp_path):
    path = str(tmp_path / "state.json")
    portfolio = Portfolio(cash_usd=10000.0)
    close_prices = [float(i) for i in range(MAX_PERSISTED_CANDLES + 50)]

    save_paper_trading_state(path, portfolio, close_prices, since_ms=None)
    loaded = load_paper_trading_state(path)

    assert loaded is not None
    assert len(loaded.close_prices) == MAX_PERSISTED_CANDLES
    assert loaded.close_prices == close_prices[-MAX_PERSISTED_CANDLES:]


def test_save_leaves_no_tmp_file_behind(tmp_path):
    path = tmp_path / "state.json"
    save_paper_trading_state(str(path), Portfolio(cash_usd=10000.0), [], since_ms=None)

    assert path.exists()
    assert not path.with_suffix(".json.tmp").exists()
