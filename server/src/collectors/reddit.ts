import type { TrackedTicker } from "../tickers";
import { extractTickers } from "../tickers";
import type { Collector, Mention } from "./types";
import { CollectorNotConfiguredError } from "./types";

const DEFAULT_SUBREDDITS = ["CryptoCurrency", "CryptoMarkets"];

interface RedditTokenResponse {
  access_token: string;
  expires_in: number;
}

interface RedditPostData {
  id: string;
  title: string;
  selftext?: string;
  created_utc: number;
  permalink: string;
}

interface RedditListingResponse {
  data: { children: { data: RedditPostData }[] };
}

interface CachedToken {
  accessToken: string;
  expiresAt: number;
}

export interface RedditCollectorConfig {
  clientId?: string;
  clientSecret?: string;
  userAgent?: string;
  subreddits?: string[];
  fetchImpl?: typeof fetch;
}

/**
 * Reddit's official OAuth "application only" (client-credentials) flow —
 * read-only access to public posts, no user login required. Free, but
 * does require registering a "script" type app at reddit.com/prefs/apps.
 * See server/src/collectors/README.md for setup steps.
 */
export class RedditCollector implements Collector {
  readonly platform = "reddit" as const;

  private readonly clientId: string | undefined;
  private readonly clientSecret: string | undefined;
  private readonly userAgent: string;
  private readonly subreddits: string[];
  private readonly fetchImpl: typeof fetch;
  private cachedToken: CachedToken | null = null;

  constructor(config: RedditCollectorConfig = {}) {
    this.clientId = config.clientId ?? process.env.REDDIT_CLIENT_ID;
    this.clientSecret = config.clientSecret ?? process.env.REDDIT_CLIENT_SECRET;
    this.userAgent = config.userAgent ?? process.env.REDDIT_USER_AGENT ?? "cryptotrader-sentiment-monitor:0.1.0";
    this.subreddits =
      config.subreddits ?? process.env.REDDIT_SUBREDDITS?.split(",").map((s) => s.trim()) ?? DEFAULT_SUBREDDITS;
    this.fetchImpl = config.fetchImpl ?? fetch;
  }

  private async getAccessToken(): Promise<string> {
    if (this.cachedToken && this.cachedToken.expiresAt > Date.now()) return this.cachedToken.accessToken;

    if (!this.clientId || !this.clientSecret) {
      throw new CollectorNotConfiguredError("reddit", ["REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET"]);
    }

    const basicAuth = Buffer.from(`${this.clientId}:${this.clientSecret}`).toString("base64");
    const response = await this.fetchImpl("https://www.reddit.com/api/v1/access_token", {
      method: "POST",
      headers: {
        Authorization: `Basic ${basicAuth}`,
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": this.userAgent,
      },
      body: "grant_type=client_credentials",
    });

    if (!response.ok) throw new Error(`Reddit token request failed: ${response.status}`);

    const { access_token: accessToken, expires_in: expiresIn } = (await response.json()) as RedditTokenResponse;
    this.cachedToken = { accessToken, expiresAt: Date.now() + (expiresIn - 60) * 1000 };
    return accessToken;
  }

  private async fetchSubredditPosts(subreddit: string): Promise<RedditPostData[]> {
    const accessToken = await this.getAccessToken();
    const response = await this.fetchImpl(`https://oauth.reddit.com/r/${subreddit}/new?limit=100`, {
      headers: {
        Authorization: `Bearer ${accessToken}`,
        "User-Agent": this.userAgent,
      },
    });

    if (!response.ok) throw new Error(`Reddit listing request failed for r/${subreddit}: ${response.status}`);

    const listing = (await response.json()) as RedditListingResponse;
    return listing.data.children.map((child) => child.data);
  }

  async collect(tickers: readonly TrackedTicker[]): Promise<Mention[]> {
    const wanted = new Set<TrackedTicker>(tickers);
    const mentions: Mention[] = [];

    for (const subreddit of this.subreddits) {
      const posts = await this.fetchSubredditPosts(subreddit);

      for (const post of posts) {
        const text = `${post.title} ${post.selftext ?? ""}`;
        const foundTickers = extractTickers(text).filter((ticker) => wanted.has(ticker));

        for (const ticker of foundTickers) {
          mentions.push({
            platform: "reddit",
            id: `reddit:${post.id}:${ticker}`,
            ticker,
            text,
            postedAt: new Date(post.created_utc * 1000).toISOString(),
            url: `https://www.reddit.com${post.permalink}`,
          });
        }
      }
    }

    return mentions;
  }
}
