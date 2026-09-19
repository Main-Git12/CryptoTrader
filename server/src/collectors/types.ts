import type { TrackedTicker } from "../tickers";

export interface Mention {
  platform: "reddit" | "twitter" | "telegram" | "discord";
  /** Platform-specific id, used to de-duplicate re-ingested mentions. */
  id: string;
  ticker: TrackedTicker;
  text: string;
  /** ISO 8601 timestamp of when the mention was posted (not when it was collected). */
  postedAt: string;
  url: string;
}

/**
 * One implementation per platform. A collector that isn't configured with
 * real credentials must throw a clear "not configured" error from
 * `collect()` — never silently return an empty array, which would be
 * indistinguishable from "configured, genuinely nothing new."
 */
export interface Collector {
  readonly platform: Mention["platform"];
  collect(tickers: readonly TrackedTicker[]): Promise<Mention[]>;
}

/** The collector is fully implemented but missing required credentials — set the env vars named. */
export class CollectorNotConfiguredError extends Error {
  constructor(platform: string, missingEnvVars: string[]) {
    super(`${platform} collector is not configured — missing: ${missingEnvVars.join(", ")}`);
    this.name = "CollectorNotConfiguredError";
  }
}

/**
 * The collector is a structural stub only — no real API integration
 * exists yet, regardless of whether env vars are set. Distinct from
 * CollectorNotConfiguredError so "I set the credentials and it still
 * doesn't work" isn't confused with "I haven't set credentials yet."
 */
export class CollectorNotImplementedError extends Error {
  constructor(platform: string, details: string) {
    super(`${platform} collector is not implemented yet — ${details}`);
    this.name = "CollectorNotImplementedError";
  }
}
