import { test } from "node:test";
import assert from "node:assert/strict";
import { generateKeyPairSync } from "node:crypto";
import jwt from "jsonwebtoken";
import { CoinbasePriceFeed, CoinbaseNotConfiguredError } from "./coinbase";

// A throwaway P-256 key pair generated fresh for this test run — never the
// user's real Coinbase key. This validates the JWT is actually
// well-formed and correctly signed (verifiable with the matching public
// key), not just that the code compiles.
const { publicKey, privateKey } = generateKeyPairSync("ec", {
  namedCurve: "prime256v1",
  publicKeyEncoding: { type: "spki", format: "pem" },
  privateKeyEncoding: { type: "pkcs8", format: "pem" },
});

const API_KEY_NAME = "organizations/test-org/apiKeys/test-key";

test("throws CoinbaseNotConfiguredError when credentials are missing", async () => {
  const feed = new CoinbasePriceFeed({});
  await assert.rejects(() => feed.getPrice("BTC"), CoinbaseNotConfiguredError);
});

test("signs a valid ES256 JWT with the documented CDP claim shape", async () => {
  let capturedAuthHeader = "";

  const feed = new CoinbasePriceFeed({
    apiKeyName: API_KEY_NAME,
    privateKeyPem: privateKey,
    fetchImpl: (async (_url: string | URL, init?: RequestInit) => {
      const headers = init?.headers as Record<string, string> | undefined;
      capturedAuthHeader = headers?.Authorization ?? "";
      return new Response(JSON.stringify({ price: "65000.50" }), { status: 200 });
    }) as typeof fetch,
  });

  await feed.getPrice("BTC");

  assert.match(capturedAuthHeader, /^Bearer /);
  const token = capturedAuthHeader.replace("Bearer ", "");

  // Verifying with the matching public key proves the signature is real,
  // not just present.
  const decoded = jwt.verify(token, publicKey, { algorithms: ["ES256"] }) as jwt.JwtPayload;
  assert.equal(decoded.sub, API_KEY_NAME);
  assert.equal(decoded.iss, "cdp");
  assert.equal(decoded.uri, "GET api.coinbase.com/api/v3/brokerage/products/BTC-USD");
  assert.ok(typeof decoded.exp === "number" && decoded.exp > (decoded.nbf as number));

  const header = jwt.decode(token, { complete: true })?.header as (jwt.JwtHeader & { nonce?: string }) | undefined;
  assert.equal(header?.kid, API_KEY_NAME);
  assert.ok(typeof header?.nonce === "string" && header.nonce.length > 0);
});

test("getPrice parses the price field as a number", async () => {
  const feed = new CoinbasePriceFeed({
    apiKeyName: API_KEY_NAME,
    privateKeyPem: privateKey,
    fetchImpl: (async () => new Response(JSON.stringify({ price: "3200.75" }), { status: 200 })) as typeof fetch,
  });

  assert.equal(await feed.getPrice("ETH"), 3200.75);
});

test("throws a clear error on a non-ok response", async () => {
  const feed = new CoinbasePriceFeed({
    apiKeyName: API_KEY_NAME,
    privateKeyPem: privateKey,
    fetchImpl: (async () => new Response("unauthorized", { status: 401 })) as typeof fetch,
  });

  await assert.rejects(() => feed.getPrice("SOL"), /401/);
});

test("throws a clear error when the price field can't be parsed as a number", async () => {
  const feed = new CoinbasePriceFeed({
    apiKeyName: API_KEY_NAME,
    privateKeyPem: privateKey,
    fetchImpl: (async () => new Response(JSON.stringify({ price: "not-a-number" }), { status: 200 })) as typeof fetch,
  });

  await assert.rejects(() => feed.getPrice("DOGE"), /unparseable price/);
});
