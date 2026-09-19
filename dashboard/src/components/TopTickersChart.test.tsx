import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import TopTickersChart from "./TopTickersChart";
import type { TickerSummary } from "../types";

describe("TopTickersChart", () => {
  it("shows an empty state with no tickers", () => {
    render(<TopTickersChart tickers={[]} />);
    expect(screen.getByText(/no mentions collected yet/i)).toBeInTheDocument();
  });

  it("renders a table row per ticker with a signed sentiment value", () => {
    const tickers: TickerSummary[] = [
      { ticker: "BTC", mentionCount: 42, averageSentiment: 0.35 },
      { ticker: "ETH", mentionCount: 10, averageSentiment: -0.2 },
    ];

    render(<TopTickersChart tickers={tickers} />);

    expect(screen.getByRole("cell", { name: "BTC" })).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.getByText("+0.35")).toBeInTheDocument();
    expect(screen.getByText("-0.20")).toBeInTheDocument();
  });

  it("includes a captioned table view alongside the chart", () => {
    render(<TopTickersChart tickers={[{ ticker: "BTC", mentionCount: 1, averageSentiment: 0 }]} />);
    expect(screen.getByText(/table view of the chart above/i)).toBeInTheDocument();
  });
});
