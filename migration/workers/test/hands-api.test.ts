/**
 * THE LAST WIRE — POST /hands/api/run joins the router's verdict to the API
 * hand, and this file is what holds the join down.
 *
 *   node --experimental-strip-types migration/workers/test/hands-api.test.ts
 *
 * Every check runs with no network and no real account: a real Request, the
 * real handler, the real SQL over the real migration/d1/schema.sql (test/
 * fake-d1.ts), the real connections store, and — for the two checks that
 * prove the join end to end — the REAL `runStep` over a recording vendor
 * transport. The hand is scripted everywhere else, because api_hand.ts has its
 * own 1250 checks and this file is about what the route does with an answer.
 *
 * ORDER: hardest first. The token before any read, then "the body never names
 * who", then the two refusals that keep an unclaimed or mis-laned row from
 * running, then each branch of the outcome table with its CONTROL, then the
 * row-shape invariants the brain's own parser and the workflow guard would
 * otherwise refuse, then the source legs.
 *
 * MUTATIONS THIS FILE MUST GO RED ON:
 *   * the token check moves after the row read (the 401 leg reads the D1 log);
 *   * the body's owner is believed instead of checked;
 *   * a queued or browser-claimed row runs;
 *   * the step's owner or toolkit is taken from the body;
 *   * confirmation_required is handed to the browser (it would run unattended);
 *   * a write that may have landed is re-queued anywhere;
 *   * an auth failure stops marking the connection, or marks a stranger's;
 *   * a resting row keeps its lease, or a non-succeeded row keeps a receipt;
 *   * src/index.ts dispatches the path zero or two times (the mutation literal);
 *   * the route names an app.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import type { OwnerId } from "../../../spike/two-hands/src/connections/contract.ts";
import {
  API_CLAIMANT,
  API_LANE,
  BROWSER_LANE,
  HANDS_API_RUN_PATH,
  MAX_ATTEMPTS,
  RESULT_MAX,
  approvedForCurrentVersion,
  canonical,
  dispose,
  handsApiRun,
  settleWorkflow,
  stepFromRow,
  type HandsApiDeps,
  type HandsApiEnv,
} from "../src/routes/hands_api.ts";
import type { ApiHandOutcome, ApiHandRefusal, ApiHandStep } from "../src/connections/api_hand.ts";
import { COMPOSIO_BASE_URL, ComposioConnections } from "../src/connections/provider.ts";
import { createD1Store, forgetLiveColumns, type StoredConnection } from "../src/connections/store.ts";
import { webhookStore } from "../src/routes/connections_webhook.ts";
import { FakeD1, asD1 } from "./fake-d1.ts";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(here, "..", "..", "..");
const ROUTE_SOURCE = readFileSync(join(here, "..", "src", "routes", "hands_api.ts"), "utf8");
const INDEX_SOURCE = readFileSync(join(here, "..", "src", "index.ts"), "utf8");
const BRAIN_HANDS = readFileSync(join(repoRoot, "brain", "hands.py"), "utf8");
const BRAIN_WORKER = readFileSync(join(repoRoot, "brain", "worker.py"), "utf8");
const BRAIN_WORKFLOW = readFileSync(join(repoRoot, "brain", "workflow.py"), "utf8");
const GUARD_SOURCE = readFileSync(join(here, "..", "src", "policy", "workflow_guard.ts"), "utf8");

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

/** Silence the route's own log lines during `fn`; return them. */
async function quiet<T>(fn: () => Promise<T>): Promise<{ value: T; lines: string[] }> {
  const lines: string[] = [];
  const original = console.log;
  console.log = (...args: unknown[]) => { lines.push(args.map(String).join(" ")); };
  try {
    return { value: await fn(), lines };
  } finally {
    console.log = original;
  }
}

// ---------------------------------------------------------------------------
// FIXTURES. The toolkit is invented; the owners are the two the hand's own
// suite uses, because a floor that only ever sees one owner cannot be shown to
// scope by owner.
// ---------------------------------------------------------------------------

const OWNER = "qeuy6sv1raof9rw" as OwnerId;
const STRANGER = "sxkotd1h02qb6gw" as OwnerId;
const TOKEN = "hands-api-test-service-token-0001";
const KEY = "comp_test_supersecret_key_1234567890";
const APP = "zellibrix";
const READ_TOOL = "ZELLIBRIX_FIND_THING";
const ARGS = { thing_id: "t_42" };
const JOB = "jobapi000000001";
const LEASE = "lease-token-api-1";
const NOW = "2026-09-06 20:00:00.000Z";
const ACCOUNT = "ca_zell_owner_0001";

function plan(over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    plan_id: "wf-api-0001", owner_ref: OWNER, lineage_key: "lineage-a", version: 1,
    goal: "what did Dana send me this week", authority_text: "", consequence: "read_only",
    state: "running", scope_digest: "scope-digest-1", effect_key: "effect-key-1",
    facts: {}, required: [], source_event_ids: [], approval: null,
    lease: { token: LEASE, actor_id: API_CLAIMANT, acquired_at: "2026-09-06T19:59:00+00:00",
             expires_at: "2026-09-06T20:09:00+00:00", attempt: 1 },
    receipt: null, attempts: 1, reason: "claimed",
    created_at: "2026-09-06T19:58:00+00:00", updated_at: "2026-09-06T19:59:00+00:00",
    act: null, undo: null, announce: null, undo_of: null, lineage_seq: 0,
    ...over,
  };
}

function note(over: Record<string, unknown> = {}): Record<string, unknown> {
  return { hand: "api", reason: "his mail app is connected", app: APP, effect: "read",
           asked: 1, lane: API_LANE, tool: READ_TOOL, args: { ...ARGS }, ...over };
}

interface JobSeed {
  id?: string; owner_ref?: string; status?: string; lane?: string; claimed_by?: string;
  attempts?: number; workflow?: Record<string, unknown> | null; note?: Record<string, unknown>;
  extraParams?: Record<string, unknown>;
}

function seedJob(db: FakeD1, s: JobSeed = {}): string {
  const id = s.id ?? JOB;
  const wf = s.workflow === undefined ? plan() : s.workflow;
  const params: Record<string, unknown> = { source: "test", ...(s.extraParams ?? {}), _hand: s.note ?? note() };
  if (wf) params._workflow = wf;
  db.db.prepare(
    `INSERT INTO jobs (id, created, updated, goal, params, status, owner_ref, lane, claimed_by,
       claimed_at, attempts, workflow_id, workflow_version, workflow_state, consequence,
       lineage_key, effect_key, scope_digest, lease_token, lease_until, device_id)
     VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'anticipy')`,
  ).run(
    id, NOW, NOW, String(wf?.goal ?? "what did Dana send me this week"), JSON.stringify(params),
    s.status ?? "running", s.owner_ref ?? OWNER, s.lane ?? API_LANE, s.claimed_by ?? API_CLAIMANT,
    NOW, s.attempts ?? 1, wf ? String(wf.plan_id) : "", wf ? 1 : 0, wf ? String(wf.state) : "",
    wf ? String(wf.consequence) : "", wf ? String(wf.lineage_key) : "", wf ? String(wf.effect_key) : "",
    wf ? String(wf.scope_digest) : "", wf ? LEASE : "", wf ? NOW : "",
  );
  return id;
}

interface Row {
  status: string; lane: string; result: string; params: string; claimed_by: string;
  claimed_at: string; lease_token: string; lease_until: string; workflow_state: string;
  receipt: string; effect_uncertain: number; updated: string;
}
function readJob(db: FakeD1, id = JOB): Row & { p: Record<string, any> } {
  const row = db.rows<Row>(`SELECT * FROM jobs WHERE id = ?`, id)[0];
  assert.ok(row, "the job row vanished");
  return { ...row, p: JSON.parse(row.params) };
}

interface Rig {
  db: FakeD1;
  env: HandsApiEnv;
  store: ReturnType<typeof createD1Store>;
}
function rig(token: string | null = TOKEN): Rig {
  const db = new FakeD1();
  const env = { DB: asD1(db), COMPOSIO_API_KEY: KEY,
                ...(token === null ? {} : { ANTICIPY_SERVICE_TOKEN: token }) } as unknown as HandsApiEnv;
  forgetLiveColumns(env);
  return { db, env, store: createD1Store(env) };
}

function post(body: unknown, token: string | null = TOKEN, method = "POST"): Request {
  const headers: Record<string, string> = { "content-type": "application/json" };
  if (token !== null) headers["X-Anticipy-Token"] = token;
  return new Request("https://api.anticipy.ai" + HANDS_API_RUN_PATH, {
    method, headers, body: method === "POST" ? (typeof body === "string" ? body : JSON.stringify(body)) : undefined,
  });
}

/** A scripted hand: records every step it was handed, answers `outcome`. */
function scripted(outcome: ApiHandOutcome | ((step: ApiHandStep) => ApiHandOutcome)) {
  const seen: ApiHandStep[] = [];
  const hand: NonNullable<HandsApiDeps["hand"]> = async (_env, step) => {
    seen.push(step);
    return typeof outcome === "function" ? outcome(step) : outcome;
  };
  return { seen, hand };
}

const ran = (over: Record<string, unknown> = {}): ApiHandOutcome => ({
  outcome: "ran", toolkit: APP as never, tool: READ_TOOL, account: ACCOUNT, effect: "read",
  data: { items: [{ id: "m1", subject: "the form" }] }, logId: "log_777", ms: 41, ...over,
} as ApiHandOutcome);
const refused = (reason: ApiHandRefusal): ApiHandOutcome => ({
  outcome: "refused", reason, detail: "scripted", effect: "read", catalogRead: false,
});
const failed = (kind: "auth" | "rate" | "schema" | "other", over: Record<string, unknown> = {}): ApiHandOutcome => ({
  outcome: "failed", toolkit: APP as never, tool: READ_TOOL, account: ACCOUNT, effect: "read",
  error: { kind, status: kind === "auth" ? 401 : kind === "rate" ? 429 : kind === "schema" ? 400 : 502,
           token: kind === "auth" ? "Unauthorized" : "", retryable: kind === "rate", message: "scripted" },
  mayHaveLanded: kind === "other", ms: 12, ...over,
} as ApiHandOutcome);

async function run(r: Rig, deps: HandsApiDeps, body: unknown = { job: JOB, owner: OWNER }, token: string | null = TOKEN) {
  const { value, lines } = await quiet(() => handsApiRun(post(body, token), r.env, deps));
  const text = await value.text();
  let parsed: any = null;
  try { parsed = JSON.parse(text); } catch { parsed = null; }
  return { status: value.status, body: parsed, text, lines, headers: value.headers };
}

/** brain/workflow.py STATE_FOR_STATUS twin, read off the guard's own source so
 *  the invariant this file checks is the one production enforces. */
const STATE_FOR_STATUS: Record<string, string[]> = (() => {
  const m = GUARD_SOURCE.match(/const STATE_FOR_STATUS: Record<string, string\[\]> = \{([\s\S]*?)\};/);
  assert.ok(m, "workflow_guard.ts no longer declares STATE_FOR_STATUS");
  const out: Record<string, string[]> = {};
  for (const [, status, states] of m[1]!.matchAll(/(\w+): \[([^\]]*)\]/g)) {
    out[status!] = states!.split(",").map((s) => s.trim().replace(/"/g, "")).filter(Boolean);
  }
  return out;
})();

/** The invariants brain/workflow.py Plan.assert_valid and the guard hold over
 *  a stored row; every written row below passes through here. */
function assertConsistent(row: ReturnType<typeof readJob>): void {
  const wf = row.p._workflow;
  if (wf) {
    assert.ok(STATE_FOR_STATUS[row.status]?.includes(row.workflow_state),
      `status ${row.status} disagrees with workflow_state ${row.workflow_state}`);
    assert.equal(wf.state, row.workflow_state, "embedded state disagrees with the column");
    if (wf.state === "running") assert.ok(wf.lease, "running work must have a lease");
    else assert.equal(wf.lease, null, "only running work may retain a lease");
    if (wf.state === "succeeded") {
      assert.ok(wf.receipt && wf.receipt.verified === true, "success requires a verified receipt");
      assert.equal(wf.receipt.effect_key, wf.effect_key, "receipt belongs to a different plan version");
      assert.equal(row.receipt, canonical(wf.receipt), "the receipt column disagrees with the embedded one");
    } else {
      assert.equal(wf.receipt, null, "only successful work may carry a final receipt");
      assert.equal(row.receipt, "");
    }
    assert.equal(row.lease_token, wf.lease ? wf.lease.token : "", "the lease column disagrees with the plan");
  }
  if (row.status !== "running") {
    assert.equal(row.lease_token, "", "non-running work may not retain an execution lease");
    assert.equal(row.lease_until, "");
  }
  if (row.lane === BROWSER_LANE) {
    assert.equal(row.claimed_by, "", "a handed-back row must be claimable by the browser");
    assert.equal(row.status, "queued");
  }
  assert.equal(row.p._hand.lane, row.lane, "the verdict's lane disagrees with the row's");
}

// ===========================================================================
// 1. THE TOKEN, BEFORE ANY READ.
// ===========================================================================

await check("no token is 401 and the database was never asked", async () => {
  const r = rig();
  seedJob(r.db);
  const { hand, seen } = scripted(ran());
  const out = await run(r, { hand }, { job: JOB }, null);
  assert.equal(out.status, 401);
  assert.equal(out.body?.ok, false);
  assert.deepEqual(r.db.log, [], "a read happened before the token was checked");
  assert.equal(seen.length, 0);
});

await check("a wrong token is 401, the same answer, and no read", async () => {
  const r = rig();
  seedJob(r.db);
  const { hand, seen } = scripted(ran());
  const out = await run(r, { hand }, { job: JOB }, TOKEN.slice(0, -1) + "X");
  assert.equal(out.status, 401);
  assert.deepEqual(r.db.log, []);
  assert.equal(seen.length, 0);
});

await check("a Worker with no token configured opens for nobody", async () => {
  const r = rig(null);
  seedJob(r.db);
  const { hand } = scripted(ran());
  assert.equal((await run(r, { hand }, { job: JOB }, TOKEN)).status, 401);
  assert.equal((await run(r, { hand }, { job: JOB }, "")).status, 401);
  assert.deepEqual(r.db.log, []);
});

await check("THE CONTROL: the right token gets past the door (404 for an id nobody minted)", async () => {
  const r = rig();
  const { hand } = scripted(ran());
  const out = await run(r, { hand }, { job: "nosuchjob000001" });
  assert.equal(out.status, 404);
  assert.equal(out.body?.ok, false);
  assert.ok(r.db.log.some((sql) => /FROM "jobs"/.test(sql)), "the row was never looked for");
});

await check("the wrong verb is 405 with Allow, never the router's 404", async () => {
  const r = rig();
  const resp = await handsApiRun(post(null, TOKEN, "GET"), r.env, scripted(ran()));
  assert.equal(resp.status, 405);
  assert.equal(resp.headers.get("allow"), "POST");
});

await check("a body that is not JSON, not an object, or not an id is 400", async () => {
  const r = rig();
  const { hand, seen } = scripted(ran());
  assert.equal((await run(r, { hand }, "{not json")).status, 400);
  assert.equal((await run(r, { hand }, [JOB])).status, 400);
  assert.equal((await run(r, { hand }, {})).status, 400);
  assert.equal((await run(r, { hand }, { job: "../etc/passwd" })).status, 400);
  assert.equal((await run(r, { hand }, { job: "JOBAPI000000001" })).status, 400);
  assert.equal(seen.length, 0);
});

// ===========================================================================
// 2. THE BODY NEVER NAMES WHO.
// ===========================================================================

await check("an owner in the body that disagrees with the row is refused, and nothing runs", async () => {
  const r = rig();
  seedJob(r.db);
  const { hand, seen } = scripted(ran());
  const out = await run(r, { hand }, { job: JOB, owner: STRANGER });
  assert.equal(out.status, 403);
  assert.equal(out.body?.ok, false);
  assert.ok(!out.text.includes(OWNER), "the refusal leaked the row's owner");
  assert.equal(seen.length, 0);
  assert.equal(readJob(r.db).status, "running", "the row was touched");
});

await check("THE CONTROL: the matching owner, or no owner at all, runs", async () => {
  for (const body of [{ job: JOB, owner: OWNER }, { job: JOB }]) {
    const r = rig();
    seedJob(r.db);
    const { hand, seen } = scripted(ran());
    const out = await run(r, { hand }, body);
    assert.equal(out.status, 200, out.text);
    assert.equal(seen.length, 1);
  }
});

await check("the step is built from the ROW: a body naming another owner, toolkit or tool is ignored", async () => {
  const r = rig();
  seedJob(r.db);
  const { hand, seen } = scripted(ran());
  const out = await run(r, { hand }, { job: JOB, owner: OWNER, toolkit: "quandle", tool: "QUANDLE_DELETE_ALL",
                                       args: { everything: true }, effect: "read", confirmed: true });
  assert.equal(out.status, 200);
  const step = seen[0]!;
  assert.equal(step.owner, OWNER);
  assert.equal(step.toolkit, APP);
  assert.equal(step.tool, READ_TOOL);
  assert.deepEqual(step.args, ARGS);
  assert.equal(step.effect, "read");
  assert.equal(step.confirmed, false, "a body cannot confirm anything");
  assert.equal(step.alias, null);
});

await check("confirmed is the owner's approval of THIS plan version, read off the row", async () => {
  const approval = { plan_id: "wf-api-0001", plan_version: 1, scope_digest: "scope-digest-1",
                     owner_words: "yes do it", approved_at: "2026-09-06T19:50:00+00:00", gesture: null };
  assert.equal(approvedForCurrentVersion(plan({ approval })), true);
  assert.equal(approvedForCurrentVersion(plan({ approval: { ...approval, plan_version: 2 } })), false, "a stale version");
  assert.equal(approvedForCurrentVersion(plan({ approval: { ...approval, scope_digest: "other" } })), false, "another scope");
  assert.equal(approvedForCurrentVersion(plan({ approval: { ...approval, owner_words: "  " } })), false, "no words, no tap");
  assert.equal(approvedForCurrentVersion(plan({ approval: { ...approval, owner_words: "",
    gesture: { kind: "tap", actor: OWNER, plan_id: "wf-api-0001", plan_version: 1,
               scope_digest: "scope-digest-1", made_at: "2026-09-06T19:50:00+00:00" } } })), true, "a tap counts");
  assert.equal(approvedForCurrentVersion(plan({ approval: null })), false);
  assert.equal(approvedForCurrentVersion(null), false);
  // And it reaches the hand.
  const r = rig();
  seedJob(r.db, { workflow: plan({ approval }) });
  const { hand, seen } = scripted(ran());
  await run(r, { hand });
  assert.equal(seen[0]!.confirmed, true);
});

await check("an alias on the note reaches the hand; an empty one is null", () => {
  assert.equal(stepFromRow({ owner_ref: OWNER }, note({ alias: "work" }), null).alias, "work");
  assert.equal(stepFromRow({ owner_ref: OWNER }, note({ alias: "  " }), null).alias, null);
  assert.equal(stepFromRow({ owner_ref: OWNER }, note(), null).alias, null);
});

// ===========================================================================
// 3. ONLY A CLAIMED, API-LANE ROW RUNS.
// ===========================================================================

await check("a row that is not on the api lane, or whose verdict is not api, is 409 and nothing runs", async () => {
  const shapes: JobSeed[] = [
    { lane: BROWSER_LANE },
    { lane: "research" },
    { note: note({ hand: "browser", lane: BROWSER_LANE }) },
    { note: note({ lane: BROWSER_LANE }) },
    { note: note({ hand: "browser" }) },
  ];
  for (const s of shapes) {
    const r = rig();
    seedJob(r.db, s);
    const { hand, seen } = scripted(ran());
    const out = await run(r, { hand });
    assert.equal(out.status, 409, JSON.stringify(s));
    assert.equal(out.body?.ok, false);
    assert.equal(seen.length, 0, JSON.stringify(s));
    assert.equal(readJob(r.db).status, "running");
  }
});

await check("a row nobody claimed, or a browser claimed, is 409 and nothing runs", async () => {
  const shapes: JobSeed[] = [
    { status: "queued", claimed_by: "" },
    { status: "running", claimed_by: "ext-abc" },
    { status: "queued", claimed_by: API_CLAIMANT },
    { status: "needs_user", claimed_by: API_CLAIMANT },
  ];
  for (const s of shapes) {
    const r = rig();
    seedJob(r.db, s);
    const { hand, seen } = scripted(ran());
    const out = await run(r, { hand });
    assert.equal(out.status, 409, JSON.stringify(s));
    assert.equal(seen.length, 0, JSON.stringify(s));
  }
});

await check("a row that moved while the hand ran is not written over", async () => {
  const r = rig();
  seedJob(r.db);
  const hand: NonNullable<HandsApiDeps["hand"]> = async () => {
    // The stranded-claim sweep took the row back mid-run.
    r.db.db.prepare(`UPDATE jobs SET status='queued', claimed_by='' WHERE id=?`).run(JOB);
    return ran();
  };
  const out = await run(r, { hand });
  assert.equal(out.status, 409);
  const row = readJob(r.db);
  assert.equal(row.status, "queued");
  assert.equal(row.result, "");
});

// ===========================================================================
// 4. THE OUTCOME TABLE, branch by branch, each with its control.
// ===========================================================================

await check("ran -> done: the answer on the row, a verified receipt naming the vendor's log, lease released", async () => {
  const r = rig();
  seedJob(r.db);
  const out = await run(r, scripted(ran()));
  assert.equal(out.status, 200, out.text);
  assert.deepEqual({ outcome: out.body.outcome, status: out.body.status, lane: out.body.lane },
                   { outcome: "ran", status: "done", lane: API_LANE });
  const row = readJob(r.db);
  assert.equal(row.status, "done");
  assert.equal(row.lane, API_LANE);
  assert.ok(row.result.includes('"subject":"the form"'), row.result);
  assert.ok(row.result.startsWith(`Ran ${APP}/${READ_TOOL}`));
  assert.equal(row.workflow_state, "succeeded");
  assert.equal(row.effect_uncertain, 0);
  assert.equal(row.claimed_by, API_CLAIMANT, "who ran it stays on the row");
  const wf = row.p._workflow;
  assert.deepEqual(wf.receipt.evidence, ["vendor-log:log_777"]);
  assert.equal(wf.receipt.effect_key, "effect-key-1");
  assert.equal(wf.reason, "verified complete");
  assert.equal(row.p._hand.outcome.outcome, "ran");
  assert.equal(row.p._hand.outcome.tool, READ_TOOL);
  assert.ok(!("args" in row.p._hand.outcome) && !("data" in row.p._hand.outcome));
  assert.notEqual(row.updated, NOW, "updated was not stamped");
  assertConsistent(row);
});

await check("ran with no vendor log id still cites the run itself", () => {
  const d = dispose(ran({ logId: null }), 1);
  assert.equal(d.state, "succeeded");
  assert.deepEqual(d.evidence, [`vendor-run:${APP}/${READ_TOOL}@${ACCOUNT}`]);
});

await check("a huge vendor reply is bounded in result", () => {
  const d = dispose(ran({ data: { blob: "x".repeat(20_000) } }), 1);
  assert.ok(d.result.length <= RESULT_MAX);
  assert.ok(d.result.endsWith("…"));
});

const HANDBACK_REASONS: ApiHandRefusal[] = [
  "not_connected", "writes_not_enabled", "tool_unknown", "tool_required", "args_required",
  "effect_required", "toolkit_required", "account_ambiguous", "catalog_unavailable",
  "store_unavailable", "unconfigured",
];

await check("every refusal but two hands the job to the browser lane, claim cleared, plan queued", async () => {
  for (const reason of HANDBACK_REASONS) {
    const r = rig();
    seedJob(r.db);
    const out = await run(r, scripted(refused(reason)));
    assert.equal(out.status, 200, `${reason}: ${out.text}`);
    assert.deepEqual({ outcome: out.body.outcome, reason: out.body.reason, status: out.body.status, lane: out.body.lane },
                     { outcome: "refused", reason, status: "queued", lane: BROWSER_LANE }, reason);
    const row = readJob(r.db);
    assert.equal(row.status, "queued", reason);
    assert.equal(row.lane, BROWSER_LANE, reason);
    assert.equal(row.claimed_by, "", reason);
    assert.equal(row.claimed_at, "", reason);
    assert.equal(row.workflow_state, "queued", reason);
    assert.equal(row.p._workflow.state, "queued", reason);
    assert.equal(row.p._workflow.lease, null, reason);
    assert.equal(row.p._hand.hand, "api", "the verdict is history, not rewritten");
    assert.equal(row.p._hand.lane, BROWSER_LANE, reason);
    assert.equal(row.p._hand.outcome.reason, reason);
    assert.ok(row.result.includes(reason), row.result);
    assertConsistent(row);
  }
});

await check("THE CONTROL: confirmation_required PARKS the job for the owner — the browser would run it unattended", async () => {
  const r = rig();
  seedJob(r.db);
  const out = await run(r, scripted(refused("confirmation_required")));
  assert.equal(out.status, 200, out.text);
  assert.equal(out.body.status, "needs_user");
  assert.equal(out.body.lane, API_LANE);
  const row = readJob(r.db);
  assert.equal(row.status, "needs_user");
  assert.equal(row.lane, API_LANE);
  assert.equal(row.workflow_state, "needs_user");
  assert.equal(row.effect_uncertain, 0);
  assert.ok(/go-ahead/.test(row.result), row.result);
  assertConsistent(row);
});

await check("THE CONTROL: owner_required fails the job — no hand may take a row that names nobody", async () => {
  const r = rig();
  seedJob(r.db);
  const out = await run(r, scripted(refused("owner_required")));
  assert.equal(out.body.status, "failed");
  const row = readJob(r.db);
  assert.equal(row.status, "failed");
  assert.equal(row.lane, API_LANE);
  assertConsistent(row);
});

await check("a handback past the attempt cap fails instead of bouncing between hands forever", async () => {
  const r = rig();
  seedJob(r.db, { attempts: MAX_ATTEMPTS, workflow: plan({ attempts: MAX_ATTEMPTS }) });
  const out = await run(r, scripted(refused("not_connected")));
  assert.equal(out.body.status, "failed");
  const row = readJob(r.db);
  assert.equal(row.status, "failed");
  assert.equal(row.lane, API_LANE);
  assert.ok(row.result.includes(`${MAX_ATTEMPTS} times`), row.result);
  assertConsistent(row);
  // And one below the cap still hands back.
  assert.equal(dispose(refused("not_connected"), MAX_ATTEMPTS - 1).state, "queued");
});

await check("a WRITE that may have landed is parked for the owner and NEVER re-queued", async () => {
  for (const effect of ["write", "irreversible"] as const) {
    const r = rig();
    seedJob(r.db, { note: note({ effect }) });
    const out = await run(r, scripted(failed("other", { effect })));
    assert.equal(out.status, 200, out.text);
    assert.equal(out.body.status, "needs_user", effect);
    assert.equal(out.body.effect_uncertain, true);
    const row = readJob(r.db);
    assert.equal(row.status, "needs_user", effect);
    assert.equal(row.lane, API_LANE);
    assert.equal(row.effect_uncertain, 1, effect);
    assert.equal(row.claimed_by, API_CLAIMANT);
    assert.ok(/may have gone through/.test(row.result), row.result);
    assert.equal(row.p._hand.outcome.may_have_landed, true);
    assertConsistent(row);
  }
});

await check("THE CONTROL: a READ that may have landed landed nothing — it goes to the browser, not uncertain", async () => {
  const r = rig();
  seedJob(r.db);
  const out = await run(r, scripted(failed("other")));
  assert.equal(out.body.status, "queued");
  assert.equal(out.body.lane, BROWSER_LANE);
  const row = readJob(r.db);
  assert.equal(row.effect_uncertain, 0);
  assert.equal(row.lane, BROWSER_LANE);
  assertConsistent(row);
});

await check("rate and schema failures — the vendor's promise nothing ran — go to the browser", async () => {
  for (const kind of ["rate", "schema"] as const) {
    const r = rig();
    seedJob(r.db, { note: note({ effect: "write" }) });
    const out = await run(r, scripted(failed(kind, { effect: "write" })));
    assert.equal(out.body.status, "queued", kind);
    assert.equal(out.body.lane, BROWSER_LANE, kind);
    assert.equal(readJob(r.db).effect_uncertain, 0, kind);
  }
});

function connection(over: Partial<StoredConnection> = {}): StoredConnection {
  return { user_id: OWNER, toolkit: APP as never, connected_account_id: ACCOUNT, alias: null,
           status: "connected", writes_enabled: true, last_used_at: null, ...over };
}

await check("an auth failure marks the connection needs_reconnect — the webhook's own write — and hands the job back", async () => {
  const r = rig();
  await r.store.putConnection(connection());
  seedJob(r.db);
  const out = await run(r, scripted(failed("auth")));
  assert.equal(out.status, 200, out.text);
  assert.equal(out.body.status, "queued");
  assert.equal(out.body.lane, BROWSER_LANE);
  assert.equal(out.body.connection, "marked");
  const rows = await r.store.connectionsForOwner(OWNER);
  assert.equal(rows.length, 1);
  assert.equal(rows[0]!.status, "needs_reconnect");
  assert.equal(rows[0]!.writes_enabled, true, "the opt-in is a decision about an app, not a credential");
  const nudge = await r.store.readNudge(OWNER, APP as never);
  assert.ok(nudge && nudge.state === "needs_reconnect", "the ask engine was not told");
  const row = readJob(r.db);
  assert.equal(row.lane, BROWSER_LANE);
  assert.equal(row.p._hand.outcome.connection, "marked");
  assert.ok(/reconnect/.test(row.result), row.result);
  assertConsistent(row);
});

await check("an auth failure never marks a STRANGER'S connection, even when the vendor names their account", async () => {
  const r = rig();
  await r.store.putConnection(connection({ user_id: STRANGER, connected_account_id: "ca_zell_stranger_1" }));
  seedJob(r.db);
  const out = await run(r, scripted(failed("auth", { account: "ca_zell_stranger_1" })));
  assert.equal(out.status, 200);
  assert.equal(out.body.connection, "wrong-owner");
  const theirs = await r.store.connectionsForOwner(STRANGER);
  assert.equal(theirs[0]!.status, "connected", "a stranger's row was marked");
  assert.equal(readJob(r.db).lane, BROWSER_LANE, "the job still goes to the browser");
});

await check("THE CONTROL: a rate failure leaves the connection row alone", async () => {
  const r = rig();
  await r.store.putConnection(connection());
  seedJob(r.db);
  const out = await run(r, scripted(failed("rate")));
  assert.equal(out.body.connection, undefined);
  assert.equal((await r.store.connectionsForOwner(OWNER))[0]!.status, "connected");
});

await check("a connection store that cannot write does not lose the job's outcome", async () => {
  const r = rig();
  await r.store.putConnection(connection());
  seedJob(r.db);
  const reconnect = { ...webhookStore(r.env), putConnection: async () => { throw new Error("D1_ERROR: refused"); } };
  const out = await run(r, { ...scripted(failed("auth")), reconnect });
  assert.equal(out.status, 200, out.text);
  assert.equal(out.body.connection, undefined);
  assert.equal(readJob(r.db).lane, BROWSER_LANE);
});

// ===========================================================================
// 5. THE ROW STAYS ONE THE BRAIN CAN READ.
// ===========================================================================

await check("a pre-workflow row is written the same way, with no plan invented for it", async () => {
  for (const [outcome, status, lane] of [
    [ran(), "done", API_LANE],
    [refused("not_connected"), "queued", BROWSER_LANE],
    [failed("other", { effect: "write" }), "needs_user", API_LANE],
  ] as const) {
    const r = rig();
    seedJob(r.db, { workflow: null, note: note({ effect: outcome.outcome === "failed" ? "write" : "read" }) });
    const out = await run(r, scripted(outcome));
    assert.equal(out.status, 200, out.text);
    const row = readJob(r.db);
    assert.equal(row.status, status);
    assert.equal(row.lane, lane);
    assert.equal(row.workflow_state, "");
    assert.equal(row.receipt, "");
    assert.equal(row.p._workflow, undefined, "a plan was invented for a row that had none");
    assert.equal(row.lease_token, "");
    assertConsistent(row);
  }
});

await check("settleWorkflow: a resting plan has no lease, only success carries a receipt", () => {
  const at = "2026-09-06T20:00:01+00:00";
  const ok = dispose(ran(), 1);
  const succeeded = settleWorkflow(plan(), { effect_key: "effect-key-1" }, ok, at);
  assert.equal(succeeded.state, "succeeded");
  assert.equal(succeeded.lease, null);
  assert.deepEqual(succeeded.receipt, { effect_key: "effect-key-1", summary: ok.result.slice(0, 2000),
                                        evidence: ["vendor-log:log_777"], verified: true, recorded_at: at });
  for (const d of [dispose(refused("not_connected"), 1), dispose(refused("confirmation_required"), 1),
                   dispose(failed("other", { effect: "write" }), 1)]) {
    const rest = settleWorkflow(plan(), { effect_key: "effect-key-1" }, d, at);
    assert.equal(rest.lease, null, d.state);
    assert.equal(rest.receipt, null, d.state);
    assert.equal(rest.updated_at, at);
    assert.equal(rest.reason, d.reason);
  }
  // A plan whose dict lacks effect_key falls back to the column.
  assert.equal((settleWorkflow(plan({ effect_key: "" }), { effect_key: "col-key" }, ok, at).receipt as any).effect_key, "col-key");
});

await check("canonical() is Python's json.dumps(sort_keys=True, separators=(',', ':'))", () => {
  assert.equal(canonical({ b: 1, a: [{ d: 2, c: "x" }], e: null }), '{"a":[{"c":"x","d":2}],"b":1,"e":null}');
  assert.equal(canonical([]), "[]");
});

// ===========================================================================
// 6. THE JOIN, END TO END, with the REAL hand over the real store.
// ===========================================================================

function vendor(catalog: unknown[], execute: { status?: number; body?: unknown } = {}) {
  const calls: { method: string; path: string }[] = [];
  const impl = async (url: any, init: any) => {
    const full = String(url);
    const path = full.startsWith(COMPOSIO_BASE_URL) ? full.slice(COMPOSIO_BASE_URL.length) : full;
    calls.push({ method: init?.method ?? "GET", path });
    if (path.startsWith("/tools?")) {
      return { status: 200, json: async () => ({ items: catalog, next_cursor: null }) } as unknown as Response;
    }
    if (path.startsWith("/tools/execute/")) {
      return { status: execute.status ?? 200,
               json: async () => execute.body ?? { data: { found: 1 }, error: null, successful: true, log_id: "log_e2e" } } as unknown as Response;
    }
    return { status: 500, json: async () => ({ error: { slug: "unexpected_route" } }) } as unknown as Response;
  };
  return { calls, impl: impl as unknown as typeof globalThis.fetch };
}
const CATALOG = [{
  slug: READ_TOOL, name: "find thing", description: "finds", toolkit: { slug: APP, name: APP, logo: "" },
  tags: ["readOnlyHint"], scopes: [], input_parameters: {}, is_deprecated: false,
  deprecated: { displayName: READ_TOOL, version: "1", is_deprecated: false },
}];

await check("THE JOIN, WITH THE REAL HAND: no connection row -> refused not_connected -> browser lane, ZERO vendor calls", async () => {
  const r = rig();
  seedJob(r.db);
  const v = vendor(CATALOG);
  const provider = new ComposioConnections({ apiKey: KEY, fetchImpl: v.impl });
  const out = await run(r, { store: r.store, provider });
  assert.equal(out.status, 200, out.text);
  assert.equal(out.body.outcome, "refused");
  assert.equal(out.body.reason, "not_connected");
  assert.equal(out.body.lane, BROWSER_LANE);
  assert.equal(v.calls.length, 0, "the vendor heard about a step nothing licensed");
  const row = readJob(r.db);
  assert.equal(row.status, "queued");
  assert.equal(row.lane, BROWSER_LANE);
  assertConsistent(row);
});

await check("THE JOIN, WITH THE REAL HAND: a connected row and a listed read tool -> the vendor runs it -> done", async () => {
  const r = rig();
  await r.store.putConnection(connection({ writes_enabled: false }));
  seedJob(r.db);
  const v = vendor(CATALOG);
  const provider = new ComposioConnections({ apiKey: KEY, fetchImpl: v.impl });
  const out = await run(r, { store: r.store, provider });
  assert.equal(out.status, 200, out.text);
  assert.equal(out.body.outcome, "ran");
  assert.equal(out.body.status, "done");
  assert.deepEqual(v.calls.map((c) => c.method), ["GET", "POST"], "one catalog read, one execute");
  const row = readJob(r.db);
  assert.equal(row.status, "done");
  assert.ok(row.result.includes('"found":1'), row.result);
  assert.deepEqual(row.p._workflow.receipt.evidence, ["vendor-log:log_e2e"]);
  assertConsistent(row);
});

await check("THE JOIN, WITH THE REAL HAND: a tool the note never named is refused before the vendor hears of it", async () => {
  const r = rig();
  await r.store.putConnection(connection());
  seedJob(r.db, { note: note({ tool: undefined, args: undefined }) });
  const v = vendor(CATALOG);
  const provider = new ComposioConnections({ apiKey: KEY, fetchImpl: v.impl });
  const out = await run(r, { store: r.store, provider });
  assert.equal(out.body.reason, "tool_required");
  assert.equal(out.body.lane, BROWSER_LANE);
  assert.equal(v.calls.length, 0);
});

// ===========================================================================
// 7. THE SOURCE LEGS.
// ===========================================================================

/** The same list the hand's suite keeps. A word list in a TEST is where law 1 puts one. */
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

await check("NO APP IS NAMED anywhere in hands_api.ts — comments included", () => {
  assert.deepEqual(namesIn("const x = 'gmail'"), ["gmail"], "the scan is vacuous");
  const found = namesIn(ROUTE_SOURCE);
  assert.deepEqual(found, [], `src/routes/hands_api.ts names ${found.join(", ")}`);
});

await check("src/index.ts imports the route and dispatches its path EXACTLY ONCE (the mutation literal)", () => {
  assert.ok(INDEX_SOURCE.includes('from "./routes/hands_api.ts"'), "index.ts does not import the route");
  const dispatches = INDEX_SOURCE.split("path === HANDS_API_RUN_PATH").length - 1;
  assert.equal(dispatches, 1, `index.ts dispatches HANDS_API_RUN_PATH ${dispatches} times`);
  assert.equal(INDEX_SOURCE.split("handsApiRun(request").length - 1, 1);
  assert.equal(HANDS_API_RUN_PATH, "/hands/api/run");
});

await check("the constants the brain shares are the brain's", () => {
  assert.ok(BRAIN_HANDS.includes(`LANE_API = "${API_LANE}"`), "brain/hands.py LANE_API moved");
  assert.ok(BRAIN_HANDS.includes("HAND_API: LANE_API"), "brain/hands.py no longer maps api -> LANE_API");
  assert.ok(BRAIN_WORKER.includes(`API_CLAIMANT = "${API_CLAIMANT}"`), "brain/worker.py API_CLAIMANT moved");
  assert.ok(BRAIN_WORKER.includes(`"${HANDS_API_RUN_PATH}"`), "brain/worker.py does not POST to this path");
  assert.ok(BRAIN_WORKFLOW.includes(`max_attempts: int = ${MAX_ATTEMPTS}`), "brain/workflow.py's attempt cap moved");
  assert.ok(BRAIN_WORKER.includes(`[:${RESULT_MAX}]`), "brain/worker.py's result bound moved");
});

await check("the token is checked with a difference-accumulating compare, before the first prepare()", () => {
  const tokenAt = ROUTE_SOURCE.indexOf("if (!tokenOk(env, request))");
  const readAt = ROUTE_SOURCE.indexOf('env.DB.prepare(');
  assert.ok(tokenAt > 0 && readAt > 0 && tokenAt < readAt, "the row is read before the token is checked");
  assert.ok(/d \|= got\.charCodeAt\(i\) \^ want\.charCodeAt\(i\)/.test(ROUTE_SOURCE));
});

await check("the route reads no prose: its only string comparisons are enums and identifiers", () => {
  // Every `=== "..."` in executable code compares against a closed set the
  // file declares, an outcome/reason/kind enum, or a lane/status literal.
  const code = ROUTE_SOURCE.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");
  const literals = [...code.matchAll(/[!=]==\s*"([^"]+)"/g)].map((m) => m[1]!);
  const allowed = new Set(["ran", "refused", "failed", "confirmation_required", "owner_required", "auth",
                           "read", "api", "running", "succeeded", "queued", "POST", "string", "object"]);
  const stray = literals.filter((l) => !allowed.has(l));
  assert.deepEqual(stray, [], `unexpected string comparisons: ${stray.join(", ")}`);
});

console.log(`hands-api: ${passes} checks passed, ${failures} failed`);
if (failures) process.exit(1);
