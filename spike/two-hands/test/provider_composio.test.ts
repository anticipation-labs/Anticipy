// Every test here injects its own transport. There is no network in this file,
// no API key is needed to run it, and no account exists behind it — which is
// the point: the week-1 spike has to be runnable by anyone who clones the repo,
// or the only person who can check it is the person who set up the vendor.

import { test } from "node:test";
import assert from "node:assert/strict";

import type { CapabilitySignature } from "../src/contract.ts";
import {
  ComposioProvider,
  ComposioRequestFailed,
  ComposioResponseShape,
  ComposioUnconfigured,
  execErrorKindForStatus,
  mapConnectionStatus,
  premiumVerdict,
  searchKnownFields,
  searchUseCase,
} from "../src/provider_composio.ts";

const KEY = "comp_live_supersecret_key_1234567890";
const OWNER_EMAIL = "sam@example.com";

function sig(over: Partial<CapabilitySignature> = {}): CapabilitySignature {
  return {
    // The planner's guess. It must never leave this object: the contract calls
    // it advisory and bars it from being a routing key.
    app_hint: "superhuman",
    verb: "send",
    object: "email",
    inputs: { to: OWNER_EMAIL, subject: "lunch", body: "moving it to 1pm" },
    expected_effect: "a new message appears in Sent addressed to Sam",
    side_effect: "write",
    account_hint: "work",
    signature_hash: "abc123",
    ...over,
  };
}

interface FakeCall {
  url: string;
  method: string;
  headers: Record<string, string>;
  body: any;
  rawBody: string;
}

/** A transport that answers from a route table and records every request.
 *  `routes` is matched by substring on the URL, in order, and the handler may
 *  return a different answer on each call so retry behaviour is observable. */
function fakeFetch(
  routes: Array<{ match: string; reply: (call: FakeCall, n: number) => { status?: number; body?: unknown; retryAfter?: string } }>,
) {
  const calls: FakeCall[] = [];
  const counts = new Map<string, number>();
  const impl = async (url: string, init: any) => {
    const rawBody = typeof init?.body === "string" ? init.body : "";
    const call: FakeCall = {
      url: String(url),
      method: init?.method ?? "GET",
      headers: init?.headers ?? {},
      body: rawBody ? JSON.parse(rawBody) : undefined,
      rawBody,
    };
    calls.push(call);
    const route = routes.find((r) => call.url.includes(r.match));
    if (!route) throw new Error(`no fake route for ${call.url}`);
    const n = (counts.get(route.match) ?? 0) + 1;
    counts.set(route.match, n);
    const out = route.reply(call, n);
    return {
      status: out.status ?? 200,
      headers: { get: (h: string) => (h.toLowerCase() === "retry-after" ? out.retryAfter ?? null : null) },
      json: async () => out.body ?? null,
    } as any;
  };
  (impl as any).calls = calls;
  return impl as any;
}

const sessionRoute = {
  match: "/tool_router/session",
  reply: () => ({ status: 201, body: { session_id: "sess-1" } }),
};

/** The session route is matched by substring, so a search/execute/link route
 *  has to be listed BEFORE it or it would swallow them. */
function routesFor(match: string, reply: (call: FakeCall, n: number) => any) {
  return [{ match, reply }, sessionRoute];
}

function searchBody(over: Record<string, unknown> = {}) {
  return {
    success: true,
    error: null,
    results: [
      {
        index: 0,
        use_case: "send email",
        primary_tool_slugs: ["GMAIL_SEND_EMAIL"],
        related_tool_slugs: ["GMAIL_CREATE_EMAIL_DRAFT"],
      },
    ],
    toolkit_connection_statuses: [{ toolkit: "gmail", has_active_connection: true }],
    tool_schemas: {
      GMAIL_SEND_EMAIL: {
        toolkit: "gmail",
        tool_slug: "GMAIL_SEND_EMAIL",
        description: "Send an email as the authenticated user.",
        input_schema: { type: "object", properties: { to: { type: "string" } } },
      },
      GMAIL_CREATE_EMAIL_DRAFT: {
        toolkit: "gmail",
        tool_slug: "GMAIL_CREATE_EMAIL_DRAFT",
        description: "Create a draft.",
        input_schema: { type: "object" },
      },
    },
    ...over,
  };
}

const noopSleep = async () => {};

function provider(fetchImpl: any, over: Record<string, unknown> = {}) {
  return new ComposioProvider({ apiKey: KEY, fetchImpl, sleepImpl: noopSleep, ...over });
}

// ---------------------------------------------------------------------------
// request shape
// ---------------------------------------------------------------------------

test("search creates a per-owner session, then searches with the signature's words", async () => {
  const f = fakeFetch(routesFor("/search", () => ({ body: searchBody() })));
  const out = await provider(f).search(sig(), "owner-7", { connectedOnly: false, limit: 5 });

  assert.equal(f.calls.length, 2);
  assert.equal(f.calls[0].method, "POST");
  assert.match(f.calls[0].url, /\/api\/v3\.1\/tool_router\/session$/);
  assert.deepEqual(f.calls[0].body, { user_id: "owner-7" });

  assert.equal(f.calls[1].method, "POST");
  assert.match(f.calls[1].url, /\/tool_router\/session\/sess-1\/search$/);
  const q = f.calls[1].body.queries[0];
  assert.match(q.use_case, /send/);
  assert.match(q.use_case, /email/);
  assert.match(q.use_case, /appears in Sent/);
  // Key names, sorted, and nothing else.
  assert.equal(q.known_fields, "body, subject, to");

  assert.equal(out.length, 2);
  assert.equal(out[0].toolSlug, "GMAIL_SEND_EMAIL");
  assert.equal(out[0].app, "gmail");
  assert.deepEqual(out[0].schema, { type: "object", properties: { to: { type: "string" } } });
});

test("the owner's own data never reaches the vendor's search endpoint", async () => {
  const f = fakeFetch(routesFor("/search", () => ({ body: searchBody() })));
  await provider(f).search(sig(), "owner-7", { connectedOnly: false, limit: 5 });
  const wire = f.calls.map((c: FakeCall) => c.rawBody).join("\n");
  // Retrieval needs the shape of the step, not its contents. Shipping the
  // recipient and the message body to a vendor's search endpoint is a leak
  // bought for nothing.
  assert.equal(wire.includes(OWNER_EMAIL), false);
  assert.equal(wire.includes("moving it to 1pm"), false);
  assert.equal(wire.includes("lunch"), false);
});

test("app_hint is never sent: the planner's guess may not scope the search", async () => {
  const f = fakeFetch(routesFor("/search", () => ({ body: searchBody() })));
  await provider(f).search(sig({ app_hint: "superhuman" }), "owner-7", {
    connectedOnly: false,
    limit: 5,
  });
  // If the hint scoped the vendor's search, a wrong hint would be
  // indistinguishable from "no API exists for this step".
  assert.equal(f.calls.map((c: FakeCall) => c.rawBody).join("\n").includes("superhuman"), false);
});

test("the API key travels in the header and nowhere else", async () => {
  const f = fakeFetch(routesFor("/search", () => ({ body: searchBody() })));
  await provider(f).search(sig(), "owner-7", { connectedOnly: false, limit: 5 });
  for (const call of f.calls as FakeCall[]) {
    assert.equal(call.headers["x-api-key"], KEY);
    assert.equal(call.rawBody.includes(KEY), false);
    assert.equal(call.url.includes(KEY), false);
  }
});

// ---------------------------------------------------------------------------
// the score orders, it does not decide
// ---------------------------------------------------------------------------

test("a vendor score is carried through unchanged", async () => {
  const body = searchBody();
  (body.tool_schemas as any).GMAIL_SEND_EMAIL.score = 0.4137;
  const f = fakeFetch(routesFor("/search", () => ({ body })));
  const out = await provider(f).search(sig(), "o", { connectedOnly: false, limit: 5 });
  assert.equal(out[0].score, 0.4137);
});

test("with no vendor score the order survives as a number that cannot pass for a confidence", async () => {
  const f = fakeFetch(routesFor("/search", () => ({ body: searchBody() })));
  const out = await provider(f).search(sig(), "o", { connectedOnly: false, limit: 5 });
  assert.deepEqual(out.map((c) => c.toolSlug), ["GMAIL_SEND_EMAIL", "GMAIL_CREATE_EMAIL_DRAFT"]);
  assert.deepEqual(out.map((c) => c.score), [0, -1]);
  // Nothing here may be compared against 0.75 and read as agreement.
  assert.equal(out.every((c) => c.score <= 0), true);
});

test("limit truncates after the vendor's ordering, it does not reorder", async () => {
  const f = fakeFetch(routesFor("/search", () => ({ body: searchBody() })));
  const out = await provider(f).search(sig(), "o", { connectedOnly: false, limit: 1 });
  assert.deepEqual(out.map((c) => c.toolSlug), ["GMAIL_SEND_EMAIL"]);
});

// ---------------------------------------------------------------------------
// connectedOnly
// ---------------------------------------------------------------------------

test("connectedOnly drops toolkits the owner has not connected", async () => {
  const body = searchBody({
    toolkit_connection_statuses: [{ toolkit: "gmail", has_active_connection: false }],
  });
  const f = fakeFetch(routesFor("/search", () => ({ body })));
  const out = await provider(f).search(sig(), "o", { connectedOnly: true, limit: 5 });
  assert.deepEqual(out, []);
});

test("connectedOnly asks connections() when the search response omits the statuses", async () => {
  const body = searchBody();
  delete (body as any).toolkit_connection_statuses;
  const f = fakeFetch([
    { match: "/search", reply: () => ({ body }) },
    {
      match: "/connected_accounts",
      reply: () => ({
        body: { items: [{ id: "ca_1", toolkit: { slug: "GMAIL" }, status: "ACTIVE" }] },
      }),
    },
    sessionRoute,
  ]);
  const out = await provider(f).search(sig(), "o", { connectedOnly: true, limit: 5 });
  // "GMAIL" from one endpoint and "gmail" from the other are the same app; a
  // raw comparison would silently drop every connected account.
  assert.equal(out.length, 2);
  assert.equal(f.calls.some((c: FakeCall) => c.url.includes("/connected_accounts")), true);
});

// ---------------------------------------------------------------------------
// premium exclusion — the spend seatbelt
// ---------------------------------------------------------------------------

test("a vendor-declared premium tool is excluded by default", async () => {
  const body = searchBody();
  (body.tool_schemas as any).GMAIL_SEND_EMAIL.premium = true;
  const f = fakeFetch(routesFor("/search", () => ({ body })));
  const out = await provider(f).search(sig(), "o", { connectedOnly: false, limit: 5 });
  assert.deepEqual(out.map((c) => c.toolSlug), ["GMAIL_CREATE_EMAIL_DRAFT"]);
  // The kept candidate is still numbered from zero: dropping a premium tool
  // must not leave a hole that a later reader reads as a missing result.
  assert.deepEqual(out.map((c) => c.score), [0]);
});

test("a declared per-call price above zero is a premium declaration", async () => {
  const body = searchBody();
  (body.tool_schemas as any).GMAIL_SEND_EMAIL.pricing = { per_call_usd: 0.7 };
  const f = fakeFetch(routesFor("/search", () => ({ body })));
  const out = await provider(f).search(sig(), "o", { connectedOnly: false, limit: 5 });
  assert.deepEqual(out.map((c) => c.toolSlug), ["GMAIL_CREATE_EMAIL_DRAFT"]);
});

test("a toolkit the owner configured as premium is excluded even with no vendor flag", async () => {
  const f = fakeFetch(routesFor("/search", () => ({ body: searchBody() })));
  const out = await provider(f, { premiumToolkits: ["GMAIL"] }).search(sig(), "o", {
    connectedOnly: false,
    limit: 5,
  });
  assert.deepEqual(out, []);
});

test("allowPremium keeps them, and only allowPremium does", async () => {
  const body = searchBody();
  (body.tool_schemas as any).GMAIL_SEND_EMAIL.premium = true;
  const f = fakeFetch(routesFor("/search", () => ({ body })));
  const out = await provider(f, { allowPremium: true }).search(sig(), "o", {
    connectedOnly: false,
    limit: 5,
  });
  assert.deepEqual(out.map((c) => c.toolSlug), ["GMAIL_SEND_EMAIL", "GMAIL_CREATE_EMAIL_DRAFT"]);
});

test("an undeclared premium status is KEPT — this pins the known hole, not a fix", async () => {
  // Composio documents no premium flag, so on the live API this is the normal
  // case. Failing closed here would drop every tool the vendor has and make the
  // API hand unreachable; keeping them means the guard rests on the caller's
  // configured slug set until a live check proves otherwise.
  const f = fakeFetch(routesFor("/search", () => ({ body: searchBody() })));
  const out = await provider(f).search(sig(), "o", { connectedOnly: false, limit: 5 });
  assert.equal(out.length, 2);
  assert.equal(premiumVerdict({}, "gmail", new Set()), null);
  assert.equal(premiumVerdict({ premium: false }, "gmail", new Set()), false);
});

test("nothing is excluded by reading the words in a description", async () => {
  // The forbidden shape is a word list over natural language deciding a routing
  // outcome. A tool whose description is nothing but the trigger words must
  // survive, or this file has grown the thing the spike exists to avoid.
  const body = searchBody();
  (body.tool_schemas as any).GMAIL_SEND_EMAIL.description =
    "premium browser automation billed per run at $0.70 — expensive paid credits";
  const f = fakeFetch(routesFor("/search", () => ({ body })));
  const out = await provider(f).search(sig(), "o", { connectedOnly: false, limit: 5 });
  assert.equal(out.length, 2);
});

// ---------------------------------------------------------------------------
// execute — error kinds
// ---------------------------------------------------------------------------

const KIND_CASES: Array<[number, string]> = [
  [401, "auth"],
  [403, "auth"],
  [429, "rate"],
  [400, "schema"],
  [422, "schema"],
  [404, "other"],
  [409, "other"],
  [500, "other"],
  [502, "other"],
];

for (const [status, kind] of KIND_CASES) {
  test(`execute maps HTTP ${status} to ${kind}`, async () => {
    const f = fakeFetch(
      routesFor("/execute", () => ({ status, body: { error: { code: "vendor_code", status } } })),
    );
    const res = await provider(f).execute("o", "GMAIL_SEND_EMAIL", { to: OWNER_EMAIL });
    assert.equal(res.ok, false);
    assert.equal(res.error?.kind, kind);
    assert.equal(typeof res.ms, "number");
    assert.equal(res.ms >= 0, true);
  });
}

test("the status map is by code, never by the vendor's prose", () => {
  assert.equal(execErrorKindForStatus(401), "auth");
  assert.equal(execErrorKindForStatus(429), "rate");
  assert.equal(execErrorKindForStatus(422), "schema");
  assert.equal(execErrorKindForStatus(404), "other");
  assert.equal(execErrorKindForStatus(200), "other");
});

test("a 200 carrying a tool failure is a failure, not a success", async () => {
  const f = fakeFetch(
    routesFor("/execute", () => ({
      status: 200,
      body: { data: null, error: "the message could not be sent", log_id: "log_1" },
    })),
  );
  const res = await provider(f).execute("o", "GMAIL_SEND_EMAIL", {});
  // A rung that climbs on failed sends is the worst outcome this spike could
  // produce, so the HTTP status alone is never the verdict.
  assert.equal(res.ok, false);
  assert.equal(res.error?.kind, "other");
});

test("a 200 tool failure takes its kind from a structured status, never from words", async () => {
  const f = fakeFetch(
    routesFor("/execute", () => ({
      status: 200,
      body: { data: null, error: { message: "unauthorized", status: 401, code: "bad_grant" } },
    })),
  );
  const res = await provider(f).execute("o", "GMAIL_SEND_EMAIL", {});
  assert.equal(res.ok, false);
  assert.equal(res.error?.kind, "auth");
});

test("a clean execute returns the vendor's data and a measured duration", async () => {
  const times = [1000, 1250];
  const f = fakeFetch(routesFor("/execute", () => ({ body: { data: { id: "m_1" }, error: null } })));
  const res = await provider(f, { clock: () => times.shift() ?? 1250 }).execute(
    "o",
    "GMAIL_SEND_EMAIL",
    {},
  );
  assert.equal(res.ok, true);
  assert.deepEqual(res.data, { id: "m_1" });
  assert.equal(res.ms, 250);
});

test("cost is omitted rather than reported as zero when the vendor declares none", async () => {
  const f = fakeFetch(routesFor("/execute", () => ({ body: { data: {}, error: null } })));
  const res = await provider(f).execute("o", "GMAIL_SEND_EMAIL", {});
  // A 0 here would tell the ledger the API hand is free — the exact claim the
  // premium guard exists to stop us making.
  assert.equal("costUsd" in res, false);

  const g = fakeFetch(routesFor("/execute", () => ({ body: { data: {}, error: null, cost_usd: 0.7 } })));
  const paid = await provider(g).execute("o", "X", {});
  assert.equal(paid.costUsd, 0.7);
});

test("execute passes the connected account through when one is given", async () => {
  const f = fakeFetch(routesFor("/execute", () => ({ body: { data: {}, error: null } })));
  await provider(f).execute("o", "GMAIL_SEND_EMAIL", { to: "x" }, "ca_9");
  const call = (f.calls as FakeCall[]).find((c) => c.url.includes("/execute"))!;
  assert.deepEqual(call.body, { tool_slug: "GMAIL_SEND_EMAIL", arguments: { to: "x" }, account: "ca_9" });
});

// ---------------------------------------------------------------------------
// retries
// ---------------------------------------------------------------------------

test("429 retries exactly once, then fails", async () => {
  const f = fakeFetch(routesFor("/execute", () => ({ status: 429, body: { error: { code: "rate_limited" } } })));
  const slept: number[] = [];
  const p = new ComposioProvider({
    apiKey: KEY,
    fetchImpl: f,
    sleepImpl: async (ms: number) => { slept.push(ms); },
  });
  const res = await p.execute("o", "GMAIL_SEND_EMAIL", {});
  assert.equal(res.ok, false);
  assert.equal(res.error?.kind, "rate");
  const executes = (f.calls as FakeCall[]).filter((c) => c.url.includes("/execute"));
  assert.equal(executes.length, 2);
  assert.equal(slept.length, 1);
});

test("a 429 that clears on the retry succeeds without a third attempt", async () => {
  const f = fakeFetch(
    routesFor("/execute", (_c, n) =>
      n === 1 ? { status: 429, body: {} } : { status: 200, body: { data: { ok: 1 }, error: null } },
    ),
  );
  const res = await provider(f).execute("o", "GMAIL_SEND_EMAIL", {});
  assert.equal(res.ok, true);
  assert.equal((f.calls as FakeCall[]).filter((c) => c.url.includes("/execute")).length, 2);
});

test("nothing else retries: a retried write is a duplicate write", async () => {
  for (const status of [500, 502, 503, 401, 400, 404]) {
    const f = fakeFetch(routesFor("/execute", () => ({ status, body: {} })));
    await provider(f).execute("o", "GMAIL_SEND_EMAIL", {});
    const executes = (f.calls as FakeCall[]).filter((c) => c.url.includes("/execute"));
    assert.equal(executes.length, 1, `HTTP ${status} must not be retried`);
  }
});

test("Retry-After is honoured but capped, so a slow vendor cannot park a step for an hour", async () => {
  const f = fakeFetch(routesFor("/execute", () => ({ status: 429, body: {}, retryAfter: "3600" })));
  const slept: number[] = [];
  const p = new ComposioProvider({
    apiKey: KEY, fetchImpl: f, sleepImpl: async (ms: number) => { slept.push(ms); },
  });
  await p.execute("o", "X", {});
  assert.deepEqual(slept, [5000]);
});

// ---------------------------------------------------------------------------
// missing key
// ---------------------------------------------------------------------------

test("with no API key every method refuses by name and nothing is sent", async () => {
  const f = fakeFetch([{ match: "", reply: () => ({ body: {} }) }]);
  const p = new ComposioProvider({ fetchImpl: f });

  await assert.rejects(
    () => p.search(sig(), "o", { connectedOnly: false, limit: 5 }),
    (e: any) => e instanceof ComposioUnconfigured && e.code === "composio_no_api_key",
  );
  await assert.rejects(() => p.connections("o"), ComposioUnconfigured);
  await assert.rejects(() => p.connectLink("o", "gmail"), ComposioUnconfigured);

  // An empty result would be indistinguishable from "this owner has no tools",
  // which is how a misconfigured spike reports a week of zeros as a finding.
  assert.equal(f.calls.length, 0);
});

test("a missing key is 'other', not 'auth' — the owner is not the one who is misconfigured", async () => {
  const f = fakeFetch([{ match: "", reply: () => ({ body: {} }) }]);
  const res = await new ComposioProvider({ fetchImpl: f }).execute("o", "GMAIL_SEND_EMAIL", {});
  assert.equal(res.ok, false);
  // `auth` would nudge her to reconnect Gmail because WE forgot a server key.
  assert.equal(res.error?.kind, "other");
  assert.match(res.error!.message, /no API key/);
  assert.equal(f.calls.length, 0);
});

test("a constructor with no key does not throw", () => {
  assert.doesNotThrow(() => new ComposioProvider({}));
  assert.doesNotThrow(() => new ComposioProvider({ apiKey: null }));
});

// ---------------------------------------------------------------------------
// secrets
// ---------------------------------------------------------------------------

test("no key, token or request body ever reaches a log or an error message", async () => {
  const captured: string[] = [];
  const real = { log: console.log, warn: console.warn, error: console.error, info: console.info, debug: console.debug };
  for (const k of Object.keys(real) as Array<keyof typeof real>) {
    (console as any)[k] = (...a: unknown[]) => captured.push(a.map(String).join(" "));
  }
  try {
    const f = fakeFetch([
      {
        match: "/execute",
        reply: (call) => ({
          status: 400,
          // The vendor quoting our request back at us, key header and all.
          body: {
            error: {
              code: "invalid_arguments",
              message: `rejected ${call.rawBody} with key ${KEY}`,
            },
          },
        }),
      },
      { match: "/search", reply: () => ({ status: 401, body: { error: { message: KEY } } }) },
      sessionRoute,
    ]);
    const p = provider(f);
    const res = await p.execute("o", "GMAIL_SEND_EMAIL", { to: OWNER_EMAIL, body: "moving it to 1pm" });
    assert.equal(res.ok, false);
    assert.equal(res.error!.message.includes(KEY), false);
    assert.equal(res.error!.message.includes(OWNER_EMAIL), false);
    assert.equal(res.error!.message.includes("moving it to 1pm"), false);

    const err = await p.search(sig(), "o", { connectedOnly: false, limit: 3 }).catch((e) => e);
    assert.ok(err instanceof ComposioRequestFailed);
    assert.equal(String(err.message).includes(KEY), false);
    assert.equal(String(err.stack ?? "").includes(KEY), false);

    assert.deepEqual(captured, []);
  } finally {
    Object.assign(console, real);
  }
});

// ---------------------------------------------------------------------------
// connections / connectLink
// ---------------------------------------------------------------------------

test("connections maps the vendor enum fail-closed", async () => {
  const f = fakeFetch([
    {
      match: "/connected_accounts",
      reply: () => ({
        body: {
          items: [
            { id: "ca_1", toolkit: { slug: "Gmail" }, status: "ACTIVE", alias: "work inbox", params: { scopes: ["gmail.send"] } },
            { id: "ca_2", toolkit: "notion", status: "EXPIRED" },
            { id: "ca_3", toolkit: "slack", status: "INITIATED" },
            { id: "ca_4", toolkit: "linear", status: "FAILED" },
          ],
        },
      }),
    },
  ]);
  const out = await provider(f).connections("owner-7");
  assert.match(f.calls[0].url, /\/connected_accounts\?user_ids=owner-7$/);
  assert.deepEqual(out.map((a) => [a.app, a.status]), [
    ["gmail", "active"],
    ["notion", "expired"],
    // A half-finished connection is reported revoked: calling it active routes
    // a step to a hand with no credential, which the owner reads as failure.
    ["slack", "revoked"],
    ["linear", "revoked"],
  ]);
  assert.equal(out[0].label, "work inbox");
  assert.deepEqual(out[0].scopes, ["gmail.send"]);
  assert.equal(out[0].accountId, "ca_1");
});

test("an unreadable connections response is an error, never an empty list", async () => {
  const f = fakeFetch([{ match: "/connected_accounts", reply: () => ({ body: { data: [] } }) }]);
  await assert.rejects(() => provider(f).connections("o"), ComposioResponseShape);
});

test("connectLink returns the vendor's redirect_url", async () => {
  const f = fakeFetch(
    routesFor("/link", () => ({
      status: 201,
      body: { link_token: "lt_1", redirect_url: "https://auth.composio.dev/x", connected_account_id: "ca_9" },
    })),
  );
  const { url } = await provider(f).connectLink("owner-7", "GMAIL");
  assert.equal(url, "https://auth.composio.dev/x");
  const call = (f.calls as FakeCall[]).find((c) => c.url.includes("/link"))!;
  assert.deepEqual(call.body, { toolkit: "gmail" });
});

test("a link response with no url is an error, not an empty string", async () => {
  const f = fakeFetch(routesFor("/link", () => ({ status: 201, body: { link_token: "lt_1" } })));
  // Returning "" would send the owner a nudge with a dead button in it.
  await assert.rejects(() => provider(f).connectLink("o", "gmail"), ComposioResponseShape);
});

// ---------------------------------------------------------------------------
// shapes we did not understand are never reported as zeros
// ---------------------------------------------------------------------------

test("ranked slugs with no schemas is a shape failure, not 'this owner has no tools'", async () => {
  const body = searchBody({ tool_schemas: {} });
  const f = fakeFetch(routesFor("/search", () => ({ body })));
  await assert.rejects(
    () => provider(f).search(sig(), "o", { connectedOnly: false, limit: 5 }),
    ComposioResponseShape,
  );
});

test("a body-level search failure on an HTTP 200 is not an empty result", async () => {
  const body = searchBody({ success: false, error: "search backend unavailable", results: [] });
  const f = fakeFetch(routesFor("/search", () => ({ body })));
  await assert.rejects(
    () => provider(f).search(sig(), "o", { connectedOnly: false, limit: 5 }),
    ComposioRequestFailed,
  );
});

test("a genuinely empty ranking is an empty list", async () => {
  const body = searchBody({ results: [{ primary_tool_slugs: [], related_tool_slugs: [] }] });
  const f = fakeFetch(routesFor("/search", () => ({ body })));
  const out = await provider(f).search(sig(), "o", { connectedOnly: false, limit: 5 });
  assert.deepEqual(out, []);
});

// ---------------------------------------------------------------------------
// sessions
// ---------------------------------------------------------------------------

test("one session per owner, reused across calls", async () => {
  const f = fakeFetch(routesFor("/search", () => ({ body: searchBody() })));
  const p = provider(f);
  await p.search(sig(), "owner-7", { connectedOnly: false, limit: 5 });
  await p.search(sig(), "owner-7", { connectedOnly: false, limit: 5 });
  const creates = (f.calls as FakeCall[]).filter((c) => c.url.endsWith("/tool_router/session"));
  assert.equal(creates.length, 1);
});

test("two owners never share a session", async () => {
  const f = fakeFetch(routesFor("/search", () => ({ body: searchBody() })));
  const p = provider(f);
  await Promise.all([
    p.search(sig(), "owner-a", { connectedOnly: false, limit: 5 }),
    p.search(sig(), "owner-b", { connectedOnly: false, limit: 5 }),
  ]);
  const creates = (f.calls as FakeCall[]).filter((c) => c.url.endsWith("/tool_router/session"));
  // Sessions scope which connected accounts a tool runs against. Sharing one
  // would execute a step against a different person's mailbox.
  assert.deepEqual(creates.map((c) => c.body.user_id).sort(), ["owner-a", "owner-b"]);
});

test("concurrent steps for one owner mint one session, not two", async () => {
  const f = fakeFetch(routesFor("/search", () => ({ body: searchBody() })));
  const p = provider(f);
  await Promise.all([
    p.search(sig(), "owner-7", { connectedOnly: false, limit: 5 }),
    p.search(sig(), "owner-7", { connectedOnly: false, limit: 5 }),
  ]);
  const creates = (f.calls as FakeCall[]).filter((c) => c.url.endsWith("/tool_router/session"));
  assert.equal(creates.length, 1);
});

test("a dead session is forgotten but the failed execute is NOT re-issued", async () => {
  let sessionN = 0;
  const f = fakeFetch([
    { match: "/execute", reply: () => ({ status: 404, body: { error: { code: "session_not_found" } } }) },
    { match: "/tool_router/session", reply: () => ({ status: 201, body: { session_id: `sess-${++sessionN}` } }) },
  ]);
  const p = provider(f);
  const first = await p.execute("o", "GMAIL_SEND_EMAIL", {});
  assert.equal(first.ok, false);
  assert.equal((f.calls as FakeCall[]).filter((c) => c.url.includes("/execute")).length, 1);
  await p.execute("o", "GMAIL_SEND_EMAIL", {});
  const creates = (f.calls as FakeCall[]).filter((c) => c.url.endsWith("/tool_router/session"));
  // The next step gets a fresh session; the one that failed is not repeated,
  // because "the session probably expired before the tool ran" is not good
  // enough when the tool sends money or email and there is no idempotency key.
  assert.equal(creates.length, 2);
});

// ---------------------------------------------------------------------------
// side-effect hints — may only ratchet stricter
// ---------------------------------------------------------------------------

test("MCP annotations are read only in the direction that cannot loosen a step", async () => {
  const body = searchBody();
  (body.tool_schemas as any).GMAIL_SEND_EMAIL.annotations = { destructiveHint: true };
  (body.tool_schemas as any).GMAIL_CREATE_EMAIL_DRAFT.annotations = { readOnlyHint: false };
  const f = fakeFetch(routesFor("/search", () => ({ body })));
  const out = await provider(f).search(sig(), "o", { connectedOnly: false, limit: 5 });
  assert.equal(out[0].sideEffectHint, "irreversible");
  // `readOnlyHint: false` is not a claim that this writes. A tool that declares
  // nothing has declared nothing.
  assert.equal(out[1].sideEffectHint, undefined);
});

// ---------------------------------------------------------------------------
// pure helpers
// ---------------------------------------------------------------------------

test("the query is built from the step, and the field list from key names only", () => {
  const s = sig();
  assert.equal(searchUseCase(s), "send — email — a new message appears in Sent addressed to Sam");
  assert.equal(searchKnownFields(s), "body, subject, to");
  // Sorted, so the same step does not produce a different query on every run.
  assert.equal(searchKnownFields(sig({ inputs: { to: 1, body: 2, subject: 3 } })), "body, subject, to");
  assert.equal(searchUseCase(sig({ expected_effect: "x".repeat(5000) })).length <= 1024, true);
});

test("connection status tokens are matched exactly, not by substring", () => {
  assert.equal(mapConnectionStatus("ACTIVE"), "active");
  assert.equal(mapConnectionStatus(" active "), "active");
  // "INACTIVE" contains "ACTIVE"; a substring test would call a dead account live.
  assert.equal(mapConnectionStatus("INACTIVE"), "revoked");
  assert.equal(mapConnectionStatus(undefined), "revoked");
});

test("a STRUCTURED body error is a failure too, on search as well as execute", async () => {
  // The vendor spells this failure both ways. Reading only the string form let
  // every structured failure through: a send that never happened counted as a
  // success on execute, and a vendor outage counted as "this owner has no API
  // for this step" on search. Both silent, both permanent.
  const body = searchBody({ success: true, error: { message: "backend down", code: "unavailable" }, results: [] });
  const f = fakeFetch(routesFor("/search", () => ({ body })));
  await assert.rejects(
    () => provider(f).search(sig(), "o", { connectedOnly: false, limit: 5 }),
    ComposioRequestFailed,
  );
});
