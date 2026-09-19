import { createServer as createHttpServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";
import { TRACKED_TICKERS, type TrackedTicker } from "../tickers";
import { JsonFileStore } from "../storage/jsonFileStore";
import type { Store } from "../storage/types";

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, OPTIONS",
};

const DEFAULT_WINDOW_MS = 24 * 60 * 60 * 1000;

function sendJson(res: ServerResponse, statusCode: number, body: unknown): void {
  res.writeHead(statusCode, { "Content-Type": "application/json", ...CORS_HEADERS });
  res.end(JSON.stringify(body));
}

function isTrackedTicker(value: string): value is TrackedTicker {
  return (TRACKED_TICKERS as readonly string[]).includes(value);
}

/** Read-only JSON API over a Store — informational endpoints only, nothing here places trades or emits buy/sell signals. */
export function createServer(store: Store): Server {
  return createHttpServer((req: IncomingMessage, res: ServerResponse) => {
    void (async () => {
      if (req.method === "OPTIONS") {
        res.writeHead(204, CORS_HEADERS);
        res.end();
        return;
      }

      if (req.method !== "GET" || !req.url) {
        sendJson(res, 405, { error: "Method not allowed" });
        return;
      }

      const url = new URL(req.url, "http://localhost");
      const since = url.searchParams.get("since") ?? new Date(Date.now() - DEFAULT_WINDOW_MS).toISOString();

      try {
        if (url.pathname === "/api/tickers") {
          const limitParam = url.searchParams.get("limit");
          const limit = limitParam ? Number(limitParam) : undefined;
          const summaries = await store.getTopTickers(since, limit);
          sendJson(res, 200, { since, tickers: summaries });
          return;
        }

        const timeSeriesMatch = /^\/api\/tickers\/([^/]+)\/timeseries$/.exec(url.pathname);
        if (timeSeriesMatch) {
          const symbol = (timeSeriesMatch[1] ?? "").toUpperCase();
          if (!isTrackedTicker(symbol)) {
            sendJson(res, 404, { error: `Unknown ticker: ${symbol}` });
            return;
          }
          const points = await store.getTimeSeries(symbol, since);
          sendJson(res, 200, { ticker: symbol, since, points });
          return;
        }

        sendJson(res, 404, { error: "Not found" });
      } catch (err) {
        console.error(err);
        sendJson(res, 500, { error: "Internal server error" });
      }
    })();
  });
}

if (require.main === module) {
  const port = Number(process.env.PORT ?? 4000);
  const server = createServer(new JsonFileStore());
  server.listen(port, () => console.log(`CryptoTrader API listening on :${port}`));
}
