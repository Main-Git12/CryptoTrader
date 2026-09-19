import pytest

from crypto_trader.portfolio import InsufficientFunds, InsufficientPosition, Portfolio


def test_buy_deducts_cost_plus_fee():
    portfolio = Portfolio(cash_usd=1000.0)
    fill = portfolio.buy(price=100.0, quantity=5.0)

    assert fill.fee == pytest.approx(0.5)  # 500 * 0.1%
    assert portfolio.cash_usd == pytest.approx(1000.0 - 500.0 - 0.5)
    assert portfolio.position_qty == 5.0


def test_sell_adds_proceeds_minus_fee():
    portfolio = Portfolio(cash_usd=0.0, position_qty=5.0)
    fill = portfolio.sell(price=100.0, quantity=5.0)

    assert fill.fee == pytest.approx(0.5)
    assert portfolio.cash_usd == pytest.approx(500.0 - 0.5)
    assert portfolio.position_qty == 0.0


def test_buy_rejects_when_cash_is_insufficient():
    portfolio = Portfolio(cash_usd=10.0)
    with pytest.raises(InsufficientFunds):
        portfolio.buy(price=100.0, quantity=1.0)


def test_sell_rejects_when_position_is_insufficient():
    portfolio = Portfolio(cash_usd=0.0, position_qty=1.0)
    with pytest.raises(InsufficientPosition):
        portfolio.sell(price=100.0, quantity=2.0)


def test_equity_is_cash_plus_position_at_mark_price():
    portfolio = Portfolio(cash_usd=500.0, position_qty=2.0)
    assert portfolio.equity(mark_price=100.0) == pytest.approx(700.0)
