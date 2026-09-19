import type { TrackedTicker } from "../../tickers";
import type { PriceFeed } from "./types";

// CoinGecko's free "simple price" endpoint uses its own coin ids, not
// ticker symbols. No API key required for this endpoint at low volume.
const COINGECKO_IDS: Record<TrackedTicker, string> = {
  BTC: "bitcoin",
  ETH: "ethereum",
  SOL: "solana",
  XRP: "ripple",
  DOGE: "dogecoin",
  AVAX: "avalanche-2",
  MATIC: "matic-network",
  DOT: "polkadot",
  LINK: "chainlink",
  ADA: "cardano",
};

interface CoinGeckoPriceResponse {
  [coinId: string]: { usd: number };
}

export interface CoinGeckoPriceFeedConfig {
  fetchImpl?: typeof fetch;
  baseUrl?: string;
}

/**
 * Real implementation, tested here with a mocked fetch — but note this
 * can only be exercised against the live API from an environment with
 * unrestricted internet access. It is not reachable from the sandbox
 * this was built in (see server/src/trading/README.md).
 */
export class CoinGeckoPriceFeed implements PriceFeed {
  private readonly fetchImpl: typeof fetch;
  private readonly baseUrl: string;

  constructor(config: CoinGeckoPriceFeedConfig = {}) {
    this.fetchImpl = config.fetchImpl ?? fetch;
    this.baseUrl = config.baseUrl ?? "https://api.coingecko.com/api/v3";
  }

  async getPrice(ticker: TrackedTicker): Promise<number> {
    const coinId = COINGECKO_IDS[ticker];
    const response = await this.fetchImpl(`${this.baseUrl}/simple/price?ids=${coinId}&vs_currencies=usd`);

    if (!response.ok) throw new Error(`CoinGecko price request failed for ${ticker}: ${response.status}`);

    const data = (await response.json()) as CoinGeckoPriceResponse;
    const price = data[coinId]?.usd;
    if (price === undefined) throw new Error(`CoinGecko response missing a USD price for ${ticker}`);

    return price;
  }
}
