/** Offline transport regressions, including native fetch over loopback only. */
import assert from "node:assert/strict";
import { createServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";
import { pathToFileURL } from "node:url";
import {
  ComposioConnections,
  ConnectionsRequestFailed,
  ConnectionsResponseShape,
} from "../src/connections/provider.ts";
import type { OwnerId } from "../../../spike/two-hands/src/connections/contract.ts";
import { runStep, forgetCatalogs } from "../src/connections/api_hand.ts";
import { createD1Store, forgetLiveColumns } from "../src/connections/store.ts";
import { dispose } from "../src/routes/hands_api.ts";
import { FakeD1, asD1 } from "./fake-d1.ts";

const OWNER = "aaaaaaaaaaaaaaa" as OwnerId;
const OTHER = "bbbbbbbbbbbbbbb" as OwnerId;
const KEY = "fixture-only-not-a-credential";
const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));
const account = (id = "fixture-account", user = OWNER) => ({
  id, user_id: user, toolkit: { slug: "fixture" }, status: "ACTIVE",
});
const session = (id = "fixture-session") => ({
  session_id: id, config: { manage_connections: { enabled: false } }, tool_router_tools: [],
});
const reply = (body: unknown, status = 200) => Response.json(body, { status });
function provider(fetchImpl: typeof fetch, bounds: Record<string, unknown> = {}) {
  return new ComposioConnections({
    apiKey: KEY, fetchImpl, requestTimeoutMs: 35, paginationTimeoutMs: 200,
    ...bounds,
  } as ConstructorParameters<typeof ComposioConnections>[0]);
}
async function bounded<T>(promise: Promise<T>, ms = 1200): Promise<T> {
  let timer: ReturnType<typeof setTimeout>;
  try {
    return await Promise.race([promise, new Promise<never>((_, reject) => {
      timer = setTimeout(() => reject(new Error("test watchdog: operation did not settle")), ms);
    })]);
  } finally { clearTimeout(timer!); }
}
async function failure(promise: Promise<unknown>, detail: string) {
  await assert.rejects(bounded(promise), (error: unknown) => {
    assert.ok(error instanceof ConnectionsRequestFailed, String(error));
    assert.equal(error.status, 0);
    assert.match(error.message, new RegExp(detail));
    // Preserve the existing status classification. The API hand separately
    // treats HTTP 0 as kind=other/mayHaveLanded; this adapter never retries it.
    assert.equal(error.retryable, true);
    assert.ok(!error.message.includes(KEY));
    return true;
  });
}
async function listening(server: Server) {
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  return `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
}
async function close(server: Server) {
  server.closeAllConnections();
  await new Promise<void>((resolve) => server.close(() => resolve()));
}

export async function runProviderLivenessTests() {
  let passed = 0;
  const failures: string[] = [];
  async function check(name: string, test: () => Promise<void> | void) {
    try { await test(); passed++; }
    catch (error) { failures.push(name); console.error(`FAIL liveness ${name}: ${String(error)}`); }
  }

  await check("uncooperative headers settle and receive an aborted signal", async () => {
    let signal: AbortSignal | undefined;
    let calls = 0;
    const p = provider((async (_url, init) => {
      calls++; signal = init?.signal as AbortSignal;
      return await new Promise<Response>(() => {});
    }) as typeof fetch);
    await failure(p.connections(OWNER), "request_timeout");
    assert.equal(calls, 1);
    assert.equal(signal?.aborted, true);
  });

  await check("native fetch header stall closes the socket without retry", async () => {
    let calls = 0;
    let socketClosed = false;
    const server = createServer((request) => {
      calls++; request.socket.on("close", () => { socketClosed = true; });
    });
    const baseUrl = await listening(server);
    try {
      const p = new ComposioConnections({ apiKey: KEY, baseUrl, requestTimeoutMs: 100 } as any);
      await failure(p.connections(OWNER), "request_timeout");
      for (let i = 0; i < 50 && !socketClosed; i++) await sleep(10);
      assert.equal(calls, 1);
      assert.equal(socketClosed, true, "actual network I/O must be aborted");
    } finally { await close(server); }
  });

  await check("native fetch body stall is covered by the same timeout", async () => {
    let calls = 0;
    let socketClosed = false;
    const server = createServer((request, response) => {
      calls++; request.socket.on("close", () => { socketClosed = true; });
      response.writeHead(200, { "content-type": "application/json" });
      response.write('{"items":[');
    });
    const baseUrl = await listening(server);
    try {
      const p = new ComposioConnections({ apiKey: KEY, baseUrl, requestTimeoutMs: 100 } as any);
      await failure(p.connections(OWNER), "request_timeout");
      for (let i = 0; i < 50 && !socketClosed; i++) await sleep(10);
      assert.equal(calls, 1);
      assert.equal(socketClosed, true);
    } finally { await close(server); }
  });

  await check("injected stalled body is cancelled even when cancel never settles", async () => {
    let cancelled = 0;
    const body = new ReadableStream<Uint8Array>({ cancel() {
      cancelled++; return new Promise<void>(() => {});
    } });
    await failure(provider((async () => new Response(body)) as typeof fetch).connections(OWNER), "request_timeout");
    assert.equal(cancelled, 1);
  });

  await check("legacy injected json reader also has a deadline", async () => {
    await failure(provider((async () => ({
      status: 200, json: () => new Promise(() => {}),
    })) as unknown as typeof fetch).connections(OWNER), "request_timeout");
  });

  await check("header and body delays share one budget, not one each", async () => {
    let cancelled = false;
    const p = provider((async () => {
      await sleep(25);
      let bodyTimer: ReturnType<typeof setTimeout>;
      return new Response(new ReadableStream({
        start(controller) { bodyTimer = setTimeout(() => {
          controller.enqueue(new TextEncoder().encode('{"items":[]}'));
          controller.close();
        }, 25); },
        cancel() { clearTimeout(bodyTimer); cancelled = true; },
      }));
    }) as typeof fetch, { requestTimeoutMs: 40 });
    await failure(p.connections(OWNER), "request_timeout");
    assert.equal(cancelled, true);
  });

  await check("a completed response clears its abort timer", async () => {
    let signal: AbortSignal | undefined;
    const p = provider((async (_url, init) => {
      signal = init?.signal as AbortSignal;
      return reply({ items: [] });
    }) as typeof fetch);
    assert.deepEqual(await p.connections(OWNER), []);
    await sleep(55);
    assert.equal(signal?.aborted, false);
  });

  await check("session timeout releases all singleflight waiters and permits a fresh session", async () => {
    let calls = 0;
    const p = provider((async () => {
      calls++;
      return calls === 1 ? await new Promise<Response>(() => {}) : reply(session());
    }) as typeof fetch);
    await Promise.all([failure(p.session(OWNER), "request_timeout"), failure(p.session(OWNER), "request_timeout")]);
    assert.equal(calls, 1);
    assert.equal((await bounded(p.session(OWNER))).sessionId, "fixture-session");
    assert.equal(calls, 2);
    await p.session(OWNER);
    assert.equal(calls, 2, "only the completed session is cached");
  });

  await check("late timed-out session response is cancelled and never cached", async () => {
    let complete!: (response: Response) => void;
    let cancelled = 0;
    let calls = 0;
    const p = provider((async () => ++calls === 1
      ? await new Promise<Response>((resolve) => { complete = resolve; })
      : reply(session("fresh-session"))) as typeof fetch);
    await failure(p.session(OWNER), "request_timeout");
    complete(new Response(new ReadableStream({ cancel() { cancelled++; } })));
    await sleep(5);
    assert.equal(cancelled, 1);
    assert.equal((await p.session(OWNER)).sessionId, "fresh-session");
    assert.equal(calls, 2);
  });

  await check("one owner's timed-out session does not block another owner", async () => {
    const p = provider((async (_url, init) => JSON.parse(String(init?.body)).user_id === OWNER
      ? await new Promise<Response>(() => {}) : reply(session("other-session"))) as typeof fetch);
    const stalled = failure(p.session(OWNER), "request_timeout");
    assert.equal((await p.session(OTHER)).sessionId, "other-session");
    await stalled;
  });

  await check("distinct cursors stop at the page cap without partial results", async () => {
    let calls = 0;
    const p = provider((async () => {
      if (++calls > 32) throw new Error("fixture safety stop");
      return reply({ items: [account(`fixture-${calls}`)], next_cursor: `cursor-${calls}` });
    }) as typeof fetch, { maxConnectionPages: 3 });
    await assert.rejects(bounded(p.connections(OWNER)), ConnectionsResponseShape);
    assert.equal(calls, 3);
  });

  await check("exact final page at the cap remains a complete answer", async () => {
    let calls = 0;
    const p = provider((async () => reply({ items: [account(`fixture-${++calls}`)],
      next_cursor: calls < 3 ? `cursor-${calls}` : null })) as typeof fetch, { maxConnectionPages: 3 });
    const rows = await p.connections(OWNER);
    assert.equal(rows.length, 3);
    assert.ok(rows.every((row) => row.user_id === OWNER && row.writes_enabled === false));
  });

  await check("default distinct-cursor ceiling is ten pages", async () => {
    let calls = 0;
    const p = provider((async () => {
      if (++calls > 12) throw new Error("fixture safety stop");
      return reply({ items: [], next_cursor: `next-${calls}` });
    }) as typeof fetch);
    await assert.rejects(p.connections(OWNER), ConnectionsResponseShape);
    assert.equal(calls, 10);
  });

  await check("aggregate pagination deadline aborts a later page and never returns the prefix", async () => {
    let calls = 0;
    let lastSignal: AbortSignal | undefined;
    const p = provider((async (_url, init) => {
      calls++; lastSignal = init?.signal as AbortSignal;
      await sleep(25);
      return reply({ items: [account(`fixture-${calls}`)], next_cursor: calls < 4 ? `cursor-${calls}` : null });
    }) as typeof fetch, { requestTimeoutMs: 100, paginationTimeoutMs: 45 });
    await failure(p.connections(OWNER), "request_timeout|pagination_timeout");
    assert.equal(calls, 2);
    assert.equal(lastSignal?.aborted, true);
  });

  await check("a later-page wrong owner still refuses the entire response", async () => {
    let calls = 0;
    const p = provider((async () => reply({ items: [account("fixture", ++calls === 1 ? OWNER : OTHER)],
      next_cursor: calls === 1 ? "next" : null })) as typeof fetch);
    await assert.rejects(p.connections(OWNER), { name: "ConnectionsOwnerMismatch" });
  });

  await check("tool catalogue pages share the same aggregate deadline", async () => {
    let calls = 0;
    const p = provider((async () => {
      await sleep(25);
      return reply({ items: [{ slug: "FIXTURE_READ", name: "fixture read", toolkit: { slug: "fixture" },
        tags: ["readOnlyHint"], input_parameters: { type: "object" } }],
        next_cursor: ++calls < 4 ? `next-${calls}` : null });
    }) as typeof fetch, { requestTimeoutMs: 100, paginationTimeoutMs: 45 });
    await failure(p.tools("fixture"), "request_timeout|pagination_timeout");
  });

  await check("execute timeout never retries or claims a receipt", async () => {
    let calls = 0;
    const p = provider((async () => { calls++; return await new Promise<Response>(() => {}); }) as typeof fetch);
    await failure(p.execute(OWNER, "FIXTURE_EXECUTE", { fixture: true }, "fixture-account"), "request_timeout");
    assert.equal(calls, 1);
  });

  await check("stalled execute success body remains unknown, not success or retry", async () => {
    let calls = 0;
    const p = provider((async () => { calls++; return new Response(new ReadableStream()); }) as typeof fetch);
    await failure(p.execute(OWNER, "FIXTURE_EXECUTE", {}, "fixture-account"), "request_timeout");
    assert.equal(calls, 1);
  });

  await check("actual API hand preserves uncertain-write fence after a provider timeout", async () => {
    const env = { DB: asD1(new FakeD1()), COMPOSIO_API_KEY: KEY };
    const store = createD1Store(env);
    forgetLiveColumns(env);
    forgetCatalogs();
    await store.putConnection({ user_id: OWNER, toolkit: "fixture", connected_account_id: "fixture-account",
      alias: null, status: "connected", writes_enabled: true, last_used_at: null });
    let sends = 0;
    const p = provider((async (url, init) => {
      if (String(url).includes("/tools?")) return reply({ items: [{ slug: "FIXTURE_CREATE", name: "fixture create",
        toolkit: { slug: "fixture" }, tags: ["createHint"], input_parameters: { type: "object" } }] });
      sends++;
      const body = JSON.parse(String(init?.body));
      assert.equal(body.user_id, OWNER);
      assert.equal(body.connected_account_id, "fixture-account");
      return await new Promise<Response>(() => {});
    }) as typeof fetch);
    const outcome = await bounded(runStep(env, { owner: OWNER, toolkit: "fixture", tool: "FIXTURE_CREATE",
      args: { fixture: true }, effect: "write" }, { store, provider: p }));
    assert.equal(outcome.outcome, "failed");
    if (outcome.outcome !== "failed") throw new Error("expected failed outcome");
    assert.equal(outcome.error.kind, "other");
    assert.equal(outcome.error.status, 0);
    assert.equal(outcome.mayHaveLanded, true);
    const disposition = dispose(outcome, 0);
    assert.equal(disposition.state, "needs_user");
    assert.equal(disposition.effectUncertain, true);
    assert.equal(disposition.lane, "api");
    assert.equal(sends, 1, "neither the provider nor the API hand may retry a timed-out write");
    forgetCatalogs();
  });

  await check("revoke timeout never proceeds to delete", async () => {
    const methods: string[] = [];
    const p = provider((async (_url, init) => {
      methods.push(String(init?.method));
      return methods.length === 1 ? reply({ items: [account()] }) : await new Promise<Response>(() => {});
    }) as typeof fetch);
    await failure(p.disconnect(OWNER, "fixture-account"), "request_timeout");
    assert.deepEqual(methods, ["GET", "POST"]);
  });

  await check("streamed bytes are capped without trusting content-length", async () => {
    let cancelled = false;
    const p = provider((async () => new Response(new ReadableStream<Uint8Array>({
      start(controller) { controller.enqueue(new Uint8Array(65)); },
      cancel() { cancelled = true; },
    }), { headers: { "content-length": "1" } })) as typeof fetch, { maxResponseBytes: 64 });
    await failure(p.connections(OWNER), "response_too_large");
    assert.equal(cancelled, true);
  });

  await check("oversized declared body is refused and cancelled before reading", async () => {
    let cancelled = false;
    const p = provider((async () => new Response(new ReadableStream({ cancel() { cancelled = true; } }),
      { headers: { "content-length": "1000000" } })) as typeof fetch, { maxResponseBytes: 64 });
    await failure(p.connections(OWNER), "response_too_large");
    assert.equal(cancelled, true);
  });

  await check("UTF-8 byte cap preserves an exact-boundary valid response", async () => {
    const text = JSON.stringify({ successful: true, data: { text: "é" } });
    const p = provider((async () => new Response(text)) as typeof fetch,
      { maxResponseBytes: new TextEncoder().encode(text).byteLength });
    assert.deepEqual((await p.execute(OWNER, "FIXTURE_READ", {})).data, { text: "é" });
  });

  await check("malformed JSON preserves a definitive HTTP failure status", async () => {
    const p = provider((async () => new Response("<html>bad gateway</html>", { status: 502 })) as typeof fetch);
    await assert.rejects(p.connections(OWNER), (error: any) => error.status === 502);
  });

  await check("body transport cancellation is a bounded unknown-effect error", async () => {
    const p = provider((async () => new Response(new ReadableStream({ start(controller) {
      controller.error(new DOMException(`unsafe ${KEY} https://secret.invalid/path`, "AbortError"));
    } }))) as typeof fetch);
    await failure(p.execute(OWNER, "FIXTURE_EXECUTE", {}), "transport_failure");
  });

  await check("a rejecting stream cleanup cannot replace the bounded error", async () => {
    const p = provider((async () => new Response(new ReadableStream({ cancel() {
      throw new Error(`unsafe cleanup ${KEY}`);
    } }))) as typeof fetch);
    await failure(p.connections(OWNER), "request_timeout");
  });

  await check("transport exception name, body, cause, and key never escape", async () => {
    const toxic = new Error(`unsafe ${KEY}`, { cause: { key: KEY } });
    toxic.name = `unsafe-name-${KEY}`;
    const p = provider((async () => { throw toxic; }) as typeof fetch);
    await failure(p.connections(OWNER), "transport_failure");
  });

  await check("invalid or oversized configured bounds refuse before I/O", () => {
    for (const [key, cap] of Object.entries({ requestTimeoutMs: 20000, paginationTimeoutMs: 30000,
      maxConnectionPages: 10, maxResponseBytes: 4 * 1024 * 1024 })) {
      for (const value of [0, -1, NaN, Infinity, true, "1", 1.5, cap + 1]) {
        assert.throws(() => provider((async () => { throw new Error("must not fetch"); }) as typeof fetch,
          { [key]: value }), { name: "ConnectionsBadArgument" }, `${key}=${value}`);
      }
    }
  });

  if (failures.length) throw new Error(`connections-provider-liveness: ${failures.length} failing, ${passed} passing`);
  console.log(`connections-provider-liveness: all ${passed} cases pass`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  await runProviderLivenessTests();
}
