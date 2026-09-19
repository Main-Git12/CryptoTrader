import type { TrackedTicker } from "../tickers";
import type { Collector, Mention } from "./types";
import { CollectorNotImplementedError } from "./types";

/**
 * Structural stub. A Discord bot (free) must be invited to each specific
 * server with permission to read the channels you want monitored — like
 * Telegram, there is no "monitor all of Discord" mode. Implementing this
 * for real needs DISCORD_BOT_TOKEN plus the list of guild/channel ids the
 * bot has been invited to. See server/src/collectors/README.md.
 */
export class DiscordCollector implements Collector {
  readonly platform = "discord" as const;

  async collect(_tickers: readonly TrackedTicker[]): Promise<Mention[]> {
    throw new CollectorNotImplementedError(
      "discord",
      "requires DISCORD_BOT_TOKEN and the bot to be invited into specific servers/channels with read access"
    );
  }
}
