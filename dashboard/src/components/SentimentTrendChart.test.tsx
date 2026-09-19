import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import SentimentTrendChart from "./SentimentTrendChart";
import type { TimeSeriesPoint } from "../types";

describe("SentimentTrendChart", () => {
  it("shows an empty state when there are no points for the selected ticker", () => {
    render(<SentimentTrendChart selectedTicker="BTC" onSelectTicker={() => {}} points={[]} />);
    expect(screen.getByText(/no btc mentions collected yet/i)).toBeInTheDocument();
  });

  it("marks the selected ticker button as pressed", () => {
    render(<SentimentTrendChart selectedTicker="ETH" onSelectTicker={() => {}} points={[]} />);
    expect(screen.getByRole("button", { name: "ETH" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "BTC" })).toHaveAttribute("aria-pressed", "false");
  });

  it("calls onSelectTicker when a different ticker button is clicked", () => {
    const onSelectTicker = vi.fn();
    render(<SentimentTrendChart selectedTicker="BTC" onSelectTicker={onSelectTicker} points={[]} />);

    fireEvent.click(screen.getByRole("button", { name: "SOL" }));

    expect(onSelectTicker).toHaveBeenCalledWith("SOL");
  });

  it("renders a table row per time bucket when points are present", () => {
    const points: TimeSeriesPoint[] = [
      { bucketStart: "2025-01-15T10:00:00.000Z", mentionCount: 5, averageSentiment: 0.4 },
      { bucketStart: "2025-01-15T11:00:00.000Z", mentionCount: 2, averageSentiment: -0.1 },
    ];

    render(<SentimentTrendChart selectedTicker="BTC" onSelectTicker={() => {}} points={points} />);

    expect(screen.getByText(/table view of btc's hourly mentions/i)).toBeInTheDocument();
    expect(screen.getAllByRole("row")).toHaveLength(points.length + 1); // + header row
  });
});
