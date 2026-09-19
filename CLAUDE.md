# crypto-trader — project conventions

## Architecture

- `src/crypto_trader/config.py` — single source of truth for runtime config, read from env vars. Never hardcode credentials here or anywhere else.
- `src/crypto_trader/exchange.py` — all exchange I/O goes through this wrapper (ccxt). Public market data (`fetch_ohlcv`) never requires credentials. `place_order` is gated behind `Config.live_trading` and real credentials — don't bypass that gate to "test" live order placement.
- `src/crypto_trader/portfolio.py` — the simulated wallet used by backtests and paper trading. Fee-aware; equity is cash + position * mark price.
- `src/crypto_trader/strategy.py` — `Strategy` is the interface (`next_signal(price_history) -> Signal`); add new strategies here, don't special-case them in `engine.py`.
- `src/crypto_trader/engine.py` — orchestrates strategy + portfolio + exchange over a sequence of candles.

## Working conventions

- **No fabricated credentials, ever:** don't invent exchange API keys, wallet addresses, or auth tokens anywhere — in code, tests, `.env.example`, or docs. Real ones come from the user.
- **Paper mode is the safe default:** `Config.live_trading` defaults to `False`. Any change that makes live order placement easier to reach accidentally (e.g. relaxing the credential guard, defaulting `live_trading` to `True`) needs explicit sign-off, not just a passing test.
- **Public data needs no auth:** `fetch_ohlcv` and other read-only market-data calls should work with no API key configured — don't add an auth requirement to them.
- **Test with synthetic data:** strategy and portfolio tests use deterministic synthetic price series (see `tests/conftest.py`), not live network calls — the suite must pass with no network access and no credentials.
- **Run the checks before considering a change done:** `pytest` needs to pass.
