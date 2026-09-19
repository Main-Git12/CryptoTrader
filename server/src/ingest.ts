import type { Collector } from "./collectors/types";
import { CollectorNotConfiguredError, CollectorNotImplementedError } from "./collectors/types";
import { RedditCollector } from "./collectors/reddit";
import { TwitterCollector } from "./collectors/twitter";
import { TelegramCollector } from "./collectors/telegram";
import { DiscordCollector } from "./collectors/discord";
import { LexiconSentimentScorer } from "./scoring/lexicon";
import type { SentimentScorer } from "./scoring/types";
import { JsonFileStore } from "./storage/jsonFileStore";
import type { Store } from "./storage/types";
import { TRACKED_TICKERS } from "./tickers";

export interface IngestSummary {
  platform: string;
  status: "ok" | "skipped";
  mentionsFound?: number;
  added?: number;
  duplicates?: number;
  reason?: string;
}

/**
 * Runs every registered collector, scores what it finds, and writes it to
 * the store. A collector that isn't set up (missing credentials or not
 * implemented yet) is skipped with a clear reason — never treated as a
 * failure, since "X isn't configured" is expected for most of these right
 * now, not an error condition.
 */
export async function runIngest(
  collectors: Collector[] = [new RedditCollector(), new TwitterCollector(), new TelegramCollector(), new DiscordCollector()],
  scorer: SentimentScorer = new LexiconSentimentScorer(),
  store: Store = new JsonFileStore()
): Promise<IngestSummary[]> {
  const summaries: IngestSummary[] = [];

  for (const collector of collectors) {
    try {
      const mentions = await collector.collect(TRACKED_TICKERS);
      const scored = mentions.map((mention) => ({ ...mention, sentiment: scorer.score(mention.text) }));
      const { added, duplicates } = await store.addMentions(scored);
      summaries.push({ platform: collector.platform, status: "ok", mentionsFound: mentions.length, added, duplicates });
    } catch (err) {
      if (err instanceof CollectorNotConfiguredError || err instanceof CollectorNotImplementedError) {
        summaries.push({ platform: collector.platform, status: "skipped", reason: err.message });
      } else {
        throw err;
      }
    }
  }

  return summaries;
}

if (require.main === module) {
  runIngest()
    .then((summaries) => {
      for (const summary of summaries) {
        console.log(JSON.stringify(summary));
      }
    })
    .catch((err: unknown) => {
      console.error(err);
      process.exitCode = 1;
    });
}
