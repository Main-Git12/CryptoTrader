import type { PriceFeed } from "./priceFeed/types";
import { InsufficientFundsError, NoPositionToSellError } from "./types";
import type { PortfolioStore, Trade, TradeDecision } from "./types";

/**
 * Simulates order execution against a real (or simulated) price feed —
 * no real money ever moves. Fixed position sizing: every buy spends
 * exactly `positionSizeUsd`, every sell exits the entire position. This
 * is simpler than partial sizing/scaling and easier to reason about the
 * P&L of, at the cost of not modeling more realistic position management.
 */
export class PaperExchange {
  constructor(
    private readonly priceFeed: PriceFeed,
    private readonly portfolioStore: PortfolioStore,
    private readonly positionSizeUsd: number = 100
  ) {}

  /** Returns null for a "hold" decision (nothing to execute). Persists the updated portfolio on any trade. */
  async execute(decision: TradeDecision): Promise<Trade | null> {
    if (decision.action === "hold") return null;

    const state = await this.portfolioStore.load();
    const price = await this.priceFeed.getPrice(decision.ticker);

    if (decision.action === "buy") {
      if (state.cashUsd < this.positionSizeUsd) {
        throw new InsufficientFundsError(decision.ticker, this.positionSizeUsd, state.cashUsd);
      }

      const quantity = this.positionSizeUsd / price;
      state.cashUsd -= this.positionSizeUsd;
      state.holdings[decision.ticker] = (state.holdings[decision.ticker] ?? 0) + quantity;

      const trade: Trade = {
        timestamp: new Date().toISOString(),
        ticker: decision.ticker,
        action: "buy",
        quantity,
        price,
        usdValue: this.positionSizeUsd,
        reason: decision.reason,
      };
      state.trades.push(trade);
      await this.portfolioStore.save(state);
      return trade;
    }

    // sell
    const quantity = state.holdings[decision.ticker] ?? 0;
    if (quantity <= 0) throw new NoPositionToSellError(decision.ticker);

    const usdValue = quantity * price;
    state.cashUsd += usdValue;
    state.holdings[decision.ticker] = 0;

    const trade: Trade = {
      timestamp: new Date().toISOString(),
      ticker: decision.ticker,
      action: "sell",
      quantity,
      price,
      usdValue,
      reason: decision.reason,
    };
    state.trades.push(trade);
    await this.portfolioStore.save(state);
    return trade;
  }
}
