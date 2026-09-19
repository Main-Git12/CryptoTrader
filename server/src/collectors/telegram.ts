import type { TrackedTicker } from "../tickers";
import type { Collector, Mention } from "./types";
import { CollectorNotImplementedError } from "./types";

/**
 * Structural stub. A Telegram bot (free, via @BotFather) can only read
 * messages in public channels/groups it has been explicitly added to —
 * there is no "monitor all of Telegram" mode, and it cannot see private
 * DMs. Implementing this for real needs TELEGRAM_BOT_TOKEN plus a
 * TELEGRAM_CHANNELS list of channels the bot has actually joined.
 * See server/src/collectors/README.md.
 */
export class TelegramCollector implements Collector {
  readonly platform = "telegram" as const;

  async collect(_tickers: readonly TrackedTicker[]): Promise<Mention[]> {
    throw new CollectorNotImplementedError(
      "telegram",
      "requires TELEGRAM_BOT_TOKEN and a list of channels the bot has joined — public channels only, never private DMs"
    );
  }
}
