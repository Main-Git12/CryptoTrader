import os
from dataclasses import dataclass


class LiveTradingMisconfigured(Exception):
    """Raised when LIVE_TRADING=true but real exchange credentials aren't set."""


def _bool_env(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Config:
    exchange_id: str
    symbol: str
    timeframe: str
    starting_balance_usd: float
    live_trading: bool
    api_key: str | None
    api_secret: str | None

    def __post_init__(self) -> None:
        if self.live_trading and not (self.api_key and self.api_secret):
            raise LiveTradingMisconfigured(
                "LIVE_TRADING=true requires EXCHANGE_API_KEY and EXCHANGE_API_SECRET "
                "to both be set. Provide your own real credentials — never fabricate "
                "or guess these."
            )

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            exchange_id=os.environ.get("EXCHANGE_ID", "kraken"),
            symbol=os.environ.get("SYMBOL", "BTC/USD"),
            timeframe=os.environ.get("TIMEFRAME", "1h"),
            starting_balance_usd=float(os.environ.get("STARTING_BALANCE_USD", "10000")),
            live_trading=_bool_env("LIVE_TRADING", default=False),
            api_key=os.environ.get("EXCHANGE_API_KEY") or None,
            api_secret=os.environ.get("EXCHANGE_API_SECRET") or None,
        )
