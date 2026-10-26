import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import { webcrypto } from "node:crypto";
function browser() {
  let offset = 0;
  class Clock extends Date {
    static now() {
      return Date.now() + offset;
    }
  }
  let network = 0;
  const scope = {
    DEMO_SEED: JSON.parse(
      readFileSync(new URL("./seed.json", import.meta.url), "utf8"),
    ),
    structuredClone,
    Response,
    Headers,
    URL,
    DOMException,
    TextEncoder,
    TextDecoder,
    Uint8Array,
    Date: Clock,
    crypto: webcrypto,
    location: new URL("https://example.test/project/"),
    fetch: async () => {
      network++;
      throw Error("Unexpected network request");
    },
  };
  runInNewContext(
    readFileSync(new URL("./browser.js", import.meta.url), "utf8"),
    scope,
  );
  return {
    call: async (path, method = "GET", body, headers) => {
      const response = await scope.fetch(path, {
        method,
        ...(body ? { body: JSON.stringify(body) } : {}),
        headers,
      });
      return { status: response.status, body: await response.json() };
    },
    advance: (ms) => {
      offset += ms;
    },
    network: () => network,
  };
}
test("only a reviewer decides and terminal decisions cannot be overwritten", async () => {
  const b = browser();
  const row = (
    await b.call("/api/approval-requests", "POST", { title: "Review this" })
  ).body;
  const path = "/api/approval-requests/" + row.id + "/approve";
  assert.equal(
    (await b.call(path, "POST", {}, { "X-User-Id": "author" })).status,
    403,
  );
  assert.equal(
    (await b.call(path, "POST", {}, { "X-User-Id": "reviewer" })).body.status,
    "approved",
  );
  assert.equal(
    (await b.call(path, "POST", {}, { "X-User-Id": "reviewer" })).status,
    409,
  );
  assert.equal((await b.call("/api/events")).body.length, 2);
  assert.equal(b.network(), 0);
});
