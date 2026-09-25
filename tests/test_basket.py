import pytest

from crypto_trader.basket import _aggregate_equity, run_basket_backtest
from crypto_trader.risk import RiskLimits, RiskManager, annualized_volatility
from crypto_trader.strategy import Signal, TimeSeriesMomentumStrategy


def _rising(n: int = 120, start: float = 100.0, step: float = 1.0) -> list[float]:
    return [start + i * step for i in range(n)]


def _falling(n: int = 120, start: float = 220.0, step: float = 1.0) -> list[float]:
    return [start - i * step for i in range(n)]


# --- time-series momentum ---------------------------------------------------


def test_momentum_rejects_a_non_positive_lookback():
    with pytest.raises(ValueError):
        TimeSeriesMomentumStrategy(lookback=0)
    with pytest.raises(ValueError):
        TimeSeriesMomentumStrategy(lookback=-5)


def test_momentum_holds_until_it_has_a_full_lookback():
    strategy = TimeSeriesMomentumStrategy(lookback=10)
    for i in range(1, 11):
        assert strategy.next_signal(_rising(i)) is Signal.HOLD


def test_momentum_goes_long_on_a_positive_trailing_return():
    strategy = TimeSeriesMomentumStrategy(lookback=10)
    assert strategy.next_signal(_rising(30)) is Signal.BUY


def test_momentum_exits_on_a_negative_trailing_return():
    strategy = TimeSeriesMomentumStrategy(lookback=10)
    assert strategy.next_signal(_falling(30)) is Signal.SELL


def test_momentum_looks_back_exactly_the_requested_distance():
    # Price is higher than 3 candles ago but lower than 10 ago: the lookback
    # is what decides, which is the whole parameter.
    prices = [200.0] * 5 + [100.0] * 10 + [110.0]

    assert TimeSeriesMomentumStrategy(lookback=3).next_signal(prices) is Signal.BUY
    assert TimeSeriesMomentumStrategy(lookback=12).next_signal(prices) is Signal.SELL


# --- volatility targeting ---------------------------------------------------


def test_annualized_volatility_needs_movement_and_enough_points():
    assert annualized_volatility([100.0], 365) is None
    assert annualized_volatility([100.0, 100.0, 100.0], 365) is None


def test_annualized_volatility_grows_with_choppiness():
    calm = annualized_volatility([100.0, 100.5, 100.2, 100.6, 100.3], 365)
    wild = annualized_volatility([100.0, 130.0, 80.0, 140.0, 70.0], 365)

    assert calm is not None and wild is not None
    assert wild > calm


def test_volatility_target_scales_a_position_down_when_the_asset_is_wild():
    limits = RiskLimits(max_position_fraction=1.0, target_volatility_pct=0.40, periods_per_year=365)
    risk = RiskManager(limits, starting_equity=10000.0)
    wild = [100.0, 130.0, 80.0, 140.0, 70.0, 150.0]

    sized = risk.buy_quantity(cash_usd=10000.0, equity=10000.0, price=100.0, recent_prices=wild)
    unsized = risk.buy_quantity(cash_usd=10000.0, equity=10000.0, price=100.0)

    assert sized < unsized


def test_volatility_target_never_scales_above_the_position_cap():
    # Very calm asset: targeting would ask for leverage, which this wallet
    # doesn't have, so the cap must remain the ceiling.
    limits = RiskLimits(max_position_fraction=0.5, target_volatility_pct=2.0, periods_per_year=365)
    risk = RiskManager(limits, starting_equity=10000.0)
    calm = [100.0, 100.01, 100.02, 100.01, 100.03]

    sized = risk.buy_quantity(cash_usd=10000.0, equity=10000.0, price=100.0, recent_prices=calm)
    capped = risk.buy_quantity(cash_usd=10000.0, equity=10000.0, price=100.0)

    assert sized == pytest.approx(capped)


def test_volatility_target_is_inert_without_recent_prices():
    limits = RiskLimits(max_position_fraction=0.5, target_volatility_pct=0.20)
    risk = RiskManager(limits, starting_equity=10000.0)

    assert risk.buy_quantity(10000.0, 10000.0, 100.0) == pytest.approx(
        risk.buy_quantity(10000.0, 10000.0, 100.0, recent_prices=None)
    )


def test_limits_validate_the_new_fields():
    with pytest.raises(ValueError):
        RiskLimits(target_volatility_pct=0)
    with pytest.raises(ValueError):
        RiskLimits(periods_per_year=0)
    with pytest.raises(ValueError):
        RiskLimits(volatility_lookback=1)


# --- basket -----------------------------------------------------------------


def test_aggregate_equity_truncates_to_the_shortest_sleeve():
    from crypto_trader.basket import Sleeve
    from crypto_trader.engine import BacktestResult
    from crypto_trader.metrics import compute_metrics
    from crypto_trader.portfolio import Portfolio

    def sleeve(symbol: str, curve: list[float]) -> Sleeve:
        result = BacktestResult(portfolio=Portfolio(cash_usd=0.0), equity_curve=curve, trade_count=0)
        return Sleeve(symbol=symbol, result=result, metrics=compute_metrics(result, 100.0))

    aggregated = _aggregate_equity([sleeve("A", [1.0, 2.0, 3.0, 4.0]), sleeve("B", [10.0, 20.0])])

    assert aggregated == [11.0, 22.0]


def test_basket_splits_capital_evenly_across_symbols():
    prices = {"A/USD": _rising(), "B/USD": _rising(), "C/USD": _rising(), "D/USD": _rising()}

    basket = run_basket_backtest(
        prices, lambda: TimeSeriesMomentumStrategy(lookback=10), starting_balance_usd=10000.0, min_history=11
    )

    assert len(basket.sleeves) == 4
    # Four equal sleeves of a rising market: the basket starts at the full
    # balance, not at one sleeve's worth.
    assert basket.equity_curve[0] == pytest.approx(10000.0, rel=0.01)


def test_basket_skips_symbols_without_enough_history():
    prices = {"LONG/USD": _rising(120), "SHORT/USD": _rising(3)}

    basket = run_basket_backtest(
        prices, lambda: TimeSeriesMomentumStrategy(lookback=10), starting_balance_usd=10000.0, min_history=11
    )

    assert [sleeve.symbol for sleeve in basket.sleeves] == ["LONG/USD"]


def test_basket_with_no_usable_symbols_reports_nothing_rather_than_crashing():
    basket = run_basket_backtest(
        {"A/USD": [1.0, 2.0]}, lambda: TimeSeriesMomentumStrategy(lookback=50), starting_balance_usd=10000.0,
        min_history=51,
    )

    assert basket.sleeves == []
    assert basket.metrics is None
    assert basket.equity_curve == []


def test_basket_sleeves_cannot_spend_each_others_cash():
    # One sleeve crashing to nothing must not fund the others — independent
    # wallets are the point of the design.
    prices = {"UP/USD": _rising(120), "DOWN/USD": _falling(120, start=220.0, step=1.5)}

    basket = run_basket_backtest(
        prices, lambda: TimeSeriesMomentumStrategy(lookback=10), starting_balance_usd=10000.0, min_history=11
    )

    for sleeve in basket.sleeves:
        assert sleeve.result.portfolio.cash_usd >= 0
        assert sleeve.result.portfolio.position_qty >= 0


def test_basket_reports_a_buy_and_hold_benchmark():
    prices = {"A/USD": _rising(120), "B/USD": _rising(120)}

    basket = run_basket_backtest(
        prices, lambda: TimeSeriesMomentumStrategy(lookback=10), starting_balance_usd=10000.0, min_history=11
    )

    assert basket.buy_and_hold_return_pct is not None
    assert basket.buy_and_hold_return_pct > 0  # both sleeves rose


def test_basket_honours_risk_limits():
    prices = {"A/USD": _rising(120), "B/USD": _rising(120)}
    limits = RiskLimits(max_position_fraction=0.25)

    sized = run_basket_backtest(
        prices, lambda: TimeSeriesMomentumStrategy(lookback=10), 10000.0, min_history=11, limits=limits
    )
    unsized = run_basket_backtest(
        prices, lambda: TimeSeriesMomentumStrategy(lookback=10), 10000.0, min_history=11
    )

    assert sized.metrics is not None and unsized.metrics is not None
    # Quarter-sized exposure to a rising market gains less than full.
    assert sized.metrics.total_return_pct < unsized.metrics.total_return_pct


def test_basket_trade_count_sums_its_sleeves():
    prices = {"A/USD": _rising(120), "B/USD": _falling(120)}

    basket = run_basket_backtest(
        prices, lambda: TimeSeriesMomentumStrategy(lookback=10), starting_balance_usd=10000.0, min_history=11
    )

    assert basket.metrics is not None
    assert basket.metrics.trade_count == sum(s.result.trade_count for s in basket.sleeves)
