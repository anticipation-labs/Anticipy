/**
 * THE CONNECTIONS ADAPTER AND ITS COPY, IN THE WORKER.
 *
 *   node --experimental-strip-types migration/workers/test/connections-provider.test.ts
 *
 * Every test here injects its own transport. There is no network in this file,
 * no API key is needed to run it, and no Composio account exists behind it.
 *
 * The tests are ordered by what they protect, hardest first. The first block is
 * the one the provider is shaped around: a connection bound to the wrong
 * person. That already happened once during the spike — one operator's Gmail
 * connected under `user_id: "omar"` — and it is invisible from the outside,
 * because a stranger's mailbox works perfectly. Everything after it is ordinary
 * adapter behaviour, then the words the owner actually reads.
 *
 * TWO FACTS ARE READ OUT OF THE CONTRACT'S SOURCE rather than typed here: the
 * owner-id shape and the five real moments. `src/connections/*.ts` re-declare
 * both so the deployed Worker carries no runtime edge into the spike tree, and
 * a copy nobody checks is how two files drift for a month. This is the trick
 * test/llm-proxy.test.ts already uses for the extension's reply floor.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { inspect } from "node:util";

import type { OwnerId, ToolkitMeta } from "../../../spike/two-hands/src/connections/contract.ts";
import {
  COMPOSIO_BASE_URL,
  ComposioConnections,
  MANAGE_CONNECTIONS_TOOL,
  MAX_CACHED_SESSIONS,
  MAX_SEARCH_RESULTS,
  OWNER_ID_SHAPE,
  connectionsFromEnv,
  isRetryableStatus,
  mapConnectionStatus,
  readAlias,
  readLastUsedAt,
  readOwnerEcho,
  requireOwner,
  resetConnectionsProvider,
  revokeIsDefinitivelyUnavailable,
  toolkitSlug,
} from "../src/connections/provider.ts";
import {
  CONNECT_LINK_PREFIX,
  FORBIDDEN_TERMS,
  MAX_ASK_CHARS_GSM7,
  MAX_ASK_CHARS_UCS2,
  MAX_ASK_SEGMENTS,
  MAX_SENTENCE_CHARS,
  PermissionWordsRefused,
  SENTENCE_COUNT,
  STIFF_FORMS,
  TRIGGER_SCORE,
  askText,
  makePermissionWords,
  permissionSentences,
  smsShape,
} from "../src/connections/words.ts";
import type { AskEvidence, Refusal } from "../src/connections/words.ts";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(here, "..", "..", "..");
const contractSource = readFileSync(
  join(repoRoot, "spike", "two-hands", "src", "connections", "contract.ts"),
  "utf8",
);

let failures = 0;
let passes = 0;
function check(what: string, fn: () => void | Promise<void>): Promise<void> {
  return Promise.resolve()
    .then(fn)
    .then(() => { passes++; })
    .catch((err) => {
      failures++;
      console.error("FAIL " + what + "\n     " + (err as Error).message);
    });
}

/** Two real owner-row-shaped ids: 15 lowercase alphanumerics, as D1 mints them.
 *  `OWNER_A` is the one recorded in research/2026-09-05-composio-connections.md
 *  and `OWNER_B` is the production probe owner from CLAUDE.md. Two of them
 *  because one is never enough to catch a cache that leaks across people. */
const OWNER_A = "sxkotd1h02qb6gw" as OwnerId;
const OWNER_B = "qeuy6sv1raof9rw" as OwnerId;

const KEY = "comp_live_supersecret_key_1234567890";
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
  const impl = async (url: any, init: any) => {
    const full = String(url);
    const raw = typeof init?.body === "string" ? init.body : "";
    const call: Recorded = {
      method: init?.method ?? "GET",
      path: full.startsWith(COMPOSIO_BASE_URL) ? full.slice(COMPOSIO_BASE_URL.length) : full,
      headers: (init?.headers ?? {}) as Record<string, string>,
      body: raw === "" ? undefined : JSON.parse(raw),
    };
    calls.push(call);
    const reply = handler(call, calls.length);
    if (reply.throws !== undefined) throw reply.throws;
    const status = reply.status ?? 200;
    return {
      status,
      json: async () => reply.body ?? null,
    } as unknown as Response;
  };
  return { calls, impl: impl as unknown as typeof globalThis.fetch };
}

function sessionBody(id: string, over: Record<string, unknown> = {}) {
  return {
    session_id: id,
    config: { manage_connections: { enabled: false } },
    tool_router_tools: TOOLS_WITHOUT_MANAGE,
    ...over,
  };
}

/** A connected-account row in the measured shape. */
function accountRow(owner: string, over: Record<string, unknown> = {}) {
  return {
    id: "ca_BNgvxQtJ703C",
    user_id: owner,
    toolkit: { slug: "gmail" },
    status: "ACTIVE",
    ...over,
  };
}

function provider(impl: typeof globalThis.fetch, apiKey: string = KEY) {
  return new ComposioConnections({ apiKey, fetchImpl: impl });
}

async function refusalOf(fn: () => Promise<unknown>): Promise<Error> {
  try {
    await fn();
  } catch (err) {
    return err as Error;
  }
  throw new Error("expected a refusal, got a value");
}

// ===========================================================================
// 0. THE CONTRACT IS THE CONTRACT — the two re-declared facts, pinned.
// ===========================================================================

await check("the owner-id shape is the contract's own, read from its source", () => {
  assert.ok(
    contractSource.includes("/^[a-z0-9]{15}$/"),
    "the connections contract no longer validates owner ids as 15 lowercase alphanumerics; "
      + "src/connections/provider.ts carries a copy of that rule and must be updated with it",
  );
  assert.equal(OWNER_ID_SHAPE.source, "^[a-z0-9]{15}$");
  assert.ok(OWNER_ID_SHAPE.test("sxkotd1h02qb6gw"));
  assert.ok(!OWNER_ID_SHAPE.test("omar"), "a name is not an owner id");
  assert.ok(!OWNER_ID_SHAPE.test("jose@anticipy.ai"), "an email is not an owner id");
  assert.ok(!OWNER_ID_SHAPE.test("SXKOTD1H02QB6GW"), "ids are lowercase");
});

await check("every real moment in words.ts is a real moment in the contract", () => {
  const block = contractSource.match(/TRIGGER_SCORE:\s*Record<NudgeTrigger,\s*number>\s*=\s*\{([^}]*)\}/);
  assert.ok(block, "the contract no longer declares TRIGGER_SCORE as a Record<NudgeTrigger, number>");
  const pairs = [...block![1].matchAll(/([a-z_]+):\s*([0-9.]+)/g)];
  assert.equal(pairs.length, 5, "the contract declares five triggers");
  const fromContract: Record<string, number> = {};
  for (const [, name, value] of pairs) fromContract[name!] = Number(value);
  assert.deepEqual(
    { ...TRIGGER_SCORE },
    fromContract,
    "words.ts and the contract disagree about which moments are real, or about their scores",
  );
});

await check("our link prefix is the one the recorded requirement names", () => {
  // Not in contract.ts — it is in the research record of what the spec requires,
  // which is where "every link is anticipy.ai/c/{token}" was written down after
  // four raw vendor links went into messages and died unused.
  const research = readFileSync(
    join(repoRoot, "research", "2026-09-05-composio-connections.md"),
    "utf8",
  );
  assert.ok(research.includes("anticipy.ai/c/{token}"), "the recorded link shape moved");
  assert.equal(CONNECT_LINK_PREFIX, "https://anticipy.ai/c/");
});

// ===========================================================================
// 1. THE WRONG PERSON. Everything in this block is the failure that happened.
// ===========================================================================

await check("two owners get two sessions, and a cached session is never returned for the other one", async () => {
  const { calls, impl } = fakeFetch((call) => ({
    status: 201,
    body: sessionBody(`sess-${call.body.user_id}`),
  }));
  const p = provider(impl);
  const a = await p.session(OWNER_A);
  const b = await p.session(OWNER_B);
  const aAgain = await p.session(OWNER_A);
  assert.equal(a.sessionId, `sess-${OWNER_A}`);
  assert.equal(b.sessionId, `sess-${OWNER_B}`);
  assert.equal(aAgain.sessionId, a.sessionId, "the cache serves the same owner");
  assert.notEqual(a.sessionId, b.sessionId);
  assert.equal(calls.length, 2, "one session per owner, and the third call was cached");
});

await check("the cached session follows the owner all the way onto the wire", async () => {
  const { calls, impl } = fakeFetch((call) =>
    call.path === "/tool_router/session"
      ? { status: 201, body: sessionBody(`sess-${call.body.user_id}`) }
      : { status: 200, body: { redirect_url: "https://vendor.example/link/xyz" } });
  const p = provider(impl);
  await p.authorize(OWNER_A, "gmail", { callbackUrl: CALLBACK });
  await p.authorize(OWNER_B, "gmail", { callbackUrl: CALLBACK });
  const links = calls.filter((c) => c.path.endsWith("/link"));
  assert.equal(links.length, 2);
  assert.equal(links[0]!.path, `/tool_router/session/sess-${OWNER_A}/link`);
  assert.equal(links[1]!.path, `/tool_router/session/sess-${OWNER_B}/link`);
});

await check("concurrent calls for one owner mint ONE session; two owners still mint two", async () => {
  const { calls, impl } = fakeFetch((call) => ({
    status: 201,
    body: sessionBody(`sess-${call.body.user_id}`),
  }));
  const p = provider(impl);
  const [a1, a2, b1] = await Promise.all([p.session(OWNER_A), p.session(OWNER_A), p.session(OWNER_B)]);
  assert.equal(a1.sessionId, a2.sessionId);
  assert.notEqual(a1.sessionId, b1.sessionId);
  assert.equal(calls.length, 2, "one in-flight creation per owner");
});

await check("a session id the vendor hands to a second owner is refused, not shared", async () => {
  const { impl } = fakeFetch(() => ({ status: 201, body: sessionBody("sess-shared") }));
  const p = provider(impl);
  await p.session(OWNER_A);
  const err = await refusalOf(() => p.session(OWNER_B));
  assert.equal(err.name, "ConnectionsOwnerMismatch");
  assert.match(err.message, /already minted for a different owner/);
});

const FOREIGN_SPELLINGS: Array<[string, Record<string, unknown>]> = [
  ["user_id as a bare string", { user_id: OWNER_B }],
  ["user_ids as an array", { user_id: undefined, user_ids: [OWNER_B] }],
  ["userId camelCase", { user_id: undefined, userId: OWNER_B }],
  ["userIds camelCase array", { user_id: undefined, userIds: [OWNER_B] }],
  ["nested user.id", { user_id: undefined, user: { id: OWNER_B } }],
  ["nested user.user_id", { user_id: undefined, user: { user_id: OWNER_B } }],
  ["nested user.userId", { user_id: undefined, user: { userId: OWNER_B } }],
  ["ours AND a stranger in one array", { user_ids: [OWNER_A, OWNER_B], user_id: undefined }],
];

for (const [what, over] of FOREIGN_SPELLINGS) {
  await check(`a stranger's id as ${what} is a mismatch, not a row we adopt`, async () => {
    const { impl } = fakeFetch(() => ({ status: 200, body: { items: [accountRow(OWNER_B, over)] } }));
    const err = await refusalOf(() => provider(impl).connections(OWNER_A));
    assert.equal(err.name, "ConnectionsOwnerMismatch", `${what} was adopted`);
    assert.match(err.message, /bound to a different user_id/);
  });
}

const UNREADABLE_ECHOES: Array<[string, Record<string, unknown>]> = [
  ["an empty string", { user_id: "" }],
  ["a null", { user_id: null }],
  ["a number", { user_id: 12345 }],
  ["an empty array", { user_id: undefined, user_ids: [] }],
  ["a nested object naming nobody", { user_id: undefined, user: {} }],
  ["a nested object holding a blank id", { user_id: undefined, user: { id: "" } }],
];

for (const [what, over] of UNREADABLE_ECHOES) {
  await check(`an owner echo that is ${what} refuses — unreadable is not agreement`, async () => {
    const { impl } = fakeFetch(() => ({ status: 200, body: { items: [accountRow(OWNER_A, over)] } }));
    const err = await refusalOf(() => provider(impl).connections(OWNER_A));
    assert.equal(err.name, "ConnectionsResponseShape", `${what} was read as agreement`);
    assert.match(err.message, /could not be read as the one queried/);
  });
}

await check("a row that names no owner at all is refused, not adopted under ours", async () => {
  const { impl } = fakeFetch(() => ({
    status: 200,
    body: { items: [{ id: "ca_1", toolkit: { slug: "gmail" }, status: "ACTIVE" }] },
  }));
  const err = await refusalOf(() => provider(impl).connections(OWNER_A));
  assert.equal(err.name, "ConnectionsResponseShape");
  assert.match(err.message, /named no owner at all/);
});

await check("disconnect() cannot be walked onto a stranger's account by an unreadable echo", async () => {
  const { calls, impl } = fakeFetch(() => ({
    status: 200,
    body: { items: [accountRow(OWNER_A, { id: "ca_stranger", user_id: "" })] },
  }));
  const err = await refusalOf(() => provider(impl).disconnect(OWNER_A, "ca_stranger"));
  assert.equal(err.name, "ConnectionsResponseShape");
  assert.equal(calls.length, 1, "the listing refused; nothing was revoked and nothing was deleted");
  assert.ok(!calls.some((c) => c.method === "DELETE" || c.path.endsWith("/revoke")));
});

await check("disconnect() refuses an account id that is not in this owner's list", async () => {
  const { calls, impl } = fakeFetch(() => ({ status: 200, body: { items: [accountRow(OWNER_A)] } }));
  const err = await refusalOf(() => provider(impl).disconnect(OWNER_A, "ca_somebody_else"));
  assert.equal(err.name, "ConnectionsOwnerMismatch");
  assert.equal(calls.length, 1, "proved ownership BEFORE touching the unscoped endpoints");
});

// --- THE PORT'S FIX: a positive `ours` outranks the quiet verdicts. ---------

await check("FIX: a row that names the queried owner is ours even when another field is blank", () => {
  assert.equal(readOwnerEcho({ user_id: OWNER_A, user_ids: [] }, OWNER_A), "ours");
  assert.equal(readOwnerEcho({ user_ids: [OWNER_A], user_id: "" }, OWNER_A), "ours");
  assert.equal(readOwnerEcho({ user_id: OWNER_A, user: {} }, OWNER_A), "ours");
});

await check("FIX: connections() returns the row instead of taking the whole call down", async () => {
  const { impl } = fakeFetch(() => ({
    status: 200,
    body: { items: [accountRow(OWNER_A, { user_ids: [] })] },
  }));
  const rows = await provider(impl).connections(OWNER_A);
  assert.equal(rows.length, 1, "an empty user_ids beside a correct user_id is not an outage");
  assert.equal(rows[0]!.user_id, OWNER_A);
});

await check("CONTROL: a stranger anywhere still outranks a correct field on the same row", () => {
  assert.equal(readOwnerEcho({ user_id: OWNER_A, user_ids: [OWNER_B] }, OWNER_A), "foreign");
  assert.equal(readOwnerEcho({ user_id: OWNER_A, user: { id: OWNER_B } }, OWNER_A), "foreign");
  assert.equal(readOwnerEcho({ user_ids: [OWNER_A, OWNER_B] }, OWNER_A), "foreign");
});

await check("CONTROL: the quiet verdicts are still quiet, and still refuse", () => {
  assert.equal(readOwnerEcho({ user_id: "", user_ids: [] }, OWNER_A), "unreadable");
  assert.equal(readOwnerEcho({ id: "ca_1" }, OWNER_A), "absent");
  assert.equal(readOwnerEcho({ user_id: OWNER_B }, OWNER_A), "foreign");
  assert.equal(readOwnerEcho({ user_id: OWNER_A }, OWNER_A), "ours");
});

await check("CONTROL: every correctly-scoped spelling of our own id still lists", async () => {
  const spellings: Array<Record<string, unknown>> = [
    { user_id: OWNER_A },
    { user_id: undefined, user_ids: [OWNER_A] },
    { user_id: undefined, userId: OWNER_A },
    { user_id: undefined, userIds: [OWNER_A] },
    { user_id: undefined, user: { id: OWNER_A } },
    { user_id: undefined, user: { user_id: OWNER_A } },
    { user_id: undefined, user: { userId: OWNER_A } },
  ];
  for (const over of spellings) {
    const { impl } = fakeFetch(() => ({ status: 200, body: { items: [accountRow(OWNER_A, over)] } }));
    const rows = await provider(impl).connections(OWNER_A);
    assert.equal(rows.length, 1, `${JSON.stringify(over)} was refused`);
    assert.equal(rows[0]!.user_id, OWNER_A);
  }
});

await check("CONTROL: a correctly-scoped disconnect still revokes and deletes", async () => {
  const { calls, impl } = fakeFetch((call) =>
    call.method === "GET" ? { status: 200, body: { items: [accountRow(OWNER_A)] } } : { status: 200, body: {} });
  const out = await provider(impl).disconnect(OWNER_A, "ca_BNgvxQtJ703C");
  assert.deepEqual(out, { revoked: true, deleted: true, revokeUnavailable: false });
  assert.deepEqual(calls.map((c) => c.method), ["GET", "POST", "DELETE"]);
});

await check("connections() stamps OUR validated owner on every row it returns", async () => {
  const { impl } = fakeFetch(() => ({
    status: 200,
    body: { items: [accountRow(OWNER_A), accountRow(OWNER_A, { id: "ca_2", toolkit: { slug: "notion" } })] },
  }));
  const rows = await provider(impl).connections(OWNER_A);
  assert.equal(rows.length, 2);
  for (const row of rows) assert.equal(row.user_id, OWNER_A);
});

await check("connections() scopes the query by user_ids on the wire", async () => {
  const { calls, impl } = fakeFetch(() => ({ status: 200, body: { items: [] } }));
  await provider(impl).connections(OWNER_A);
  assert.equal(calls[0]!.path, `/connected_accounts?user_ids=${OWNER_A}`);
});

await check("a blank, missing or name-shaped owner throws and never reaches the wire", async () => {
  const bad = ["", "   ", "omar", "jose@anticipy.ai", "SXKOTD1H02QB6GW", "sxkotd1h02qb6g", null, undefined, 12345];
  for (const value of bad) {
    const { calls, impl } = fakeFetch(() => ({ status: 200, body: { items: [] } }));
    const p = provider(impl);
    for (const call of [
      () => p.session(value as unknown as OwnerId),
      () => p.connections(value as unknown as OwnerId),
      () => p.authorize(value as unknown as OwnerId, "gmail", { callbackUrl: CALLBACK }),
      () => p.disconnect(value as unknown as OwnerId, "ca_1"),
    ]) {
      const err = await refusalOf(call);
      assert.equal(err.name, "ConnectionsOwnerRequired", `${String(value)} was accepted as an owner`);
    }
    assert.equal(calls.length, 0, `${String(value)} reached the network`);
  }
});

await check("requireOwner reports the SHAPE of a bad id and never echoes the value", () => {
  const err = refusalShape(() => requireOwner("session", "jose@anticipy.ai"));
  assert.equal(err.name, "ConnectionsOwnerRequired");
  assert.ok(!err.message.includes("jose"), "the value must not reach a log line");
  assert.ok(!err.message.includes("anticipy.ai"));
  assert.match(err.message, /16 characters/);
  assert.match(refusalShape(() => requireOwner("session", "  ")).message, /blank/);
  assert.equal(requireOwner("session", ` ${OWNER_A} `), OWNER_A, "a trimmed id is still an id");
});

await check("a caller holding a plain string crosses the seam through requireOwner, not a cast", async () => {
  // The route that resolves the signed-in owner out of D1 has a `string`. This
  // is the crossing that is checked; `as OwnerId` is the crossing that is not,
  // and it is how "omar" got onto a Composio session the first time.
  const { calls, impl } = fakeFetch(() => ({ status: 200, body: { items: [] } }));
  const p = provider(impl);
  const fromDb: string = "sxkotd1h02qb6gw";
  assert.deepEqual(await p.connections(requireOwner("connect page", fromDb)), []);
  assert.equal(calls.length, 1);
  const displayName: string = "Omar";
  const err = refusalShape(() => requireOwner("connect page", displayName));
  assert.equal(err.name, "ConnectionsOwnerRequired");
  assert.equal(calls.length, 1, "the refusal happened before a request was issued");
});

function refusalShape(fn: () => unknown): Error {
  try {
    fn();
  } catch (err) {
    return err as Error;
  }
  throw new Error("expected a throw");
}

// ===========================================================================
// 2. THE SESSION, AND THE TOOL THAT MUST NOT BE IN IT.
// ===========================================================================

await check("session posts exactly {user_id, manage_connections:{enable:false}}", async () => {
  const { calls, impl } = fakeFetch(() => ({ status: 201, body: sessionBody("sess-1") }));
  await provider(impl).session(OWNER_A);
  assert.equal(calls[0]!.method, "POST");
  assert.equal(calls[0]!.path, "/tool_router/session");
  assert.deepEqual(calls[0]!.body, { user_id: OWNER_A, manage_connections: { enable: false } });
  // Measured 2026-09-05: `enabled` on the way IN is a 400, and a bare boolean
  // is a 400. The echo spells it `enabled`, which is how the first version of
  // this shipped with the tool still switched on.
  assert.ok(!("enabled" in calls[0]!.body.manage_connections), "the input key is `enable`");
  assert.equal(typeof calls[0]!.body.manage_connections, "object");
  assert.equal(calls[0]!.headers["x-api-key"], KEY);
});

await check("a session whose config comes back enabled is refused and not cached", async () => {
  const { calls, impl } = fakeFetch(() => ({
    status: 201,
    body: sessionBody("sess-1", { config: { manage_connections: { enabled: true } } }),
  }));
  const p = provider(impl);
  const err = await refusalOf(() => p.session(OWNER_A));
  assert.equal(err.name, "ConnectionsManageConnectionsOn");
  await refusalOf(() => p.session(OWNER_A));
  assert.equal(calls.length, 2, "a refused session is never cached and reused");
});

await check("the manage tool still in the tool list is refused, even when the config says off", async () => {
  const { impl } = fakeFetch(() => ({
    status: 201,
    body: sessionBody("sess-1", { tool_router_tools: [...TOOLS_WITHOUT_MANAGE, MANAGE_CONNECTIONS_TOOL] }),
  }));
  const err = await refusalOf(() => provider(impl).session(OWNER_A));
  assert.equal(err.name, "ConnectionsManageConnectionsOn");
  assert.match(err.message, /still in the session's tool list/);
});

await check("the tool list is read in every spelling the vendor uses", async () => {
  const spellings = [
    { name: MANAGE_CONNECTIONS_TOOL },
    { slug: MANAGE_CONNECTIONS_TOOL },
    { tool_slug: MANAGE_CONNECTIONS_TOOL },
    { tool_name: MANAGE_CONNECTIONS_TOOL },
    { function: { name: MANAGE_CONNECTIONS_TOOL } },
    { name: "composio_manage_connections" },
  ];
  for (const entry of spellings) {
    const { impl } = fakeFetch(() => ({
      status: 201,
      body: sessionBody("sess-1", { config: null, tool_router_tools: [entry] }),
    }));
    const err = await refusalOf(() => provider(impl).session(OWNER_A));
    assert.equal(err.name, "ConnectionsManageConnectionsOn", `${JSON.stringify(entry)} slipped past`);
  }
});

await check("a session that confirms nothing is refused — the floor does not lift itself", async () => {
  const { impl } = fakeFetch(() => ({
    status: 201,
    body: { session_id: "sess-1" },
  }));
  const err = await refusalOf(() => provider(impl).session(OWNER_A));
  assert.equal(err.name, "ConnectionsResponseShape");
  assert.match(err.message, /nothing confirms the connection tool is off/);
});

await check("a tool list whose entries hide their identifier confirms NOTHING", async () => {
  const { impl } = fakeFetch(() => ({
    status: 201,
    body: { session_id: "sess-1", tool_router_tools: [{ id: "0f1e-uuid" }, { id: "9a8b-uuid" }] },
  }));
  const err = await refusalOf(() => provider(impl).session(OWNER_A));
  assert.equal(err.name, "ConnectionsResponseShape", "an unparseable list read as 'confirmed absent'");
});

await check("ONE unreadable entry among readable ones voids the verdict", async () => {
  const { impl } = fakeFetch(() => ({
    status: 201,
    body: { session_id: "sess-1", tool_router_tools: [...TOOLS_WITHOUT_MANAGE, { id: "uuid-only" }] },
  }));
  const err = await refusalOf(() => provider(impl).session(OWNER_A));
  assert.equal(err.name, "ConnectionsResponseShape");
});

await check("CONTROL: an unreadable tool list is still fine when the CONFIG says off", async () => {
  const { impl } = fakeFetch(() => ({
    status: 201,
    body: sessionBody("sess-1", { tool_router_tools: [{ id: "uuid-only" }] }),
  }));
  const out = await provider(impl).session(OWNER_A);
  assert.equal(out.sessionId, "sess-1");
});

await check("CONTROL: readable tool lists still confirm, in every spelling", async () => {
  const lists: unknown[] = [
    TOOLS_WITHOUT_MANAGE,
    TOOLS_WITHOUT_MANAGE.map((name) => ({ name })),
    TOOLS_WITHOUT_MANAGE.map((slug) => ({ slug })),
    TOOLS_WITHOUT_MANAGE.map((name) => ({ function: { name } })),
    [],
  ];
  for (const tool_router_tools of lists) {
    const { impl } = fakeFetch(() => ({
      status: 201,
      body: { session_id: "sess-1", config: null, tool_router_tools },
    }));
    const out = await provider(impl).session(OWNER_A);
    assert.equal(out.sessionId, "sess-1", `${JSON.stringify(tool_router_tools)} was refused`);
  }
});

await check("the config's own `enable` spelling is read as well as `enabled`", async () => {
  const { impl } = fakeFetch(() => ({
    status: 201,
    body: { session_id: "sess-1", config: { manage_connections: { enable: true } } },
  }));
  const err = await refusalOf(() => provider(impl).session(OWNER_A));
  assert.equal(err.name, "ConnectionsManageConnectionsOn");
});

await check("a session response with no session_id is a shape refusal, not a blank id", async () => {
  const { impl } = fakeFetch(() => ({ status: 201, body: { config: { manage_connections: { enabled: false } } } }));
  const err = await refusalOf(() => provider(impl).session(OWNER_A));
  assert.equal(err.name, "ConnectionsResponseShape");
  assert.match(err.message, /no session_id/);
});

await check("a failing session is a named request failure carrying the status", async () => {
  const { impl } = fakeFetch(() => ({ status: 503, body: { error: { code: "upstream_down" } } }));
  const err = await refusalOf(() => provider(impl).session(OWNER_A)) as Error & { status: number; retryable: boolean };
  assert.equal(err.name, "ConnectionsRequestFailed");
  assert.equal(err.status, 503);
  assert.equal(err.retryable, true);
  assert.match(err.message, /upstream_down/);
});

// ===========================================================================
// 3. AUTHORIZE — minted at REDEEM time, never at send time.
// ===========================================================================

await check("authorize posts toolkit, callback and alias to the owner's own session", async () => {
  const { calls, impl } = fakeFetch((call) =>
    call.path === "/tool_router/session"
      ? { status: 201, body: sessionBody("sess-A") }
      : { status: 200, body: { redirect_url: "https://vendor.example/link/xyz" } });
  const out = await provider(impl).authorize(OWNER_A, "GMAIL", { callbackUrl: CALLBACK, alias: "work" });
  assert.equal(out.redirectUrl, "https://vendor.example/link/xyz");
  assert.equal(calls[1]!.path, "/tool_router/session/sess-A/link");
  assert.deepEqual(calls[1]!.body, { toolkit: "gmail", callback_url: CALLBACK, alias: "work" });
});

await check("authorize omits alias when there is none, and case-folds the one there is", async () => {
  for (const [given, expected] of [[undefined, undefined], [null, undefined], ["Work", "work"], ["PERSONAL", "personal"]] as const) {
    const { calls, impl } = fakeFetch((call) =>
      call.path === "/tool_router/session"
        ? { status: 201, body: sessionBody("sess-A") }
        : { status: 200, body: { redirect_url: "https://vendor.example/x" } });
    await provider(impl).authorize(OWNER_A, "gmail", { callbackUrl: CALLBACK, alias: given as never });
    assert.equal(calls[1]!.body.alias, expected, `alias ${String(given)}`);
  }
});

await check("an alias outside the contract's two values is refused before any request", async () => {
  const { calls, impl } = fakeFetch(() => ({ status: 201, body: sessionBody("sess-A") }));
  const err = await refusalOf(() =>
    provider(impl).authorize(OWNER_A, "gmail", { callbackUrl: CALLBACK, alias: "school" as never }));
  assert.equal(err.name, "ConnectionsBadArgument");
  assert.equal(calls.length, 0);
});

await check("a blank or relative callback is refused before any session is minted", async () => {
  for (const callbackUrl of ["", "   ", "/c/abc/done", "ftp://x.example/done"]) {
    const { calls, impl } = fakeFetch(() => ({ status: 201, body: sessionBody("sess-A") }));
    const err = await refusalOf(() => provider(impl).authorize(OWNER_A, "gmail", { callbackUrl }));
    assert.equal(err.name, "ConnectionsBadArgument", `${callbackUrl} was accepted`);
    assert.equal(calls.length, 0);
  }
});

await check("a toolkit slug is required, by authorize and by toolkit()", async () => {
  const { calls, impl } = fakeFetch(() => ({ status: 200, body: {} }));
  const p = provider(impl);
  assert.equal((await refusalOf(() => p.authorize(OWNER_A, "  ", { callbackUrl: CALLBACK }))).name, "ConnectionsBadArgument");
  assert.equal((await refusalOf(() => p.toolkit(""))).name, "ConnectionsBadArgument");
  assert.equal(calls.length, 0);
});

await check("a dead session is re-minted once, because minting a link changes nothing", async () => {
  let sessions = 0;
  const { calls, impl } = fakeFetch((call) => {
    if (call.path === "/tool_router/session") {
      sessions++;
      return { status: 201, body: sessionBody(`sess-${sessions}`) };
    }
    return call.path === "/tool_router/session/sess-1/link"
      ? { status: 404, body: { error: { code: "session_not_found" } } }
      : { status: 200, body: { redirect_url: "https://vendor.example/link/xyz" } };
  });
  const out = await provider(impl).authorize(OWNER_A, "gmail", { callbackUrl: CALLBACK });
  assert.equal(out.redirectUrl, "https://vendor.example/link/xyz");
  assert.deepEqual(calls.map((c) => c.path), [
    "/tool_router/session",
    "/tool_router/session/sess-1/link",
    "/tool_router/session",
    "/tool_router/session/sess-2/link",
  ]);
});

await check("a second dead session is a failure, not an endless remint", async () => {
  let sessions = 0;
  const { calls, impl } = fakeFetch((call) => {
    if (call.path === "/tool_router/session") {
      sessions++;
      return { status: 201, body: sessionBody(`sess-${sessions}`) };
    }
    return { status: 404, body: { error: { code: "session_not_found" } } };
  });
  const err = await refusalOf(() => provider(impl).authorize(OWNER_A, "gmail", { callbackUrl: CALLBACK })) as Error & { status: number };
  assert.equal(err.name, "ConnectionsRequestFailed");
  assert.equal(err.status, 404);
  assert.equal(calls.length, 4, "exactly one retry");
});

await check("a link response with no redirect_url refuses rather than returning a dead button", async () => {
  const { impl } = fakeFetch((call) =>
    call.path === "/tool_router/session"
      ? { status: 201, body: sessionBody("sess-A") }
      : { status: 200, body: { url: "https://vendor.example/link/xyz" } });
  const err = await refusalOf(() => provider(impl).authorize(OWNER_A, "gmail", { callbackUrl: CALLBACK }));
  assert.equal(err.name, "ConnectionsResponseShape");
  assert.match(err.message, /no redirect_url/);
  assert.ok(!err.message.includes("vendor.example"), "the body is never quoted back");
});

// ===========================================================================
// 4. CONNECTIONS — what the Settings screen and the nudge engine read.
// ===========================================================================

await check("connections maps the vendor's statuses fail-closed and never invents a write opt-in", async () => {
  const rows = [
    { status: "ACTIVE", expect: "connected" },
    { status: "active", expect: "connected" },
    { status: "EXPIRED", expect: "needs_reconnect" },
    { status: "INITIATED", expect: "disconnected" },
    { status: "INITIALIZING", expect: "disconnected" },
    { status: "FAILED", expect: "disconnected" },
    { status: "SOMETHING_NEW_NEXT_QUARTER", expect: "disconnected" },
    { status: undefined, expect: "disconnected" },
  ];
  for (const { status, expect } of rows) {
    const { impl } = fakeFetch(() => ({ status: 200, body: { items: [accountRow(OWNER_A, { status })] } }));
    const out = await provider(impl).connections(OWNER_A);
    assert.equal(out[0]!.status, expect, `status ${String(status)}`);
    assert.equal(out[0]!.writes_enabled, false, "writes_enabled lives in D1, never at the vendor");
  }
});

await check("connections reads the toolkit slug from every shape, and the alias from either key", async () => {
  const cases: Array<[Record<string, unknown>, string, string | null]> = [
    [{ toolkit: { slug: "GoogleCalendar" } }, "googlecalendar", null],
    [{ toolkit: undefined, toolkit_slug: "Notion" }, "notion", null],
    [{ toolkit: "Slack" }, "slack", null],
    [{ alias: "Work" }, "gmail", "work"],
    [{ alias: undefined, label: "personal" }, "gmail", "personal"],
    [{ alias: "school" }, "gmail", null],
  ];
  for (const [over, slug, alias] of cases) {
    const { impl } = fakeFetch(() => ({ status: 200, body: { items: [accountRow(OWNER_A, over)] } }));
    const out = await provider(impl).connections(OWNER_A);
    assert.equal(out[0]!.toolkit, slug, JSON.stringify(over));
    assert.equal(out[0]!.alias, alias, JSON.stringify(over));
  }
});

await check("last_used_at is a timestamp or null — never a guess from updated_at", async () => {
  const { impl } = fakeFetch(() => ({
    status: 200,
    body: {
      items: [
        accountRow(OWNER_A, { id: "ca_1", last_used_at: "2026-09-05T10:00:00Z" }),
        accountRow(OWNER_A, { id: "ca_2", last_used_at: 1757066400000 }),
        accountRow(OWNER_A, { id: "ca_3", updated_at: "2026-09-05T10:00:00Z" }),
        accountRow(OWNER_A, { id: "ca_4", last_used_at: "not a date" }),
      ],
    },
  }));
  const out = await provider(impl).connections(OWNER_A);
  assert.equal(out[0]!.last_used_at, Date.parse("2026-09-05T10:00:00Z"));
  assert.equal(out[1]!.last_used_at, 1757066400000);
  assert.equal(out[2]!.last_used_at, null, "updated_at is not last use");
  assert.equal(out[3]!.last_used_at, null);
});

await check("connections refuses an unreadable item instead of reporting an app as unconnected", async () => {
  const { impl } = fakeFetch(() => ({
    status: 200,
    body: { items: [accountRow(OWNER_A), accountRow(OWNER_A, { id: undefined, connected_account_id: undefined })] },
  }));
  const err = await refusalOf(() => provider(impl).connections(OWNER_A));
  assert.equal(err.name, "ConnectionsResponseShape");
  assert.match(err.message, /1 of 2/);
});

await check("connections refuses a response with no items array", async () => {
  const { impl } = fakeFetch(() => ({ status: 200, body: { data: [] } }));
  const err = await refusalOf(() => provider(impl).connections(OWNER_A));
  assert.equal(err.name, "ConnectionsResponseShape");
  assert.match(err.message, /no items array/);
});

await check("connections reads a bare array too, and an empty list is an honest empty list", async () => {
  const bare = fakeFetch(() => ({ status: 200, body: [accountRow(OWNER_A)] }));
  assert.equal((await provider(bare.impl).connections(OWNER_A)).length, 1);
  const empty = fakeFetch(() => ({ status: 200, body: { items: [] } }));
  assert.deepEqual(await provider(empty.impl).connections(OWNER_A), []);
});

// ===========================================================================
// 5. DISCONNECT — revoke, THEN delete, and say which one happened.
// ===========================================================================

await check("disconnect revokes BEFORE it deletes", async () => {
  const seen: string[] = [];
  const { impl } = fakeFetch((call) => {
    if (call.method === "GET") return { status: 200, body: { items: [accountRow(OWNER_A)] } };
    seen.push(`${call.method} ${call.path}`);
    return { status: 200, body: {} };
  });
  await provider(impl).disconnect(OWNER_A, "ca_BNgvxQtJ703C");
  assert.deepEqual(seen, [
    "POST /connected_accounts/ca_BNgvxQtJ703C/revoke",
    "DELETE /connected_accounts/ca_BNgvxQtJ703C",
  ]);
});

await check("a 409 revoke sets revokeUnavailable and still deletes", async () => {
  const { calls, impl } = fakeFetch((call) => {
    if (call.method === "GET") return { status: 200, body: { items: [accountRow(OWNER_A)] } };
    if (call.path.endsWith("/revoke")) return { status: 409, body: { error: { code: "not_revocable" } } };
    return { status: 200, body: {} };
  });
  const out = await provider(impl).disconnect(OWNER_A, "ca_BNgvxQtJ703C");
  assert.deepEqual(out, { revoked: false, deleted: true, revokeUnavailable: true });
  assert.equal(calls.length, 3);
});

const NO_DELETE_STATUSES = [400, 401, 403, 404, 405, 410, 418, 422, 429, 500, 503];
for (const status of NO_DELETE_STATUSES) {
  await check(`a ${status} on revoke aborts — the delete would strand a live token`, async () => {
    const { calls, impl } = fakeFetch((call) => {
      if (call.method === "GET") return { status: 200, body: { items: [accountRow(OWNER_A)] } };
      if (call.path.endsWith("/revoke")) return { status, body: { error: { code: "nope" } } };
      return { status: 200, body: {} };
    });
    const err = await refusalOf(() => provider(impl).disconnect(OWNER_A, "ca_BNgvxQtJ703C")) as Error & { status: number };
    assert.equal(err.name, "ConnectionsRequestFailed");
    assert.equal(err.status, status);
    assert.ok(!calls.some((c) => c.method === "DELETE"), `a ${status} deleted the only revoke handle`);
  });
}

await check("a transport failure during revoke aborts before the delete", async () => {
  const { calls, impl } = fakeFetch((call) => {
    if (call.method === "GET") return { status: 200, body: { items: [accountRow(OWNER_A)] } };
    return { throws: new TypeError("network down") };
  });
  const err = await refusalOf(() => provider(impl).disconnect(OWNER_A, "ca_BNgvxQtJ703C")) as Error & { status: number };
  assert.equal(err.status, 0);
  assert.ok(!calls.some((c) => c.method === "DELETE"));
});

await check("a revoke that worked and a delete that did not is reported, not thrown", async () => {
  const { impl } = fakeFetch((call) => {
    if (call.method === "GET") return { status: 200, body: { items: [accountRow(OWNER_A)] } };
    if (call.path.endsWith("/revoke")) return { status: 200, body: {} };
    return { status: 500, body: {} };
  });
  const out = await provider(impl).disconnect(OWNER_A, "ca_BNgvxQtJ703C");
  assert.deepEqual(out, { revoked: true, deleted: false, revokeUnavailable: false });
});

await check("a delete that failed after a revoke that also failed is a hard failure", async () => {
  const { impl } = fakeFetch((call) => {
    if (call.method === "GET") return { status: 200, body: { items: [accountRow(OWNER_A)] } };
    if (call.path.endsWith("/revoke")) return { status: 409, body: {} };
    return { status: 500, body: {} };
  });
  const err = await refusalOf(() => provider(impl).disconnect(OWNER_A, "ca_BNgvxQtJ703C"));
  assert.equal(err.name, "ConnectionsRequestFailed");
  assert.match(err.message, /disconnect delete/);
});

await check("a 404 on delete means the row is already gone, which is what delete was for", async () => {
  const { impl } = fakeFetch((call) => {
    if (call.method === "GET") return { status: 200, body: { items: [accountRow(OWNER_A)] } };
    if (call.path.endsWith("/revoke")) return { status: 200, body: {} };
    return { status: 404, body: {} };
  });
  assert.deepEqual(await provider(impl).disconnect(OWNER_A, "ca_BNgvxQtJ703C"), {
    revoked: true, deleted: true, revokeUnavailable: false,
  });
});

await check("disconnect requires an account id, and asks for nothing without one", async () => {
  const { calls, impl } = fakeFetch(() => ({ status: 200, body: { items: [] } }));
  for (const id of ["", "   ", null, undefined]) {
    const err = await refusalOf(() => provider(impl).disconnect(OWNER_A, id as unknown as string));
    assert.equal(err.name, "ConnectionsBadArgument");
  }
  assert.equal(calls.length, 0);
});

await check("the status readers are allow-lists, not inverses", () => {
  assert.equal(revokeIsDefinitivelyUnavailable(409), true);
  for (const s of [400, 401, 403, 404, 405, 410, 418, 422, 429, 500, 0]) {
    assert.equal(revokeIsDefinitivelyUnavailable(s), false, `${s} claimed to be unrevocable`);
  }
  for (const s of [0, 408, 425, 429, 500, 502, 503]) assert.equal(isRetryableStatus(s), true, `${s}`);
  for (const s of [400, 401, 403, 404, 409, 422]) assert.equal(isRetryableStatus(s), false, `${s}`);
});

// ===========================================================================
// 6. TOOLKIT — the catalog the connect page is generated from.
// ===========================================================================

await check("toolkit returns name, logo, description, appUrl and scopes from the vendor", async () => {
  const { calls, impl } = fakeFetch(() => ({
    status: 200,
    body: {
      slug: "GoogleCalendar",
      name: "Google Calendar",
      logo: "https://cdn.example/gcal.png",
      description: "Calendars and events",
      app_url: "https://calendar.google.com",
      scopes: ["https://www.googleapis.com/auth/calendar"],
      meta: { scopes: ["https://www.googleapis.com/auth/calendar.events"] },
      auth_config_details: [{ scopes: ["https://www.googleapis.com/auth/calendar", "openid"] }],
    },
  }));
  const meta = await provider(impl).toolkit("googlecalendar");
  assert.equal(calls[0]!.path, "/toolkits/googlecalendar");
  assert.equal(meta.slug, "googlecalendar", "the canonical slug, case folded");
  assert.equal(meta.name, "Google Calendar");
  assert.equal(meta.logo, "https://cdn.example/gcal.png");
  assert.equal(meta.description, "Calendars and events");
  assert.equal(meta.appUrl, "https://calendar.google.com");
  assert.deepEqual(meta.scopes, [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
    "openid",
  ], "gathered from every place, in order, deduped");
});

await check("a toolkit with no name refuses instead of shipping the slug as a name", async () => {
  const { impl } = fakeFetch(() => ({ status: 200, body: { slug: "googlecalendar", scopes: [] } }));
  const err = await refusalOf(() => provider(impl).toolkit("googlecalendar"));
  assert.equal(err.name, "ConnectionsResponseShape");
  assert.match(err.message, /nothing to call this app/);
});

await check("an absent scopes list comes back empty, and that means UNKNOWN", async () => {
  const { impl } = fakeFetch(() => ({ status: 200, body: { name: "Notion" } }));
  const meta = await provider(impl).toolkit("notion");
  assert.deepEqual(meta.scopes, []);
  // words.ts is the half that refuses to generate from nothing; proved below.
});

await check("a toolkit fetch that fails is a named failure, not an empty catalog entry", async () => {
  const { impl } = fakeFetch(() => ({ status: 500, body: {} }));
  const err = await refusalOf(() => provider(impl).toolkit("notion")) as Error & { status: number };
  assert.equal(err.name, "ConnectionsRequestFailed");
  assert.equal(err.status, 500);
});

await check("a toolkit response that is not an object refuses", async () => {
  const { impl } = fakeFetch(() => ({ status: 200, body: ["not", "an", "object"] }));
  assert.equal((await refusalOf(() => provider(impl).toolkit("notion"))).name, "ConnectionsResponseShape");
});


// ===========================================================================
// 6b. SEARCH — the only way to add an app the system never asked about.
//
// The finding this block closes: `GET /me/connections/catalog?q=` answered 503
// unconditionally, because the adapter offered `toolkit(slug)` — a point lookup
// on a vendor primary key — and nothing else. The agent that found it was right
// not to fake it: treating a typed phrase as a primary key is the Worker
// deciding what somebody's words MEANT.
//
// So every check here is about one of two things: the letters reaching the
// VENDOR unchanged, and a failure never coming back as an empty list.
// ===========================================================================

/** A catalog row in the listing shape the vendor's own v3.1 reference gives:
 *  `slug` and `name` at the root, everything else under `meta`. */
function catalogListRow(slug: string, name: string, over: Record<string, unknown> = {}) {
  return {
    slug,
    name,
    meta: {
      description: `Everything about ${name}.`,
      logo: `https://cdn.example.invalid/${slug}.png`,
      app_url: `https://${slug}.example.invalid`,
    },
    ...over,
  };
}

await check("search puts the typed letters on the wire and nothing else", async () => {
  // LAW 1. Spaces, capitals, punctuation and a non-ASCII character all survive
  // the trip: the vendor is the thing entitled to interpret them, and every
  // transform applied here would be a small decision about meaning taken by the
  // wrong layer.
  const typed = "  My Work Mail (2nd) — café ";
  const { calls, impl } = fakeFetch(() => ({ status: 200, body: { items: [] } }));
  await provider(impl).search(typed);
  assert.equal(calls.length, 1);
  assert.equal(calls[0]!.method, "GET");
  const url = new URL("https://vendor.invalid" + calls[0]!.path);
  assert.equal(url.pathname, "/toolkits");
  assert.equal(url.searchParams.get("search"), typed,
    "the letters reached the vendor altered; the rule is 'as typed'");
  assert.equal(url.searchParams.get("limit"), String(MAX_SEARCH_RESULTS));
  // CONTROL: the assertion above is only worth anything if a changed query
  // would actually fail it.
  assert.notEqual(url.searchParams.get("search"), typed.trim());
});

await check("search reads the listing row shape: slug, name, and meta for the rest", async () => {
  const { impl } = fakeFetch(() => ({
    status: 200,
    body: { items: [catalogListRow("zellibrix", "Zellibrix")], next_cursor: "cursor-2", total_items: 1400 },
  }));
  const hits = await provider(impl).search("notes");
  assert.equal(hits.length, 1);
  assert.equal(hits[0]!.slug, "zellibrix");
  assert.equal(hits[0]!.name, "Zellibrix");
  assert.equal(hits[0]!.description, "Everything about Zellibrix.");
  assert.equal(hits[0]!.logo, "https://cdn.example.invalid/zellibrix.png");
  assert.equal(hits[0]!.appUrl, "https://zellibrix.example.invalid");
  // The listing carries no auth_config_details, so scopes are UNKNOWN — and
  // empty is how this file spells unknown. words.ts refuses to write permission
  // sentences from nothing, so a search row can never produce consent copy.
  assert.deepEqual(hits[0]!.scopes, []);
});

await check("search keeps the vendor's order and never re-sorts it", async () => {
  // Re-ranking would be a local opinion about which app somebody meant, formed
  // with no context at all. Reversed alphabetical on purpose: any local sort
  // would move these.
  const order = ["zellibrix", "quandle_mail", "aardvark_notes"];
  const { impl } = fakeFetch(() => ({
    status: 200,
    body: { items: order.map((s) => catalogListRow(s, s.toUpperCase())) },
  }));
  const hits = await provider(impl).search("anything");
  assert.deepEqual(hits.map((h) => h.slug), order);
});

await check("search caps the answer at MAX_SEARCH_RESULTS, asked for AND cut", async () => {
  const many = Array.from({ length: MAX_SEARCH_RESULTS + 17 },
    (_, i) => catalogListRow(`app${i}`, `App ${i}`));
  const { calls, impl } = fakeFetch(() => ({ status: 200, body: { items: many } }));
  const hits = await provider(impl).search("x");
  assert.ok(calls[0]!.path.includes(`limit=${MAX_SEARCH_RESULTS}`), "the vendor was not asked for a limit");
  assert.equal(hits.length, MAX_SEARCH_RESULTS,
    "a vendor that ignores `limit` put the whole catalog on a phone");
  assert.equal(hits[0]!.slug, "app0", "the cut took from the wrong end");
});

await check("a caller cannot raise the cap, and an unusable one falls back to it", async () => {
  for (const [limit, wire] of [
    [5, "5"], [1, "1"],
    [MAX_SEARCH_RESULTS + 500, String(MAX_SEARCH_RESULTS)],
    [0, String(MAX_SEARCH_RESULTS)],
    [-3, String(MAX_SEARCH_RESULTS)],
    [Number.NaN, String(MAX_SEARCH_RESULTS)],
    [Number.POSITIVE_INFINITY, String(MAX_SEARCH_RESULTS)],
  ] as [number, string][]) {
    const { calls, impl } = fakeFetch(() => ({ status: 200, body: { items: [] } }));
    await provider(impl).search("x", { limit });
    assert.ok(calls[0]!.path.includes(`limit=${wire}`),
      `limit ${String(limit)} reached the vendor as something other than ${wire}: ${calls[0]!.path}`);
  }
});

await check("a caller asking for fewer than the cap gets fewer, not more", async () => {
  const many = Array.from({ length: 30 }, (_, i) => catalogListRow(`app${i}`, `App ${i}`));
  const { impl } = fakeFetch(() => ({ status: 200, body: { items: many } }));
  assert.equal((await provider(impl).search("x", { limit: 4 })).length, 4,
    "a vendor that ignored a small limit was not cut to it");
});

await check("the vendor's OWN empty list is an answer: nothing matched", async () => {
  const { impl } = fakeFetch(() => ({ status: 200, body: { items: [], total_items: 0 } }));
  assert.deepEqual(await provider(impl).search("qqqzzz"), []);
});

await check("a dead catalog is a named failure and NEVER an empty list", async () => {
  // The whole reason this method throws rather than returning []: an empty
  // search result tells a person the catalog holds nothing, and the catalog
  // holds 1,400 apps.
  for (const status of [400, 401, 403, 404, 429, 500, 502, 503]) {
    const { impl } = fakeFetch(() => ({ status, body: { error: { code: "nope" } } }));
    const err = await refusalOf(() => provider(impl).search("mail")) as Error & { status: number };
    assert.equal(err.name, "ConnectionsRequestFailed", String(status));
    assert.equal(err.status, status);
  }
  const dead = fakeFetch(() => ({ throws: new TypeError("network down") }));
  const err = await refusalOf(() => provider(dead.impl).search("mail")) as Error & { status: number };
  assert.equal(err.name, "ConnectionsRequestFailed");
  assert.equal(err.status, 0);
});

await check("search with no API key refuses before a request is issued", async () => {
  const { calls, impl } = fakeFetch(() => ({ status: 200, body: { items: [] } }));
  const err = await refusalOf(() => provider(impl, "").search("mail"));
  assert.equal(err.name, "ConnectionsUnconfigured");
  assert.equal(calls.length, 0, "an unconfigured Worker still called the vendor");
});

await check("a body with no items array refuses instead of reading as nothing matched", async () => {
  for (const body of [{}, { items: null }, { items: "gmail" }, { results: [] }, null, 7]) {
    const { impl } = fakeFetch(() => ({ status: 200, body }));
    const err = await refusalOf(() => provider(impl).search("mail"));
    assert.equal(err.name, "ConnectionsResponseShape", inspect(body));
    assert.match(err.message, /no items array/);
  }
});

await check("a bare array of rows is read too", async () => {
  const { impl } = fakeFetch(() => ({ status: 200, body: [catalogListRow("zellibrix", "Zellibrix")] }));
  assert.deepEqual((await provider(impl).search("notes")).map((h) => h.slug), ["zellibrix"]);
});

await check("one unreadable row is dropped; the readable ones survive it", async () => {
  // The opposite of what connections() does with an unreadable row, and on
  // purpose: there a dropped row becomes "you have not connected Notion" and
  // texts somebody about the app they connected last week. Here it is one line
  // missing from a list of forty.
  const { impl } = fakeFetch(() => ({
    status: 200,
    body: {
      items: [
        catalogListRow("zellibrix", "Zellibrix"),
        { slug: "nameless" },                                  // no name
        { name: "Slugless" },                                  // no slug
        { slug: "  ", name: "Blank slug" },                    // slug is spaces
        "not even an object",
        null,
        catalogListRow("quandle_mail", "Quandle Mail"),
      ],
    },
  }));
  assert.deepEqual((await provider(impl).search("x")).map((h) => h.slug),
    ["zellibrix", "quandle_mail"]);
});

await check("a page where NOTHING is readable refuses; it is not an empty catalog", async () => {
  const { impl } = fakeFetch(() => ({
    status: 200,
    body: { items: [{ slug: "nameless" }, { name: "Slugless" }, 42] },
  }));
  const err = await refusalOf(() => provider(impl).search("x"));
  assert.equal(err.name, "ConnectionsResponseShape");
  assert.match(err.message, /nothing here is an answer about what the catalog holds/);
});

await check("a search row's slug is case folded, like every other slug here", async () => {
  const { impl } = fakeFetch(() => ({
    status: 200,
    body: { items: [catalogListRow("GoogleCalendar", "Google Calendar")] },
  }));
  const hits = await provider(impl).search("calendar");
  assert.equal(hits[0]!.slug, "googlecalendar",
    "two spellings of one toolkit is one app with two nudge rows");
  assert.equal(hits[0]!.name, "Google Calendar", "the NAME is the vendor's, untouched");
});

await check("search reads a root-level logo/description/app_url too, not only meta", async () => {
  const { impl } = fakeFetch(() => ({
    status: 200,
    body: { items: [{
      slug: "zellibrix", name: "Zellibrix",
      logo: "https://cdn.example.invalid/root.png",
      description: "At the root.",
      app_url: "https://root.example.invalid",
    }] },
  }));
  const hit = (await provider(impl).search("x"))[0]!;
  assert.equal(hit.logo, "https://cdn.example.invalid/root.png");
  assert.equal(hit.description, "At the root.");
  assert.equal(hit.appUrl, "https://root.example.invalid");
});

await check("the search and the detail endpoint read one row the same way", async () => {
  // Two readers would be two answers to what an app is called, and the search
  // list and the connect page would disagree about the same toolkit.
  const row = catalogListRow("zellibrix", "Zellibrix");
  const listed = await provider(fakeFetch(() => ({ status: 200, body: { items: [row] } })).impl)
    .search("notes");
  const fetched = await provider(fakeFetch(() => ({ status: 200, body: row })).impl)
    .toolkit("zellibrix");
  assert.deepEqual(listed[0], fetched);
});

await check("search carries the key in the header and never in the query", async () => {
  const { calls, impl } = fakeFetch(() => ({ status: 200, body: { items: [] } }));
  await provider(impl).search(KEY);
  assert.equal(calls[0]!.headers["x-api-key"], KEY);
  // The one place a query is echoed is the query string, so searching FOR the
  // key is the sharpest version of this: it must appear because it was typed,
  // and the header is where the credential lives.
  assert.ok(!calls[0]!.path.includes("x-api-key"), "the key was put in the URL");
});

// ===========================================================================
// 7. NOTHING LEAKS: no key, no token, no redirect_url, no log line.
// ===========================================================================

await check("this adapter writes nothing to a log, on the happy path or any failure path", async () => {
  const original = { log: console.log, warn: console.warn, error: console.error, info: console.info, debug: console.debug };
  const said: string[] = [];
  for (const name of Object.keys(original) as Array<keyof typeof original>) {
    (console as any)[name] = (...args: unknown[]) => said.push(`${name}: ${args.join(" ")}`);
  }
  try {
    const ok = fakeFetch((call) =>
      call.path === "/tool_router/session"
        ? { status: 201, body: sessionBody("sess-A") }
        : { status: 200, body: { redirect_url: "https://vendor.example/link/secret-token" } });
    await provider(ok.impl).authorize(OWNER_A, "gmail", { callbackUrl: CALLBACK });
    const bad = fakeFetch(() => ({ throws: new Error(`boom ${KEY}`) }));
    await refusalOf(() => provider(bad.impl).connections(OWNER_A));
    const shape = fakeFetch(() => ({ status: 200, body: { items: [accountRow(OWNER_B)] } }));
    await refusalOf(() => provider(shape.impl).connections(OWNER_A));
  } finally {
    Object.assign(console, original);
  }
  assert.deepEqual(said, [], "the adapter logged something");
});

await check("a key the vendor echoes back is redacted out of the error it lands in", async () => {
  const { impl } = fakeFetch(() => ({ status: 400, body: { error: { code: `bad_key_${KEY}` } } }));
  const err = await refusalOf(() => provider(impl).connections(OWNER_A));
  assert.ok(!err.message.includes(KEY), "the api key reached an error message");
  assert.match(err.message, /\[redacted\]/);
});

await check("a tokenised URL never survives into an error message", async () => {
  const { impl } = fakeFetch(() => ({ throws: { name: "https://connect.vendor.dev/link/abc123?key=x" } }));
  const err = await refusalOf(() => provider(impl).connections(OWNER_A));
  assert.ok(!err.message.includes("abc123"), "a tokenised link reached an error message");
  assert.match(err.message, /\[redacted-url\]/);
});

await check("PORT FIX: a SCHEMELESS tokenised URL is redacted too", async () => {
  const { impl } = fakeFetch(() => ({ throws: { name: "connect.vendor.dev/link/abc123" } }));
  const err = await refusalOf(() => provider(impl).connections(OWNER_A));
  assert.ok(!err.message.includes("abc123"), "a schemeless link rode into an error intact");
  assert.match(err.message, /\[redacted-url\]/);
});

await check("CONTROL: an ordinary vendor error token still reaches the log intact", async () => {
  const { impl } = fakeFetch(() => ({ status: 422, body: { error: { code: "invalid_toolkit_slug" } } }));
  const err = await refusalOf(() => provider(impl).connections(OWNER_A));
  assert.match(err.message, /invalid_toolkit_slug/, "over-redaction costs the next person their only clue");
  const transport = fakeFetch(() => ({ throws: new TypeError("failed") }));
  const err2 = await refusalOf(() => provider(transport.impl).connections(OWNER_A));
  assert.match(err2.message, /TypeError/);
});

await check("a vendor error's prose message is dropped, not forwarded", async () => {
  const { impl } = fakeFetch(() => ({
    status: 400,
    body: { error: { message: `x-api-key ${KEY} was rejected for user omar` } },
  }));
  const err = await refusalOf(() => provider(impl).connections(OWNER_A));
  assert.ok(!err.message.includes(KEY));
  assert.ok(!err.message.includes("omar"));
});

await check("the key is not reachable through inspection or serialisation of the provider", async () => {
  const { impl } = fakeFetch(() => ({ status: 200, body: { items: [] } }));
  const p = provider(impl);
  await p.connections(OWNER_A);
  assert.ok(!JSON.stringify(p).includes(KEY));
  assert.ok(!inspect(p, { depth: 6 }).includes(KEY));
  assert.ok(!Object.keys(p).join(",").includes("apiKey"));
});

// ===========================================================================
// 8. THE UNBOUND BINDING. `env.COMPOSIO_API_KEY` is a secret and may be absent.
// ===========================================================================

await check("with no api key every method throws ConnectionsUnconfigured and issues no request", async () => {
  const { calls, impl } = fakeFetch(() => ({ status: 200, body: {} }));
  for (const apiKey of ["", "   ", null, undefined]) {
    // Constructed directly: `provider()`'s default argument would turn the
    // `undefined` case — an unbound `env.COMPOSIO_API_KEY`, the whole point of
    // this test — back into a configured provider.
    const p = new ComposioConnections({ apiKey: apiKey as string | null, fetchImpl: impl });
    const attempts: Array<() => Promise<unknown>> = [
      () => p.session(OWNER_A),
      () => p.connections(OWNER_A),
      () => p.authorize(OWNER_A, "gmail", { callbackUrl: CALLBACK }),
      () => p.disconnect(OWNER_A, "ca_1"),
      () => p.toolkit("gmail"),
    ];
    for (const attempt of attempts) {
      const err = await refusalOf(attempt) as Error & { code: string };
      assert.equal(err.name, "ConnectionsUnconfigured", `key ${JSON.stringify(apiKey)}`);
      assert.equal(err.code, "connections_no_api_key");
      assert.ok(!/revoked|deleted/.test(err.message), "an unconfigured disconnect must not read as a result");
    }
  }
  assert.equal(calls.length, 0, "an unbound COMPOSIO_API_KEY still reached the network");
});

await check("a key with no usable transport fails by name rather than reaching the network", async () => {
  const p = new ComposioConnections({ apiKey: KEY, fetchImpl: undefined as never });
  const saved = globalThis.fetch;
  try {
    (globalThis as { fetch?: unknown }).fetch = undefined;
    const q = new ComposioConnections({ apiKey: KEY });
    const err = await refusalOf(() => q.connections(OWNER_A)) as Error & { status: number };
    assert.equal(err.name, "ConnectionsRequestFailed");
    assert.equal(err.status, 0);
  } finally {
    (globalThis as { fetch?: unknown }).fetch = saved;
  }
  assert.ok(p instanceof ComposioConnections);
});

await check("connectionsFromEnv: an unbound secret refuses and never calls fetch", async () => {
  const saved = globalThis.fetch;
  let called = 0;
  try {
    (globalThis as { fetch?: unknown }).fetch = async () => { called++; return new Response("{}"); };
    resetConnectionsProvider();
    const p = connectionsFromEnv({});
    const err = await refusalOf(() => p.connections(OWNER_A));
    assert.equal(err.name, "ConnectionsUnconfigured");
    const p2 = connectionsFromEnv(undefined);
    assert.equal((await refusalOf(() => p2.session(OWNER_A))).name, "ConnectionsUnconfigured");
    assert.equal(called, 0, "an unbound binding issued a request");
  } finally {
    (globalThis as { fetch?: unknown }).fetch = saved;
    resetConnectionsProvider();
  }
});

await check("connectionsFromEnv: one provider per isolate, replaced when the secret rotates", async () => {
  const saved = globalThis.fetch;
  const seen: Array<Record<string, string>> = [];
  try {
    (globalThis as { fetch?: unknown }).fetch = async (_url: unknown, init: any) => {
      seen.push(init.headers);
      return { status: 200, json: async () => ({ items: [] }) } as unknown as Response;
    };
    resetConnectionsProvider();
    const first = connectionsFromEnv({ COMPOSIO_API_KEY: ` ${KEY} ` });
    const second = connectionsFromEnv({ COMPOSIO_API_KEY: KEY });
    assert.equal(first, second, "the session cache is thrown away if the instance is");
    await first.connections(OWNER_A);
    assert.equal(seen[0]!["x-api-key"], KEY, "the key is trimmed of dashboard whitespace");
    const rotated = connectionsFromEnv({ COMPOSIO_API_KEY: "comp_live_rotated_key_0987654321" });
    assert.notEqual(rotated, first, "a rotated secret must not be served by the old instance");
  } finally {
    (globalThis as { fetch?: unknown }).fetch = saved;
    resetConnectionsProvider();
  }
});

await check("the isolate's session cache has a ceiling, and a cleared cache just re-mints", async () => {
  const { calls, impl } = fakeFetch((call) => ({ status: 201, body: sessionBody(`sess-${call.body.user_id}`) }));
  const p = provider(impl);
  const owners: OwnerId[] = [];
  for (let i = 0; i < MAX_CACHED_SESSIONS + 1; i++) {
    owners.push(`o${String(i).padStart(14, "0")}` as OwnerId);
  }
  for (const owner of owners) await p.session(owner);
  assert.equal(calls.length, MAX_CACHED_SESSIONS + 1);
  await p.session(owners[0]!);
  assert.equal(calls.length, MAX_CACHED_SESSIONS + 2, "the ceiling never cleared, so the isolate leaks");
  const alsoForgotten = owners[MAX_CACHED_SESSIONS - 1]!;
  await p.session(alsoForgotten);
  assert.equal(calls.length, MAX_CACHED_SESSIONS + 3, "everything before the ceiling is forgotten together");
  const survivor = owners[owners.length - 1]!;
  await p.session(survivor);
  assert.equal(calls.length, MAX_CACHED_SESSIONS + 3, "CONTROL: the cache still caches");
});

await check("the exported readers map enums and identifiers, and nothing else", () => {
  assert.equal(toolkitSlug(" GMAIL "), "gmail");
  assert.equal(toolkitSlug(undefined), "");
  assert.equal(toolkitSlug({ slug: "gmail" }), "[object object]", "an object is not a slug, and says so");
  assert.equal(mapConnectionStatus("ACTIVE"), "connected");
  assert.equal(mapConnectionStatus(" expired "), "needs_reconnect");
  assert.equal(mapConnectionStatus(null), "disconnected");
  assert.equal(readAlias("WORK"), "work");
  assert.equal(readAlias("personal"), "personal");
  assert.equal(readAlias("school"), null);
  assert.equal(readLastUsedAt(0), 0);
  assert.equal(readLastUsedAt(Number.NaN), null);
  assert.equal(readLastUsedAt(""), null);
});

// ===========================================================================
// 9. THE WORDS — three permission sentences and one text, neither written here.
// ===========================================================================
//
// Every assertion that matters runs TWICE: once against a toolkit that exists
// and once against `zorptastic-9000`, which does not and never will. If anybody
// ever adds a per-app string table, the second run is where it dies.

function realApp(over: Partial<ToolkitMeta> = {}): ToolkitMeta {
  return {
    slug: "gmail",
    name: "Gmail",
    logo: null,
    description: null,
    appUrl: null,
    scopes: ["https://www.googleapis.com/auth/gmail.readonly"],
    ...over,
  };
}

function inventedApp(over: Partial<ToolkitMeta> = {}): ToolkitMeta {
  return {
    slug: "zorptastic-9000",
    name: "Zorptastic 9000",
    logo: null,
    description: null,
    appUrl: null,
    scopes: ["zorp.read", "zorp.write"],
    ...over,
  };
}

const APPS: Array<[string, (over?: Partial<ToolkitMeta>) => ToolkitMeta]> = [
  ["a real app", realApp],
  ["an app nobody has heard of", inventedApp],
];

const LINK = `${CONNECT_LINK_PREFIX}9f2k1qb`;
const GOOD_THREE = ["Read your recent mail", "Draft replies for you", "Never delete anything"];

function evidence(over: Partial<AskEvidence> = {}): AskEvidence {
  return { link: LINK, resultDelivered: true, whatHappened: "a browser run took 40s", ...over };
}

function refusal(result: { ok: boolean }): Refusal {
  assert.equal(result.ok, false, "expected a refusal");
  return result as Refusal;
}

for (const [what, app] of APPS) {
  await check(`permission sentences: the control, for ${what}`, async () => {
    const out = await permissionSentences(app(), () => GOOD_THREE);
    assert.equal(out.ok, true);
    assert.deepEqual((out as { sentences: string[] }).sentences, GOOD_THREE);
  });

  await check(`permission sentences: two are refused and four are refused, for ${what}`, async () => {
    assert.equal(refusal(await permissionSentences(app(), () => GOOD_THREE.slice(0, 2))).cause, "wrong-count");
    assert.equal(refusal(await permissionSentences(app(), () => [...GOOD_THREE, "And one more"])).cause, "wrong-count");
    assert.equal(refusal(await permissionSentences(app(), () => [])).cause, "wrong-count");
  });

  await check(`permission sentences: ${MAX_SENTENCE_CHARS} sends and one more refuses, for ${what}`, async () => {
    const at = "a".repeat(MAX_SENTENCE_CHARS);
    const over = "a".repeat(MAX_SENTENCE_CHARS + 1);
    assert.equal((await permissionSentences(app(), () => [at, "Two", "Three"])).ok, true);
    assert.equal(refusal(await permissionSentences(app(), () => [over, "Two", "Three"])).cause, "too-long");
  });

  await check(`permission sentences: no scopes never reaches the model, for ${what}`, async () => {
    let called = 0;
    const out = await permissionSentences(app({ scopes: [] }), () => { called++; return GOOD_THREE; });
    assert.equal(refusal(out).cause, "no-scopes");
    assert.equal(called, 0, "a sentence written without a scope is an invention on a consent screen");
    assert.equal(refusal(await permissionSentences(app({ scopes: ["  "] }), () => GOOD_THREE)).cause, "no-scopes");
  });

  await check(`permission sentences: a repeated line is refused, for ${what}`, async () => {
    assert.equal(refusal(await permissionSentences(app(), () => ["Read mail", "read MAIL", "Draft replies"])).cause, "duplicate");
  });

  await check(`permission sentences: a scope URL is not plain language, for ${what}`, async () => {
    assert.equal(refusal(await permissionSentences(app(), () => ["https://mail.google.com/", "Two", "Three"])).cause, "not-plain");
    assert.equal(
      refusal(await permissionSentences(app(), () => ["www.googleapis.com/auth/gmail.readonly", "Two", "Three"])).cause,
      "not-plain",
      "a schemeless scope string is still not a sentence",
    );
  });

  await check(`permission sentences: nobody answered is not a bad answer, for ${what}`, async () => {
    assert.equal(refusal(await permissionSentences(app(), () => { throw new Error("model down"); })).cause, "no-verdict");
    assert.equal(refusal(await permissionSentences(app(), () => null)).cause, "no-verdict");
    assert.equal(refusal(await permissionSentences(app(), () => undefined)).cause, "no-verdict");
    assert.equal(refusal(await permissionSentences(app(), () => "three sentences")).cause, "malformed-reply");
    assert.equal(refusal(await permissionSentences(app(), () => ["One", 2, "Three"])).cause, "malformed-reply");
    assert.equal(refusal(await permissionSentences(app(), () => ["One", "   ", "Three"])).cause, "malformed-reply");
  });

  await check(`permission sentences: an unusable toolkit row is never rendered, for ${what}`, async () => {
    assert.equal(refusal(await permissionSentences(app({ name: "" }), () => GOOD_THREE)).cause, "malformed-meta");
    assert.equal(refusal(await permissionSentences(app({ slug: "" }), () => GOOD_THREE)).cause, "malformed-meta");
    assert.equal(refusal(await permissionSentences(null as unknown as ToolkitMeta, () => GOOD_THREE)).cause, "malformed-meta");
  });

  await check(`the ask: the control, for ${what}`, async () => {
    const text = `That run took a while. Connect your app here ${LINK} — only if you want to, it is fine either way.`;
    const out = await askText("in_task", app(), evidence(), () => text);
    assert.equal(out.ok, true, JSON.stringify(out));
    assert.equal((out as { text: string }).text, text);
  });

  await check(`the ask: a second link, schemeless or not, is refused, for ${what}`, async () => {
    const withScheme = `Here you go ${LINK} or https://connect.vendor.dev/link/abc — up to you.`;
    const schemeless = `Here you go ${LINK} or connect.vendor.dev/link/abc — up to you.`;
    assert.equal(refusal(await askText("in_task", app(), evidence(), () => withScheme)).cause, "extra-link");
    assert.equal(
      refusal(await askText("in_task", app(), evidence(), () => schemeless)).cause,
      "extra-link",
      "a phone linkifies a schemeless vendor link exactly as it linkifies one with a scheme",
    );
  });
}

await check("the ask: ordinary prose is not a second link — the control", async () => {
  const text = `Your run finished in the browser.Connect it once and I can do it directly ${LINK} — only if you want.`;
  const out = await askText("in_task", realApp(), evidence(), () => text);
  assert.equal(out.ok, true, "a good ask was refused for a full stop between two words");
});

for (const term of FORBIDDEN_TERMS) {
  await check(`the register: "${term}" is refused in a permission sentence and in an ask`, async () => {
    const line = `We will ${term} things for you`;
    assert.equal(refusal(await permissionSentences(realApp(), () => [line, "Two", "Three"])).cause, "forbidden-word");
    const ask = `${line}. Here you go ${LINK} — only if you want to.`;
    assert.equal(refusal(await askText("in_task", realApp(), evidence(), () => ask)).cause, "forbidden-word");
  });
}

await check("the register: a word that merely contains a forbidden one is fine", async () => {
  const fine = ["Capital letters stay put", "A therapist reads this fine", "Nothing is granted here"];
  const out = await permissionSentences(realApp(), () => fine);
  assert.equal(out.ok, true, "whole-word matching stopped working; good copy is being refused");
});

for (const stiff of STIFF_FORMS) {
  await check(`the voice: "${stiff}" is refused in an ask`, async () => {
    const ask = `This ${stiff} required. Here you go ${LINK} — only if you want to.`;
    assert.equal(refusal(await askText("in_task", realApp(), evidence(), () => ask)).cause, "stiff");
  });
}

await check("the voice: a curly apostrophe reads as a contraction, not as a stiff form", async () => {
  const ask = `It doesn’t take long. Here you go ${LINK} — only if you want.`;
  const out = await askText("in_task", realApp(), evidence(), () => ask);
  assert.equal(out.ok, true, JSON.stringify(out));
});

await check("an exclamation mark is refused on both surfaces", async () => {
  assert.equal(refusal(await permissionSentences(realApp(), () => ["Read your mail!", "Two", "Three"])).cause, "exclamation");
  const ask = `All done! Here you go ${LINK} — only if you want to.`;
  assert.equal(refusal(await askText("in_task", realApp(), evidence(), () => ask)).cause, "exclamation");
});

await check("the segment arithmetic is the carrier's, not ours", () => {
  assert.equal(MAX_ASK_CHARS_GSM7, 306);
  assert.equal(MAX_ASK_CHARS_UCS2, 134);
  assert.equal(MAX_ASK_SEGMENTS, 2);
  assert.equal(SENTENCE_COUNT, 3);
  assert.deepEqual(smsShape("a".repeat(160)), { encoding: "gsm-7", units: 160, segments: 1, ceiling: 306 });
  assert.deepEqual(smsShape("a".repeat(161)), { encoding: "gsm-7", units: 161, segments: 2, ceiling: 306 });
  assert.equal(smsShape("a".repeat(306)).segments, 2);
  assert.equal(smsShape("a".repeat(307)).segments, 3);
  assert.equal(smsShape("{}").units, 4, "the extension table costs two septets each");
  assert.equal(smsShape("a’").encoding, "ucs-2", "one curly apostrophe changes the whole encoding");
  assert.equal(smsShape("a".repeat(69) + "’").segments, 1, "70 UCS-2 units still fit alone");
  assert.equal(smsShape("a".repeat(70) + "’").segments, 2);
  assert.equal(smsShape("a".repeat(133) + "’").segments, 2);
  assert.equal(smsShape("a".repeat(134) + "’").segments, 3);
  assert.equal(smsShape("😀").units, 2, "a non-BMP character is billed as two code units");
});

await check("the ask: 306 GSM-7 characters send and 307 refuses, uncut", async () => {
  const build = (n: number) => {
    const tail = ` ${LINK} ok`;
    return "a".repeat(n - tail.length) + tail;
  };
  const at = await askText("in_task", realApp(), evidence(), () => build(MAX_ASK_CHARS_GSM7));
  assert.equal(at.ok, true, JSON.stringify(at));
  assert.equal((at as { text: string }).text.length, MAX_ASK_CHARS_GSM7, "never trimmed to fit");
  const over = refusal(await askText("in_task", realApp(), evidence(), () => build(MAX_ASK_CHARS_GSM7 + 1)));
  assert.equal(over.cause, "too-long");
  assert.match(over.refusal, /gsm-7/);
});

await check("the ask: one curly apostrophe drops the real ceiling to 134", async () => {
  const build = (n: number) => {
    const tail = ` ${LINK} ok’`;
    return "a".repeat(n - tail.length) + tail;
  };
  const at = await askText("in_task", realApp(), evidence(), () => build(MAX_ASK_CHARS_UCS2));
  assert.equal(at.ok, true, JSON.stringify(at));
  const over = refusal(await askText("in_task", realApp(), evidence(), () => build(MAX_ASK_CHARS_UCS2 + 1)));
  assert.equal(over.cause, "too-long");
  assert.match(over.refusal, /ucs-2/);
});

await check("the ask: the same 200 characters send or refuse on ONE character's account", async () => {
  const body = (last: string) => {
    const tail = ` ${LINK} ok${last}`;
    return "a".repeat(200 - tail.length) + tail;
  };
  assert.equal((await askText("in_task", realApp(), evidence(), () => body("."))).ok, true);
  assert.equal(refusal(await askText("in_task", realApp(), evidence(), () => body("’"))).cause, "too-long");
});

await check("the ask: our link must be there, exactly once", async () => {
  const none = `You could connect this. Only if you want to.`;
  assert.equal(refusal(await askText("in_task", realApp(), evidence(), () => none)).cause, "no-link");
  const twice = `Here ${LINK} and again ${LINK} — only if you want.`;
  assert.equal(refusal(await askText("in_task", realApp(), evidence(), () => twice)).cause, "extra-link");
});

await check("the ask: a link with characters welded onto the token is a 404, so it is refused", async () => {
  const mangled = `Here you go ${LINK}-x.com/path — only if you want.`;
  const out = refusal(await askText("in_task", realApp(), evidence(), () => mangled));
  assert.equal(out.cause, "mangled-link");
});

await check("the ask: a full stop after the link belongs to the sentence", async () => {
  const text = `That run took a while, so here is the link ${LINK}. Only if you want to, either way is fine.`;
  const out = await askText("in_task", realApp(), evidence(), () => text);
  assert.equal(out.ok, true, JSON.stringify(out));
});

await check("the ask: a message that is only the link has neither the why nor the optional line", async () => {
  assert.equal(refusal(await askText("in_task", realApp(), evidence(), () => LINK)).cause, "nothing-before-link");
  assert.equal(refusal(await askText("in_task", realApp(), evidence(), () => `Here you go ${LINK}`)).cause, "nothing-after-link");
  assert.equal(refusal(await askText("in_task", realApp(), evidence(), () => `${LINK} — only if you want.`)).cause, "nothing-before-link");
});

await check("the ask: a random token is not the ask saying a forbidden word", async () => {
  const tokenLink = `${CONNECT_LINK_PREFIX}x-api-7`;
  const text = `That took a while. Here you go ${tokenLink} — only if you want to.`;
  const out = await askText("in_task", realApp(), evidence({ link: tokenLink }), () => text);
  assert.equal(out.ok, true, "nine random characters cost a perfectly good ask");
});

await check("the ask: never before the task's own result has gone out", async () => {
  let called = 0;
  const out = await askText("in_task", realApp(), evidence({ resultDelivered: false }), () => { called++; return "x"; });
  assert.equal(refusal(out).cause, "result-not-delivered");
  assert.equal(called, 0, "the model was paid for a message that could never be sent");
});

await check("the ask: which half is broken — the catalog row or the run behind it", async () => {
  assert.equal(refusal(await askText("in_task", realApp({ name: "" }), evidence(), () => "x")).cause, "malformed-meta");
  assert.equal(refusal(await askText("in_task", realApp(), null as unknown as AskEvidence, () => "x")).cause, "malformed-evidence");
});

await check("the ask: never out of nowhere, and every contract moment is a real one", async () => {
  for (const bogus of ["", "because", "in-task", "nudge", undefined]) {
    const out = await askText(bogus as never, realApp(), evidence(), () => "x");
    assert.equal(refusal(out).cause, "no-moment", `${String(bogus)} was accepted as a moment`);
  }
  for (const moment of Object.keys(TRIGGER_SCORE)) {
    const text = `That run took a while. Here you go ${LINK} — only if you want to.`;
    const out = await askText(moment as never, realApp(), evidence(), () => text);
    assert.equal(out.ok, true, `${moment} was refused`);
  }
});

await check("the ask: a link that is not ours is refused before a model call is spent", async () => {
  for (const link of ["", "   ", "https://connect.vendor.dev/link/abc", CONNECT_LINK_PREFIX, "http://anticipy.ai/c/tok", `${CONNECT_LINK_PREFIX}a b`]) {
    let called = 0;
    const out = await askText("in_task", realApp(), evidence({ link }), () => { called++; return "x"; });
    assert.equal(refusal(out).cause, "bad-link", `${link} was accepted as our link`);
    assert.equal(called, 0);
  }
});

await check("the ask: nobody answered is not a bad answer", async () => {
  assert.equal(refusal(await askText("in_task", realApp(), evidence(), () => { throw new Error("down"); })).cause, "no-verdict");
  assert.equal(refusal(await askText("in_task", realApp(), evidence(), () => null)).cause, "no-verdict");
  assert.equal(refusal(await askText("in_task", realApp(), evidence(), () => 42)).cause, "malformed-reply");
  assert.equal(refusal(await askText("in_task", realApp(), evidence(), () => "   ")).cause, "malformed-reply");
});

await check("the contract adapter hands back the sentences, or throws the refusal", async () => {
  const good = makePermissionWords(() => GOOD_THREE);
  assert.deepEqual(await good.sentences(realApp()), GOOD_THREE);
  const bad = makePermissionWords(() => ["one", "two"]);
  try {
    await bad.sentences(realApp());
    assert.fail("a blank permission list must never be returnable");
  } catch (err) {
    assert.ok(err instanceof PermissionWordsRefused);
    assert.equal((err as PermissionWordsRefused).refusal.cause, "wrong-count");
  }
});

await check("the register list still holds every term the spec forbids", () => {
  for (const term of ["authorize", "permissions", "integration", "api", "oauth", "composio", "grant access"]) {
    assert.ok(FORBIDDEN_TERMS.includes(term), `"${term}" fell out of the register`);
  }
  assert.ok(STIFF_FORMS.includes("cannot"));
});


// ===========================================================================
// LAW 1, READ OFF THE SHIPPED SOURCE.
//
// Every check above proves the adapter BEHAVES: the letters go out unchanged
// and the vendor's order comes back. This block proves the source CANNOT do
// otherwise — because the way a search box quietly acquires a local opinion is
// one `if (slug === "gmail")` added in a hurry, and a behavioural test only
// catches the cases somebody thought to write.
//
// The scan runs over EXECUTABLE code with comments removed, because both files
// discuss real apps at length in prose ("you have not connected Notion",
// "Connect your googlecalendar") and must go on being allowed to. A string
// literal is NOT stripped: a name in a literal is exactly the violation.
// ===========================================================================

const PROVIDER_SOURCE = readFileSync(join(here, "..", "src", "connections", "provider.ts"), "utf8");
const ROUTE_SOURCE = readFileSync(join(here, "..", "src", "routes", "connections_api.ts"), "utf8");

/** Comments out, code and string literals in.
 *
 *  Hand-written rather than regexed because both files contain `"://"` inside a
 *  string and `/\/\//`-shaped regex literals, and a line-based stripper cuts
 *  those in half — which would let a violation hide in the half it deleted. The
 *  three controls under `codeOnly` prove it removes what it should and keeps
 *  what it should before anything is concluded from it. */
function codeOnly(src: string): string {
  const canStartRegex = /^$|[=(,:;[!&|?{}+\-*%~^<>]/;
  let out = "";
  let prev = "";
  let i = 0;
  while (i < src.length) {
    const c = src[i]!;
    const d = src[i + 1];
    if (c === "/" && d === "/") {
      while (i < src.length && src[i] !== "\n") i++;
      continue;
    }
    if (c === "/" && d === "*") {
      i += 2;
      while (i < src.length && !(src[i] === "*" && src[i + 1] === "/")) i++;
      i += 2;
      continue;
    }
    if (c === '"' || c === "'" || c === "`") {
      out += c;
      i++;
      while (i < src.length) {
        const s = src[i]!;
        out += s;
        i++;
        if (s === "\\") {
          if (i < src.length) { out += src[i]; i++; }
          continue;
        }
        if (s === c) break;
      }
      prev = c;
      continue;
    }
    if (c === "/" && canStartRegex.test(prev)) {
      out += c;
      i++;
      let inClass = false;
      while (i < src.length) {
        const s = src[i]!;
        out += s;
        i++;
        if (s === "\\") {
          if (i < src.length) { out += src[i]; i++; }
          continue;
        }
        if (s === "[") inClass = true;
        else if (s === "]") inClass = false;
        else if (s === "/" && !inClass) break;
      }
      prev = "/";
      continue;
    }
    out += c;
    if (!/\s/.test(c)) prev = c;
    i++;
  }
  return out;
}

/** Real catalog apps, plus the two invented for test/connections-api.test.ts.
 *  This list lives in a TEST, which is where HARNESS-LAWS law 1 puts a word
 *  list: "gates and evals — deterministic tests of outcomes. Measuring is not
 *  programming." The same list in src/ would be the violation it is checking
 *  for. */
const APP_NAMES = [
  "gmail", "googlecalendar", "googledrive", "google_drive", "outlook", "notion",
  "slack", "dropbox", "salesforce", "github", "gitlab", "linear", "asana",
  "trello", "hubspot", "shopify", "zoom", "jira", "confluence", "calendly",
  "airtable", "discord", "telegram", "whatsapp", "spotify", "figma", "clickup",
  "monday", "intercom", "zendesk", "quickbooks", "mailchimp", "sendgrid",
  "zellibrix", "quandle", "quandle_mail",
];

function namesIn(code: string): string[] {
  return APP_NAMES.filter((name) =>
    new RegExp(`(^|[^a-z0-9_])${name}($|[^a-z0-9_])`, "i").test(code));
}

await check("the comment stripper removes prose, keeps code, and the scan is not vacuous", () => {
  const stripped = codeOnly(PROVIDER_SOURCE);
  // CONTROL 1 — comments really went. This sentence exists only in the file's
  // header prose. If it survives, every "no app name in the source" result
  // below is measuring nothing.
  const PROSE = "Zero dependencies and an injected";
  assert.ok(PROVIDER_SOURCE.includes(PROSE),
    "the header sentence this control is anchored on moved; pick another and say so");
  assert.ok(!stripped.includes(PROSE),
    "the stripper left comments in, so the scan below cannot tell prose from code");
  // CONTROL 2 — code really stayed, string literals included.
  assert.ok(stripped.includes('"x-api-key"'), "the stripper ate a string literal");
  assert.ok(stripped.includes("encodeURIComponent"), "the stripper ate code");
  assert.ok(stripped.includes("/^[a-z0-9]{15}$/"), "the stripper ate a regex literal");
  // CONTROL 3 — the scan finds an app name when one IS in a branch. Every
  // "assert nothing was found" below is worthless without this.
  assert.deepEqual(namesIn('if (slug === "gmail") return GMAIL_META;'), ["gmail"]);
  assert.deepEqual(namesIn('const RANK = { notion: 1, slack: 2 };').sort(), ["notion", "slack"]);
  assert.deepEqual(namesIn("// a comment about gmail is fine"), ["gmail"],
    "the scan must see prose too; codeOnly is what removes it, not this");
});

await check("NO APP IS NAMED in the adapter's executable source", () => {
  const found = namesIn(codeOnly(PROVIDER_SOURCE));
  assert.deepEqual(found, [],
    `src/connections/provider.ts names ${found.join(", ")} in code. A catalog search that `
      + "knows an app's name has an opinion about what somebody typed, and "
      + '"a new app in the catalog is a new app in Anticipy with zero code" is false.');
});

await check("NO APP IS NAMED in the route's executable source", () => {
  const found = namesIn(codeOnly(ROUTE_SOURCE));
  assert.deepEqual(found, [],
    `src/routes/connections_api.ts names ${found.join(", ")} in code.`);
});

/** The body of one method, from the comment-stripped source, by brace match. */
function methodBody(code: string, signature: string): string {
  const at = code.indexOf(signature);
  assert.notEqual(at, -1, `${signature} is no longer in the source under that signature`);
  // Past the PARAMETER LIST first. `opts?: { limit?: number }` puts a brace
  // inside the signature, and matching from the first one returns that type
  // instead of the body — which reads as a method that never mentions its own
  // argument, i.e. a false pass on the strictest check in this file.
  let depthP = 0;
  let afterParams = -1;
  for (let i = code.indexOf("(", at); i < code.length; i++) {
    if (code[i] === "(") depthP++;
    else if (code[i] === ")") {
      depthP--;
      if (depthP === 0) { afterParams = i; break; }
    }
  }
  assert.notEqual(afterParams, -1, `${signature} has an unbalanced parameter list`);
  const open = code.indexOf("{", afterParams);
  assert.notEqual(open, -1, `${signature} has no body`);
  let depth = 0;
  for (let i = open; i < code.length; i++) {
    if (code[i] === "{") depth++;
    else if (code[i] === "}") {
      depth--;
      if (depth === 0) return code.slice(open, i + 1);
    }
  }
  throw new Error(`${signature} has an unbalanced body`);
}

await check("search() does exactly one thing with the query: hand it to the vendor", () => {
  // The sharpest form of law 1 available over source. A local filter, a
  // ranking, a did-you-mean or a synonym table all have to READ the query
  // first — so the check is that the query is never read at all.
  const body = methodBody(codeOnly(PROVIDER_SOURCE), "async search(query: string");

  const uses = body.match(/\bquery\b/g) ?? [];
  assert.equal(uses.length, 1,
    `search() mentions the query ${uses.length} times in its body; it may mention it once, `
      + "to put it in the query string");
  assert.equal(body.split("encodeURIComponent(query)").length - 1, 1,
    "the one use is no longer `encodeURIComponent(query)`");

  // No method called on it, no index into it, no comparison against it.
  assert.ok(!/\bquery\s*(?:\.|\[)/.test(body), "search() reaches into the query");
  assert.ok(!/\bquery\s*(?:===?|!==?|<|>)/.test(body), "search() compares the query");
  assert.ok(!/(?:===?|!==?|<|>)\s*query\b/.test(body), "search() compares against the query");

  // And nothing anywhere in the method re-orders or sifts what came back.
  for (const op of [".sort(", ".localeCompare(", ".toLowerCase(", ".toUpperCase(",
                    ".startsWith(", ".endsWith(", ".indexOf(", ".search(", ".match(",
                    ".split(", ".reverse("]) {
    assert.ok(!body.includes(op),
      `search() calls ${op} — a local ranking or filter is the one thing this method may not do`);
  }
  // CONTROL: those assertions are only worth something if they fire.
  const fake = "{ const hit = rows.filter((r) => r.name.toLowerCase().includes(query)); }";
  assert.ok(/\bquery\s*(?:\.|\[)/.test("{ query.trim(); }"));
  assert.ok(fake.includes(".toLowerCase("));
  assert.equal((fake.match(/\bquery\b/g) ?? []).length, 1);
});

// ===========================================================================
// MUTATIONS RUN AGAINST src/connections/provider.ts's SEARCH, 2026-09-06.
//
// Each is anchored on a literal occurring EXACTLY ONCE in that file — the
// script refuses to patch otherwise, because a regex that silently fails to
// match produces a false "it is tested" reading, and that mistake was made
// twice in this repo on 2026-09-05. ALL ELEVEN WENT RED.
//
//   1  `encodeURIComponent(query)` -> `encodeURIComponent(query.trim().toLowerCase())`
//      -> "search puts the typed letters on the wire and nothing else"
//         and "search() does exactly one thing with the query"
//   2  `return out.slice(0, limit)` -> `return out`
//      -> "search caps the answer at MAX_SEARCH_RESULTS, asked for AND cut"
//   3  `&limit=${limit}` dropped from the path
//      -> "search caps the answer at MAX_SEARCH_RESULTS, asked for AND cut"
//   4  the missing-`items` refusal -> `return []`
//      -> "a body with no items array refuses instead of reading as nothing
//         matched"
//   5  `if (out.length === 0 && unreadable > 0)` -> `if (false)`
//      -> "a page where NOTHING is readable refuses; it is not an empty catalog"
//   6  that same test -> `if (out.length === 0)`, so the vendor's own empty
//      answer refuses too
//      -> "the vendor's OWN empty list is an answer: nothing matched"
//   7  `Math.min(MAX_SEARCH_RESULTS, …)` dropped, so a caller sets the cap
//      -> "a caller cannot raise the cap, and an unusable one falls back to it"
//   8  `return out.slice(0, limit).reverse()` — a local re-rank
//      -> "search keeps the vendor's order and never re-sorts it" and
//         "search() does exactly one thing with the query"
//   9  unreadable rows dropped without being counted
//      -> "a page where NOTHING is readable refuses…"
//  10  `readToolkitMeta(row, null)` -> `readToolkitMeta(row, "unknown")`, so a
//      slugless row is attributed to a made-up primary key
//      -> "one unreadable row is dropped; the readable ones survive it"
//  11  `if (!name || slug.length === 0)` -> `if (!name)`
//      -> "one unreadable row is dropped; the readable ones survive it"
//  12  `if (query === "gmail") return […]` added at the top of search()
//      -> "NO APP IS NAMED in the adapter's executable source"
// ===========================================================================

if (failures) {
  console.error(`connections-provider: ${failures} failing, ${passes} passing`);
  process.exit(1);
}
console.log(`connections-provider: all ${passes} cases pass`);
