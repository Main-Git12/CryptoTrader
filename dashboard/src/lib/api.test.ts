import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { api } from "./api";

describe("api client", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ since: "2025-01-01", tickers: [] }), { status: 200 }))
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("getTopTickers calls the tickers endpoint with since and limit", async () => {
    await api.getTopTickers("2025-01-01T00:00:00.000Z", 3);
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining("/api/tickers?since="));
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining("limit=3"));
  });

  it("getTimeSeries calls the per-ticker endpoint", async () => {
    await api.getTimeSeries("BTC", "2025-01-01T00:00:00.000Z");
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining("/api/tickers/BTC/timeseries"));
  });

  it("throws with the status code on a non-ok response", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("error", { status: 500 })));
    await expect(api.getTopTickers("2025-01-01T00:00:00.000Z")).rejects.toThrow(/500/);
  });
});
