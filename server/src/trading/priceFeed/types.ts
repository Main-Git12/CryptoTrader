import type { TrackedTicker } from "../../tickers";

export interface PriceFeed {
  /** Current price in USD for a tracked ticker. Throws if the ticker can't be priced. */
  getPrice(ticker: TrackedTicker): Promise<number>;
}
