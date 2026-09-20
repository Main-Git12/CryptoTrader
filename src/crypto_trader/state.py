import json
from dataclasses import dataclass
from pathlib import Path

from .portfolio import Fill, Portfolio

MAX_PERSISTED_CANDLES = 500


@dataclass
class LoadedPaperTradingState:
    portfolio: Portfolio
    close_prices: list[float]
    since_ms: int | None


def save_paper_trading_state(
    path: str,
    portfolio: Portfolio,
    close_prices: list[float],
    since_ms: int | None,
) -> None:
    """Persists everything needed to resume paper trading later: the wallet,
    enough recent close prices to rebuild a strategy's internal indicators
    (SMAs etc.) before trading resumes, and the timestamp cursor so polling
    picks up where it left off instead of re-fetching from scratch.

    Only the most recent `MAX_PERSISTED_CANDLES` close prices are kept —
    plenty for any reasonably-sized indicator window, and unbounded growth
    over a long-running process would otherwise never stop. Written
    write-then-rename so a save interrupted partway through never leaves a
    corrupt, half-written file behind.
    """
    payload = {
        "cash_usd": portfolio.cash_usd,
        "position_qty": portfolio.position_qty,
        "fills": [{"side": f.side, "price": f.price, "quantity": f.quantity, "fee": f.fee} for f in portfolio.fills],
        "close_prices": close_prices[-MAX_PERSISTED_CANDLES:],
        "since_ms": since_ms,
    }
    target = Path(path)
    tmp_path = target.with_suffix(target.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2))
    tmp_path.replace(target)


def load_paper_trading_state(path: str) -> LoadedPaperTradingState | None:
    """Returns None if `path` doesn't exist yet — the normal case for a
    first run, not an error condition."""
    target = Path(path)
    if not target.exists():
        return None

    payload = json.loads(target.read_text())
    fills = [Fill(**fill) for fill in payload["fills"]]
    portfolio = Portfolio(cash_usd=payload["cash_usd"], position_qty=payload["position_qty"], fills=fills)
    return LoadedPaperTradingState(
        portfolio=portfolio,
        close_prices=payload["close_prices"],
        since_ms=payload["since_ms"],
    )
