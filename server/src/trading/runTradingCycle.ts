import { TRACKED_TICKERS, type TrackedTicker } from "../tickers";
import type { Store } from "../storage/types";
import { JsonFileStore } from "../storage/jsonFileStore";
import { CoinGeckoPriceFeed } from "./priceFeed/coingecko";
import { CoinbasePriceFeed } from "./priceFeed/coinbase";
import type { PriceFeed } from "./priceFeed/types";
import { SentimentMomentumStrategy } from "./strategies/sentimentMomentum";
import type { TradingStrategy } from "./types";
import { JsonPortfolioStore } from "./portfolioStore";
import { InsufficientFundsError, NoPositionToSellError } from "./types";
import type { PortfolioStore, Trade, TradeDecision } from "./types";
import { PaperExchange } from "./paperExchange";

const DEFAULT_WINDOW_MS = 24 * 60 * 60 * 1000;
const DEFAULT_POSITION_SIZE_USD = 100;

export interface TradingCycleResult {
  ticker: TrackedTicker;
  decision: TradeDecision;
  trade: Trade | null;
  skippedReason?: string;
}

function defaultPriceFeed(): PriceFeed {
  // Prefer the user's own Coinbase account data when it's configured;
  // CoinGecko needs no credentials and is the zero-config fallback.
  if (process.env.COINBASE_CDP_API_KEY_NAME && process.env.COINBASE_CDP_PRIVATE_KEY) {
    return new CoinbasePriceFeed();
  }
  return new CoinGeckoPriceFeed();
}

/**
 * Pulls each tracked ticker's recent sentiment summary, runs the trading
 * strategy, and executes any resulting decision against the paper
 * exchange. Never touches real money — see server/src/trading/README.md.
 */
export async function runTradingCycle(
  mentionStore: Store = new JsonFileStore(),
  priceFeed: PriceFeed = defaultPriceFeed(),
  strategy: TradingStrategy = new SentimentMomentumStrategy(),
  portfolioStore: PortfolioStore = new JsonPortfolioStore(),
  positionSizeUsd: number = DEFAULT_POSITION_SIZE_USD,
  windowMs: number = DEFAULT_WINDOW_MS
): Promise<TradingCycleResult[]> {
  const sinceIso = new Date(Date.now() - windowMs).toISOString();
  const summaries = await mentionStore.getTopTickers(sinceIso, TRACKED_TICKERS.length);
  const summaryByTicker = new Map(summaries.map((s) => [s.ticker, s]));

  const portfolioState = await portfolioStore.load();
  const exchange = new PaperExchange(priceFeed, portfolioStore, positionSizeUsd);

  const results: TradingCycleResult[] = [];

  for (const ticker of TRACKED_TICKERS) {
    const summary = summaryByTicker.get(ticker) ?? null;
    const hasOpenPosition = (portfolioState.holdings[ticker] ?? 0) > 0;
    const decision = strategy.decide({ ticker, sentimentSummary: summary, hasOpenPosition });

    try {
      const trade = await exchange.execute(decision);
      results.push({ ticker, decision, trade });
    } catch (err) {
      if (err instanceof InsufficientFundsError || err instanceof NoPositionToSellError) {
        results.push({ ticker, decision, trade: null, skippedReason: err.message });
      } else {
        throw err;
      }
    }
  }

  return results;
}

if (require.main === module) {
  runTradingCycle()
    .then(async (results) => {
      for (const result of results) {
        console.log(JSON.stringify(result));
      }
      const finalState = await new JsonPortfolioStore().load();
      console.log(
        JSON.stringify({
          cashUsd: finalState.cashUsd,
          holdings: finalState.holdings,
          totalTrades: finalState.trades.length,
        })
      );
    })
    .catch((err: unknown) => {
      console.error(err);
      process.exitCode = 1;
    });
}
