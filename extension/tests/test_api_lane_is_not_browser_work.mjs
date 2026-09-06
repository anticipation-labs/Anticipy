// THE API LANE IS NOT BROWSER WORK — the extension's half.
//
// Run: node extension/tests/test_api_lane_is_not_browser_work.mjs
//
// THE DEFECT, measured 2026-09-06: this worker polled
//   workflow_id!="" && lane!="research"
// It names `lane`, so the server's research_lane leg 1 appends nothing to it,
// and it excludes ONLY research — so an api-lane row (brain/hands.py LANE_API:
// the row brain/worker.py run_api_jobs claims and the Worker's /hands/api/run
// executes) was LISTED here, claimed here, and run through the browser
// vocabulary whenever this browser polled before the brain. The api hand was
// bypassed every time.
//
// TWO LAYERS, and this file is the COURTESY, not the floor. The floor is
// migration/workers/src/policy/research_lane.ts, which now refuses a non-worker
// claim on lane "api" whatever this filter says; its proof is
// migration/workers/test/api-lane-claim.test.ts, and that proof also reads THIS
// file's BROWSER_LANE out of the source and lists with it end to end. This
// file proves the courtesy on its own: the exact filter string claimJob and
// the stale sweep send, parsed by the server's own filter DSL and run over the
// server's own schema in SQLite — so the two suites cannot disagree about what
// one string means.
//
// EVERY REFUSAL HAS A CONTROL: the same poll still lists the browser lane's own
// row, and the 2026-09-06 filter — held here as a literal on purpose — still
// lists the api row through the same pipe. That is the reproduction, kept.
//
// MUTATIONS THIS FILE MUST GO RED ON:
//   * `lane!="api"` leaves BROWSER_LANE (the poll lists the api row);
//   * a second `lane!="api"` appears anywhere (two definitions — the drift
//     that silenced the queue in 2026-08, see test_hunt_round2.mjs).
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";
import { dirname, join } from "node:path";
import { installChrome } from "./chrome_mock.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const workers = join(here, "..", "..", "migration", "workers");
const bg = readFileSync(join(here, "..", "background.js"), "utf8");

// THE SERVER'S OWN PARSER, SCHEMA AND FAKE D1. Node strips the types natively
// (CI pins Node 24 — .github/workflows/system-invariants.yml), the same way
// the worker suite itself runs. Nothing here re-implements what a filter means.
const dsl = await import(pathToFileURL(join(workers, "filter-dsl.ts")).href);
const { COLLECTIONS } = await import(pathToFileURL(join(workers, "src", "pb", "schema.ts")).href);
const { FakeD1 } = await import(pathToFileURL(join(workers, "test", "fake-d1.ts")).href);

let passes = 0;
let failures = 0;
function check(what, fn) {
  try { fn(); passes++; console.log(`  ok    ${what}`); }
  catch (e) { failures++; console.error(`  FAIL  ${what}\n        ${e.message}`); }
}

// ---------------------------------------------------------------- the probe
const OWNER = "owner-1";
const STRANGER = "owner-2";
const NOW = "2026-09-06 12:00:00.000Z";

/**
 * Which lanes a filter lists, decided by the server's compiler over the
 * server's schema. One row per lane for the owner, plus a stranger's api row;
 * `status` seeds every row so the sweep's running poll can be probed too.
 */
function listedLanes(filter, status = "queued") {
  const db = new FakeD1();
  const rows = [
    ["jobbrw000000001", "", "wf-brw", OWNER],
    ["jobres000000001", "research", "wf-res", OWNER],
    ["jobapi000000001", "api", "wf-api", OWNER],
    ["jobsup000000001", "supervised_read", "", OWNER],      // never carries a plan
    ["jobdev000000001", "device_calendar", "wf-dev", OWNER],
    ["jobapi000000002", "api", "wf-api2", STRANGER],
  ];
  for (const [id, lane, wf, owner] of rows) {
    db.db.exec(`INSERT INTO jobs (id, created, updated, goal, params, status, owner_ref, lane,
                  claimed_by, claimed_at, attempts, workflow_id, device_id)
                VALUES ('${id}', '${NOW}', '${NOW}', 'g', '{}', '${status}', '${owner}', '${lane}',
                        '', '', 0, '${wf}', 'anticipy')`);
  }
  const c = dsl.compileFilter(dsl.parseFilter(filter), { schema: COLLECTIONS.jobs.columns });
  return db.rows(`SELECT id, lane FROM jobs WHERE ${c.sql} ORDER BY id`, ...c.params);
}
const lanesOf = (rows) => rows.map((r) => r.lane);

// ------------------------------------------- what the shipped worker sends
const harness = installChrome();
globalThis.chrome.storage.session = { get: async () => ({}), set: async () => {} };
globalThis.fetch = async () => ({ ok: false, status: 0, json: async () => ({}), text: async () => "" });
const { claimJob } = await import("../background.js");
// The module polls on import, exactly as the real worker does on boot. Let it
// settle so its dead-fetch cycle cannot land in the middle of a case below.
await new Promise((r) => setTimeout(r, 20));

const BASE = "http://127.0.0.1:8090";
Object.assign(harness.storageData, {
  backendUrl: BASE, agentId: "agent-1", agentToken: "t".repeat(64), ownerRef: OWNER, paired: true,
});

const reply = (body, status = 200) => ({
  ok: status >= 200 && status < 300, status,
  json: async () => body, text: async () => JSON.stringify(body),
});
const polls = [];  // every jobs-list filter this worker sent, decoded, in order
globalThis.fetch = async (url, opts = {}) => {
  const u = new URL(String(url));
  if (u.pathname === "/api/collections/jobs/records" && (opts.method || "GET") === "GET") {
    polls.push(u.searchParams.get("filter") || "");
    return reply({ items: [] });
  }
  return reply({});
};

await claimJob();
const claimPoll = polls.find((f) => /status="queued"/.test(f) && !/lane="supervised_read"/.test(f));
assert.ok(claimPoll, `claimJob sent no queued poll; saw: ${JSON.stringify(polls)}`);

// The sweep is not exported; the alarm is how the real worker reaches it.
polls.length = 0;
harness.fireAlarm("anticipy-poll");
await new Promise((r) => setTimeout(r, 100));
const sweepPoll = polls.find((f) => /status="running"/.test(f));
assert.ok(sweepPoll, `the poll cycle sent no running sweep; saw: ${JSON.stringify(polls)}`);

// The filter every extension shipped up to 2026-09-06 sent. A literal ON
// PURPOSE: it is the reproduction, and it has to keep reproducing.
const LANE_2026_09_06 = 'workflow_id!="" && lane!="research"';
const poll2026 = `status="queued" && owner_ref="${OWNER}" && ${LANE_2026_09_06}`;

// ---------------------------------------------------------------- the legs

check("the claim poll, through the server's own parser, lists no api row", () => {
  const rows = listedLanes(claimPoll);
  assert.ok(!lanesOf(rows).includes("api"), `api listed by ${claimPoll}: ${JSON.stringify(rows)}`);
});

check("...and no research row (the neighbour exclusion survived)", () => {
  assert.ok(!lanesOf(listedLanes(claimPoll)).includes("research"), claimPoll);
});

check("CONTROL: the same poll still lists the browser lane's own row, and only the owner's", () => {
  const rows = listedLanes(claimPoll);
  assert.ok(rows.some((r) => r.id === "jobbrw000000001"), `the browser lost its own lane: ${claimPoll}`);
  assert.ok(!rows.some((r) => r.id === "jobapi000000002"), "a stranger's row came back");
});

check("REPRODUCTION, kept: the 2026-09-06 filter DID list the api row through this same pipe", () => {
  const rows = listedLanes(poll2026);
  assert.ok(rows.some((r) => r.id === "jobapi000000001"),
    `the probe cannot see an api row at all, so the legs above prove nothing: ${JSON.stringify(rows)}`);
});

check("the poll NAMES lane, so the server's leg-1 rewrite appends nothing — this mirror is load-bearing", () => {
  assert.ok(dsl.mentionsField(dsl.parseFilter(claimPoll), "lane"));
  assert.ok(dsl.mentionsField(dsl.parseFilter(sweepPoll), "lane"));
});

check("the stale sweep takes its lanes from the same definition: a running api row is not this browser's to requeue", () => {
  const rows = listedLanes(sweepPoll, "running");
  assert.ok(!lanesOf(rows).includes("api"), `the sweep would touch a running api row: ${sweepPoll}`);
  assert.ok(!lanesOf(rows).includes("research"), sweepPoll);
  assert.ok(rows.some((r) => r.id === "jobbrw000000001"), "CONTROL: the sweep lost the browser lane");
});

check("MEASURED, NOT ENDORSED: a device_calendar row with a plan is still listed here", () => {
  // The server refuses that claim ("a calendar errand happens on your phone,
  // never in a browser"), so it costs a warn line per poll, not a wrong hand.
  // Recorded so the day it changes is a visible day; the day the filter names
  // that lane too, delete this leg.
  assert.ok(lanesOf(listedLanes(claimPoll)).includes("device_calendar"), claimPoll);
});

check('`lane!="api"` occurs EXACTLY ONCE in background.js — one definition, the mutation literal', () => {
  assert.equal(bg.split('lane!="api"').length - 1, 1);
  const m = bg.match(/const BROWSER_LANE = '([^']+)';/);
  assert.ok(m, "BROWSER_LANE moved");
  assert.ok(m[1].includes('lane!="research"') && m[1].includes('lane!="api"'),
    `BROWSER_LANE names both lanes: ${m[1]}`);
  assert.ok(m[1].includes('workflow_id!=""'), "the unplanned-row exclusion fell out");
});

check("the floor exists and reads this file's filter out of the source", () => {
  const twin = join(workers, "test", "api-lane-claim.test.ts");
  assert.ok(existsSync(twin), "the server-side proof is gone");
  const src = readFileSync(twin, "utf8");
  assert.ok(/BROWSER_LANE = '\(\[\^'\]\+\)'/.test(src) || src.includes("shippedBrowserLane"),
    "the server proof no longer measures the shipped extension filter");
});

// ---------------------------------------------------------------------------
if (failures) {
  console.error(`test_api_lane_is_not_browser_work: ${passes} passed, ${failures} FAILED`);
  process.exit(1);
}
console.log(`test_api_lane_is_not_browser_work: all ${passes} passed — the api lane is the worker's, and this browser does not list it`);
