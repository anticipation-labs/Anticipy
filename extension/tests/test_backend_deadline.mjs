import assert from "node:assert/strict";
import http from "node:http";
import { once } from "node:events";
import { backendFetch, BACKEND_REQUEST_TIMEOUT_MS } from "../backend_transport.js";

// Real local HTTP responses: no model, external site, or customer account.
let writes = 0;
const server = http.createServer((request, response) => {
  if (request.method === "POST") writes++;
  if (request.url === "/hang-before-headers") return;
  if (request.url === "/hang-in-body") {
    response.writeHead(200, { "Content-Type": "application/json" });
    response.write('{"partial":');
    return;
  }
  response.writeHead(200, { "Content-Type": "application/json" });
  response.end('{"ok":true}');
});
server.listen(0, "127.0.0.1");
await once(server, "listening");
const base = `http://127.0.0.1:${server.address().port}`;

try {
  assert.equal(BACKEND_REQUEST_TIMEOUT_MS, 20_000);
  await assert.rejects(
    backendFetch(`${base}/hang-before-headers`, { method: "POST" }, 80),
    (error) => error.name === "TimeoutError",
    "a request that never returns headers is actually aborted",
  );
  assert.equal(writes, 1, "a timed-out POST is never replayed by transport");

  const partial = await backendFetch(`${base}/hang-in-body`, {}, 80);
  assert.equal(partial.status, 200);
  await assert.rejects(partial.json(),
    (error) => ["TimeoutError", "AbortError"].includes(error.name),
    "a response whose body stops halfway is also aborted",
  );

  const cancelled = new AbortController();
  cancelled.abort(new Error("owner stopped this request"));
  await assert.rejects(
    backendFetch(`${base}/ok`, { signal: cancelled.signal }, 500),
    /owner stopped this request/,
    "the caller's earlier cancellation survives the deadline wrapper",
  );
  assert.deepEqual(await (await backendFetch(`${base}/ok`)).json(), { ok: true },
    "one failed request cannot poison the next healthy request");
  console.log("PASS: header deadline, body deadline, no POST replay, caller cancellation, recovery");
} finally {
  server.closeAllConnections();
  await new Promise((resolve) => server.close(resolve));
}
