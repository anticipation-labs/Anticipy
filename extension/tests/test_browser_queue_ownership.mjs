// Read filters run through the Worker's real DSL and SQLite schema. The PATCH
// boundary models a refused claim or a concurrent winner. No browser or network
// traffic leaves this process, and no task is executed.
import assert from "node:assert/strict";
import { parseFilter, compileFilter } from "../../migration/workers/filter-dsl.ts";
import { COLLECTIONS } from "../../migration/workers/src/api/schema.ts";
import { FakeD1 } from "../../migration/workers/test/fake-d1.ts";
import { installChrome } from "./chrome_mock.mjs";

const harness = installChrome();
globalThis.fetch = async () => ({ ok: false, status: 0, json: async () => ({}), text: async () => "" });
const { claimJob } = await import("../background.js");
await new Promise((resolve) => setTimeout(resolve, 20));

let db;
let refused;
let lost;
let patches;
const OWNER = "owner-1";
const ME = "agent-1";
const reply = (body, status = 200) => ({
  ok: status >= 200 && status < 300, status,
  json: async () => body, text: async () => JSON.stringify(body),
});
function reset() {
  db?.db.close();
  db = new FakeD1();
  refused = new Set();
  lost = new Set();
  patches = [];
  for (const key of Object.keys(harness.storageData)) delete harness.storageData[key];
  Object.assign(harness.storageData, {
    backendUrl: "http://127.0.0.1:8090", agentId: ME, agentToken: "fixture-token",
    ownerRef: OWNER, paired: true,
  });
}
function seed(id, lane = "", owner = OWNER, order = 0) {
  const now = new Date(Date.now() - 60000 + order * 1000).toISOString();
  const params = JSON.stringify({ task: `do ${id}`, _workflow: {
    plan_id: `plan-${id}`, owner_ref: owner, lineage_key: `lin-${id}`,
    version: 1, goal: `do ${id}`, consequence: "read_only", state: "queued",
    scope_digest: "sd", effect_key: `ek-${id}`, facts: {}, required: [],
    approval: null, lease: null, receipt: null, attempts: 0,
  } });
  db.db.prepare(`INSERT INTO jobs
    (id, created, updated, goal, params, status, owner_ref, lane, claimed_by,
     claimed_at, attempts, workflow_id, workflow_version, workflow_state,
     consequence, lineage_key, lease_token, lease_until, device_id)
    VALUES (?, ?, ?, ?, ?, 'queued', ?, ?, '', '', 0, ?, 1, 'queued',
            'read_only', ?, '', '', 'fixture')`)
    .run(id, now, now, `do ${id}`, params, owner, lane, `plan-${id}`, `lin-${id}`);
}
globalThis.fetch = async (raw, opts = {}) => {
  const url = new URL(String(raw));
  if (url.pathname === "/api/collections/jobs/records") {
    const filter = compileFilter(parseFilter(url.searchParams.get("filter")),
      { schema: COLLECTIONS.jobs.columns });
    const limit = Number(url.searchParams.get("perPage") || 30);
    return reply({ items: db.rows(`SELECT * FROM jobs WHERE ${filter.sql}
      ORDER BY created, id LIMIT ?`, ...filter.params, limit) });
  }
  if (url.pathname.startsWith("/api/collections/jobs/records/") && opts.method === "PATCH") {
    const id = url.pathname.split("/").at(-1);
    const body = JSON.parse(opts.body);
    patches.push({ id, body });
    const [row] = db.rows("SELECT * FROM jobs WHERE id = ?", id);
    if (row.lane === "device_calendar" || refused.has(id)) return reply({ message: "claim refused" }, 403);
    if (lost.has(id)) return reply({ ...row, ...body, claimed_by: "other-browser", lease_token: "other-lease" });
    return reply({ ...row, ...body });
  }
  return reply({});
};

let failures = 0;
async function check(name, run) {
  try { reset(); await run(); console.log(`PASS: ${name}`); }
  catch (error) { failures++; console.error(`FAIL: ${name}\n${error.stack}`); }
}

await check("ten phone jobs cannot starve the browser job behind them", async () => {
  for (let i = 0; i < 10; i++) seed(`device${i}`, "device_calendar", OWNER, i);
  seed("browser", "", OWNER, 20);
  seed("stranger", "", "owner-2", -1);
  const job = await claimJob();
  assert.equal(job?.id, "browser");
  assert.deepEqual(patches.map((p) => p.id), ["browser"], "the phone's rows must never be written by this browser");
  assert.equal(harness.storageData.currentJob.id, "browser");
});

await check("a supervised read with workflow metadata cannot enter the action runner", async () => {
  seed("supervised", "supervised_read", OWNER, 0);
  seed("browser", "", OWNER, 1);
  assert.equal((await claimJob())?.id, "browser");
  assert.deepEqual(patches.map((p) => p.id), ["browser"]);
});

await check("a rejected claim cannot display work this browser does not own", async () => {
  seed("refused");
  refused.add("refused");
  const previous = { id: "completed", status: "done", result: "Previous result" };
  harness.storageData.currentJob = previous;
  assert.equal(await claimJob(), null);
  assert.deepEqual(harness.storageData.currentJob, previous);
});

await check("a concurrent claim winner cannot leave a false picking-up card", async () => {
  seed("lost");
  lost.add("lost");
  assert.equal(await claimJob(), null);
  assert.equal(harness.storageData.currentJob, undefined);
});

await check("a lost claim still leaves the next runnable row available", async () => {
  seed("lost", "", OWNER, 0);
  seed("browser", "", OWNER, 1);
  lost.add("lost");
  assert.equal((await claimJob())?.id, "browser");
  assert.equal(harness.storageData.currentJob.id, "browser");
});

db.db.close();
if (failures) process.exitCode = 1;
else console.log("test_browser_queue_ownership: all 5 scenarios passed");
