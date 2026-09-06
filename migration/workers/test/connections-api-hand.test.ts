/**
 * THE API HAND CAN ACT — and the floors that decide whether it may.
 *
 *   node --experimental-strip-types migration/workers/test/connections-api-hand.test.ts
 *
 * Every check here runs with no network, no key that opens anything, and no
 * account behind it: the transport is injected and records every request, the
 * store is the REAL D1 store over the REAL schema (test/fake-d1.ts loads
 * migration/d1/schema.sql verbatim into node:sqlite), so every guard the store
 * carries — owner scoping, refuseMixedOwners, the CHECKs — is live in every
 * check below. The invented toolkit is `zellibrix` and its tools are invented
 * too, so that no real app is named anywhere a source scan could confuse with
 * code.
 *
 * ORDER: hardest first. The first block is the thing the hand is shaped
 * around — a step that runs when nothing licensed it. The second is the
 * control, without which every "zero fetches" above it is measuring nothing.
 * Then the adapter's two new methods on their own, then the source legs.
 *
 * WHAT WAS MEASURED LIVE and is written down here rather than in a chat
 * (HARNESS-LAWS law 4), 2026-09-06, this account's key, api v3.1:
 *   * `GET /tools?toolkit_slug=googlecalendar&limit=100` -> 49 tools in one
 *     page, `next_cursor: null`; two of the slugs: GOOGLECALENDAR_FIND_EVENT
 *     (tags readOnlyHint, idempotentHint, openWorldHint, important) and
 *     GOOGLECALENDAR_CREATE_EVENT (tags openWorldHint, important, createHint).
 *     `limit=3` paged: page 2 came back under `cursor=` with `current_page: 2`.
 *     gmail 63, slack 167, hubspot 245 (`limit=1000` returned all 245 at once).
 *   * an unknown toolkit slug -> 200 `{items: [], total_items: 0}`.
 *   * `deprecated` is an object; `is_deprecated` is the boolean (4 of 49 true).
 *   * `POST /tools/execute/GOOGLECALENDAR_FIND_EVENT` for the probe owner
 *     qeuy6sv1raof9rw, who has NO connection (live D1 `connections`: 0 rows
 *     for that owner, 0 rows in the table) -> 404
 *     `{error:{slug:"ActionExecute_ConnectedAccountNotFound", code:1810}}`;
 *     with `connected_account_id: "ca_doesnotexist000"` the same slug, naming
 *     the id; an unknown tool slug -> 404 `{error:{slug:"Tool_ToolNotFound",
 *     code:2401}}`; an unrecognised body key is accepted in silence.
 *   * the execute SUCCESS body is NOT measured: nobody has a connected account
 *     and creating one is the owner's tap. The adapter reads the documented
 *     shape as a floor, and the checks under "the reply is read as a floor"
 *     pin that polarity.
 *   * THE FLOOR, LIVE: `runStep` for the probe owner over a store mirroring
 *     live D1 (no rows), a counting wrapper over the real `fetch` and the real
 *     key, on a read-only tool -> `refused: not_connected`, ZERO fetches. The
 *     same with a seeded connected row and a typed-not-listed slug -> ONE fetch
 *     (the catalog GET, 49 tools back), `refused: tool_unknown`, zero POSTs.
 */
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import type { OwnerId } from "../../../spike/two-hands/src/connections/contract.ts";
import {
  CATALOG_TTL_MS,
  CREATE_HINT,
  DESTRUCTIVE_HINT,
  READ_ONLY_HINT,
  SIDE_EFFECT_ORDER,
  UPDATE_HINT,
  failureMayHaveLanded,
  forgetCatalogs,
  runStep,
  sideEffectHint,
  tightenSideEffect,
  type ApiHandOutcome,
  type ApiHandStep,
} from "../src/connections/api_hand.ts";
import {
  COMPOSIO_BASE_URL,
  ComposioConnections,
  EXECUTE_NO_ACCOUNT_TOKEN,
  EXECUTE_TOOL_NOT_FOUND_TOKEN,
  MAX_TOOL_PAGES,
  TOOLS_PAGE_LIMIT,
  execErrorKind,
} from "../src/connections/provider.ts";
import { createD1Store, forgetLiveColumns, type StoredConnection } from "../src/connections/store.ts";
import { FakeD1, asD1 } from "./fake-d1.ts";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(here, "..", "..", "..");
const HAND_SOURCE = readFileSync(join(here, "..", "src", "connections", "api_hand.ts"), "utf8");
const PROVIDER_SOURCE = readFileSync(join(here, "..", "src", "connections", "provider.ts"), "utf8");
const TWO_HANDS_CONTRACT = readFileSync(join(repoRoot, "spike", "two-hands", "src", "contract.ts"), "utf8");

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

/** The production probe owner (CLAUDE.md) and the owner recorded in
 *  research/2026-09-05-composio-connections.md. Two, because a floor that only
 *  ever sees one owner cannot be shown to scope by owner. */
const OWNER = "qeuy6sv1raof9rw" as OwnerId;
const STRANGER = "sxkotd1h02qb6gw" as OwnerId;
const KEY = "comp_test_supersecret_key_1234567890";

/** The invented toolkit and its tools. Tags are the vendor's measured spellings
 *  on invented slugs. */
const APP = "zellibrix";
const READ_TOOL = "ZELLIBRIX_FIND_THING";
const CREATE_TOOL = "ZELLIBRIX_CREATE_THING";
const UPDATE_TOOL = "ZELLIBRIX_UPDATE_THING";
const DELETE_TOOL = "ZELLIBRIX_DELETE_THING";
const UNTAGGED_TOOL = "ZELLIBRIX_UNTAGGED";
const CATALOG = [
  toolRow(READ_TOOL, [READ_ONLY_HINT, "idempotentHint", "openWorldHint"]),
  toolRow(CREATE_TOOL, ["openWorldHint", "important", CREATE_HINT]),
  toolRow(UPDATE_TOOL, [UPDATE_HINT, "idempotentHint"]),
  toolRow(DELETE_TOOL, [DESTRUCTIVE_HINT, "idempotentHint", "important"]),
  toolRow(UNTAGGED_TOOL, ["Quick Operations"]),
];

const ACCOUNT = "ca_zell_owner_0001";
const ACCOUNT_WORK = "ca_zell_owner_work";
const ACCOUNT_STRANGER = "ca_zell_stranger_1";
const ARGS = { thing_id: "t_42", note: "SECRET-MAIL-BODY-9f3" };

/** A catalog row in the measured shape (toolkit nested, `deprecated` an object). */
function toolRow(slug: string, tags: string[], over: Record<string, unknown> = {}) {
  return {
    slug,
    name: slug.toLowerCase().replace(/_/g, " "),
    description: `does the ${slug} thing`,
    toolkit: { slug: APP, name: APP, logo: "https://logos.example/api/zellibrix" },
    tags,
    scopes: ["https://scopes.example/auth/thing"],
    input_parameters: { type: "object", properties: { thing_id: { type: "string" } } },
    is_deprecated: false,
    deprecated: { displayName: slug, version: "20260902_00", is_deprecated: false },
    ...over,
  };
}

interface Recorded {
  method: string;
  path: string;
  headers: Record<string, string>;
  body: any;
}
interface Reply {
  status?: number;
  body?: unknown;
  throws?: unknown;
}

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
    return { status: reply.status ?? 200, json: async () => reply.body ?? null } as unknown as Response;
  };
  return { calls, impl: impl as unknown as typeof globalThis.fetch };
}

const isCatalog = (c: Recorded) => c.method === "GET" && c.path.startsWith("/tools?");
const isExecute = (c: Recorded) => c.method === "POST" && c.path.startsWith("/tools/execute/");

/** The vendor as it was measured: the catalog answers for our toolkit, execute
 *  answers success in the documented shape. Overrides per check. */
function vendor(over: Partial<{ catalog: Reply; execute: Reply | ((c: Recorded) => Reply) }> = {}) {
  return fakeFetch((call) => {
    if (isCatalog(call)) return over.catalog ?? { status: 200, body: { items: CATALOG, next_cursor: null } };
    if (isExecute(call)) {
      const e = over.execute;
      if (typeof e === "function") return e(call);
      return e ?? { status: 200, body: { data: { ok: 1 }, error: null, successful: true, log_id: "log_1" } };
    }
    return { status: 500, body: { error: { slug: "unexpected_route" } } };
  });
}

function row(over: Partial<StoredConnection> = {}): StoredConnection {
  return {
    user_id: OWNER,
    toolkit: APP,
    connected_account_id: ACCOUNT,
    alias: null,
    status: "connected",
    writes_enabled: false,
    last_used_at: null,
    ...over,
  };
}

interface Rig {
  db: FakeD1;
  env: { DB: D1Database; COMPOSIO_API_KEY?: string };
  store: ReturnType<typeof createD1Store>;
  provider: ComposioConnections;
  calls: Recorded[];
}

/** The real store over the real schema, seeded through the store's own
 *  guarded writes, and an adapter over a recording transport. */
async function rig(seed: StoredConnection[], fetchRig = vendor(), apiKey: string | null = KEY): Promise<Rig> {
  const db = new FakeD1();
  const env = { DB: asD1(db), COMPOSIO_API_KEY: apiKey ?? undefined };
  const store = createD1Store(env);
  forgetLiveColumns(env);
  for (const r of seed) await store.putConnection(r);
  const provider = new ComposioConnections({ apiKey, fetchImpl: fetchRig.impl });
  return { db, env, store, provider, calls: fetchRig.calls };
}

function step(over: Partial<ApiHandStep> = {}): ApiHandStep {
  return { owner: OWNER, toolkit: APP, tool: READ_TOOL, args: { ...ARGS }, effect: "read", ...over };
}

async function run(r: Rig, s: ApiHandStep, clock?: () => number): Promise<ApiHandOutcome> {
  return runStep(r.env, s, { store: r.store, provider: r.provider, ...(clock ? { clock } : {}) });
}

/** Capture every console.log line during `fn`. The hand logs each outcome;
 *  the checks below read those lines for what they must and must not carry. */
async function logged<T>(fn: () => Promise<T>): Promise<{ value: T; lines: string[] }> {
  const lines: string[] = [];
  const original = console.log;
  console.log = (...args: unknown[]) => { lines.push(args.map(String).join(" ")); };
  try {
    return { value: await fn(), lines };
  } finally {
    console.log = original;
  }
}

function refused(out: ApiHandOutcome, reason: string): asserts out is Extract<ApiHandOutcome, { outcome: "refused" }> {
  assert.equal(out.outcome, "refused", `expected a refusal, got ${out.outcome}`);
  assert.equal((out as { reason: string }).reason, reason);
}

// ===========================================================================
// 0. THE CONTRACT IS THE CONTRACT — the re-declared rule, pinned to its source.
// ===========================================================================

await check("tightenSideEffect is the Two Hands contract's own, read from its source", () => {
  const block = TWO_HANDS_CONTRACT.match(
    /export function tightenSideEffect\(planned: SideEffect, hint\?: SideEffect\): SideEffect \{\s*if \(!hint\) return planned;\s*return SIDE_EFFECT_ORDER\[hint\] > SIDE_EFFECT_ORDER\[planned\] \? hint : planned;\s*\}/,
  );
  assert.ok(block, "the contract's tightenSideEffect changed; api_hand.ts carries a copy and must change with it");
  const order = TWO_HANDS_CONTRACT.match(/SIDE_EFFECT_ORDER: Record<SideEffect, number> = \{([^}]*)\}/);
  assert.ok(order, "the contract no longer declares SIDE_EFFECT_ORDER");
  const fromContract: Record<string, number> = {};
  for (const [, k, v] of order![1].matchAll(/(\w+):\s*(\d+)/g)) fromContract[k!] = Number(v);
  assert.deepEqual({ ...SIDE_EFFECT_ORDER }, fromContract);
  // The behaviour, both directions.
  assert.equal(tightenSideEffect("read", "write"), "write", "a hint tightens");
  assert.equal(tightenSideEffect("write", "read"), "write", "a hint NEVER loosens");
  assert.equal(tightenSideEffect("irreversible", "write"), "irreversible");
  assert.equal(tightenSideEffect("read", null), "read");
  assert.equal(tightenSideEffect("read", undefined), "read");
});

await check("the hint tags are the measured spellings, and the strictest tag wins", () => {
  // Pinned to the adapter's receipt of the live catalog, which is where they
  // were measured. A renamed tag in the vendor's catalog goes red HERE.
  for (const tag of [READ_ONLY_HINT, DESTRUCTIVE_HINT, CREATE_HINT, UPDATE_HINT]) {
    assert.ok(PROVIDER_SOURCE.includes(tag), `${tag} is not in provider.ts's measured receipt`);
  }
  assert.equal(sideEffectHint([READ_ONLY_HINT, "idempotentHint"]), "read");
  assert.equal(sideEffectHint([CREATE_HINT]), "write");
  assert.equal(sideEffectHint([UPDATE_HINT]), "write");
  assert.equal(sideEffectHint([DESTRUCTIVE_HINT]), "irreversible");
  assert.equal(sideEffectHint([READ_ONLY_HINT, CREATE_HINT]), "write", "a self-contradicting row reads as the stricter");
  assert.equal(sideEffectHint([CREATE_HINT, READ_ONLY_HINT]), "write", "…in either order");
  assert.equal(sideEffectHint([READ_ONLY_HINT, DESTRUCTIVE_HINT]), "irreversible");
  assert.equal(sideEffectHint([]), null, "no tags is NO hint, not a read");
  assert.equal(sideEffectHint(["Quick Operations", "important"]), null, "non-hint tags are not read as anything");
  assert.equal(sideEffectHint(["readonlyhint"]), null, "an exact identifier match, not a case-folded one");
});

await check("failureMayHaveLanded matches the contract's three promises", () => {
  assert.equal(failureMayHaveLanded("auth"), false);
  assert.equal(failureMayHaveLanded("rate"), false);
  assert.equal(failureMayHaveLanded("schema"), false);
  assert.equal(failureMayHaveLanded("other"), true);
});

await check("execErrorKind: status decides, and the two measured 404 slugs decide between auth and schema", () => {
  assert.equal(execErrorKind(401, ""), "auth");
  assert.equal(execErrorKind(403, ""), "auth");
  assert.equal(execErrorKind(429, ""), "rate");
  assert.equal(execErrorKind(400, ""), "schema");
  assert.equal(execErrorKind(422, ""), "schema");
  assert.equal(execErrorKind(404, EXECUTE_NO_ACCOUNT_TOKEN), "auth", "the owner's connection is gone at the vendor: re-auth, not a demotion");
  assert.equal(execErrorKind(404, EXECUTE_TOOL_NOT_FOUND_TOKEN), "schema");
  assert.equal(execErrorKind(404, ""), "other", "an unmeasured 404 is not a promise that nothing ran");
  assert.equal(execErrorKind(404, "SomethingElse"), "other");
  assert.equal(execErrorKind(500, ""), "other");
  assert.equal(execErrorKind(0, ""), "other");
  assert.equal(EXECUTE_NO_ACCOUNT_TOKEN, "ActionExecute_ConnectedAccountNotFound");
  assert.equal(EXECUTE_TOOL_NOT_FOUND_TOKEN, "Tool_ToolNotFound");
});

// ===========================================================================
// 1. THE FLOORS. A step that runs when nothing licensed it is the failure.
//    Every refusal below is asserted to have cost ZERO execute calls, and the
//    ones before the catalog ZERO calls of any kind.
// ===========================================================================

await check("no connection row -> refused not_connected, and NO fetch", async () => {
  const r = await rig([]);
  const out = await run(r, step());
  refused(out, "not_connected");
  assert.equal(out.catalogRead, false);
  assert.equal(out.effect, "read");
  assert.equal(r.calls.length, 0, "the vendor was called for an owner with no row");
});

await check("a row for the toolkit that is needs_reconnect is not connected — no fetch", async () => {
  const r = await rig([row({ status: "needs_reconnect" })]);
  const out = await run(r, step());
  refused(out, "not_connected");
  assert.match(out.detail, /needs_reconnect/);
  assert.equal(r.calls.length, 0);
});

await check("a row that is disconnected is not connected — no fetch", async () => {
  const r = await rig([row({ status: "disconnected" })]);
  const out = await run(r, step());
  refused(out, "not_connected");
  assert.equal(r.calls.length, 0);
});

await check("a STRANGER's connected row on the same toolkit licenses nothing for this owner — no fetch", async () => {
  const r = await rig([row({ user_id: STRANGER, connected_account_id: ACCOUNT_STRANGER })]);
  const out = await run(r, step());
  refused(out, "not_connected");
  assert.equal(r.calls.length, 0, "a stranger's row was read as this owner's");
});

await check("this owner's row on ANOTHER toolkit licenses nothing for this one — no fetch", async () => {
  const r = await rig([row({ toolkit: "quandle_mail", connected_account_id: "ca_other_app" })]);
  const out = await run(r, step());
  refused(out, "not_connected");
  assert.equal(r.calls.length, 0);
});

await check("the toolkit is matched as a canonical slug: 'Zellibrix ' finds the 'zellibrix' row", async () => {
  const r = await rig([row()]);
  const out = await run(r, step({ toolkit: " Zellibrix " }));
  assert.equal(out.outcome, "ran", "case and whitespace on an identifier must not read as a different app");
});

for (const effect of ["write", "irreversible"] as const) {
  await check(`a ${effect} on a connected row with writes_enabled false -> refused writes_not_enabled, NO fetch`, async () => {
    const r = await rig([row({ writes_enabled: false })]);
    const out = await run(r, step({ tool: CREATE_TOOL, effect, confirmed: true }));
    refused(out, "writes_not_enabled");
    assert.equal(out.catalogRead, false, "the vendor learned of an unlicensed write");
    assert.equal(out.effect, effect);
    assert.equal(r.calls.length, 0);
  });
}

await check("THE WRITE OPT-IN IS READ FROM THE ROW: the same write with writes_enabled true goes through", async () => {
  const r = await rig([row({ writes_enabled: true })]);
  const out = await run(r, step({ tool: CREATE_TOOL, effect: "write" }));
  assert.equal(out.outcome, "ran", JSON.stringify(out));
  assert.equal(r.calls.filter(isExecute).length, 1);
  // And it is the STORED value that decided: flip it in the database and the
  // next step refuses. Nothing else changed.
  r.db.db.prepare(`UPDATE connections SET writes_enabled = 0 WHERE connected_account_id = ?`).run(ACCOUNT);
  const again = await run(r, step({ tool: CREATE_TOOL, effect: "write" }));
  refused(again, "writes_not_enabled");
  assert.equal(r.calls.filter(isExecute).length, 1, "a second execute went out after the toggle went off");
});

await check("a declared READ on a tool whose own tags say createHint is tightened to a write, and refused without the opt-in", async () => {
  const r = await rig([row({ writes_enabled: false })]);
  const out = await run(r, step({ tool: CREATE_TOOL, effect: "read" }));
  refused(out, "writes_not_enabled");
  assert.equal(out.effect, "write", "the tightened effect is what the refusal reports");
  assert.match(out.detail, /tool's own metadata/);
  assert.equal(out.catalogRead, true, "the catalog had to be read to learn the tag");
  assert.equal(r.calls.filter(isCatalog).length, 1);
  assert.equal(r.calls.filter(isExecute).length, 0, "a planner mislabelling a create as a read got it executed");
});

await check("a declared READ on an updateHint tool is a write too", async () => {
  const r = await rig([row({ writes_enabled: false })]);
  const out = await run(r, step({ tool: UPDATE_TOOL, effect: "read" }));
  refused(out, "writes_not_enabled");
  assert.equal(out.effect, "write");
  assert.equal(r.calls.filter(isExecute).length, 0);
});

await check("a declared WRITE on a readOnlyHint tool stays a write: hints never loosen", async () => {
  const r = await rig([row({ writes_enabled: false })]);
  const out = await run(r, step({ tool: READ_TOOL, effect: "write" }));
  refused(out, "writes_not_enabled");
  assert.equal(out.effect, "write");
  assert.equal(r.calls.length, 0, "and it refused before the catalog, on the declared effect");
});

await check("an untagged tool tightens nothing: the declared read stands", async () => {
  const r = await rig([row({ writes_enabled: false })]);
  const out = await run(r, step({ tool: UNTAGGED_TOOL, effect: "read" }));
  assert.equal(out.outcome, "ran", JSON.stringify(out));
  assert.equal((out as { effect: string }).effect, "read");
});

await check("a destructiveHint tool is irreversible: declared read, opt-in ON, still refused without confirmation", async () => {
  const r = await rig([row({ writes_enabled: true })]);
  const out = await run(r, step({ tool: DELETE_TOOL, effect: "read" }));
  refused(out, "confirmation_required");
  assert.equal(out.effect, "irreversible");
  assert.equal(r.calls.filter(isExecute).length, 0, "a delete ran with nobody having confirmed the payload");
});

await check("…and with writes ON and confirmed: true it runs, reported as irreversible", async () => {
  const r = await rig([row({ writes_enabled: true })]);
  const out = await run(r, step({ tool: DELETE_TOOL, effect: "read", confirmed: true }));
  assert.equal(out.outcome, "ran", JSON.stringify(out));
  assert.equal((out as { effect: string }).effect, "irreversible");
});

await check("…but confirmed: true does not stand in for the opt-in: writes OFF still refuses, no fetch", async () => {
  const r = await rig([row({ writes_enabled: false })]);
  const out = await run(r, step({ tool: DELETE_TOOL, effect: "irreversible", confirmed: true }));
  refused(out, "writes_not_enabled");
  assert.equal(r.calls.length, 0);
});

await check("a slug the catalog does not list -> refused tool_unknown: ONE catalog GET, ZERO execute", async () => {
  const r = await rig([row()]);
  const out = await run(r, step({ tool: "ZELLIBRIX_DELETE_EVERYTHING" }));
  refused(out, "tool_unknown");
  assert.equal(out.catalogRead, true);
  assert.match(out.detail, /lists 5 tool\(s\)/);
  assert.equal(r.calls.filter(isCatalog).length, 1);
  assert.equal(r.calls.filter(isExecute).length, 0, "a slug a model typed reached the execute endpoint");
  assert.equal(r.calls.length, 1);
});

await check("a slug from ANOTHER toolkit's catalog is unknown here, even though it exists at the vendor", async () => {
  // The allow-list is per toolkit, because the connection row and its write
  // opt-in are per toolkit. A real tool of app B under app A's row is the
  // seatbelt bypass.
  const r = await rig([row()]);
  const out = await run(r, step({ tool: "QUANDLE_MAIL_SEND" }));
  refused(out, "tool_unknown");
  assert.equal(r.calls.filter(isExecute).length, 0);
});

await check("an empty catalog from the vendor is an answer: every slug is unknown", async () => {
  const r = await rig([row()], vendor({ catalog: { status: 200, body: { items: [], next_cursor: null } } }));
  const out = await run(r, step());
  refused(out, "tool_unknown");
  assert.match(out.detail, /lists 0 tool/);
  assert.equal(r.calls.filter(isExecute).length, 0);
});

await check("a catalog that cannot be read is NOT an empty catalog: refused catalog_unavailable, zero execute", async () => {
  for (const reply of [
    { status: 200, body: { nope: [] } },
    { status: 500, body: { error: { slug: "upstream_down" } } },
    { status: 200, body: { items: [{ slug: "", toolkit: { slug: APP } }, { name: "no slug" }], next_cursor: null } },
  ] as Reply[]) {
    const r = await rig([row()], vendor({ catalog: reply }));
    const out = await run(r, step());
    refused(out, "catalog_unavailable");
    assert.equal(out.catalogRead, true);
    assert.equal(r.calls.filter(isExecute).length, 0);
  }
});

await check("no vendor key -> refused unconfigured, and no request was issued", async () => {
  const r = await rig([row()], vendor(), null);
  const out = await run(r, step());
  refused(out, "unconfigured");
  assert.equal(r.calls.length, 0);
});

await check("the store cannot answer -> refused store_unavailable, not 'not connected', and no fetch", async () => {
  const r = await rig([row()]);
  r.db.failOn = (sql) => /FROM "connections"/.test(sql);
  const out = await run(r, step());
  refused(out, "store_unavailable");
  assert.match(out.detail, /D1_ERROR/);
  assert.equal(r.calls.length, 0);
});

await check("two connected accounts on one app and no alias -> refused account_ambiguous, no fetch", async () => {
  const r = await rig([row({ alias: "personal" }), row({ alias: "work", connected_account_id: ACCOUNT_WORK })]);
  const out = await run(r, step());
  refused(out, "account_ambiguous");
  assert.equal(r.calls.length, 0, "the hand guessed which of two accounts to use");
});

await check("…with alias 'work' the step runs against the work account, and that id goes on the wire", async () => {
  const r = await rig([row({ alias: "personal" }), row({ alias: "work", connected_account_id: ACCOUNT_WORK })]);
  const out = await run(r, step({ alias: "work" }));
  assert.equal(out.outcome, "ran", JSON.stringify(out));
  assert.equal((out as { account: string }).account, ACCOUNT_WORK);
  const exec = r.calls.find(isExecute)!;
  assert.equal(exec.body.connected_account_id, ACCOUNT_WORK);
});

await check("…and an alias nobody connected refuses rather than falling back to the other account", async () => {
  const r = await rig([row({ alias: "personal" })]);
  const out = await run(r, step({ alias: "work" }));
  refused(out, "not_connected");
  assert.match(out.detail, /"work"/);
  assert.equal(r.calls.length, 0);
});

await check("the owner is the ROW id or nothing: a name, an email, a blank all refuse with no fetch, and NONE is echoed into the log", async () => {
  for (const owner of ["omar", "jose@anticipy.ai", "", "   ", "QEUY6SV1RAOF9RW"]) {
    const r = await rig([row()]);
    const { value: out, lines } = await logged(() => run(r, step({ owner })));
    refused(out, "owner_required");
    assert.equal(r.calls.length, 0, `${JSON.stringify(owner)} reached the vendor`);
    assert.equal(lines.length, 1);
    assert.ok(lines[0]!.includes("owner_required"), lines[0]);
    const shown = owner.trim();
    if (shown) {
      assert.ok(!out.detail.includes(shown), "the offending value was echoed into the detail");
      assert.ok(!lines[0]!.includes(shown), `the offending value was echoed into the log: ${lines[0]}`);
    }
  }
});

await check("a sentence passed as the tool slug is never written into the log either", async () => {
  const r = await rig([row()]);
  const sentence = "delete every event Sam Okafor is invited to";
  const { value: out, lines } = await logged(() => run(r, step({ tool: sentence })));
  refused(out, "tool_required");
  assert.equal(lines.length, 1);
  assert.ok(!lines[0]!.includes("Okafor"), `a model-typed sentence reached the log: ${lines[0]}`);
  assert.ok(lines[0]!.includes(OWNER) && lines[0]!.includes(APP), lines[0]);
  assert.equal(r.calls.length, 0);
});

await check("a step with no declared effect is refused: silence licenses nothing", async () => {
  for (const effect of [undefined, null, "", "READ", "reads", "unknown", 0] as unknown[]) {
    const r = await rig([row({ writes_enabled: true })]);
    const out = await run(r, step({ effect: effect as never }));
    refused(out, "effect_required");
    assert.equal(out.effect, null);
    assert.equal(r.calls.length, 0);
  }
});

await check("arguments must be a plain JSON object", async () => {
  for (const args of [undefined, null, "send it", 42, ["a"], { big: 10n }] as unknown[]) {
    const r = await rig([row()]);
    const out = await run(r, step({ args: args as never }));
    refused(out, "args_required");
    assert.equal(r.calls.length, 0);
  }
});

await check("a blank or sentence-shaped tool slug is refused before the store is read", async () => {
  for (const tool of ["", "   ", "find the thing", "ZELLIBRIX FIND"]) {
    const r = await rig([row()]);
    r.db.failOn = () => true; // a store read here would throw and become store_unavailable
    const out = await run(r, step({ tool }));
    refused(out, "tool_required");
    assert.equal(r.calls.length, 0);
  }
});

await check("a blank toolkit is refused before the store is read", async () => {
  const r = await rig([row()]);
  r.db.failOn = () => true;
  const out = await run(r, step({ toolkit: "  " }));
  refused(out, "toolkit_required");
  assert.equal(r.calls.length, 0);
});

// ===========================================================================
// 2. THE CONTROL. A read on a connected row goes through — exactly one execute,
//    the owner as user_id, the catalog's slug in the path.
// ===========================================================================

await check("CONTROL: a read tool with a connected row -> ran; ONE execute; user_id is the owner; the exact slug is in the path", async () => {
  const r = await rig([row()]);
  const out = await run(r, step());
  assert.equal(out.outcome, "ran", JSON.stringify(out));
  const ran = out as Extract<ApiHandOutcome, { outcome: "ran" }>;
  assert.equal(ran.tool, READ_TOOL);
  assert.equal(ran.toolkit, APP);
  assert.equal(ran.account, ACCOUNT);
  assert.equal(ran.effect, "read");
  assert.deepEqual(ran.data, { ok: 1 });
  assert.equal(ran.logId, "log_1");

  const execs = r.calls.filter(isExecute);
  assert.equal(execs.length, 1, "exactly one execute");
  assert.equal(r.calls.length, 2, "the catalog GET and the execute, nothing else");
  assert.equal(execs[0]!.path, `/tools/execute/${READ_TOOL}`);
  assert.equal(execs[0]!.body.user_id, OWNER);
  assert.deepEqual(execs[0]!.body.arguments, ARGS);
  assert.equal(execs[0]!.body.connected_account_id, ACCOUNT);
  assert.equal(execs[0]!.headers["x-api-key"], KEY);
  assert.ok(!("text" in execs[0]!.body), "only one of text/arguments may be sent, and it is arguments");
  assert.equal(Object.keys(execs[0]!.body).sort().join(","), "arguments,connected_account_id,user_id",
    "every body key is one the vendor's own error text named back; an unrecognised key is accepted in silence");
});

await check("CONTROL: the fetch counter counts — the same rig with an execute reply of 500 shows the POST", async () => {
  const r = await rig([row()], vendor({ execute: { status: 500, body: {} } }));
  const out = await run(r, step());
  assert.equal(out.outcome, "failed");
  assert.equal(r.calls.filter(isExecute).length, 1);
});

await check("the second step on the same toolkit is exactly ONE vendor call: the catalog is cached per adapter", async () => {
  const r = await rig([row()]);
  await run(r, step());
  const before = r.calls.length;
  const out = await run(r, step({ tool: UNTAGGED_TOOL }));
  assert.equal(out.outcome, "ran");
  assert.equal(r.calls.length - before, 1);
  assert.equal(r.calls.filter(isCatalog).length, 1, "the catalog was fetched twice");
});

await check("the cache expires: after CATALOG_TTL_MS the catalog is fetched again", async () => {
  let now = 1_000_000;
  const r = await rig([row()]);
  await run(r, step(), () => now);
  now += CATALOG_TTL_MS;
  await run(r, step(), () => now);
  assert.equal(r.calls.filter(isCatalog).length, 2);
  // and forgetCatalogs drops it on demand
  forgetCatalogs(r.provider);
  await run(r, step(), () => now);
  assert.equal(r.calls.filter(isCatalog).length, 3);
});

await check("two adapters do not share a catalog: a slug listed for one is unknown to the other", async () => {
  const a = await rig([row()]);
  const b = await rig([row()], vendor({ catalog: { status: 200, body: { items: [], next_cursor: null } } }));
  assert.equal((await run(a, step())).outcome, "ran");
  refused(await run(b, step()), "tool_unknown");
});

await check("a slug spelled in another case is matched to the catalog, and the CATALOG's spelling goes on the wire", async () => {
  const r = await rig([row()]);
  const out = await run(r, step({ tool: " zellibrix_find_thing " }));
  assert.equal(out.outcome, "ran");
  assert.equal(r.calls.find(isExecute)!.path, `/tools/execute/${READ_TOOL}`);
});

// ===========================================================================
// 3. FAILURES ARE TYPED. runStep never throws; the vendor's answer becomes one
//    of four kinds and a landed/not-landed fact the router can act on.
// ===========================================================================

const VENDOR_FAILURES: Array<[string, Reply, { kind: string; status: number; token: string; retryable: boolean; landed: boolean }]> = [
  ["a 500", { status: 500, body: { error: { slug: "Internal" } } }, { kind: "other", status: 500, token: "Internal", retryable: true, landed: true }],
  ["a 502 with an HTML body", { status: 502, body: null }, { kind: "other", status: 502, token: "", retryable: true, landed: true }],
  ["a 401", { status: 401, body: { error: { slug: "Unauthorized" } } }, { kind: "auth", status: 401, token: "Unauthorized", retryable: false, landed: false }],
  ["a 429", { status: 429, body: { error: { slug: "RateLimited" } } }, { kind: "rate", status: 429, token: "RateLimited", retryable: true, landed: false }],
  ["a 400", { status: 400, body: { error: { slug: "BadRequest" } } }, { kind: "schema", status: 400, token: "BadRequest", retryable: false, landed: false }],
  ["the measured no-account 404", { status: 404, body: { error: { slug: EXECUTE_NO_ACCOUNT_TOKEN, code: 1810, status: 404 } } }, { kind: "auth", status: 404, token: EXECUTE_NO_ACCOUNT_TOKEN, retryable: false, landed: false }],
  ["the measured no-tool 404", { status: 404, body: { error: { slug: EXECUTE_TOOL_NOT_FOUND_TOKEN, code: 2401 } } }, { kind: "schema", status: 404, token: EXECUTE_TOOL_NOT_FOUND_TOKEN, retryable: false, landed: false }],
  ["an unmeasured 404", { status: 404, body: { error: { slug: "Mystery" } } }, { kind: "other", status: 404, token: "Mystery", retryable: false, landed: true }],
];

for (const [what, reply, want] of VENDOR_FAILURES) {
  await check(`vendor ${what} on execute -> a typed failure, never a throw`, async () => {
    const r = await rig([row()], vendor({ execute: reply }));
    const out = await run(r, step());
    assert.equal(out.outcome, "failed", JSON.stringify(out));
    const failed = out as Extract<ApiHandOutcome, { outcome: "failed" }>;
    assert.equal(failed.error.kind, want.kind);
    assert.equal(failed.error.status, want.status);
    assert.equal(failed.error.token, want.token);
    assert.equal(failed.error.retryable, want.retryable);
    assert.equal(failed.mayHaveLanded, want.landed);
    assert.equal(failed.tool, READ_TOOL);
    assert.equal(failed.account, ACCOUNT);
    assert.equal(typeof failed.error.message, "string");
    assert.equal(r.calls.filter(isExecute).length, 1, "the hand retried — it must never");
  });
}

await check("a transport failure on execute -> failed other, status 0, may have landed, no retry", async () => {
  const r = await rig([row()], vendor({ execute: { throws: new TypeError("fetch failed") } }));
  const out = await run(r, step());
  assert.equal(out.outcome, "failed");
  const failed = out as Extract<ApiHandOutcome, { outcome: "failed" }>;
  assert.equal(failed.error.kind, "other");
  assert.equal(failed.error.status, 0);
  assert.equal(failed.error.retryable, true);
  assert.equal(failed.mayHaveLanded, true);
  assert.equal(r.calls.filter(isExecute).length, 1);
});

await check("the reply is read as a FLOOR: a 200 that says the tool failed is a failure, kinded by its structured status", async () => {
  const r = await rig([row()], vendor({
    execute: { status: 200, body: { data: null, error: { status: 401, slug: "TokenExpired" }, successful: false, log_id: "log_x" } },
  }));
  const out = await run(r, step());
  assert.equal(out.outcome, "failed");
  const failed = out as Extract<ApiHandOutcome, { outcome: "failed" }>;
  assert.equal(failed.error.kind, "auth");
  assert.equal(failed.error.status, 401);
  assert.equal(failed.error.token, "TokenExpired");
  assert.equal(failed.mayHaveLanded, false);
});

await check("…a 200 with a prose error and no status is `other`: the kind is never guessed from words", async () => {
  const r = await rig([row()], vendor({
    execute: { status: 200, body: { data: null, error: "Unauthorized: token expired, please re-authenticate", successful: false } },
  }));
  const out = await run(r, step());
  assert.equal(out.outcome, "failed");
  const failed = out as Extract<ApiHandOutcome, { outcome: "failed" }>;
  assert.equal(failed.error.kind, "other", "a word in a message decided the kind");
  assert.equal(failed.error.status, 0);
  assert.equal(failed.mayHaveLanded, true);
});

await check("…a 200 that says NOTHING is not a success", async () => {
  for (const body of [{}, { successful: null }, { data: "a string", error: null }, { log_id: "only" }, "not an object", null]) {
    const r = await rig([row()], vendor({ execute: { status: 200, body } }));
    const out = await run(r, step());
    assert.equal(out.outcome, "failed", `${JSON.stringify(body)} was read as the tool having run`);
    const failed = out as Extract<ApiHandOutcome, { outcome: "failed" }>;
    assert.equal(failed.error.kind, "other");
    assert.equal(failed.mayHaveLanded, true, "the request went out; the outcome is unknown, not 'nothing happened'");
  }
});

await check("…a 200 with `successful: true` and no data is a run with null data; a data object without `successful` is a run too", async () => {
  const a = await rig([row()], vendor({ execute: { status: 200, body: { successful: true, error: null } } }));
  const outA = await run(a, step());
  assert.equal(outA.outcome, "ran");
  assert.equal((outA as { data: unknown }).data, null);
  const b = await rig([row()], vendor({ execute: { status: 200, body: { data: { items: [] } } } }));
  const outB = await run(b, step());
  assert.equal(outB.outcome, "ran");
  assert.deepEqual((outB as { data: unknown }).data, { items: [] });
});

// ===========================================================================
// 4. THE LOG NEVER CARRIES THE ARGUMENTS.
// ===========================================================================

await check("every outcome is logged with owner, toolkit, tool and reason — and never an argument value", async () => {
  const sentinel = ARGS.note;
  const runs: Array<[Rig, ApiHandStep, string]> = [
    [await rig([]), step(), "not_connected"],
    [await rig([row()]), step({ tool: "ZELLIBRIX_MADE_UP" }), "tool_unknown"],
    [await rig([row()]), step({ tool: CREATE_TOOL, effect: "write" }), "writes_not_enabled"],
    [await rig([row()]), step(), "ran"],
    [await rig([row()], vendor({ execute: { status: 500, body: {} } })), step(), "failed"],
  ];
  for (const [r, s, expect] of runs) {
    const { value, lines } = await logged(() => run(r, s));
    assert.equal(lines.length, 1, `${expect}: one log line, got ${lines.length}`);
    const line = lines[0]!;
    assert.ok(line.startsWith("api hand: "), line);
    assert.ok(line.includes(OWNER) && line.includes(APP) && line.includes(s.tool.trim()), line);
    assert.ok(line.includes(expect), `${line} does not name ${expect}`);
    assert.ok(!line.includes(sentinel), `an argument value reached the log: ${line}`);
    assert.ok(!line.includes("t_42"), `an argument value reached the log: ${line}`);
    assert.ok(!JSON.stringify(value).includes(sentinel) || value.outcome === "ran" && false,
      "an argument value reached the outcome's detail");
    assert.ok(!line.includes(KEY), "the key reached the log");
  }
  // CONTROL: the sentinel WAS on the wire, so its absence from the log is a
  // redaction and not an argument that never existed.
  const r = await rig([row()]);
  await run(r, step());
  assert.equal(r.calls.find(isExecute)!.body.arguments.note, sentinel);
});

// ===========================================================================
// 5. THE ADAPTER'S TWO NEW METHODS, ON THEIR OWN.
// ===========================================================================

function adapter(handler: (call: Recorded, n: number) => Reply, apiKey: string | null = KEY) {
  const f = fakeFetch(handler);
  return { calls: f.calls, p: new ComposioConnections({ apiKey, fetchImpl: f.impl }) };
}

async function refusalOf(fn: () => Promise<unknown>): Promise<Error> {
  try { await fn(); } catch (err) { return err as Error; }
  throw new Error("expected a refusal, got a value");
}

await check("tools(): asks the vendor with the toolkit slug and the page size, reads every field, keeps the vendor's order", async () => {
  const { calls, p } = adapter(() => ({ status: 200, body: { items: CATALOG, next_cursor: null, total_items: 5 } }));
  const tools = await p.tools(" Zellibrix ");
  assert.equal(calls.length, 1);
  assert.equal(calls[0]!.path, `/tools?toolkit_slug=${APP}&limit=${TOOLS_PAGE_LIMIT}`);
  assert.equal(calls[0]!.headers["x-api-key"], KEY);
  assert.deepEqual(tools.map((t) => t.slug), CATALOG.map((t) => t.slug));
  const t = tools[0]!;
  assert.equal(t.toolkit, APP);
  assert.equal(t.name, "zellibrix find thing");
  assert.equal(t.description, `does the ${READ_TOOL} thing`);
  assert.deepEqual([...t.tags], [READ_ONLY_HINT, "idempotentHint", "openWorldHint"]);
  assert.deepEqual([...t.scopes], ["https://scopes.example/auth/thing"]);
  assert.deepEqual(t.inputParameters, { type: "object", properties: { thing_id: { type: "string" } } });
  assert.equal(t.deprecated, false, "`deprecated` is an OBJECT on the live row and would be truthy for every tool");
});

await check("tools(): `is_deprecated` is the boolean, read at the root or inside the `deprecated` object", async () => {
  const { p } = adapter(() => ({ status: 200, body: { items: [
    toolRow("Z_A", [], { is_deprecated: true }),
    toolRow("Z_B", [], { is_deprecated: undefined, deprecated: { is_deprecated: true } }),
    toolRow("Z_C", [], { is_deprecated: undefined, deprecated: "yes" }),
  ], next_cursor: null } }));
  const tools = await p.tools(APP);
  assert.deepEqual(tools.map((t) => t.deprecated), [true, true, false]);
});

await check("tools(): walks next_cursor and returns every page in order", async () => {
  const { calls, p } = adapter((call) => call.path.includes("cursor=")
    ? { status: 200, body: { items: [toolRow("Z_PAGE2", [])], next_cursor: null } }
    : { status: 200, body: { items: [toolRow("Z_PAGE1", [])], next_cursor: "c2 x" } });
  const tools = await p.tools(APP);
  assert.deepEqual(tools.map((t) => t.slug), ["Z_PAGE1", "Z_PAGE2"]);
  assert.equal(calls.length, 2);
  assert.equal(calls[1]!.path, `/tools?toolkit_slug=${APP}&limit=${TOOLS_PAGE_LIMIT}&cursor=c2%20x`);
});

await check("tools(): a catalog that never ends is refused, not cut short", async () => {
  const { calls, p } = adapter((_, n) => ({ status: 200, body: { items: [toolRow(`Z_${n}`, [])], next_cursor: `c${n + 1}` } }));
  const err = await refusalOf(() => p.tools(APP));
  assert.equal(err.name, "ConnectionsResponseShape");
  assert.match(err.message, /had not ended/);
  assert.equal(calls.length, MAX_TOOL_PAGES);
});

await check("tools(): the vendor's own empty list is an answer", async () => {
  const { p } = adapter(() => ({ status: 200, body: { items: [], next_cursor: null, total_items: 0 } }));
  assert.deepEqual(await p.tools(APP), []);
});

await check("tools(): a row naming another toolkit refuses the whole call — the filter did not hold", async () => {
  const { p } = adapter(() => ({ status: 200, body: { items: [
    toolRow("Z_OK", []),
    toolRow("Q_STRAY", [], { toolkit: { slug: "quandle_mail" } }),
  ], next_cursor: null } }));
  const err = await refusalOf(() => p.tools(APP));
  assert.equal(err.name, "ConnectionsResponseShape");
  assert.match(err.message, /different toolkit/);
});

await check("tools(): one unreadable row is dropped; a page where nothing is readable refuses", async () => {
  const { p } = adapter(() => ({ status: 200, body: { items: [toolRow("Z_OK", []), { name: "no slug" }, null], next_cursor: null } }));
  assert.deepEqual((await p.tools(APP)).map((t) => t.slug), ["Z_OK"]);
  const { p: q } = adapter(() => ({ status: 200, body: { items: [{ name: "no slug" }, { slug: "Z_NO_TOOLKIT" }], next_cursor: null } }));
  const err = await refusalOf(() => q.tools(APP));
  assert.equal(err.name, "ConnectionsResponseShape");
  assert.match(err.message, /2 of 2 catalog tool rows/);
});

await check("tools(): no items array, a non-2xx, no key, a dead network — all refuse by name, none is []", async () => {
  const cases: Array<[string, () => Reply, string | null, string]> = [
    ["no items", () => ({ status: 200, body: { tools: [] } }), KEY, "ConnectionsResponseShape"],
    ["a 503", () => ({ status: 503, body: { error: { slug: "down" } } }), KEY, "ConnectionsRequestFailed"],
    ["no key", () => ({ status: 200, body: { items: [] } }), null, "ConnectionsUnconfigured"],
    ["a dead network", () => ({ throws: new TypeError("fetch failed") }), KEY, "ConnectionsRequestFailed"],
  ];
  for (const [what, handler, key, name] of cases) {
    const { calls, p } = adapter(handler, key);
    const err = await refusalOf(() => p.tools(APP));
    assert.equal(err.name, name, what);
    if (key === null) assert.equal(calls.length, 0, "no key, yet a request went out");
  }
  const { p } = adapter(() => ({ status: 200, body: { items: [] } }));
  const err = await refusalOf(() => p.tools("  "));
  assert.equal(err.name, "ConnectionsBadArgument");
});

await check("execute(): the owner is validated before a byte leaves", async () => {
  for (const owner of ["omar", "jose@anticipy.ai", "", "QEUY6SV1RAOF9RW"]) {
    const { calls, p } = adapter(() => ({ status: 200, body: { successful: true } }));
    const err = await refusalOf(() => p.execute(owner as OwnerId, READ_TOOL, {}));
    assert.equal(err.name, "ConnectionsOwnerRequired", owner);
    assert.equal(calls.length, 0, `${JSON.stringify(owner)} reached the vendor`);
    if (owner.trim()) assert.ok(!err.message.includes(owner.trim()), "the value was echoed");
  }
});

await check("execute(): the body is {user_id, arguments[, connected_account_id]} and the slug is the path", async () => {
  const { calls, p } = adapter(() => ({ status: 200, body: { data: { n: 1 }, successful: true, log_id: "lg" } }));
  const receipt = await p.execute(OWNER, READ_TOOL, { a: 1 });
  assert.deepEqual(receipt, { data: { n: 1 }, logId: "lg" });
  assert.equal(calls[0]!.method, "POST");
  assert.equal(calls[0]!.path, `/tools/execute/${READ_TOOL}`);
  assert.deepEqual(calls[0]!.body, { user_id: OWNER, arguments: { a: 1 } });
  await p.execute(OWNER, "Z/WEIRD SLUG".replace(" ", "_"), {}, ACCOUNT);
  assert.equal(calls[1]!.path, "/tools/execute/Z%2FWEIRD_SLUG", "the slug is percent-encoded into the path");
  assert.equal(calls[1]!.body.connected_account_id, ACCOUNT);
});

await check("execute(): arguments must be an object; a blank or sentence slug refuses; no request either way", async () => {
  const { calls, p } = adapter(() => ({ status: 200, body: { successful: true } }));
  for (const args of ["find my thing", null, undefined, 3, ["x"]] as unknown[]) {
    const err = await refusalOf(() => p.execute(OWNER, READ_TOOL, args as never));
    assert.equal(err.name, "ConnectionsBadArgument");
  }
  for (const slug of ["", "  ", "find the thing"]) {
    const err = await refusalOf(() => p.execute(OWNER, slug, {}));
    assert.equal(err.name, "ConnectionsBadArgument");
  }
  assert.equal(calls.length, 0);
});

await check("execute(): no key -> ConnectionsUnconfigured and no request", async () => {
  const { calls, p } = adapter(() => ({ status: 200, body: { successful: true } }), null);
  const err = await refusalOf(() => p.execute(OWNER, READ_TOOL, {}));
  assert.equal(err.name, "ConnectionsUnconfigured");
  assert.equal(calls.length, 0);
});

await check("execute(): a non-2xx is ConnectionsExecuteFailed carrying status, token, kind and retryable", async () => {
  const { p } = adapter(() => ({ status: 404, body: { error: { slug: EXECUTE_NO_ACCOUNT_TOKEN, code: 1810, status: 404, message: "No connected account found for user ID qeuy6sv1raof9rw" } } }));
  const err = await refusalOf(() => p.execute(OWNER, READ_TOOL, {})) as Error & { status: number; token: string; kind: string; retryable: boolean; code: string };
  assert.equal(err.name, "ConnectionsExecuteFailed");
  assert.equal(err.status, 404);
  assert.equal(err.token, EXECUTE_NO_ACCOUNT_TOKEN);
  assert.equal(err.kind, "auth");
  assert.equal(err.retryable, false);
  assert.equal(err.code, "connections_request_failed", "it is a ConnectionsRequestFailed to every existing catch");
  assert.ok(!err.message.includes("No connected account found"), "the vendor's prose message, which quotes the request, reached the error");
});

await check("execute(): the key never appears in an error, even when the vendor quotes it back", async () => {
  const { p } = adapter(() => ({ status: 400, body: { error: { slug: `bad-${KEY}` } } }));
  const err = await refusalOf(() => p.execute(OWNER, READ_TOOL, {}));
  assert.ok(!err.message.includes(KEY), err.message);
  assert.ok(err.message.includes("[redacted]"));
});

// ===========================================================================
// 6. THE SOURCE LEGS. Two things a behaviour test cannot see: an app name in
//    the code, and a second road to execute() that skips the floors.
// ===========================================================================

/** Comments out, code and string literals in. Same shape as the stripper in
 *  test/connections-provider.test.ts, with the same three controls. */
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
        if (s === "\\") { if (i < src.length) { out += src[i]; i++; } continue; }
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
        if (s === "\\") { if (i < src.length) { out += src[i]; i++; } continue; }
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

/** The same list the provider test keeps, plus the invented ones. A word list
 *  in a TEST is where law 1 puts one. */
const APP_NAMES = [
  "gmail", "googlecalendar", "googledrive", "google_drive", "outlook", "notion",
  "slack", "dropbox", "salesforce", "github", "gitlab", "linear", "asana",
  "trello", "hubspot", "shopify", "zoom", "jira", "confluence", "calendly",
  "airtable", "discord", "telegram", "whatsapp", "spotify", "figma", "clickup",
  "monday", "intercom", "zendesk", "quickbooks", "mailchimp", "sendgrid",
  "zellibrix", "quandle", "quandle_mail",
];
function namesIn(code: string): string[] {
  return APP_NAMES.filter((name) => new RegExp(`(^|[^a-z0-9_])${name}($|[^a-z0-9_])`, "i").test(code));
}

await check("the stripper removes prose, keeps code, and the scan is not vacuous", () => {
  const stripped = codeOnly(HAND_SOURCE);
  const PROSE = "a log line is the one place in a server";
  assert.ok(HAND_SOURCE.includes(PROSE), "the header sentence this control is anchored on moved");
  assert.ok(!stripped.includes(PROSE), "the stripper left comments in");
  assert.ok(stripped.includes('"writes_not_enabled"'), "the stripper ate a string literal");
  assert.ok(stripped.includes("tightenSideEffect"), "the stripper ate code");
  assert.deepEqual(namesIn('if (slug === "gmail") return GMAIL_META;'), ["gmail"]);
  assert.deepEqual(namesIn("// a comment about gmail is fine"), ["gmail"]);
  // CONTROL 3 — the scan sees prose when prose names an app: the adapter's
  // header carries the measured receipt and names real apps in it. The hand's
  // own header names none, so it is the neighbour that proves the scan looks.
  assert.ok(namesIn(PROVIDER_SOURCE).length > 0, "the control that the scan sees prose is vacuous");
  assert.deepEqual(namesIn(codeOnly(PROVIDER_SOURCE)), [],
    "provider.ts's new code names an app; the provider suite's own leg would also go red");
});

await check("NO APP IS NAMED in api_hand.ts's executable source", () => {
  const found = namesIn(codeOnly(HAND_SOURCE));
  assert.deepEqual(found, [], `src/connections/api_hand.ts names ${found.join(", ")} in code`);
});

await check("api_hand.ts calls provider.execute EXACTLY ONCE, after tools(), after reading writes_enabled", () => {
  const code = codeOnly(HAND_SOURCE);
  const executes = code.match(/\.execute\(/g) ?? [];
  assert.equal(executes.length, 1, "a second road to execute() is a road around the floors");
  const executeAt = code.indexOf(".execute(");
  const toolsAt = code.indexOf(".tools(");
  const writesAt = code.indexOf("writes_enabled");
  assert.ok(toolsAt > -1 && toolsAt < executeAt, "the catalog must be read before execute is reached");
  assert.ok(writesAt > -1 && writesAt < executeAt, "the write opt-in must be read before execute is reached");
  assert.equal((code.match(/writes_enabled !== true/g) ?? []).length, 2,
    "the opt-in is checked twice: on the declared effect and again on the tightened one");
});

await check("this suite is in package.json's test script, before the end-to-end leg", () => {
  const packageJson = readFileSync(join(here, "..", "package.json"), "utf8");
  const script = /"test":\s*"([^"]*)"/.exec(packageJson)?.[1] ?? "";
  assert.ok(script.includes("test/connections-api-hand.test.ts"),
    "connections-api-hand is not in CI. Five suites were written and left out this week");
  assert.ok(script.indexOf("test/connections-api-hand.test.ts") < script.indexOf("test/connections-endtoend.test.ts"),
    "the end-to-end suite asserts it runs LAST; this one must come before it");
});

await check("NOTHING ELSE in the Worker calls execute(): the floors are the only road", () => {
  const root = join(here, "..", "src");
  const files: string[] = [];
  const walk = (dir: string) => {
    for (const name of readdirSync(dir)) {
      const full = join(dir, name);
      if (statSync(full).isDirectory()) walk(full);
      else if (full.endsWith(".ts")) files.push(full);
    }
  };
  walk(root);
  const callers = files.filter((f) => !f.endsWith("api_hand.ts") && /\.execute\(/.test(codeOnly(readFileSync(f, "utf8"))));
  assert.deepEqual(callers.map((f) => f.slice(root.length + 1)), [],
    "a file other than api_hand.ts calls .execute( — the floors are bypassed");
  assert.ok(files.length > 10, "the walk found the Worker sources");
});

// ===========================================================================
// MUTATIONS RUN AGAINST src/connections/api_hand.ts AND provider.ts, 2026-09-06.
//
// Each anchored on a literal occurring EXACTLY ONCE in its file — the runner
// refuses to patch otherwise, because a regex that silently fails to match
// produces a false "it is tested" reading. ALL EIGHTEEN WENT RED, and the file
// was restored byte-for-byte after each (from memory, never git); the suite
// was green again after the last restore.
//
//   1  hand  `if (declared !== "read" && row.writes_enabled !== true)` -> `if (false && …)`
//            [first opt-in check gone]           -> 4 red, incl. "a write … writes_enabled false"
//   2  hand  `if (effect !== "read" && row.writes_enabled !== true)` -> `if (false && …)`
//            [tightened re-check gone]           -> "a declared READ on … createHint …" + updateHint
//   3  hand  `catalog.find(…)` -> `… ?? ({ slug: toolAsked, tags: [] } as never)`
//            [unknown slug waved through]        -> 5 red, incl. "refused tool_unknown"
//   4  hand  `const connected = onApp.filter((r) => r.status === "connected");` -> `= onApp;`
//            [needs_reconnect is connected]      -> the needs_reconnect and disconnected legs
//   5  hand  `if (wanted.length === 1)` -> `>= 1`  [two accounts: first wins]
//                                                  -> "account_ambiguous"
//   6  hand  `if (tag === DESTRUCTIVE_HINT) return "irreversible";` -> `"write"`
//                                                  -> 3 red, incl. "destructiveHint tool is irreversible"
//   7  hand  `if (effect === "irreversible" && step.confirmed !== true)` -> `if (false)`
//                                                  -> "…still refused without confirmation"
//   8  prov  `user_id: owner,` -> `user_id: "omar",` -> the CONTROL and "execute(): the body is …"
//   9  prov  `if (root.successful === false || errorPresent)` -> `if (false)`
//                                                  -> "a 200 that says the tool failed is a failure"
//  10  prov  `if (root.successful !== true && asRecord(root.data) === null)` -> `if (false)`
//                                                  -> "a 200 that says NOTHING is not a success"
//  11  hand  the not_connected refusal's detail + `JSON.stringify(step.args)`
//                                                  -> "every outcome is logged … never an argument value"
//  12  hand  after `rows = await store.connectionsForOwner(owner);` an empty answer is
//            refilled from the STRANGER's rows re-stamped with our owner
//                                                  -> "a STRANGER's connected row … licenses nothing"
//  13  hand  `const effect = tightenSideEffect(declared, sideEffectHint(tool.tags));` -> `= declared;`
//                                                  -> 4 red: every tightening leg
//  14  hand  `provider.execute(…)` -> `.catch(() => provider.execute(…))`  [one retry]
//                                                  -> 11 red: every "exactly one execute" leg
//  15  prov  `if (account !== null) body.connected_account_id = account;` deleted
//                                                  -> "alias 'work' … that id goes on the wire" + CONTROL
//  16  hand  `if (!isEffect(step.effect))` also lets undefined/null/"" through as a read
//                                                  -> "a step with no declared effect is refused"
//  17  prov  the MAX_TOOL_PAGES refusal -> `if (false)`  [catalog silently cut]
//                                                  -> "a catalog that never ends is refused"
//  18  prov  `if (tool.toolkit !== asked)` -> `if (false)`  [foreign toolkit row adopted]
//                                                  -> "a row naming another toolkit refuses"
// ===========================================================================

console.log(`connections-api-hand: ${passes} checks passed, ${failures} failed`);
if (failures > 0) process.exit(1);
