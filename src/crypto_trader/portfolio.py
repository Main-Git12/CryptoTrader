import math
from dataclasses import dataclass, field

TAKER_FEE_RATE = 0.001  # 0.1%, a typical spot-market taker fee; override per exchange later


def _require_positive_finite(name: str, value: float) -> None:
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a positive finite number, got {value}")


class InsufficientFunds(Exception):
    pass


class InsufficientPosition(Exception):
    pass


@dataclass
class Fill:
    side: str  # "buy" | "sell"
    price: float
    quantity: float
    fee: float


@dataclass
class Portfolio:
    """A simulated single-asset wallet: USD cash plus a position in one symbol."""

    cash_usd: float
    position_qty: float = 0.0
    fills: list[Fill] = field(default_factory=list)

    def buy(self, price: float, quantity: float) -> Fill:
        _require_positive_finite("price", price)
        _require_positive_finite("quantity", quantity)
        cost = price * quantity
        fee = cost * TAKER_FEE_RATE
        total = cost + fee
        if total > self.cash_usd:
            raise InsufficientFunds(f"need ${total:.2f}, have ${self.cash_usd:.2f}")
        self.cash_usd -= total
        self.position_qty += quantity
        fill = Fill(side="buy", price=price, quantity=quantity, fee=fee)
        self.fills.append(fill)
        return fill

    def sell(self, price: float, quantity: float) -> Fill:
        _require_positive_finite("price", price)
        _require_positive_finite("quantity", quantity)
        if quantity > self.position_qty:
            raise InsufficientPosition(f"need {quantity}, have {self.position_qty}")
        proceeds = price * quantity
        fee = proceeds * TAKER_FEE_RATE
        self.cash_usd += proceeds - fee
        self.position_qty -= quantity
        fill = Fill(side="sell", price=price, quantity=quantity, fee=fee)
        self.fills.append(fill)
        return fill

    def equity(self, mark_price: float) -> float:
        return self.cash_usd + self.position_qty * mark_price
