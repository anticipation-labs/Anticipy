/**
 * THE API LANE IS NOT BROWSER WORK — the server's floor, and this file is
 * what holds it down.
 *
 *   node --experimental-strip-types migration/workers/test/api-lane-claim.test.ts
 *
 * THE DEFECT, measured 2026-09-06 before anything here was written: the
 * extension polls `workflow_id!="" && lane!="research"` (extension/
 * background.js BROWSER_LANE). It NAMES `lane`, so research_lane.ts leg 1
 * appends nothing to it, and it excludes ONLY research — so an api-lane row
 * (brain/hands.py LANE_API, the row brain/worker.py run_api_jobs claims and
 * POSTs to /hands/api/run) was LISTED by every shipped extension. And the
 * claim leg (leg 5) had no api rule at all, so the extension's claim PATCH
 * was ACCEPTED: a browser that polled before the brain won the row and ran an
 * api errand through the browser vocabulary. The api hand was bypassed every
 * time a browser was awake.
 *
 * TWO LAYERS, tested independently, and the order matters:
 *   THE FLOOR is the server. A non-worker claim on lane "api" is refused
 *   whatever the extension asks, because a shipped extension cannot be
 *   recalled (the research lane learned this with 0.2.3 in the wild). The
 *   worker marker (X-Anticipy-Worker + the service token) is the ONLY thing
 *   that passes; the claimant's NAME is not a credential.
 *   THE COURTESY is the extension's filter (extension/tests/
 *   test_api_lane_is_not_browser_work.mjs): it stops listing api rows so a
 *   browser never even tries. This file proves the floor holds with the
 *   courtesy absent — a poll that names lane and does not exclude api still
 *   lists the row (MEASURED, not hidden), and the claim is still refused.
 *
 * EVERY REFUSAL HAS A CONTROL that differs in exactly one thing and is
 * allowed: the same claim on the browser lane; the same claim from the
 * worker; the same body as a non-claim write.
 *
 * MUTATIONS THIS FILE MUST GO RED ON (each literal is asserted to occur
 * EXACTLY ONCE in research_lane.ts, and each was run — see the record at the
 * bottom of the extension twin and in the research note):
 *   * API_LANE leaves EXCLUDED_LANES (a 0.2.3-style poll lists api rows);
 *   * the `lane === API_LANE` claim leg is deleted (an agent's claim lands);
 *   * the claim leg keys on `claimed_by` instead of the worker marker (an
 *     agent naming itself "worker-api" lands).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import worker from "../src/index.ts";
import * as lanePolicy from "../src/policy/research_lane.ts";
import type { Ctx, Principal } from "../src/policy/chain.ts";
import { compileFilter, parseFilter, mentionsField, type Node } from "../filter-dsl.ts";
import { COLLECTIONS } from "../src/pb/schema.ts";
import { FakeD1, asD1 } from "./fake-d1.ts";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(here, "..", "..", "..");
const POLICY_SOURCE = readFileSync(join(here, "..", "src", "policy", "research_lane.ts"), "utf8");
const ROUTE_SOURCE = readFileSync(join(here, "..", "src", "routes", "hands_api.ts"), "utf8");
const BRAIN_HANDS = readFileSync(join(repoRoot, "brain", "hands.py"), "utf8");
const EXTENSION = readFileSync(join(repoRoot, "extension", "background.js"), "utf8");

const { researchLane } = lanePolicy;

let failures = 0;
let passes = 0;
async function check(what: string, fn: () => void | Promise<void>): Promise<void> {
  try {
    await fn();
    passes++;
  } catch (err) {
    failures++;
    console.error("FAIL " + what + "\n     " + (err as Error).message);
  }
}

// ---------------------------------------------------------------------------
// FIXTURES
// ---------------------------------------------------------------------------

/** The lane under test, held HERE as a literal so the test does not inherit
 *  its own expectation from the module it is testing. */
const API = "api";
const OWNER = "owner000000one1";
const STRANGER = "owner000000two2";
const AGENT_ID = "agent-1";
const AGENT_TOKEN = "agenttoken".repeat(5);          // >= 40 chars, as the column demands
const SERVICE = "service-token-0123456789abcdef";
const HOST = "https://api.anticipy.ai";
const NOW = "2026-09-06 12:00:00.000Z";
const JOBS = "/api/collections/jobs/records";

/** brain/worker.py API_CLAIMANT — what the brain stamps on an api-lane claim. */
const WORKER_API = "worker-api";

const agent: Principal = { kind: "agent", agentRowId: "agent000000001", agentId: AGENT_ID, ownerRef: OWNER };
const account: Principal = { kind: "account", ownerId: OWNER, row: { id: OWNER } };
const anonymous: Principal = { kind: "anonymous" };
const service: Principal = { kind: "service" };

/** The extension's own claim body — extension/workflow_state.js workflowPatch
 *  for "running": the lease fields plus the stamp. The lane leg reads only
 *  `claimed_by` and `status`, but the body is the shipped shape anyway. */
const extensionClaim = (who = AGENT_ID): Record<string, unknown> => ({
  status: "running", claimed_by: who, claimed_at: NOW,
  lease_token: "lease-ext-0001", lease_until: "2026-09-06T12:02:00.000Z", attempts: 1,
});
/** brain/worker.py run_api_jobs — the brain's claim body. */
const brainClaim = (): Record<string, unknown> => ({
  status: "running", claimed_by: WORKER_API, claimed_at: "2026-09-06 12:00:00",
});
/** extension/background.js requeueStaleJobs — the sweep's requeue body. */
const sweepRequeue = (): Record<string, unknown> => ({
  status: "queued", claimed_by: "", claimed_at: null,
});

interface Seed {
  id: string; lane: string; status?: string; owner?: string; workflow?: string; claimedBy?: string;
}
function seed(t: FakeD1, s: Seed): void {
  t.db.exec(`INSERT INTO jobs (id, created, updated, goal, params, status, owner_ref, lane, claimed_by,
            claimed_at, attempts, workflow_id, device_id)
          VALUES ('${s.id}', '${NOW}', '${NOW}', 'what did Dana send me', '{}',
                  '${s.status ?? "queued"}', '${s.owner ?? OWNER}', '${s.lane}',
                  '${s.claimedBy ?? ""}', '', 0, '${s.workflow ?? ""}', 'anticipy')`);
}

function rig(): { t: FakeD1; env: Record<string, unknown> } {
  const t = new FakeD1();
  for (const id of [OWNER, STRANGER]) {
    t.db.exec(`INSERT INTO owners (id, created, updated, email, emailVisibility, verified, password, tokenKey, phone, legacy_uuid)
            VALUES ('${id}', '${NOW}', '${NOW}', '${id}@example.invalid', 0, 0, '', 'tk-${id}', '', '')`);
  }
  t.db.exec(`INSERT INTO agents (id, created, updated, agent_id, agent_token, pair_code, paired, owner_ref)
          VALUES ('agent000000001', '${NOW}', '${NOW}', '${AGENT_ID}', '${AGENT_TOKEN}', 'PAIR01', 1, '${OWNER}')`);
  const env = {
    DB: asD1(t),
    ASSETS: { fetch: async () => new Response("static", { status: 200 }) },
    ANTICIPY_SERVICE_TOKEN: SERVICE,
    ANTICIPY_PUBLIC_URL: HOST,
  };
  return { t, env };
}

/** A Ctx the way src/index.ts handleRecords builds one, for the direct legs. */
function ctxFor(t: FakeD1, over: {
  method: string; path: string; body?: Record<string, unknown> | null;
  principal?: Principal; fromWorker?: boolean; filter?: string;
}): Ctx & { db: D1Database } {
  const url = new URL(HOST + over.path);
  if (over.filter !== undefined) url.searchParams.set("filter", over.filter);
  const request = new Request(url.toString(), { method: over.method });
  return {
    request, url, method: over.method, path: over.path, body: over.body ?? null,
    principal: over.principal ?? agent,
    worker: { fromWorker: over.fromWorker ?? false },
    forcedScope: null, extraAst: null, db: asD1(t),
  };
}

const claimOn = (t: FakeD1, id: string, body: Record<string, unknown>, principal: Principal = agent,
                 fromWorker = false) =>
  researchLane(ctxFor(t, { method: "PATCH", path: `${JOBS}/${id}`, body, principal, fromWorker }), {});

async function refused(r: Response | null): Promise<{ status: number; error: string; detail: string }> {
  assert.ok(r, "the write was let through (null from the chain)");
  const body = await r.json() as { error?: string; detail?: string };
  return { status: r.status, error: String(body.error ?? ""), detail: String(body.detail ?? "") };
}

/** Every `lane != "<x>"` the policy appended, in order. */
function excludedLanes(ast: Node | null): string[] {
  const out: string[] = [];
  const walk = (n: Node | null): void => {
    if (!n) return;
    if (n.kind === "and" || n.kind === "or") { walk(n.left); walk(n.right); return; }
    if (n.kind === "cmp" && n.op === "!=" && n.left.kind === "column" && n.left.name === "lane"
        && n.right.kind === "string") out.push(n.right.value);
  };
  walk(ast);
  return out;
}

const silent = async <T,>(fn: () => Promise<T>): Promise<T> => {
  const original = console.log;
  console.log = () => {};
  try { return await fn(); } finally { console.log = original; }
};

const exec = { waitUntil() {}, passThroughOnException() {} } as unknown as ExecutionContext;
const agentHeaders = { "X-Anticipy-Agent-ID": AGENT_ID, "X-Anticipy-Agent-Token": AGENT_TOKEN };
const workerHeaders = { "X-Anticipy-Worker": "1", "X-Anticipy-Token": SERVICE };
async function send(env: Record<string, unknown>, method: string, path: string,
                    headers: Record<string, string>, body?: Record<string, unknown>): Promise<Response> {
  const req = new Request(HOST + path, {
    method,
    headers: { ...headers, ...(body ? { "Content-Type": "application/json" } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  return silent(() => worker.fetch(req, env as never, exec));
}
const listed = async (r: Response): Promise<string[]> => {
  const text = await r.text();
  assert.equal(r.status, 200, `list refused: ${text}`);
  const { items } = JSON.parse(text) as { items: { id: string }[] };
  return items.map((j) => j.id).sort();
};

/** The extension's poll filter, read from the SHIPPED source rather than
 *  retyped, so this file measures the extension that exists. */
function shippedBrowserLane(): string {
  const m = EXTENSION.match(/const BROWSER_LANE = '([^']+)';/);
  assert.ok(m, "extension/background.js no longer defines BROWSER_LANE");
  return m![1];
}
const pollWith = (browserLane: string) => `status="queued" && owner_ref="${OWNER}" && ${browserLane}`;
/** The filter every extension shipped up to 2026-09-06 sent. Held as a literal
 *  ON PURPOSE: it is the reproduction, and it must keep reproducing. */
const LANE_2026_09_06 = 'workflow_id!="" && lane!="research"';
/** What 0.2.3 and older sent: no lane at all. The leg-1 rewrite exists for them. */
const POLL_0_2_3 = `status="queued" && owner_ref="${OWNER}"`;

// ---------------------------------------------------------------------------
// 1. THE FLOOR — leg 5, driven directly. Hardest first: the reproduction.
// ---------------------------------------------------------------------------

await check("REPRODUCTION: an agent's claim on a queued api-lane row is refused 403", async () => {
  const { t } = rig();
  seed(t, { id: "jobapi000000001", lane: API });
  const r = await refused(await claimOn(t, "jobapi000000001", extensionClaim()));
  assert.equal(r.status, 403);
  assert.match(r.error, /api/i, `the refusal does not say which lane: ${r.error}`);
  assert.match(r.error, /never in a browser/, `the refusal does not say who may not run it: ${r.error}`);
});

await check("CONTROL: the same claim on a browser-lane row is let through", async () => {
  const { t } = rig();
  seed(t, { id: "jobbrw000000001", lane: "" });
  assert.equal(await claimOn(t, "jobbrw000000001", extensionClaim()), null);
});

await check("CONTROL: the same claim on a research row is still refused (the neighbour leg survived)", async () => {
  const { t } = rig();
  seed(t, { id: "jobres000000001", lane: "research" });
  const r = await refused(await claimOn(t, "jobres000000001", extensionClaim()));
  assert.equal(r.status, 403);
  assert.match(r.error, /research jobs run in the worker/);
});

await check("the worker CAN claim an api row — the brain's own body, under the worker marker", async () => {
  const { t } = rig();
  seed(t, { id: "jobapi000000002", lane: API });
  assert.equal(await claimOn(t, "jobapi000000002", brainClaim(), service, true), null);
});

await check("the claimant's NAME is not a credential: an agent calling itself worker-api is refused", async () => {
  const { t } = rig();
  seed(t, { id: "jobapi000000003", lane: API });
  const r = await refused(await claimOn(t, "jobapi000000003", extensionClaim(WORKER_API)));
  assert.equal(r.status, 403);
});

await check("the service token ALONE is not the worker marker: no X-Anticipy-Worker, no api claim", async () => {
  // brain/pb.py sends both on every call. A caller holding the god credential
  // but not routing as the brain is not the api executor, and the floor says so.
  const { t } = rig();
  seed(t, { id: "jobapi000000004", lane: API });
  const r = await refused(await claimOn(t, "jobapi000000004", brainClaim(), service, false));
  assert.equal(r.status, 403);
});

await check("every non-worker principal is refused alike: account, anonymous", async () => {
  for (const [name, who] of [["account", account], ["anonymous", anonymous]] as const) {
    const { t } = rig();
    seed(t, { id: "jobapi000000005", lane: API });
    const r = await refused(await claimOn(t, "jobapi000000005", extensionClaim(), who));
    assert.equal(r.status, 403, `${name} was let through`);
    assert.match(r.error, /api/i, `${name} got a different refusal than the api one: ${r.error}`);
  }
});

await check("a claim by `status:\"running\"` alone (no claimed_by) is still a claim, and refused", async () => {
  const { t } = rig();
  seed(t, { id: "jobapi000000006", lane: API });
  const r = await refused(await claimOn(t, "jobapi000000006", { status: "running" }));
  assert.equal(r.status, 403);
});

await check("the sweep's requeue is a claim-shaped write, refused on api; CONTROL: the brain's identical requeue lands", async () => {
  // extension/background.js requeueStaleJobs writes `claimed_by: ""` — the
  // research lane learned in 2026-08 that this is exactly the write that
  // 403s on a lane a browser may not touch. brain/worker.py
  // release_stranded_api sends the same body under the worker marker.
  const { t } = rig();
  seed(t, { id: "jobapi000000007", lane: API, status: "running", claimedBy: WORKER_API });
  const r = await refused(await claimOn(t, "jobapi000000007", sweepRequeue()));
  assert.equal(r.status, 403);
  assert.equal(await claimOn(t, "jobapi000000007", sweepRequeue(), service, true), null);
});

await check("BOUNDARY: a non-claim write by an agent on an api row is not this leg's to refuse", async () => {
  // Parity with the research lane: the lane leg is claim-shaped. Other
  // writes are governed by the lease (workflow_guard) and the lane's
  // immutability (leg 2), not by this refusal.
  const { t } = rig();
  seed(t, { id: "jobapi000000008", lane: API });
  assert.equal(await claimOn(t, "jobapi000000008", { result: "a note" }), null);
});

await check("leg 2 still holds: an agent may not rename an api row's lane on the way in", async () => {
  const { t } = rig();
  seed(t, { id: "jobapi000000009", lane: API });
  const r = await refused(await claimOn(t, "jobapi000000009", { ...extensionClaim(), lane: "" }));
  assert.equal(r.status, 403);
  assert.match(r.error, /never rewritten/);
});

await check("MEASURED, NOT ENDORSED: the research leg lets an agent through when it names itself worker-research", async () => {
  // research_lane.pb.js:649 ported as written: `lane === "research" &&
  // b.claimed_by !== WORKER_CLAIMANT`. A browser that stamps the worker's
  // name walks past the research refusal. The api leg above does NOT copy
  // that shape — it keys on the worker marker. This leg records the hole so
  // the day it closes is a visible day; the day it does, delete this leg.
  const { t } = rig();
  seed(t, { id: "jobres000000002", lane: "research" });
  assert.equal(await claimOn(t, "jobres000000002", extensionClaim("worker-research")), null);
});

// ---------------------------------------------------------------------------
// 2. THE READ REWRITE — leg 1. A poll that does not name lane is protected;
//    a poll that names lane is NOT hidden from (measured), and that is why
//    the extension's filter must mirror the floor.
// ---------------------------------------------------------------------------

await check("a 0.2.3-style poll (no lane) gets `lane != \"api\"` appended — beside the three it already had", async () => {
  const { t } = rig();
  const ctx = ctxFor(t, { method: "GET", path: JOBS, filter: POLL_0_2_3 });
  assert.equal(await researchLane(ctx, {}), null, "a read is never refused, only rewritten");
  const lanes = excludedLanes(ctx.extraAst);
  assert.ok(lanes.includes(API), `api is not excluded: ${JSON.stringify(lanes)}`);
  for (const lane of ["research", "supervised_read", "device_calendar"]) {
    assert.ok(lanes.includes(lane), `CONTROL: ${lane} fell out of the rewrite: ${JSON.stringify(lanes)}`);
  }
  assert.equal(lanes.filter((l) => l === API).length, 1, "api excluded twice");
});

await check("MEASURED: a poll that names lane is left alone — the server hides nothing from it", async () => {
  // The shipped extension names lane. Leg 1 is for filters that cannot be
  // recalled and never named it; a filter that names lane is trusted to say
  // what it wants, and what keeps an api row off the browser is the CLAIM
  // refusal above, not a rewrite. That is the floor/courtesy split.
  const { t } = rig();
  const ctx = ctxFor(t, { method: "GET", path: JOBS, filter: pollWith(LANE_2026_09_06) });
  assert.equal(await researchLane(ctx, {}), null);
  assert.equal(ctx.extraAst, null);
  assert.ok(mentionsField(parseFilter(pollWith(LANE_2026_09_06)), "lane"));
});

await check("CONTROL: the worker's poll and a non-queued poll are not rewritten", async () => {
  const { t } = rig();
  const w = ctxFor(t, { method: "GET", path: JOBS, filter: POLL_0_2_3, principal: service, fromWorker: true });
  assert.equal(await researchLane(w, {}), null);
  assert.equal(w.extraAst, null, "the brain's own poll was rewritten");
  const done = ctxFor(t, { method: "GET", path: JOBS, filter: `status="done" && owner_ref="${OWNER}"` });
  assert.equal(await researchLane(done, {}), null);
  assert.equal(done.extraAst, null, "a non-queued read was rewritten");
});

// ---------------------------------------------------------------------------
// 3. END TO END through the real Worker: guard -> ownerProfileOwner ->
//    researchLane -> workflowGuard -> records, over the real schema.
// ---------------------------------------------------------------------------

function seedLanes(t: FakeD1): void {
  seed(t, { id: "e2ebrw000000001", lane: "", workflow: "wf-brw" });
  seed(t, { id: "e2eres000000001", lane: "research", workflow: "wf-res" });
  seed(t, { id: "e2eapi000000001", lane: API, workflow: "wf-api" });
  seed(t, { id: "e2esup000000001", lane: "supervised_read" });          // never carries a plan
  seed(t, { id: "e2edev000000001", lane: "device_calendar", workflow: "wf-dev" });
  seed(t, { id: "e2eapi000000002", lane: API, workflow: "wf-api2", owner: STRANGER });
}

await check("E2E: a 0.2.3-style poll from a paired agent never sees the api row (nor the other three)", async () => {
  const { t, env } = rig();
  seedLanes(t);
  const ids = await listed(await send(env, "GET", `${JOBS}?filter=${encodeURIComponent(POLL_0_2_3)}`, agentHeaders));
  assert.deepEqual(ids, ["e2ebrw000000001"]);
});

await check("E2E MEASURED: the 2026-09-06 extension filter DOES list the api row — the courtesy gap the extension closes", async () => {
  const { t, env } = rig();
  seedLanes(t);
  const ids = await listed(await send(env, "GET",
    `${JOBS}?filter=${encodeURIComponent(pollWith(LANE_2026_09_06))}`, agentHeaders));
  assert.ok(ids.includes("e2eapi000000001"), `the server hid the api row from a lane-naming poll: ${ids}`);
  assert.ok(!ids.includes("e2eres000000001"));
  assert.ok(!ids.includes("e2eapi000000002"), "a stranger's row leaked through the owner scope");
});

await check("E2E: the SHIPPED extension filter, read from its source, does not list the api row", async () => {
  const { t, env } = rig();
  seedLanes(t);
  const ids = await listed(await send(env, "GET",
    `${JOBS}?filter=${encodeURIComponent(pollWith(shippedBrowserLane()))}`, agentHeaders));
  assert.ok(!ids.includes("e2eapi000000001"), `the extension still lists api rows: ${ids}`);
  assert.ok(!ids.includes("e2eres000000001"), `the extension lists research rows again: ${ids}`);
  assert.ok(ids.includes("e2ebrw000000001"), `the extension lost its own lane: ${ids}`);
});

await check("E2E: the agent's claim PATCH on an api row is answered 403 and the row is untouched", async () => {
  const { t, env } = rig();
  seed(t, { id: "e2eapi000000003", lane: API });
  const r = await send(env, "PATCH", `${JOBS}/e2eapi000000003`, agentHeaders, extensionClaim());
  assert.equal(r.status, 403, await r.text());
  const row = t.rows<{ status: string; claimed_by: string }>(
    `SELECT status, claimed_by FROM jobs WHERE id = ?`, "e2eapi000000003")[0];
  assert.deepEqual({ ...row }, { status: "queued", claimed_by: "" });
});

await check("E2E CONTROL: the same PATCH on a browser-lane row lands, and the worker's claim on the api row lands", async () => {
  const { t, env } = rig();
  seed(t, { id: "e2ebrw000000002", lane: "" });
  seed(t, { id: "e2eapi000000004", lane: API });
  const b = await send(env, "PATCH", `${JOBS}/e2ebrw000000002`, agentHeaders, extensionClaim());
  assert.equal(b.status, 200, await b.text());
  const w = await send(env, "PATCH", `${JOBS}/e2eapi000000004`, workerHeaders, brainClaim());
  assert.equal(w.status, 200, await w.text());
  const row = t.rows<{ status: string; claimed_by: string }>(
    `SELECT status, claimed_by FROM jobs WHERE id = ?`, "e2eapi000000004")[0];
  assert.deepEqual({ ...row }, { status: "running", claimed_by: WORKER_API });
});

await check("E2E: the extension filter compiled by the server's own DSL agrees with the list above", async () => {
  // The same parser and the same SQLite the extension twin uses, so the two
  // suites cannot disagree about what one filter string means.
  const { t } = rig();
  seedLanes(t);
  const c = compileFilter(parseFilter(pollWith(shippedBrowserLane())), { schema: COLLECTIONS.jobs.columns });
  const rows = t.rows<{ lane: string }>(`SELECT lane FROM jobs WHERE ${c.sql}`, ...(c.params as never[]));
  assert.ok(!rows.some((r) => r.lane === API), "api listed");
  assert.ok(!rows.some((r) => r.lane === "research"), "research listed");
});

// ---------------------------------------------------------------------------
// 4. SOURCE LEGS — the mutation literals, and the three halves agreeing.
// ---------------------------------------------------------------------------

const count = (hay: string, needle: string): number => hay.split(needle).length - 1;

await check("research_lane.ts exports API_LANE, and it is the literal the route and the brain use", () => {
  assert.equal((lanePolicy as { API_LANE?: string }).API_LANE, API);
  assert.ok(ROUTE_SOURCE.includes(`export const API_LANE = "${API}"`), "hands_api.ts disagrees");
  assert.ok(BRAIN_HANDS.includes(`LANE_API = "${API}"`), "brain/hands.py disagrees");
});

await check("API_LANE joins EXCLUDED_LANES EXACTLY ONCE (the leg-1 mutation literal)", () => {
  assert.equal(count(POLICY_SOURCE, "EXCLUDED_LANES = ["), 1);
  const decl = POLICY_SOURCE.match(/EXCLUDED_LANES = \[([^\]]*)\]/)![1];
  assert.equal(count(decl, "API_LANE"), 1, `EXCLUDED_LANES = [${decl}]`);
  assert.ok(decl.includes('"research"') && decl.includes("SUPERVISED_LANE") && decl.includes("DEVICE_LANE"),
    "a lane fell out of the list");
});

await check("the api claim leg exists EXACTLY ONCE and keys on the worker marker, not the claimant's name", () => {
  assert.equal(count(POLICY_SOURCE, "lane === API_LANE"), 1);
  const leg = POLICY_SOURCE.slice(POLICY_SOURCE.indexOf("lane === API_LANE"));
  const stmt = leg.slice(0, leg.indexOf("}") + 1);
  assert.ok(!/claimed_by/.test(stmt), "the api leg reads claimed_by — a name a browser can type");
  const claims = POLICY_SOURCE.indexOf("if (claims && !ctx.worker.fromWorker)");
  assert.ok(claims > 0 && claims < POLICY_SOURCE.indexOf("lane === API_LANE"),
    "the api leg sits outside the non-worker claim block");
});

// ---------------------------------------------------------------------------

console.log(`api-lane-claim: ${passes} checks passed, ${failures} failed`);
if (failures) process.exit(1);
