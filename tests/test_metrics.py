import pytest

from crypto_trader.engine import BacktestResult, run_backtest
from crypto_trader.metrics import compute_metrics
from crypto_trader.portfolio import Portfolio
from crypto_trader.strategy import SmaCrossoverStrategy


def test_compute_metrics_on_no_trades_reports_zero_return_and_no_win_rate(flat_prices):
    portfolio = Portfolio(cash_usd=10000.0)
    result = run_backtest(flat_prices, SmaCrossoverStrategy(5, 15), portfolio, min_history=15)

    metrics = compute_metrics(result, starting_balance_usd=10000.0)

    assert metrics.total_return_pct == pytest.approx(0.0)
    assert metrics.max_drawdown_pct == pytest.approx(0.0)
    assert metrics.win_rate is None
    assert metrics.trade_count == 0
    assert metrics.sharpe_ratio is None  # zero variance in a flat equity curve


def test_compute_metrics_reports_total_return_and_trade_count(uptrend_then_downtrend):
    portfolio = Portfolio(cash_usd=10000.0)
    result = run_backtest(uptrend_then_downtrend, SmaCrossoverStrategy(5, 15), portfolio, min_history=15)

    metrics = compute_metrics(result, starting_balance_usd=10000.0)

    expected_return_pct = (result.equity_curve[-1] - 10000.0) / 10000.0 * 100
    assert metrics.total_return_pct == pytest.approx(expected_return_pct)
    assert metrics.trade_count == 2
    assert metrics.win_rate in (0.0, 1.0)  # exactly one round trip: either a win or a loss


def test_compute_metrics_max_drawdown_captures_a_mid_curve_dip():
    # Equity rises to 200, drops to 100 (a 50% drawdown), then partially
    # recovers to 150 — looking only at the final value would miss the
    # interim drop entirely.
    result = BacktestResult(
        portfolio=Portfolio(cash_usd=150.0),
        equity_curve=[100.0, 150.0, 200.0, 150.0, 100.0, 125.0, 150.0],
        trade_count=0,
    )

    metrics = compute_metrics(result, starting_balance_usd=100.0)

    assert metrics.max_drawdown_pct == pytest.approx(50.0)


def test_compute_metrics_uses_starting_balance_when_equity_curve_is_empty():
    result = BacktestResult(portfolio=Portfolio(cash_usd=10000.0), equity_curve=[], trade_count=0)

    metrics = compute_metrics(result, starting_balance_usd=10000.0)

    assert metrics.total_return_pct == pytest.approx(0.0)
    assert metrics.max_drawdown_pct == pytest.approx(0.0)
    assert metrics.sharpe_ratio is None
