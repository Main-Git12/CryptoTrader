import type { TrackedTicker } from "../tickers";
import type { Collector, Mention } from "./types";
import { CollectorNotImplementedError } from "./types";

/**
 * Structural stub. X's API requires a paid plan for any meaningful read
 * volume (recent-search/filtered-stream access starts well above the free
 * tier) — implementing this for real needs your own paid API credentials
 * plus a decision on which endpoint (filtered stream vs. periodic search)
 * fits the budget. See server/src/collectors/README.md.
 */
export class TwitterCollector implements Collector {
  readonly platform = "twitter" as const;

  async collect(_tickers: readonly TrackedTicker[]): Promise<Mention[]> {
    throw new CollectorNotImplementedError(
      "twitter",
      "requires a paid X API plan and a bearer token (TWITTER_BEARER_TOKEN) — no free tier covers meaningful read volume"
    );
  }
}
