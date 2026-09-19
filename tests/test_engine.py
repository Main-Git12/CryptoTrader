import pytest

from crypto_trader.engine import run_backtest
from crypto_trader.portfolio import Portfolio
from crypto_trader.strategy import SmaCrossoverStrategy


def test_backtest_buys_on_uptrend_and_sells_on_downtrend(uptrend_then_downtrend):
    strategy = SmaCrossoverStrategy(fast_window=5, slow_window=15)
    portfolio = Portfolio(cash_usd=10000.0)

    result = run_backtest(uptrend_then_downtrend, strategy, portfolio, min_history=15)

    assert result.trade_count == 2  # one buy, one sell
    assert result.portfolio.position_qty == 0.0  # flat again after the sell
    assert len(result.equity_curve) == len(uptrend_then_downtrend)


def test_backtest_on_flat_prices_never_trades(flat_prices):
    strategy = SmaCrossoverStrategy(fast_window=5, slow_window=15)
    portfolio = Portfolio(cash_usd=10000.0)

    result = run_backtest(flat_prices, strategy, portfolio, min_history=15)

    assert result.trade_count == 0
    assert result.portfolio.cash_usd == pytest.approx(10000.0)
    assert result.equity_curve[-1] == pytest.approx(10000.0)


def test_backtest_never_overdraws_cash_or_position(uptrend_then_downtrend):
    strategy = SmaCrossoverStrategy(fast_window=5, slow_window=15)
    portfolio = Portfolio(cash_usd=10000.0)

    run_backtest(uptrend_then_downtrend, strategy, portfolio, min_history=15)

    assert portfolio.cash_usd >= 0
    assert portfolio.position_qty >= 0
