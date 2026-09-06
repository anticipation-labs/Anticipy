// Every test here injects its own transport. There is no network in this file,
// no API key is needed to run it, and no Composio account exists behind it.
//
// The tests are ordered by what they protect, hardest first. The first block is
// the one this whole module is shaped around: a connection bound to the wrong
// person. That already happened once during the spike — one operator's Gmail
// connected under `user_id: "omar"` — and it is invisible from the outside,
// because a stranger's mailbox works perfectly. Everything after it is ordinary
// adapter behaviour.

import { test } from "node:test";
import assert from "node:assert/strict";
import { inspect } from "node:util";

import { ownerId, type OwnerId } from "../src/connections/contract.ts";
import {
  COMPOSIO_BASE_URL,
  ComposioConnections,
  MANAGE_CONNECTIONS_TOOL,
  isRetryableStatus,
  mapConnectionStatus,
  readAlias,
  readLastUsedAt,
  readOwnerEcho,
  requireOwner,
  revokeIsDefinitivelyUnavailable,
  toolkitSlug,
} from "../src/connections/provider_composio.ts";

const KEY = "comp_live_supersecret_key_1234567890";

/** Two real owner-row-shaped ids: 15 lowercase alphanumerics, as D1 mints them.
 *  `OWNER_A` is the one recorded in research/2026-09-05-composio-connections.md
 *  and `OWNER_B` is the production probe owner from CLAUDE.md. Two of them
 *  because one is never enough to catch a cache that leaks across people. */
const OWNER_A: OwnerId = ownerId("sxkotd1h02qb6gw");
const OWNER_B: OwnerId = ownerId("qeuy6sv1raof9rw");

const CALLBACK = "https://anticipy.ai/c/abc123/done";

/** The measured tool list with the connection tool absent, which is the whole
 *  point of creating the session with `manage_connections: {enable: false}`. */
const TOOLS_WITHOUT_MANAGE = [
  "COMPOSIO_MULTI_EXECUTE_TOOL",
  "COMPOSIO_SEARCH_TOOLS",
  "COMPOSIO_GET_TOOL_SCHEMAS",
  "COMPOSIO_REMOTE_WORKBENCH",
  "COMPOSIO_REMOTE_BASH_TOOL",
];

interface Recorded {
  method: string;
  url: string;
  /** The path with the base URL cut off, so assertions read like the endpoint
   *  table in the adapter's header comment. */
  path: string;
  headers: Record<string, string>;
  body: any;
}

interface Reply {
  status?: number;
  body?: unknown;
  /** Throw from the transport instead of answering, for the network-is-down
   *  case. The value becomes the rejection. */
  throws?: unknown;
}

/** A transport that answers from one handler and records every request. The
 *  handler sees the call and the 1-based call number, so a route can answer
 *  differently the second time. */
function fakeFetch(handler: (call: Recorded, n: number) => Reply) {
  const calls: Recorded[] = [];
  const impl = async (url: string, init: any) => {
    const raw = typeof init?.body === "string" ? init.body : "";
    const full = String(url);
    const call: Recorded = {
      method: init?.method ?? "GET",
      url: full,
      path: full.startsWith(COMPOSIO_BASE_URL) ? full.slice(COMPOSIO_BASE_URL.length) : full,
      headers: init?.headers ?? {},
      body: raw ? JSON.parse(raw) : undefined,
    };
    calls.push(call);
    const out = handler(call, calls.length);
    if (out.throws !== undefined) throw out.throws;
    return { status: out.status ?? 200, json: async () => out.body ?? null } as any;
  };
  (impl as any).calls = calls;
  return impl as any;
}

function sessionReply(id = "sess-A", over: Record<string, unknown> = {}) {
  return {
    status: 201,
    body: {
      session_id: id,
      mcp: { url: "https://mcp.composio.dev/whatever" },
      config: { manage_connections: { enabled: false } },
      tool_router_tools: TOOLS_WITHOUT_MANAGE,
      ...over,
    },
  };
}

/** A connected account as the vendor lists it, INCLUDING the owner echo.
 *
 *  The echo is part of the default fixture because the adapter refuses a row it
 *  cannot read as this owner's — a row that names nobody is a row whose only
 *  scoping is a query string we cannot check, and `disconnect()` turns that
 *  list into permission to call two endpoints that take an account id and no
 *  user scoping at all. A test world that omits it is not the world. */
function accountItem(over: Record<string, unknown> = {}) {
  return {
    id: "ca_BNgvxQtJ703C",
    user_id: OWNER_A,
    toolkit: { slug: "gmail" },
    status: "ACTIVE",
    ...over,
  };
}

/** The default world: one session per owner, one ACTIVE Gmail, links mint, and
 *  revoke/delete both succeed. Individual tests override one route. */
function happyWorld(sessions: Record<string, string> = { [OWNER_A]: "sess-A", [OWNER_B]: "sess-B" }) {
  return (call: Recorded): Reply => {
    if (call.path === "/tool_router/session") {
      return sessionReply(sessions[String(call.body?.user_id)] ?? "sess-X");
    }
    if (call.path.endsWith("/link")) {
      return { body: { redirect_url: "https://connect.composio.dev/link/TOKEN-9" } };
    }
    if (call.path.startsWith("/connected_accounts?")) {
      // Echo back whoever was asked for, the way a correctly-scoped vendor
      // does — so a test that lists OWNER_B's accounts is not silently reading
      // OWNER_A's row.
      const asked = new URL(call.url).searchParams.get("user_ids") ?? "";
      return { body: { items: [accountItem({ user_id: asked })] } };
    }
    if (call.path.endsWith("/revoke")) return { body: { status: "revoked" } };
    if (call.method === "DELETE") return { body: { deleted: true } };
    if (call.path.startsWith("/toolkits/")) {
      return { body: { slug: "gmail", name: "Gmail", scopes: [] } };
    }
    throw new Error(`no fake route for ${call.method} ${call.path}`);
  };
}

function provider(fetchImpl: any, over: Record<string, unknown> = {}) {
  return new ComposioConnections({ apiKey: KEY, fetchImpl, ...over });
}

function seq(f: any): string[] {
  return (f.calls as Recorded[]).map((c) => `${c.method} ${c.path}`);
}

async function rejectsNamed(
  fn: () => Promise<unknown>,
  name: string,
  message?: RegExp,
): Promise<Error> {
  let caught: any = null;
  try {
    await fn();
  } catch (err) {
    caught = err;
  }
  assert.ok(caught, `expected ${name} but the call resolved`);
  assert.equal(caught.name, name, `expected ${name}, got ${caught.name}: ${caught.message}`);
  if (message) assert.match(caught.message, message);
  return caught;
}

// ===========================================================================
// THE WRONG PERSON. Everything in this block is about one failure.
// ===========================================================================

test("two owners get two sessions, and a cached session is never returned for the other one", async () => {
  const f = fakeFetch(happyWorld());
  const p = provider(f);

  const a1 = await p.session(OWNER_A);
  const b1 = await p.session(OWNER_B);
  const a2 = await p.session(OWNER_A);
  const b2 = await p.session(OWNER_B);

  // Two owners, two POSTs. The repeats came out of the cache.
  assert.equal(f.calls.length, 2);
  assert.deepEqual(f.calls.map((c: Recorded) => c.body.user_id), [OWNER_A, OWNER_B]);

  assert.equal(a1.sessionId, "sess-A");
  assert.equal(b1.sessionId, "sess-B");
  assert.equal(a2.sessionId, "sess-A");
  assert.equal(b2.sessionId, "sess-B");
  assert.notEqual(a1.sessionId, b1.sessionId);
});

test("the cached session follows the owner all the way onto the wire", async () => {
  // The cache being right in memory is not the claim that matters. The claim is
  // that owner B's connect link is minted against owner B's session id, because
  // that path segment is what decides whose account the vendor attaches.
  const f = fakeFetch(happyWorld());
  const p = provider(f);

  await p.authorize(OWNER_A, "gmail", { callbackUrl: CALLBACK });
  await p.authorize(OWNER_B, "gmail", { callbackUrl: CALLBACK });
  await p.authorize(OWNER_A, "notion", { callbackUrl: CALLBACK });

  assert.deepEqual(seq(f), [
    "POST /tool_router/session",
    "POST /tool_router/session/sess-A/link",
    "POST /tool_router/session",
    "POST /tool_router/session/sess-B/link",
    "POST /tool_router/session/sess-A/link",
  ]);
});

test("concurrent calls for one owner mint ONE session; two owners still mint two", async () => {
  const f = fakeFetch(happyWorld());
  const p = provider(f);

  const [a1, a2, b1, b2] = await Promise.all([
    p.session(OWNER_A),
    p.session(OWNER_A),
    p.session(OWNER_B),
    p.session(OWNER_B),
  ]);

  assert.equal(f.calls.length, 2);
  assert.equal(a1.sessionId, a2.sessionId);
  assert.equal(b1.sessionId, b2.sessionId);
  assert.notEqual(a1.sessionId, b1.sessionId);
});

test("a session id the vendor hands to a second owner is refused, not shared", async () => {
  // Two owners in one session is one person's accounts answering for another,
  // and nothing downstream would ever notice.
  const f = fakeFetch(happyWorld({ [OWNER_A]: "sess-SAME", [OWNER_B]: "sess-SAME" }));
  const p = provider(f);

  assert.equal((await p.session(OWNER_A)).sessionId, "sess-SAME");
  await rejectsNamed(() => p.session(OWNER_B), "ConnectionsOwnerMismatch", /different owner/);
});

test("connections() refuses a response carrying somebody else's user_id", async () => {
  const f = fakeFetch((call) => {
    if (call.path.startsWith("/connected_accounts?")) {
      return {
        body: {
          items: [
            accountItem({ user_id: OWNER_A }),
            accountItem({ id: "ca_OTHER", user_id: OWNER_B, toolkit: { slug: "notion" } }),
          ],
        },
      };
    }
    return happyWorld()(call);
  });

  // Not filtered, not stamped over: the query was scoped by user_ids, so a
  // stranger's row means the scoping did not hold and none of it is trustworthy.
  await rejectsNamed(
    () => provider(f).connections(OWNER_A),
    "ConnectionsOwnerMismatch",
    /different user_id/,
  );
});

/** A world whose only override is the connected-accounts list. */
function accountsWorld(items: unknown[]) {
  return (call: Recorded): Reply =>
    call.path.startsWith("/connected_accounts?") ? { body: { items } } : happyWorld()(call);
}

test("a stranger's id in ANY spelling is a mismatch, not a row we adopt", async () => {
  // The check used to fire only for a BARE non-empty string under `user_id` or
  // `user_ids`. Every spelling below read as "the vendor said nothing", so the
  // stray row was stamped with our own validated owner id and handed back as
  // this owner's connection. The request itself sends the plural `user_ids`,
  // so an array echo is the likeliest shape of all.
  const spellings: Array<[string, Record<string, unknown>]> = [
    ["user_ids as the array the request itself uses", { user_ids: [OWNER_B] }],
    ["user_id as a one-element array", { user_id: [OWNER_B] }],
    ["camelCase userId", { userId: OWNER_B }],
    ["camelCase userIds array", { userIds: [OWNER_B] }],
    ["nested under user.id", { user: { id: OWNER_B } }],
    ["nested under user.user_id", { user: { user_id: OWNER_B } }],
    ["ours AND a stranger in one array", { user_ids: [OWNER_A, OWNER_B] }],
    // A stranger named ANYWHERE outranks every other verdict. A row that is
    // both malformed and foreign is foreign: "we could not read this" is the
    // quieter answer and it must not be the one that gets reported.
    ["a stranger beside a field we cannot read", { user_id: null, user_ids: [OWNER_B] }],
    ["a stranger beside a blank in the same array", { user_ids: [OWNER_B, ""] }],
  ];
  for (const [what, over] of spellings) {
    const f = fakeFetch(accountsWorld([accountItem({ id: "ca_STRANGER", user_id: undefined, ...over })]));
    await rejectsNamed(
      () => provider(f).connections(OWNER_A),
      "ConnectionsOwnerMismatch",
      /different user_id/,
    );
  }
});

test("an owner echo we cannot read refuses — unreadable is not agreement", async () => {
  // A floor: "does anything confirm this row is ours?" A value we cannot resolve
  // to an owner row id answers nothing, and answering nothing must refuse, or
  // the guard lifts itself exactly when the response is malformed enough to be
  // dangerous.
  const unreadable: Array<Record<string, unknown>> = [
    { user_id: 4210 },
    { user_id: "" },
    { user_id: "   " },
    { user_id: null },
    { user_id: true },
    { user_ids: [] },
    { user_ids: [{ id: OWNER_A }] },
    { user: {} },
    { user: { email: "jose@anticipy.ai" } },
  ];
  for (const over of unreadable) {
    const f = fakeFetch(accountsWorld([accountItem({ user_id: undefined, ...over })]));
    await rejectsNamed(
      () => provider(f).connections(OWNER_A),
      "ConnectionsResponseShape",
      /could not be read/,
    );
  }
});

test("a row that names no owner at all is refused, not adopted under ours", async () => {
  // The vendor's own scoping is the query string, and the query string is not
  // something we can check in the answer. If this refusal ever fires against
  // the live endpoint the fix is to read the field it DOES send — never to let
  // an unowned row through, because `disconnect()` treats this list as proof
  // of ownership over two endpoints that have none.
  const f = fakeFetch(accountsWorld([{ id: "ca_1", toolkit: { slug: "gmail" }, status: "ACTIVE" }]));
  await rejectsNamed(
    () => provider(f).connections(OWNER_A),
    "ConnectionsResponseShape",
    /named no owner/,
  );
});

test("disconnect() cannot be walked onto a stranger's account by an unreadable echo", async () => {
  // The whole point of the guard, end to end. `/{id}/revoke` and `DELETE /{id}`
  // take an account id and no user scoping, so a row laundered into this
  // owner's list is a stranger's connection deleted with a 200 for it.
  for (const over of [{ user_ids: [OWNER_B] }, { userId: OWNER_B }, { user_id: 77 }, {}]) {
    const f = fakeFetch(
      accountsWorld([{ id: "ca_STRANGER", toolkit: { slug: "gmail" }, status: "ACTIVE", ...over }]),
    );
    let threw = false;
    await provider(f).disconnect(OWNER_A, "ca_STRANGER").then(() => {}, () => { threw = true; });
    assert.ok(threw, `disconnect resolved for ${inspect(over)}`);
    // Looked, and then touched nothing.
    assert.deepEqual(seq(f), ["GET /connected_accounts?user_ids=sxkotd1h02qb6gw"]);
  }
});

test("CONTROL: every correctly-scoped spelling of our own id still lists", async () => {
  // A guard that refuses everything is an outage. These are the answers a
  // correctly-scoped vendor gives, and all of them must come back as rows.
  const ours: Array<Record<string, unknown>> = [
    { user_id: OWNER_A },
    { user_id: ` ${OWNER_A} ` },
    { user_ids: [OWNER_A] },
    { userId: OWNER_A },
    { userIds: [OWNER_A] },
    { user: { id: OWNER_A } },
    { user_id: OWNER_A, user_ids: [OWNER_A] },
  ];
  for (const over of ours) {
    const f = fakeFetch(accountsWorld([accountItem({ user_id: undefined, ...over })]));
    const rows = await provider(f).connections(OWNER_A);
    assert.equal(rows.length, 1, `no row for ${inspect(over)}`);
    assert.equal(rows[0].user_id, OWNER_A);
    assert.equal(rows[0].toolkit, "gmail");
  }
});

test("CONTROL: a correctly-scoped disconnect still revokes and deletes", async () => {
  const f = fakeFetch(accountsWorld([accountItem({ user_id: undefined, user_ids: [OWNER_A] })]));
  const out = await provider(f).disconnect(OWNER_A, "ca_BNgvxQtJ703C");
  assert.deepEqual(out, { revoked: true, deleted: true, revokeUnavailable: false });
  assert.deepEqual(seq(f).slice(1), [
    "POST /connected_accounts/ca_BNgvxQtJ703C/revoke",
    "DELETE /connected_accounts/ca_BNgvxQtJ703C",
  ]);
});

test("connections() stamps OUR validated owner on every row it returns", async () => {
  const f = fakeFetch(happyWorld());
  const rows = await provider(f).connections(OWNER_A);
  assert.equal(rows.length, 1);
  assert.equal(rows[0].user_id, OWNER_A);
  assert.match(f.calls[0].url, /\/connected_accounts\?user_ids=sxkotd1h02qb6gw$/);
});

test("disconnect() proves the account belongs to this owner before touching it", async () => {
  // /{id}/revoke and DELETE /{id} take an account id and NO user scoping. A
  // stale or mixed-up id would delete a stranger's connection and get a 200.
  const f = fakeFetch(happyWorld());
  const p = provider(f);

  await rejectsNamed(
    () => p.disconnect(OWNER_A, "ca_SOMEONE_ELSE"),
    "ConnectionsOwnerMismatch",
    /not one of this owner's accounts/,
  );
  // Looked, and then touched nothing.
  assert.deepEqual(seq(f), ["GET /connected_accounts?user_ids=sxkotd1h02qb6gw"]);
});

test("a blank, missing or name-shaped owner throws and never reaches the wire", async () => {
  const f = fakeFetch(happyWorld());
  const p = provider(f);

  for (const bad of ["", "   ", "omar", "jose@anticipy.ai", "SXKOTD1H02QB6GW", null, undefined]) {
    const user = bad as unknown as OwnerId;
    await rejectsNamed(() => p.session(user), "ConnectionsOwnerRequired");
    await rejectsNamed(() => p.authorize(user, "gmail", { callbackUrl: CALLBACK }), "ConnectionsOwnerRequired");
    await rejectsNamed(() => p.connections(user), "ConnectionsOwnerRequired");
    await rejectsNamed(() => p.disconnect(user, "ca_1"), "ConnectionsOwnerRequired");
  }
  assert.equal(f.calls.length, 0);
});

test("requireOwner reports the SHAPE of a bad id and never echoes the value", async () => {
  // An error message is the one place in a server guaranteed to reach a log. A
  // caller that confuses a name for an id passes an email address.
  const err = await rejectsNamed(
    () => provider(fakeFetch(happyWorld())).session("jose@anticipy.ai" as unknown as OwnerId),
    "ConnectionsOwnerRequired",
  );
  assert.doesNotMatch(err.message, /jose|anticipy\.ai/);
  assert.match(err.message, /16 characters/);
  assert.throws(() => requireOwner("probe", "omar"), { name: "ConnectionsOwnerRequired" });
});

// ===========================================================================
// THE SESSION BODY. The input key is `enable`; the echo says `enabled`.
// ===========================================================================

test("session posts exactly {user_id, manage_connections:{enable:false}}", async () => {
  const f = fakeFetch(happyWorld());
  const out = await provider(f).session(OWNER_A);

  assert.equal(out.sessionId, "sess-A");
  assert.equal(f.calls.length, 1);
  assert.equal(f.calls[0].method, "POST");
  assert.equal(f.calls[0].url, `${COMPOSIO_BASE_URL}/tool_router/session`);
  assert.equal(f.calls[0].headers["x-api-key"], KEY);
  assert.deepEqual(f.calls[0].body, {
    user_id: OWNER_A,
    manage_connections: { enable: false },
  });
  // Measured 2026-09-05: `{"enabled": false}` is a 400 ("Unrecognized key(s)")
  // and a bare boolean is a 400 ("Expected object, received boolean"). Spelling
  // the negative out so a future edit that "fixes" the key to match the echo
  // fails here rather than in production.
  assert.equal("enabled" in f.calls[0].body.manage_connections, false);
  assert.notEqual(typeof f.calls[0].body.manage_connections, "boolean");
});

test("a session whose config comes back enabled is refused and not cached", async () => {
  const f = fakeFetch(() =>
    sessionReply("sess-A", { config: { manage_connections: { enabled: true } } }),
  );
  const p = provider(f);

  await rejectsNamed(() => p.session(OWNER_A), "ConnectionsManageConnectionsOn", /config came back/);
  // Not cached: the next attempt gets a clean try rather than the poisoned one.
  await rejectsNamed(() => p.session(OWNER_A), "ConnectionsManageConnectionsOn");
  assert.equal(f.calls.length, 2);
});

test("the manage tool still in the tool list is refused, even when the config says off", async () => {
  // The config echoes what the vendor thinks we asked for; the tool list is
  // what the model is actually handed. The second one is the one that matters.
  const f = fakeFetch(() =>
    sessionReply("sess-A", {
      config: { manage_connections: { enabled: false } },
      tool_router_tools: [...TOOLS_WITHOUT_MANAGE, MANAGE_CONNECTIONS_TOOL],
    }),
  );
  await rejectsNamed(
    () => provider(f).session(OWNER_A),
    "ConnectionsManageConnectionsOn",
    /COMPOSIO_MANAGE_CONNECTIONS is still/,
  );
});

test("the tool list is read whether the entries are strings or objects", async () => {
  const f = fakeFetch(() =>
    sessionReply("sess-A", {
      config: {},
      tool_router_tools: [{ name: "composio_manage_connections" }],
    }),
  );
  await rejectsNamed(() => provider(f).session(OWNER_A), "ConnectionsManageConnectionsOn");
});

test("a session with the manage tool absent from an object tool list is accepted", async () => {
  const f = fakeFetch(() =>
    sessionReply("sess-A", {
      config: {},
      tool_router_tools: TOOLS_WITHOUT_MANAGE.map((name) => ({ name })),
    }),
  );
  assert.equal((await provider(f).session(OWNER_A)).sessionId, "sess-A");
});

test("a session that confirms nothing is refused — the floor does not lift itself", async () => {
  // Neither `config.manage_connections` nor `tool_router_tools` readable. This
  // must refuse: a floor that waves through when nobody answers is a
  // decoration, and the thing being waved through is a model that can text
  // somebody a raw vendor link.
  const f = fakeFetch(() => ({ status: 201, body: { session_id: "sess-A" } }));
  await rejectsNamed(
    () => provider(f).session(OWNER_A),
    "ConnectionsResponseShape",
    /nothing confirms the connection tool is off/,
  );
});

test("a tool list whose entries hide their identifier confirms NOTHING", async () => {
  // The floor used to lift itself here. Entries spelled under any key other
  // than the three it knew produced an EMPTY list of identifiers, and empty
  // read as "the connection tool is confirmed absent" — so a session was
  // accepted on the strength of a list nobody could parse, with the config
  // unreadable too. The model then holds a tool that texts people raw vendor
  // links and nothing anywhere reports it.
  for (const tools of [
    [{ tool_id: "COMPOSIO_SEARCH_TOOLS" }, { tool_id: MANAGE_CONNECTIONS_TOOL }],
    [{ label: "search" }],
    // A uuid under `id` is not an identifier. Reading one would turn "we could
    // not name this entry" into a confident non-match, which is this same hole
    // wearing a hat — so `id` is deliberately not one of the keys read.
    [{ id: "01hv8z4k9rq2mn", enabled: true }],
    [{ name: 7 }],
    [{}],
    [null],
    [[MANAGE_CONNECTIONS_TOOL]],
  ]) {
    const f = fakeFetch(() => sessionReply("sess-A", { config: {}, tool_router_tools: tools }));
    await rejectsNamed(
      () => provider(f).session(OWNER_A),
      "ConnectionsResponseShape",
      /nothing confirms the connection tool is off/,
    );
  }
});

test("ONE unreadable entry among readable ones voids the verdict", async () => {
  // The unreadable entry is the one that could be the manage tool. A partial
  // read is not a read.
  const f = fakeFetch(() =>
    sessionReply("sess-A", {
      config: {},
      tool_router_tools: [...TOOLS_WITHOUT_MANAGE, { tool_id: "something" }],
    }),
  );
  await rejectsNamed(() => provider(f).session(OWNER_A), "ConnectionsResponseShape");
});

test("CONTROL: an unreadable tool list is still fine when the CONFIG says off", async () => {
  // Two independent confirmations, and only ONE has to answer. Refusing when
  // the config plainly says `enabled: false` would be an outage on the connect
  // path in exchange for nothing.
  const f = fakeFetch(() =>
    sessionReply("sess-A", {
      config: { manage_connections: { enabled: false } },
      tool_router_tools: [{ tool_id: "COMPOSIO_SEARCH_TOOLS" }],
    }),
  );
  assert.equal((await provider(f).session(OWNER_A)).sessionId, "sess-A");
});

test("CONTROL: readable tool lists still confirm, in every spelling the vendor uses", async () => {
  // Reachability for the identifier reader itself: strings, `name`, `slug`,
  // `tool_slug`, `tool_name` and the nested `function.name` of an OpenAI-shaped
  // tool list all parse, so a session with the manage tool absent is accepted
  // and a session with it present is still caught.
  const spellings: Array<(id: string) => unknown> = [
    (id) => id,
    (id) => ({ name: id }),
    (id) => ({ slug: id }),
    (id) => ({ tool_slug: id }),
    (id) => ({ tool_name: id }),
    (id) => ({ function: { name: id } }),
  ];
  for (const spell of spellings) {
    const clean = fakeFetch(() =>
      sessionReply("sess-A", { config: {}, tool_router_tools: TOOLS_WITHOUT_MANAGE.map(spell) }),
    );
    assert.equal((await provider(clean).session(OWNER_A)).sessionId, "sess-A", inspect(spell("x")));

    const dirty = fakeFetch(() =>
      sessionReply("sess-A", {
        config: {},
        tool_router_tools: [...TOOLS_WITHOUT_MANAGE, MANAGE_CONNECTIONS_TOOL].map(spell),
      }),
    );
    await rejectsNamed(() => provider(dirty).session(OWNER_A), "ConnectionsManageConnectionsOn");
  }
});

test("an EMPTY tool list is a readable answer: the tool is not in it", async () => {
  // Zero entries is not the same failure as entries nobody could parse. The
  // vendor said the model is handed nothing, and nothing does not contain the
  // connection tool.
  const f = fakeFetch(() => sessionReply("sess-A", { config: {}, tool_router_tools: [] }));
  assert.equal((await provider(f).session(OWNER_A)).sessionId, "sess-A");
});

test("a session response with no session_id is a shape refusal, not a blank id", async () => {
  const f = fakeFetch(() => ({ status: 201, body: { config: { manage_connections: { enabled: false } } } }));
  await rejectsNamed(() => provider(f).session(OWNER_A), "ConnectionsResponseShape", /no session_id/);
});

// ===========================================================================
// authorize — minted at redeem time, never at send time.
// ===========================================================================

test("authorize posts toolkit, callback and alias to the owner's own session", async () => {
  const f = fakeFetch(happyWorld());
  const out = await provider(f).authorize(OWNER_A, "GoogleCalendar", {
    callbackUrl: CALLBACK,
    alias: "work",
  });

  assert.equal(out.redirectUrl, "https://connect.composio.dev/link/TOKEN-9");
  assert.equal(f.calls[1].path, "/tool_router/session/sess-A/link");
  assert.deepEqual(f.calls[1].body, {
    toolkit: "googlecalendar",
    callback_url: CALLBACK,
    alias: "work",
  });
});

test("authorize omits alias when there is none, and case-folds the one there is", async () => {
  const f = fakeFetch(happyWorld());
  const p = provider(f);

  await p.authorize(OWNER_A, "notion", { callbackUrl: CALLBACK });
  assert.equal("alias" in f.calls[1].body, false);

  await p.authorize(OWNER_A, "notion", { callbackUrl: CALLBACK, alias: null });
  assert.equal("alias" in f.calls[2].body, false);

  await p.authorize(OWNER_A, "notion", { callbackUrl: CALLBACK, alias: "Work" as any });
  assert.equal(f.calls[3].body.alias, "work");
});

test("an alias outside the contract's two values is refused", async () => {
  // A mislabelled account is the "which of my two Gmails is this" failure the
  // alias exists to prevent, and it is invisible until the wrong mailbox
  // answers.
  const f = fakeFetch(happyWorld());
  await rejectsNamed(
    () => provider(f).authorize(OWNER_A, "gmail", { callbackUrl: CALLBACK, alias: "side" as any }),
    "ConnectionsBadArgument",
    /"work" or "personal"/,
  );
  assert.equal(f.calls.length, 0);
});

test("a blank or relative callback is refused before any session is minted", async () => {
  // Composio publishes no success webhook — only `expired` — so the callback is
  // the only moment the product learns a connection happened. A blank one is a
  // connection that works at the vendor and never appears in the app.
  const f = fakeFetch(happyWorld());
  const p = provider(f);
  for (const bad of ["", "   ", "/c/abc/done", "anticipy.ai/c/abc", "ftp://anticipy.ai/x"]) {
    await rejectsNamed(
      () => p.authorize(OWNER_A, "gmail", { callbackUrl: bad }),
      "ConnectionsBadArgument",
      /callbackUrl/,
    );
  }
  assert.equal(f.calls.length, 0);
});

test("a toolkit slug is required", async () => {
  const f = fakeFetch(happyWorld());
  const p = provider(f);
  await rejectsNamed(() => p.authorize(OWNER_A, "  ", { callbackUrl: CALLBACK }), "ConnectionsBadArgument");
  await rejectsNamed(() => p.toolkit(""), "ConnectionsBadArgument");
  assert.equal(f.calls.length, 0);
});

test("a dead session is re-minted once, because minting a link changes nothing", async () => {
  let links = 0;
  const f = fakeFetch((call) => {
    if (call.path === "/tool_router/session") {
      return sessionReply(call.path === "/tool_router/session" && links === 0 ? "sess-OLD" : "sess-NEW");
    }
    if (call.path.endsWith("/link")) {
      links++;
      return links === 1
        ? { status: 404, body: { error: { code: "session_not_found" } } }
        : { body: { redirect_url: "https://connect.composio.dev/link/TOKEN-9" } };
    }
    return happyWorld()(call);
  });

  const out = await provider(f).authorize(OWNER_A, "gmail", { callbackUrl: CALLBACK });
  assert.equal(out.redirectUrl, "https://connect.composio.dev/link/TOKEN-9");
  assert.deepEqual(seq(f), [
    "POST /tool_router/session",
    "POST /tool_router/session/sess-OLD/link",
    "POST /tool_router/session",
    "POST /tool_router/session/sess-NEW/link",
  ]);
});

test("a second dead session is a failure, not an endless remint", async () => {
  const f = fakeFetch((call) => {
    if (call.path === "/tool_router/session") return sessionReply("sess-A");
    if (call.path.endsWith("/link")) return { status: 404, body: {} };
    return happyWorld()(call);
  });
  await rejectsNamed(
    () => provider(f).authorize(OWNER_A, "gmail", { callbackUrl: CALLBACK }),
    "ConnectionsRequestFailed",
    /HTTP 404/,
  );
  assert.equal(f.calls.length, 4);
});

test("a link response with no redirect_url refuses rather than returning a dead button", async () => {
  const f = fakeFetch((call) =>
    call.path.endsWith("/link") ? { body: { ok: true } } : happyWorld()(call),
  );
  await rejectsNamed(
    () => provider(f).authorize(OWNER_A, "gmail", { callbackUrl: CALLBACK }),
    "ConnectionsResponseShape",
    /no redirect_url/,
  );
});

// ===========================================================================
// connections
// ===========================================================================

test("connections maps the vendor's statuses fail-closed and never invents a write opt-in", async () => {
  const f = fakeFetch((call) =>
    call.path.startsWith("/connected_accounts?")
      ? {
          body: {
            items: [
              accountItem({ id: "ca_1", toolkit: { slug: "GMAIL" }, status: "ACTIVE", alias: "Work", last_used_at: "2026-09-05T10:00:00.000Z" }),
              accountItem({ id: "ca_2", toolkit: { slug: "googlecalendar" }, status: "EXPIRED", label: "personal" }),
              accountItem({ id: "ca_3", toolkit: { slug: "notion" }, status: "INITIATED" }),
              accountItem({ id: "ca_4", toolkit: { slug: "slack" }, status: "INITIALIZING", alias: "shared" }),
              accountItem({ id: "ca_5", toolkit: { slug: "linear" }, status: "SOMETHING_NEW_IN_2027" }),
            ],
          },
        }
      : happyWorld()(call),
  );

  const rows = await provider(f).connections(OWNER_A);
  assert.deepEqual(
    rows.map((r) => [r.toolkit, r.status, r.alias]),
    [
      ["gmail", "connected", "work"],
      ["googlecalendar", "needs_reconnect", "personal"],
      ["notion", "disconnected", null],
      ["slack", "disconnected", null],
      ["linear", "disconnected", null],
    ],
  );
  // `writes_enabled` is the Settings toggle and it lives in D1. A provider that
  // guessed `true` would let the Two Hands ladder reach rung 3 — sending mail —
  // for somebody who never opted in.
  assert.deepEqual(rows.map((r) => r.writes_enabled), [false, false, false, false, false]);
  assert.equal(rows[0].last_used_at, Date.parse("2026-09-05T10:00:00.000Z"));
  assert.equal(rows[1].last_used_at, null);
});

test("connections refuses an unreadable item instead of reporting an app as unconnected", async () => {
  // "You have not connected Notion" is the claim that texts somebody about the
  // app they connected yesterday.
  const f = fakeFetch((call) =>
    call.path.startsWith("/connected_accounts?")
      ? { body: { items: [accountItem(), { user_id: OWNER_A, toolkit: { slug: "notion" } }] } }
      : happyWorld()(call),
  );
  await rejectsNamed(
    () => provider(f).connections(OWNER_A),
    "ConnectionsResponseShape",
    /1 of 2 connected accounts/,
  );
});

test("connections refuses a response with no items array", async () => {
  const f = fakeFetch(() => ({ body: { data: [] } }));
  await rejectsNamed(() => provider(f).connections(OWNER_A), "ConnectionsResponseShape", /no items array/);
});

test("connections reads a bare array too, and an empty list is an honest empty list", async () => {
  const f = fakeFetch(() => ({ body: [] }));
  assert.deepEqual(await provider(f).connections(OWNER_A), []);
});

// ===========================================================================
// disconnect — REVOKE, THEN DELETE.
// ===========================================================================

test("disconnect revokes BEFORE it deletes", async () => {
  // Delete alone leaves the token live at Google while the product told the
  // person their access was revoked. The order is the whole guarantee, so the
  // SEQUENCE is what is asserted.
  const f = fakeFetch(happyWorld());
  const out = await provider(f).disconnect(OWNER_A, "ca_BNgvxQtJ703C");

  assert.deepEqual(seq(f), [
    "GET /connected_accounts?user_ids=sxkotd1h02qb6gw",
    "POST /connected_accounts/ca_BNgvxQtJ703C/revoke",
    "DELETE /connected_accounts/ca_BNgvxQtJ703C",
  ]);
  assert.deepEqual(out, { revoked: true, deleted: true, revokeUnavailable: false });
});

test("a 409 revoke sets revokeUnavailable and still deletes", async () => {
  // The measured 409: the account is not in a revocable state. About 5% cannot
  // be revoked programmatically at all, and the confirmation copy has to say
  // "removed here, you may need to clear it in the app's own settings" rather
  // than claim a revoke that did not happen.
  const f = fakeFetch((call) =>
    call.path.endsWith("/revoke")
      ? { status: 409, body: { error: { code: "not_active" } } }
      : happyWorld()(call),
  );
  const out = await provider(f).disconnect(OWNER_A, "ca_BNgvxQtJ703C");

  assert.deepEqual(out, { revoked: false, deleted: true, revokeUnavailable: true });
  assert.deepEqual(seq(f).slice(1), [
    "POST /connected_accounts/ca_BNgvxQtJ703C/revoke",
    "DELETE /connected_accounts/ca_BNgvxQtJ703C",
  ]);
});

test("a request-side revoke failure is NOT 'this account cannot be revoked'", async () => {
  // 400/404/405/422 say the REQUEST was wrong — a bad path, a stale id, a body
  // the vendor rejected. Reading them as "this account cannot be revoked
  // programmatically" did two harmful things at once: it deleted the row, which
  // destroys the only handle that could ever revoke a token that is still live
  // at Google, and it drove copy telling the owner to go clear their own Google
  // settings for a failure that was ours.
  for (const status of [400, 404, 405, 410, 422]) {
    const f = fakeFetch((call) =>
      call.path.endsWith("/revoke") ? { status, body: { error: { code: "bad_request" } } } : happyWorld()(call),
    );
    await rejectsNamed(
      () => provider(f).disconnect(OWNER_A, "ca_BNgvxQtJ703C"),
      "ConnectionsRequestFailed",
      new RegExp(`HTTP ${status}`),
    );
    assert.equal(seq(f).some((s) => s.startsWith("DELETE")), false, `deleted after ${status}`);
  }
});

test("a retryable revoke failure aborts — the delete would strand a live token", async () => {
  // DELETE destroys the account id, and that id is the only handle we will ever
  // have for revoking this token. A 500 may work on the next tap; a deleted row
  // never will.
  for (const status of [500, 502, 429, 408]) {
    const f = fakeFetch((call) =>
      call.path.endsWith("/revoke") ? { status, body: {} } : happyWorld()(call),
    );
    await rejectsNamed(
      () => provider(f).disconnect(OWNER_A, "ca_BNgvxQtJ703C"),
      "ConnectionsRequestFailed",
      new RegExp(`HTTP ${status}`),
    );
    assert.equal(seq(f).some((s) => s.startsWith("DELETE")), false);
  }
});

test("a transport failure during revoke aborts before the delete", async () => {
  const f = fakeFetch((call) =>
    call.path.endsWith("/revoke") ? { throws: new TypeError("fetch failed") } : happyWorld()(call),
  );
  await rejectsNamed(
    () => provider(f).disconnect(OWNER_A, "ca_BNgvxQtJ703C"),
    "ConnectionsRequestFailed",
    /HTTP 0/,
  );
  assert.equal(seq(f).some((s) => s.startsWith("DELETE")), false);
});

test("a 401 on revoke is OUR key, not their account, so it never claims revokeUnavailable", async () => {
  // revokeUnavailable drives copy shown to a human. Telling somebody to go
  // clean up their Google settings because we misconfigured a header is a lie
  // about their own security.
  for (const status of [401, 403]) {
    const f = fakeFetch((call) =>
      call.path.endsWith("/revoke") ? { status, body: {} } : happyWorld()(call),
    );
    await rejectsNamed(() => provider(f).disconnect(OWNER_A, "ca_BNgvxQtJ703C"), "ConnectionsRequestFailed");
    assert.equal(seq(f).some((s) => s.startsWith("DELETE")), false);
  }
});

test("a revoke that worked and a delete that did not is reported, not thrown", async () => {
  // The dangerous half succeeded: the token is dead and only the vendor's
  // bookkeeping row survives. Throwing would make the caller tell a person
  // their access is still live when it is not.
  const f = fakeFetch((call) =>
    call.method === "DELETE" ? { status: 500, body: {} } : happyWorld()(call),
  );
  const out = await provider(f).disconnect(OWNER_A, "ca_BNgvxQtJ703C");
  assert.deepEqual(out, { revoked: true, deleted: false, revokeUnavailable: false });
});

test("a delete that failed after a revoke that also failed is a hard failure", async () => {
  const f = fakeFetch((call) => {
    if (call.path.endsWith("/revoke")) return { status: 409, body: {} };
    if (call.method === "DELETE") return { status: 500, body: {} };
    return happyWorld()(call);
  });
  await rejectsNamed(
    () => provider(f).disconnect(OWNER_A, "ca_BNgvxQtJ703C"),
    "ConnectionsRequestFailed",
    /disconnect delete/,
  );
});

test("a 404 on delete means the row is already gone, which is what delete was for", async () => {
  const f = fakeFetch((call) =>
    call.method === "DELETE" ? { status: 404, body: {} } : happyWorld()(call),
  );
  const out = await provider(f).disconnect(OWNER_A, "ca_BNgvxQtJ703C");
  assert.deepEqual(out, { revoked: true, deleted: true, revokeUnavailable: false });
});

test("disconnect requires an account id", async () => {
  const f = fakeFetch(happyWorld());
  await rejectsNamed(() => provider(f).disconnect(OWNER_A, "   "), "ConnectionsBadArgument");
  assert.equal(f.calls.length, 0);
});

// ===========================================================================
// toolkit — the generic connect page's only source of app-specific anything.
// ===========================================================================

test("toolkit returns name, logo, description, appUrl and scopes from the vendor", async () => {
  const f = fakeFetch(() => ({
    body: {
      slug: "googlecalendar",
      name: "Google Calendar",
      meta: { logo: "https://cdn.example/gcal.png", description: "Calendars and events." },
      app_url: "https://calendar.google.com",
      scopes: ["https://www.googleapis.com/auth/calendar"],
      auth_config_details: [
        { scopes: ["https://www.googleapis.com/auth/calendar.events", "https://www.googleapis.com/auth/calendar"] },
      ],
    },
  }));

  const meta = await provider(f).toolkit("GoogleCalendar");
  assert.equal(f.calls[0].path, "/toolkits/googlecalendar");
  assert.deepEqual(meta, {
    slug: "googlecalendar",
    name: "Google Calendar",
    logo: "https://cdn.example/gcal.png",
    description: "Calendars and events.",
    appUrl: "https://calendar.google.com",
    // Gathered across the places the vendor puts them, deduped, order kept.
    scopes: [
      "https://www.googleapis.com/auth/calendar",
      "https://www.googleapis.com/auth/calendar.events",
    ],
  });
});

test("a toolkit with no name refuses instead of shipping the slug as a name", async () => {
  // "Connect your googlecalendar" is the sentence a slug fallback ships, and it
  // would read as a copy decision rather than a broken fetch.
  const f = fakeFetch(() => ({ body: { slug: "googlecalendar", scopes: [] } }));
  await rejectsNamed(() => provider(f).toolkit("googlecalendar"), "ConnectionsResponseShape", /no name/);
});

test("an absent scopes list comes back empty, and that means UNKNOWN", async () => {
  // Recorded here because the permission sentences read this field: an empty
  // array is "the vendor told us nothing", never "this app asks for nothing".
  const f = fakeFetch(() => ({ body: { name: "Notion" } }));
  const meta = await provider(f).toolkit("notion");
  assert.deepEqual(meta.scopes, []);
  assert.equal(meta.slug, "notion");
  assert.equal(meta.logo, null);
  assert.equal(meta.description, null);
  assert.equal(meta.appUrl, null);
});

test("a toolkit fetch that fails is a named failure, not an empty catalog entry", async () => {
  const f = fakeFetch(() => ({ status: 503, body: {} }));
  await rejectsNamed(() => provider(f).toolkit("notion"), "ConnectionsRequestFailed", /HTTP 503/);
});

// ===========================================================================
// SECRETS. A key, a token, and a tokenised redirect_url.
// ===========================================================================

test("this adapter writes nothing to a log, on the happy path or any failure path", async () => {
  const written: string[] = [];
  const methods = ["log", "info", "warn", "error", "debug", "trace"] as const;
  const saved = methods.map((m) => console[m]);
  for (const m of methods) {
    (console as any)[m] = (...args: unknown[]) => written.push(args.map((a) => String(a)).join(" "));
  }
  try {
    const good = provider(fakeFetch(happyWorld()));
    await good.session(OWNER_A);
    await good.authorize(OWNER_A, "gmail", { callbackUrl: CALLBACK });
    await good.connections(OWNER_A);
    await good.disconnect(OWNER_A, "ca_BNgvxQtJ703C");
    await good.toolkit("gmail");

    const bad = provider(fakeFetch(() => ({ status: 500, body: { error: { code: "boom" } } })));
    for (const call of [
      () => bad.session(OWNER_A),
      () => bad.authorize(OWNER_A, "gmail", { callbackUrl: CALLBACK }),
      () => bad.connections(OWNER_A),
      () => bad.disconnect(OWNER_A, "ca_1"),
      () => bad.toolkit("gmail"),
    ]) {
      await call().then(() => {}, () => {});
    }
    await new ComposioConnections({}).session(OWNER_A).then(() => {}, () => {});
  } finally {
    methods.forEach((m, i) => ((console as any)[m] = saved[i]));
  }
  assert.deepEqual(written, []);
});

test("a key the vendor echoes back is redacted out of the error it lands in", async () => {
  const f = fakeFetch(() => ({ status: 400, body: { error: { code: KEY } } }));
  const err = await rejectsNamed(() => provider(f).connections(OWNER_A), "ConnectionsRequestFailed");
  assert.equal(err.message.includes(KEY), false);
  assert.match(err.message, /\[redacted\]/);
});

test("a tokenised URL never survives into an error message", async () => {
  // The whole point of anticipy.ai/c/{token} is that the vendor's own tokenised
  // link is never written down anywhere — a log line included.
  const link = "https://connect.composio.dev/link/SUPER-SECRET-TOKEN";
  const f = fakeFetch((call) =>
    call.path.endsWith("/link")
      ? { status: 400, body: { error: { code: link, message: `bad request for ${link}` } } }
      : happyWorld()(call),
  );
  const err = await rejectsNamed(
    () => provider(f).authorize(OWNER_A, "gmail", { callbackUrl: CALLBACK }),
    "ConnectionsRequestFailed",
  );
  assert.equal(err.message.includes("SUPER-SECRET-TOKEN"), false);
  assert.equal(err.message.includes("://"), false);
});

test("a transport rejection carrying the key in its message does not carry it onward", async () => {
  const f = fakeFetch(() => ({ throws: new TypeError(`connect failed sending x-api-key ${KEY}`) }));
  const err = await rejectsNamed(() => provider(f).connections(OWNER_A), "ConnectionsRequestFailed");
  assert.equal(err.message.includes(KEY), false);
  assert.match(err.message, /TypeError/);
});

test("a URL reaching an error by ANY route is stripped, not just the vendor-token route", async () => {
  // Two independent redactions guard the same leak: `#errorToken` drops a
  // URL-shaped vendor code, and `#safe` strips a URL out of whatever text
  // survives. This test exercises the second one on its own, through the
  // transport's error NAME — the one string in this adapter that comes from a
  // library rather than from the vendor's JSON. Without it the redaction that
  // matters for every FUTURE error message in this file would be untested, and
  // an untested choke point is a comment.
  const boom = new TypeError("nope");
  boom.name = "FetchError https://connect.composio.dev/link/SUPER-SECRET-TOKEN";
  const f = fakeFetch(() => ({ throws: boom }));
  const err = await rejectsNamed(() => provider(f).connections(OWNER_A), "ConnectionsRequestFailed");

  assert.equal(err.message.includes("SUPER-SECRET-TOKEN"), false);
  assert.equal(err.message.includes("://"), false);
  // Still says something a human can act on.
  assert.match(err.message, /FetchError/);
  assert.match(err.message, /\[redacted-url\]/);
});

test("the key is not reachable through inspection or serialisation of the provider", async () => {
  const p = provider(fakeFetch(happyWorld()));
  assert.equal(JSON.stringify(p).includes(KEY), false);
  assert.equal(inspect(p, { depth: 6 }).includes(KEY), false);
});

// ===========================================================================
// NO KEY. Every method refuses by name; none of them goes quiet.
// ===========================================================================

test("with no api key every method throws ConnectionsUnconfigured and issues no request", async () => {
  const f = fakeFetch(happyWorld());
  const p = new ComposioConnections({ fetchImpl: f });

  await rejectsNamed(() => p.session(OWNER_A), "ConnectionsUnconfigured", /session/);
  await rejectsNamed(() => p.authorize(OWNER_A, "gmail", { callbackUrl: CALLBACK }), "ConnectionsUnconfigured");
  await rejectsNamed(() => p.connections(OWNER_A), "ConnectionsUnconfigured", /connections/);
  // disconnect could have returned {revoked:false, deleted:false} — it must
  // not: that shape reads as "we tried and could not", and the copy for it
  // tells the owner their access was removed.
  await rejectsNamed(() => p.disconnect(OWNER_A, "ca_1"), "ConnectionsUnconfigured");
  await rejectsNamed(() => p.toolkit("gmail"), "ConnectionsUnconfigured", /toolkit/);
  assert.equal(f.calls.length, 0);

  // A whitespace-only key is no key, because a header value with a newline is
  // rejected by fetch as an invalid HEADER, which reads as a dead vendor.
  const blank = new ComposioConnections({ apiKey: " \n ", fetchImpl: f });
  await rejectsNamed(() => blank.session(OWNER_A), "ConnectionsUnconfigured");
  assert.equal(f.calls.length, 0);
});

test("a key with no usable transport fails by name rather than reaching the network", async () => {
  // The fallback is `globalThis.fetch`, which exists on Node 24 — so the only
  // way to observe the absent case is to hand it something that is not a
  // function. It must refuse by name; the one thing it may not do is quietly
  // call the real vendor from a test.
  const p = new ComposioConnections({ apiKey: KEY, fetchImpl: 0 as any });
  await rejectsNamed(() => p.session(OWNER_A), "ConnectionsRequestFailed", /no fetch implementation/);
  await rejectsNamed(() => p.toolkit("gmail"), "ConnectionsRequestFailed", /no fetch implementation/);
});

// ===========================================================================
// The small readers, each of which decides a mapping and never a meaning.
// ===========================================================================

test("the exported readers map enums and identifiers, and nothing else", () => {
  assert.equal(mapConnectionStatus("ACTIVE"), "connected");
  assert.equal(mapConnectionStatus("active"), "connected");
  assert.equal(mapConnectionStatus("EXPIRED"), "needs_reconnect");
  assert.equal(mapConnectionStatus("INITIATED"), "disconnected");
  assert.equal(mapConnectionStatus(undefined), "disconnected");

  assert.equal(readAlias("WORK"), "work");
  assert.equal(readAlias(" personal "), "personal");
  assert.equal(readAlias("shared"), null);
  assert.equal(readAlias(null), null);

  assert.equal(readLastUsedAt(1757068800000), 1757068800000);
  assert.equal(readLastUsedAt("2026-09-05T10:00:00.000Z"), Date.parse("2026-09-05T10:00:00.000Z"));
  assert.equal(readLastUsedAt("whenever"), null);
  assert.equal(readLastUsedAt(null), null);

  assert.equal(toolkitSlug(" GMAIL "), "gmail");
  assert.equal(toolkitSlug(undefined), "");

  assert.equal(isRetryableStatus(0), true);
  assert.equal(isRetryableStatus(429), true);
  assert.equal(isRetryableStatus(503), true);
  assert.equal(isRetryableStatus(409), false);
  assert.equal(isRetryableStatus(404), false);

  // 409 — "not in a revocable state" — is the ONE measured answer that means
  // this account cannot be revoked programmatically. Everything else is our
  // request, our key, or a bad day at the vendor, and none of those may drive
  // copy telling a person to go clear their own Google settings.
  assert.equal(revokeIsDefinitivelyUnavailable(409), true);
  assert.equal(revokeIsDefinitivelyUnavailable(400), false);
  assert.equal(revokeIsDefinitivelyUnavailable(404), false);
  assert.equal(revokeIsDefinitivelyUnavailable(405), false);
  assert.equal(revokeIsDefinitivelyUnavailable(410), false);
  assert.equal(revokeIsDefinitivelyUnavailable(422), false);
  assert.equal(revokeIsDefinitivelyUnavailable(401), false);
  assert.equal(revokeIsDefinitivelyUnavailable(403), false);
  assert.equal(revokeIsDefinitivelyUnavailable(500), false);

  // The owner echo, four states, because "a stranger", "unreadable" and
  // "nobody said" are three different answers and only one of them is ours.
  assert.equal(readOwnerEcho({ user_id: OWNER_A }, OWNER_A), "ours");
  assert.equal(readOwnerEcho({ user_ids: [OWNER_A] }, OWNER_A), "ours");
  assert.equal(readOwnerEcho({ user: { id: OWNER_A } }, OWNER_A), "ours");
  assert.equal(readOwnerEcho({ user_ids: [OWNER_B] }, OWNER_A), "foreign");
  assert.equal(readOwnerEcho({ userId: OWNER_B }, OWNER_A), "foreign");
  assert.equal(readOwnerEcho({ user_ids: [OWNER_A, OWNER_B] }, OWNER_A), "foreign");
  assert.equal(readOwnerEcho({ user_id: null, user_ids: [OWNER_B] }, OWNER_A), "foreign");
  assert.equal(readOwnerEcho({ user_id: 1 }, OWNER_A), "unreadable");
  assert.equal(readOwnerEcho({ user_id: "" }, OWNER_A), "unreadable");
  assert.equal(readOwnerEcho({ user_ids: [] }, OWNER_A), "unreadable");
  assert.equal(readOwnerEcho({ id: "ca_1" }, OWNER_A), "absent");
  assert.equal(readOwnerEcho({ user_id: undefined }, OWNER_A), "absent");
});
