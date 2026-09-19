import { randomBytes } from "node:crypto";
import jwt from "jsonwebtoken";
import type { TrackedTicker } from "../../tickers";
import type { PriceFeed } from "./types";

const PRODUCT_IDS: Record<TrackedTicker, string> = {
  BTC: "BTC-USD",
  ETH: "ETH-USD",
  SOL: "SOL-USD",
  XRP: "XRP-USD",
  DOGE: "DOGE-USD",
  AVAX: "AVAX-USD",
  MATIC: "MATIC-USD",
  DOT: "DOT-USD",
  LINK: "LINK-USD",
  ADA: "ADA-USD",
};

const API_HOST = "api.coinbase.com";

export class CoinbaseNotConfiguredError extends Error {
  constructor(missingEnvVars: string[]) {
    super(`Coinbase price feed is not configured — missing: ${missingEnvVars.join(", ")}`);
    this.name = "CoinbaseNotConfiguredError";
  }
}

interface CoinbaseProductResponse {
  price: string;
}

export interface CoinbasePriceFeedConfig {
  /** Coinbase Developer Platform key name, e.g. "organizations/{org_id}/apiKeys/{key_id}". */
  apiKeyName?: string;
  /** The EC private key PEM associated with that key (ES256 / P-256). */
  privateKeyPem?: string;
  fetchImpl?: typeof fetch;
  baseUrl?: string;
}

/**
 * Coinbase Developer Platform (Advanced Trade) price feed. Authenticates
 * with a short-lived ES256 JWT per request — CDP's documented auth scheme,
 * distinct from the older HMAC-based Coinbase Exchange/Pro API.
 *
 * IMPORTANT: this has only been tested against a self-signed test key pair
 * (see coinbase.test.ts) and mocked HTTP responses — this sandbox's network
 * policy blocks api.coinbase.com, so it has never made a real request. Treat
 * it as "correctly implements the documented protocol, unverified against
 * the live API" until you've run it somewhere with real network access.
 * Read-only (price lookups) — does not place orders.
 */
export class CoinbasePriceFeed implements PriceFeed {
  private readonly apiKeyName: string | undefined;
  private readonly privateKeyPem: string | undefined;
  private readonly fetchImpl: typeof fetch;
  private readonly baseUrl: string;

  constructor(config: CoinbasePriceFeedConfig = {}) {
    this.apiKeyName = config.apiKeyName ?? process.env.COINBASE_CDP_API_KEY_NAME;
    this.privateKeyPem = config.privateKeyPem ?? process.env.COINBASE_CDP_PRIVATE_KEY;
    this.fetchImpl = config.fetchImpl ?? fetch;
    this.baseUrl = config.baseUrl ?? `https://${API_HOST}`;
  }

  private buildAuthHeader(method: string, path: string): string {
    const apiKeyName = this.apiKeyName;
    const privateKeyPem = this.privateKeyPem;
    if (!apiKeyName || !privateKeyPem) {
      throw new CoinbaseNotConfiguredError(["COINBASE_CDP_API_KEY_NAME", "COINBASE_CDP_PRIVATE_KEY"]);
    }

    // jsonwebtoken's JwtHeader type doesn't know about CDP's custom `nonce`
    // header field, hence the cast.
    const header = { alg: "ES256", kid: apiKeyName, nonce: randomBytes(16).toString("hex") } as jwt.JwtHeader;

    const token = jwt.sign(
      {
        sub: apiKeyName,
        iss: "cdp",
        nbf: Math.floor(Date.now() / 1000),
        exp: Math.floor(Date.now() / 1000) + 120,
        uri: `${method} ${API_HOST}${path}`,
      },
      privateKeyPem,
      { algorithm: "ES256", header }
    );

    return `Bearer ${token}`;
  }

  async getPrice(ticker: TrackedTicker): Promise<number> {
    const productId = PRODUCT_IDS[ticker];
    const path = `/api/v3/brokerage/products/${productId}`;

    const response = await this.fetchImpl(`${this.baseUrl}${path}`, {
      headers: { Authorization: this.buildAuthHeader("GET", path) },
    });

    if (!response.ok) throw new Error(`Coinbase price request failed for ${ticker}: ${response.status}`);

    const data = (await response.json()) as CoinbaseProductResponse;
    const price = Number(data.price);
    if (!Number.isFinite(price)) throw new Error(`Coinbase response had an unparseable price for ${ticker}: ${data.price}`);

    return price;
  }
}
