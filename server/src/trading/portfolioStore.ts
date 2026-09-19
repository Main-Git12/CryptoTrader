import { mkdir, readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";
import type { PortfolioState, PortfolioStore } from "./types";

const DEFAULT_STARTING_CASH_USD = 10_000;

export class JsonPortfolioStore implements PortfolioStore {
  private readonly filePath: string;
  private readonly startingCashUsd: number;

  constructor(
    dataDir: string = process.env.TICKER_DATA_DIR ?? join(process.cwd(), "data"),
    startingCashUsd: number = DEFAULT_STARTING_CASH_USD
  ) {
    this.filePath = join(dataDir, "portfolio.json");
    this.startingCashUsd = startingCashUsd;
  }

  async load(): Promise<PortfolioState> {
    try {
      const raw = await readFile(this.filePath, "utf-8");
      return JSON.parse(raw) as PortfolioState;
    } catch (err) {
      if ((err as NodeJS.ErrnoException).code !== "ENOENT") throw err;
      return { cashUsd: this.startingCashUsd, holdings: {}, trades: [] };
    }
  }

  async save(state: PortfolioState): Promise<void> {
    await mkdir(join(this.filePath, ".."), { recursive: true });
    await writeFile(this.filePath, JSON.stringify(state, null, 2), "utf-8");
  }
}
