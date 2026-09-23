import argparse

from .config import Config
from .engine import run_paper_trading
from .portfolio import Fill, Portfolio
from .state import load_paper_trading_state, save_paper_trading_state
from .strategy import SmaCrossoverStrategy


def _print_fill(fill: Fill, equity: float) -> None:
    print(
        f"{fill.side.upper():4} {fill.quantity:.6f} @ ${fill.price:,.2f} "
        f"(fee ${fill.fee:.2f})  equity=${equity:,.2f}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Paper-trade the SMA-crossover strategy against live market data with a "
            "simulated wallet — no exchange account, no credentials, no real orders."
        )
    )
    parser.add_argument("--exchange", default="kraken")
    parser.add_argument("--symbol", default="BTC/USD")
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--fast-window", type=int, default=10)
    parser.add_argument("--slow-window", type=int, default=30)
    parser.add_argument("--starting-balance-usd", type=float, default=10000.0)
    parser.add_argument(
        "--iterations",
        type=int,
        default=None,
        help="Stop after this many polls instead of running until interrupted (Ctrl-C).",
    )
    parser.add_argument(
        "--state-file",
        default=None,
        help=(
            "Persist the wallet, recent price history, and polling cursor here after each run, and "
            "resume from it on the next one instead of starting fresh. Without this, every run starts "
            "over from --starting-balance-usd and re-fetches from scratch."
        ),
    )
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
    strategy = SmaCrossoverStrategy(fast_window=args.fast_window, slow_window=args.slow_window)

    resume_close_prices = None
    resume_since_ms = None
    loaded = load_paper_trading_state(args.state_file) if args.state_file else None
    if loaded is not None:
        portfolio = loaded.portfolio
        resume_close_prices = loaded.close_prices
        resume_since_ms = loaded.since_ms
        print(f"Resumed from {args.state_file}: cash=${portfolio.cash_usd:,.2f} position={portfolio.position_qty}")
    else:
        portfolio = Portfolio(cash_usd=config.starting_balance_usd)

    print(f"Paper trading {config.symbol} on {config.exchange_id} ({config.timeframe} candles) — Ctrl-C to stop")
    try:
        result = run_paper_trading(
            config,
            strategy,
            portfolio,
            iterations=args.iterations,
            on_fill=_print_fill,
            resume_close_prices=resume_close_prices,
            resume_since_ms=resume_since_ms,
        )
    except KeyboardInterrupt:
        result = None
    finally:
        if args.state_file:
            saved_prices = result.close_prices if result is not None else (resume_close_prices or [])
            saved_since_ms = result.since_ms if result is not None else resume_since_ms
            save_paper_trading_state(args.state_file, portfolio, saved_prices, saved_since_ms)
            print(f"State saved to {args.state_file}")

    print(f"Trades: {len(portfolio.fills)}")
    if result is not None and result.last_price is not None:
        print(f"Final equity: ${portfolio.equity(result.last_price):,.2f}")
    elif portfolio.fills:
        print(f"Final equity: ${portfolio.equity(portfolio.fills[-1].price):,.2f}")
    else:
        print("No candles processed yet — nothing to report.")


if __name__ == "__main__":
    main()
