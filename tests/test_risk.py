import pytest

from crypto_trader.engine import execute_signal, run_backtest
from crypto_trader.portfolio import Portfolio
from crypto_trader.risk import RiskLimits, RiskManager
from crypto_trader.strategy import Signal, SmaCrossoverStrategy


def test_limits_reject_an_out_of_range_position_fraction():
    with pytest.raises(ValueError):
        RiskLimits(max_position_fraction=0)
    with pytest.raises(ValueError):
        RiskLimits(max_position_fraction=1.5)
    with pytest.raises(ValueError):
        RiskLimits(max_position_fraction=-0.5)


def test_limits_reject_an_out_of_range_drawdown():
    with pytest.raises(ValueError):
        RiskLimits(max_drawdown_pct=0)
    with pytest.raises(ValueError):
        RiskLimits(max_drawdown_pct=101)


def test_manager_rejects_non_positive_starting_equity():
    with pytest.raises(ValueError):
        RiskManager(RiskLimits(), starting_equity=0)


def test_buy_quantity_caps_at_the_position_fraction():
    risk = RiskManager(RiskLimits(max_position_fraction=0.25), starting_equity=10000.0)

    quantity = risk.buy_quantity(cash_usd=10000.0, equity=10000.0, price=100.0)

    assert quantity == pytest.approx(25.0 * 0.999)  # a quarter of equity, less fee headroom


def test_buy_quantity_never_exceeds_available_cash():
    # Equity includes an open position, but only cash can fund a buy.
    risk = RiskManager(RiskLimits(max_position_fraction=1.0), starting_equity=10000.0)

    quantity = risk.buy_quantity(cash_usd=500.0, equity=10000.0, price=100.0)

    assert quantity == pytest.approx(5.0 * 0.999)


def test_buy_quantity_is_zero_without_cash_or_at_a_nonsense_price():
    risk = RiskManager(RiskLimits(), starting_equity=10000.0)

    assert risk.buy_quantity(cash_usd=0.0, equity=10000.0, price=100.0) == 0.0
    assert risk.buy_quantity(cash_usd=1000.0, equity=10000.0, price=0.0) == 0.0


def test_observe_raises_the_high_water_mark():
    risk = RiskManager(RiskLimits(max_drawdown_pct=20.0), starting_equity=10000.0)

    risk.observe(12000.0)

    assert risk.peak_equity == 12000.0
    assert not risk.halted


def test_drawdown_from_the_peak_trips_the_kill_switch():
    risk = RiskManager(RiskLimits(max_drawdown_pct=20.0), starting_equity=10000.0)

    risk.observe(12000.0)  # peak
    risk.observe(11000.0)  # -8.3%, still fine
    assert not risk.halted

    risk.observe(9600.0)  # -20% from 12000

    assert risk.halted
    assert risk.halt_reason is not None and "20" in risk.halt_reason


def test_halt_does_not_re_arm_when_equity_recovers():
    # A kill switch that resets itself the moment things look better isn't a
    # kill switch — restarting has to be a deliberate decision.
    risk = RiskManager(RiskLimits(max_drawdown_pct=10.0), starting_equity=10000.0)
    risk.observe(9000.0)
    assert risk.halted

    risk.observe(15000.0)

    assert risk.halted


def test_reset_re_arms_the_manager():
    risk = RiskManager(RiskLimits(max_drawdown_pct=10.0), starting_equity=10000.0)
    risk.observe(9000.0)

    risk.reset()

    assert not risk.halted
    assert risk.halt_reason is None
    assert risk.peak_equity == 10000.0


def test_no_drawdown_limit_never_halts():
    risk = RiskManager(RiskLimits(max_drawdown_pct=None), starting_equity=10000.0)

    risk.observe(1.0)

    assert not risk.halted


def test_execute_signal_sizes_a_buy_to_the_position_fraction():
    portfolio = Portfolio(cash_usd=10000.0)
    risk = RiskManager(RiskLimits(max_position_fraction=0.5), starting_equity=10000.0)

    fill = execute_signal(Signal.BUY, portfolio, price=100.0, risk=risk)

    assert fill is not None
    assert fill.quantity == pytest.approx(50.0 * 0.999)
    assert portfolio.cash_usd > 4900  # roughly half the account is still cash


def test_execute_signal_without_risk_stays_all_in():
    portfolio = Portfolio(cash_usd=10000.0)

    fill = execute_signal(Signal.BUY, portfolio, price=100.0)

    assert fill is not None
    assert fill.quantity == pytest.approx(100.0 * 0.999)


def test_a_halted_manager_flattens_an_open_position():
    portfolio = Portfolio(cash_usd=0.0, position_qty=10.0)
    risk = RiskManager(RiskLimits(max_drawdown_pct=10.0), starting_equity=10000.0)
    risk.observe(1000.0)  # trip it
    assert risk.halted

    fill = execute_signal(Signal.HOLD, portfolio, price=100.0, risk=risk)

    assert fill is not None and fill.side == "sell"
    assert portfolio.position_qty == 0.0


def test_a_halted_manager_refuses_to_buy():
    portfolio = Portfolio(cash_usd=10000.0)
    risk = RiskManager(RiskLimits(max_drawdown_pct=10.0), starting_equity=10000.0)
    risk.observe(1000.0)

    assert execute_signal(Signal.BUY, portfolio, price=100.0, risk=risk) is None
    assert portfolio.position_qty == 0.0
    assert portfolio.cash_usd == 10000.0


def test_backtest_with_a_tight_drawdown_limit_stops_trading(uptrend_then_downtrend):
    # On this series the crossover buys at 102 and sells at 138, so its worst
    # peak-to-trough dip is only ~1.53% — a 1% cap breaches, and leaves the
    # account flat rather than holding through the decline.
    portfolio = Portfolio(cash_usd=10000.0)
    risk = RiskManager(RiskLimits(max_drawdown_pct=1.0), starting_equity=10000.0)

    run_backtest(uptrend_then_downtrend, SmaCrossoverStrategy(5, 15), portfolio, min_history=15, risk=risk)

    assert risk.halted
    assert portfolio.position_qty == 0.0


def test_backtest_with_a_loose_drawdown_limit_never_trips(uptrend_then_downtrend):
    portfolio = Portfolio(cash_usd=10000.0)
    risk = RiskManager(RiskLimits(max_drawdown_pct=25.0), starting_equity=10000.0)

    run_backtest(uptrend_then_downtrend, SmaCrossoverStrategy(5, 15), portfolio, min_history=15, risk=risk)

    assert not risk.halted


def test_backtest_position_fraction_leaves_cash_uninvested(uptrend_then_downtrend):
    sized = Portfolio(cash_usd=10000.0)
    risk = RiskManager(RiskLimits(max_position_fraction=0.25), starting_equity=10000.0)
    run_backtest(uptrend_then_downtrend, SmaCrossoverStrategy(5, 15), sized, min_history=15, risk=risk)

    all_in = Portfolio(cash_usd=10000.0)
    run_backtest(uptrend_then_downtrend, SmaCrossoverStrategy(5, 15), all_in, min_history=15)

    # Same signals, less exposure: the quarter-sized run can't have moved as
    # far from its starting balance as the all-in one.
    assert abs(sized.cash_usd - 10000.0) < abs(all_in.cash_usd - 10000.0)
