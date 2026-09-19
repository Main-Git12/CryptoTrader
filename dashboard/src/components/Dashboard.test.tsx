import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import Dashboard from "./Dashboard";
import { api } from "../lib/api";

vi.mock("../lib/api", () => ({
  api: {
    getTopTickers: vi.fn(),
    getTimeSeries: vi.fn(),
  },
}));

describe("Dashboard", () => {
  afterEach(() => {
    vi.resetAllMocks();
  });

  it("renders the disclaimer and fetched data", async () => {
    vi.mocked(api.getTopTickers).mockResolvedValue({
      since: "2025-01-01",
      tickers: [{ ticker: "BTC", mentionCount: 12, averageSentiment: 0.2 }],
    });
    vi.mocked(api.getTimeSeries).mockResolvedValue({ ticker: "BTC", since: "2025-01-01", points: [] });

    render(<Dashboard />);

    expect(screen.getByText(/informational only/i)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("cell", { name: "BTC" })).toBeInTheDocument());
    expect(screen.queryByText(/couldn't reach the api/i)).not.toBeInTheDocument();
  });

  it("shows an error message when the API is unreachable", async () => {
    vi.mocked(api.getTopTickers).mockRejectedValue(new Error("Request failed: 500 /api/tickers"));
    vi.mocked(api.getTimeSeries).mockRejectedValue(new Error("Request failed: 500 /api/tickers/BTC/timeseries"));

    render(<Dashboard />);

    await waitFor(() => expect(screen.getByText(/couldn't reach the api/i)).toBeInTheDocument());
    expect(screen.getByText(/500/)).toBeInTheDocument();
  });

  it("switching the selected ticker re-fetches its time series", async () => {
    vi.mocked(api.getTopTickers).mockResolvedValue({ since: "2025-01-01", tickers: [] });
    vi.mocked(api.getTimeSeries).mockResolvedValue({ ticker: "BTC", since: "2025-01-01", points: [] });

    render(<Dashboard />);

    await waitFor(() => expect(api.getTimeSeries).toHaveBeenCalledWith("BTC", expect.any(String)));

    fireEvent.click(screen.getByRole("button", { name: "ETH" }));

    await waitFor(() => expect(api.getTimeSeries).toHaveBeenCalledWith("ETH", expect.any(String)));
  });
});
