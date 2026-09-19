import type { TrackedTicker } from "../../tickers";
import type { PriceFeed } from "./types";

/**
 * Deterministic, in-memory price feed for tests and demos — no network
 * access, no randomness. Advance through a fixed price series per ticker
 * with `advance()`, or set a price directly with `setPrice()`.
 */
export class SimulatedPriceFeed implements PriceFeed {
  private readonly series: Map<TrackedTicker, number[]> = new Map();
  private readonly index: Map<TrackedTicker, number> = new Map();

  constructor(initialSeries: Partial<Record<TrackedTicker, number[]>> = {}) {
    for (const [ticker, prices] of Object.entries(initialSeries) as [TrackedTicker, number[]][]) {
      this.series.set(ticker, prices);
      this.index.set(ticker, 0);
    }
  }

  setPrice(ticker: TrackedTicker, price: number): void {
    this.series.set(ticker, [price]);
    this.index.set(ticker, 0);
  }

  /** Moves every configured ticker to the next price in its series (holds at the last value once exhausted). */
  advance(): void {
    for (const [ticker, index] of this.index.entries()) {
      const series = this.series.get(ticker) ?? [];
      if (index < series.length - 1) this.index.set(ticker, index + 1);
    }
  }

  async getPrice(ticker: TrackedTicker): Promise<number> {
    const series = this.series.get(ticker);
    const index = this.index.get(ticker) ?? 0;
    const price = series?.[index];
    if (price === undefined) throw new Error(`SimulatedPriceFeed has no price configured for ${ticker}`);
    return price;
  }
}
