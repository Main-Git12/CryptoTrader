import { mkdir, readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";
import type { TrackedTicker } from "../tickers";
import type { AddResult, ScoredMention, Store, TickerSummary, TimeSeriesPoint } from "./types";

function hourBucketStart(isoTimestamp: string): string {
  const date = new Date(isoTimestamp);
  date.setUTCMinutes(0, 0, 0);
  return date.toISOString();
}

function average(values: number[]): number {
  if (values.length === 0) return 0;
  return values.reduce((sum, v) => sum + v, 0) / values.length;
}

/**
 * A single JSON file holding every scored mention ever ingested, loaded
 * into memory and rewritten whole on each write. Fine at the mention
 * volumes this scaffold deals with; swap for a real database before this
 * needs to survive concurrent writers or six-figure record counts.
 */
export class JsonFileStore implements Store {
  private readonly filePath: string;
  private loaded = false;
  private mentions: ScoredMention[] = [];
  private knownIds = new Set<string>();

  constructor(dataDir: string = process.env.TICKER_DATA_DIR ?? join(process.cwd(), "data")) {
    this.filePath = join(dataDir, "mentions.json");
  }

  private async ensureLoaded(): Promise<void> {
    if (this.loaded) return;

    await mkdir(join(this.filePath, ".."), { recursive: true });

    try {
      const raw = await readFile(this.filePath, "utf-8");
      this.mentions = JSON.parse(raw) as ScoredMention[];
    } catch (err) {
      if ((err as NodeJS.ErrnoException).code !== "ENOENT") throw err;
      this.mentions = [];
    }

    this.knownIds = new Set(this.mentions.map((m) => m.id));
    this.loaded = true;
  }

  private async persist(): Promise<void> {
    await writeFile(this.filePath, JSON.stringify(this.mentions, null, 2), "utf-8");
  }

  async addMentions(mentions: ScoredMention[]): Promise<AddResult> {
    await this.ensureLoaded();

    let added = 0;
    let duplicates = 0;

    for (const mention of mentions) {
      if (this.knownIds.has(mention.id)) {
        duplicates++;
        continue;
      }
      this.knownIds.add(mention.id);
      this.mentions.push(mention);
      added++;
    }

    if (added > 0) await this.persist();
    return { added, duplicates };
  }

  async getTimeSeries(ticker: TrackedTicker, sinceIso: string): Promise<TimeSeriesPoint[]> {
    await this.ensureLoaded();

    const buckets = new Map<string, number[]>();
    for (const mention of this.mentions) {
      if (mention.ticker !== ticker || mention.postedAt < sinceIso) continue;
      const bucket = hourBucketStart(mention.postedAt);
      const scores = buckets.get(bucket) ?? [];
      scores.push(mention.sentiment.score);
      buckets.set(bucket, scores);
    }

    return [...buckets.entries()]
      .map(([bucketStart, scores]) => ({ bucketStart, mentionCount: scores.length, averageSentiment: average(scores) }))
      .sort((a, b) => a.bucketStart.localeCompare(b.bucketStart));
  }

  async getTopTickers(sinceIso: string, limit = 5): Promise<TickerSummary[]> {
    await this.ensureLoaded();

    const byTicker = new Map<TrackedTicker, number[]>();
    for (const mention of this.mentions) {
      if (mention.postedAt < sinceIso) continue;
      const scores = byTicker.get(mention.ticker) ?? [];
      scores.push(mention.sentiment.score);
      byTicker.set(mention.ticker, scores);
    }

    return [...byTicker.entries()]
      .map(([ticker, scores]) => ({ ticker, mentionCount: scores.length, averageSentiment: average(scores) }))
      .sort((a, b) => b.mentionCount - a.mentionCount)
      .slice(0, limit);
  }
}
