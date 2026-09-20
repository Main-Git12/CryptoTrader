import argparse
import time

from .config import Config
from .engine import run_backtest
from .exchange import fetch_ohlcv
from .portfolio import Portfolio
from .strategy import SmaCrossoverStrategy


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Backtest the SMA-crossover strategy against real historical "
            "OHLCV data (no exchange account needed)."
        )
    )
    parser.add_argument("--exchange", default="kraken")
    parser.add_argument("--symbol", default="BTC/USD")
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--fast-window", type=int, default=10)
    parser.add_argument("--slow-window", type=int, default=30)
    parser.add_argument("--starting-balance-usd", type=float, default=10000.0)
    args = parser.parse_args()

    config = Config(
        exchange_id=args.exchange,
        symbol=args.symbol,
        timeframe=args.timeframe,
        starting_balance_usd=args.starting_balance_usd,
        live_trading=False,
        api_key=None,
        api_secret=None,
    )

    since_ms = int((time.time() - args.days * 86400) * 1000)
    candles = fetch_ohlcv(config, since_ms=since_ms)
    close_prices = [candle[4] for candle in candles]

    strategy = SmaCrossoverStrategy(fast_window=args.fast_window, slow_window=args.slow_window)
    portfolio = Portfolio(cash_usd=config.starting_balance_usd)
    result = run_backtest(close_prices, strategy, portfolio, min_history=args.slow_window)

    final_equity = result.equity_curve[-1] if result.equity_curve else config.starting_balance_usd
    pnl = final_equity - config.starting_balance_usd
    pnl_pct = (pnl / config.starting_balance_usd) * 100

    print(f"{config.symbol} on {config.exchange_id}, {len(close_prices)} candles ({config.timeframe}, ~{args.days}d)")
    print(f"Trades: {result.trade_count}")
    print(f"Starting balance: ${config.starting_balance_usd:,.2f}")
    print(f"Final equity:     ${final_equity:,.2f}")
    print(f"P&L:              ${pnl:,.2f} ({pnl_pct:+.2f}%)")


if __name__ == "__main__":
    main()
