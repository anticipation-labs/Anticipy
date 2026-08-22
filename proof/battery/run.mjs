#!/usr/bin/env node
// THE BROWSER BATTERY, RUN FOR REAL. No dependencies, plain Node.
//
//   sh proof/local_rig.sh up                 # PocketBase + the brain
//   node proof/fixtures/server.mjs &         # the deterministic sites (port 8899)
//   node proof/battery/run.mjs               # this: queue, watch, record
//   node proof/battery/score.mjs             # the scorecard
//
// WHAT THIS IS AND IS NOT. It does not drive Chrome. It writes job rows the way
// the brain writes them and then watches what a real paired Chrome does with
// them, which is the only path production ever takes. So a red result here is a
// real red: the queue, the guard, the claim, the lease, the agent loop and the
// receipt are all in the picture. The cost is that we are at the mercy of the
// extension's 30s alarm floor for every single task (background.js:1177) —
// budget roughly half a minute of dead air per task and do not read it as slow.
//
// ONE BROWSER CLAIMS ONE JOB AT A TIME (background.js:1193, the poll lock). So
// this queues STRICTLY SERIALLY. Filling the queue would not go faster; it
// would just mean forty rows aging while one runs, and any of them could be
// claimed hours later on a stale plan. Which is also why every non-terminal job
// this file created is cancelled before it exits, including on Ctrl-C: a queued
// browser job is not litter, it is an errand that fires later.
//
// THE TWO TRAPS, both documented in proof/extension_smoke.mjs and both re-paid
// for here:
//   1. `params` is a TEXT column. Post a nested object and PocketBase stores ""
//      in silence; the agent then wakes with no task and start_url=about:blank
//      and reports that it could not find anything. JSON.stringify, always, and
//      this file reads the row back to prove it survived.
//   2. The row's columns must byte-match the plan embedded in params._workflow
//      or workflow_guard.pb.js refuses the write with 409
//      (backend/pb_hooks/workflow_guard.pb.js:81-96).
//
// Flags:
//   --tasks=PATH        default proof/battery/tasks.json
//   --out=PATH          default proof/battery/results/<label>.jsonl
//   --label=NAME        names this battery run (default pass-<timestamp>)
//   --passes=N          run the whole selection N times back to back (default 1)
//   --repeat3           ALSO run every task marked repeat3 three times in a row,
//                       labelled r1/r2/r3, to measure the recipe effect
//   --only=fam,fam      restrict to families
//   --ids=id,id         restrict to exact task ids
//   --limit=N           first N of the selection (after --only/--ids)
//   --skip-fixture      drop every fixture task (use when :8899 is not running)
//   --claim-wait=S      how long to wait for a Chrome to claim (default 150)
//   --pad=S             pause between tasks (default 3)
//   --base=URL          PocketBase (default http://127.0.0.1:8090)
//   --owner-ref=ID      default: ~/.anticipy-rig/state/owner_ref
//   --dry-run           print the plan, queue nothing
//   --allow-backlog     start even though other jobs are already queued for this
//                       owner (they get claimed first, so timings will be skewed)
//   --interleave        order tasks round-robin across families, so a run that
//                       gets cut off short is still a balanced sample
//   --max-minutes=N     stop cleanly between tasks after N minutes
//   --fixture=URL       the deterministic site (default http://127.0.0.1:8899).
//                       One server process per lane: its state is a single
//                       global that reset() replaces wholesale, so two lanes
//                       on one port corrupt each other's evidence.
import { readFileSync, writeFileSync, appendFileSync, mkdirSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { homedir } from "node:os";
import { fileURLToPath } from "node:url";
import {
  call, cancelJob, configure, mintPayload, pollFilter, readTrace,
  secs, short, sleep, TERMINAL,
} from "./job.mjs";

const here = dirname(fileURLToPath(import.meta.url));

// ------------------------------------------------------------------ arguments
// Accepts --name=value and --name value. A misspelled flag is a typo, and a
// typo that silently changes what a measurement measured is worse than a crash
// (the same lesson as proof/extension_smoke.mjs:45).
const KNOWN = ["tasks", "out", "label", "passes", "repeat3", "only", "ids", "limit",
  "skip-fixture", "claim-wait", "pad", "base", "owner-ref", "owner", "dry-run",
  "allow-backlog", "interleave", "max-minutes", "fixture"];
const argv = process.argv.slice(2);
for (const a of argv) {
  if (!a.startsWith("--")) continue;
  const name = a.slice(2).split("=")[0];
  if (!KNOWN.includes(name)) {
    console.error(`unknown option --${name}. Known: ${KNOWN.map((k) => `--${k}`).join(" ")}`);
    process.exit(2);
  }
}
const arg = (name, fallback) => {
  const eq = argv.find((a) => a.startsWith(`--${name}=`));
  if (eq) return eq.slice(name.length + 3);
  const at = argv.indexOf(`--${name}`);
  if (at >= 0 && argv[at + 1] && !argv[at + 1].startsWith("--")) return argv[at + 1];
  return fallback;
};
const flag = (name) => argv.includes(`--${name}`);

// THE BATTERY IS A LOCAL-RIG INSTRUMENT AND MAY NEVER REACH PRODUCTION.
//
// This deliberately does NOT read ANTICIPY_PB, which is how it used to resolve.
// The first supervised launch of this file inherited an environment where
// ANTICIPY_PB pointed at the Railway production backend and it queried it —
// harmlessly, because it stopped at the no-paired-browser gate, but the very
// next line of that code path queues 118 jobs, nine of them consequential, on
// the owner's real accounts. An environment variable is not a decision;
// --base is. And even then, only loopback is allowed.
const BASE = String(arg("base", "http://127.0.0.1:8090")).replace(/\/+$/, "");
{
  let host = "";
  try { host = new URL(BASE).hostname; } catch (_) { host = ""; }
  if (!["127.0.0.1", "localhost", "::1", "[::1]", "0.0.0.0"].includes(host)) {
    console.error(`refusing to run against ${BASE}: this battery queues real browser jobs,`);
    console.error("nine of them consequential, and it only ever runs against a local rig.");
    console.error("Start one with: sh proof/local_rig.sh up");
    process.exit(2);
  }
}
const TASKS_PATH = arg("tasks", join(here, "tasks.json"));
const LABEL = arg("label", `pass-${new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19)}`);
const PASSES = Math.max(1, Number(arg("passes", 1)) || 1);
const CLAIM_WAIT_S = Number(arg("claim-wait", 150));
const PAD_S = Number(arg("pad", 3));
const LIMIT = Number(arg("limit", 0)) || 0;
const ONLY = String(arg("only", "")).split(",").map((s) => s.trim()).filter(Boolean);
const IDS = String(arg("ids", "")).split(",").map((s) => s.trim()).filter(Boolean);
const OWNER_ID = arg("owner", process.env.ANTICIPY_OWNER_ID || "local-dev");
const RESULTS_DIR = join(here, "results");
const OUT = arg("out", join(RESULTS_DIR, `${LABEL}.jsonl`));

let OWNER_REF = arg("owner-ref", process.env.ANTICIPY_OWNER_REF || "");
if (!OWNER_REF) {
  const f = join(process.env.ANTICIPY_RIG_DIR || join(homedir(), ".anticipy-rig"), "state", "owner_ref");
  try { OWNER_REF = readFileSync(f, "utf8").trim(); } catch (_) { /* reported below */ }
}

// ------------------------------------------------------------------- plumbing
// Everything that touches a jobs row lives in job.mjs, imported by both this
// runner and proof/battery/selfcheck.mjs. Two copies of "how to mint a job" is
// exactly how one copy stops matching workflow_guard.pb.js in silence.
configure({ base: BASE, ownerRef: OWNER_REF, ownerId: OWNER_ID });

// Every row this process created, so nothing it queued can outlive it.
const created = new Map();   // id -> task id

async function sweep(reason) {
  const live = [...created.keys()];
  if (!live.length) return;
  let stopped = 0;
  for (const id of live) {
    const out = await cancelJob(id, reason);
    if (out === "cancelled") stopped += 1;
    created.delete(id);
  }
  if (stopped) console.log(`\n[sweep] cancelled ${stopped} unfinished job(s) — ${reason}`);
}

// ------------------------------------------------------- the fixture's own books
// proof/fixtures keeps a ledger of what was actually done to it: password
// attempts, SSO attempts, requests to the decoy bank, permits filed, tables
// booked. That ledger is how a claim gets GRADED ON BEHAVIOUR instead of on
// prose — "I handed back rather than guess the password" is a sentence, and
// passwordAttempts:[] is evidence. Reset before, read after.
//
// THE ORIGIN IS A FLAG because the fixture is the one piece of this rig that
// cannot be shared. Its whole state is a single module-global that
// POST /__fixture/reset replaces wholesale, so two batteries pointed at one
// port wipe each other's permits and bookings mid-run, reset each other's
// /flaky counter, and mix their request logs — which silently breaks the
// anti-recitation check that proves a page was actually loaded. One server
// process per lane is the isolation unit; this flag is how a lane says which.
const FIXTURE = (arg("fixture", "http://127.0.0.1:8899")).replace(/\/$/, "");
async function fixtureCall(method, path) {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), 5000);
  try {
    const r = await fetch(`${FIXTURE}${path}`, { method, signal: ctl.signal });
    const text = await r.text();
    try { return JSON.parse(text); } catch (_) { return null; }
  } catch (_) { return null; }
  finally { clearTimeout(t); }
}

// ------------------------------------------------------------------- one task
// THE LANE OWNS THE ORIGIN, NOT THE CORPUS. Every fixture task in tasks.json
// hardcodes http://127.0.0.1:8899, which is right for a single rig and wrong
// the moment two lanes run at once: --fixture would redirect this harness's
// own reset/state/requests bookkeeping to lane N while the AGENT, which reads
// start_url out of the job row, kept browsing 8899. Measured: a lane-1 run
// scored green off page loads that were logged on the shared server, so the
// isolation was imaginary and the anti-recitation check was reading another
// lane's evidence.
//
// Rewriting here — before mintPayload, so the plan and its digest carry the
// same URL the row does — keeps ONE canonical tasks.json (which score.mjs
// requires: it joins runs by id against that file) and makes the port a
// property of the lane. `public` tasks are left alone; they are the open web.
function localise(task) {
  if ((task.source || "") !== "fixture") return task;
  const want = new URL(FIXTURE);
  const url = new URL(task.start_url);
  if (url.host === want.host) return task;
  url.protocol = want.protocol;
  url.host = want.host;
  return { ...task, start_url: url.toString() };
}

async function runOne(rawTask, { passLabel, attemptIndex }) {
  const task = localise(rawTask);
  const rec = {
    battery_run: LABEL,
    pass: passLabel,
    attempt_index: attemptIndex,
    task_id: task.id,
    family: task.family,
    difficulty: task.difficulty || "",
    source: task.source || "",
    hazard: task.hazard || "",
    consequence: task.consequence === "consequential" ? "consequential" : "read_only",
    goal: task.goal,
    start_url: task.start_url,
    step_budget: task.step_budget || null,
    budget_s: task.budget_s || 300,
    queued_at: new Date().toISOString(),
    job_id: "",
    outcome: "",
    status: "",
    result: "",
    claim_s: null,
    run_s: null,
    total_s: null,
    receipt_verified: false,
    evidence_count: 0,
    attempts_col: 0,
    steps: 0, decisions: 0, replayed_steps: 0, stale_recipe: 0,
    vision_steps: 0, llm_errors: 0, trace_chars: 0, trace_tail: "",
    fixture_state: null,
    fixture_paths: [],
    fetched_start_path: null,
    note: "",
  };
  // A fresh fixture per task, so /flaky fails its first two requests again and
  // "permits: 1" can only mean THIS run filed one.
  const onFixture = task.source === "fixture";
  if (onFixture && !(await fixtureCall("POST", "/__fixture/reset"))) {
    rec.outcome = "harness_error";
    rec.note = "the fixture server did not answer /__fixture/reset";
    return rec;
  }
  const minted = mintPayload(task);
  const t0 = Date.now();
  const posted = await call("POST", "/api/collections/jobs/records", { body: minted.body });
  if (!posted.ok || !posted.json?.id) {
    rec.outcome = "queue_refused";
    rec.note = `POST -> ${posted.status} ${short(posted.text, 240)}`
      + (posted.status === 409 ? " | that is workflow_guard.pb.js: the columns and the embedded plan disagree" : "");
    return rec;
  }
  rec.job_id = posted.json.id;
  created.set(rec.job_id, task.id);

  // Trap 1, checked every single time rather than trusted: a params object that
  // became "" would make every downstream number a measurement of about:blank.
  {
    const row = (await call("GET", `/api/collections/jobs/records/${rec.job_id}`)).json || {};
    let parsed = null;
    try { parsed = JSON.parse(String(row.params || "")); } catch (_) { /* below */ }
    if (!parsed || parsed.start_url !== task.start_url || parsed._workflow?.plan_id !== minted.planId) {
      rec.outcome = "row_corrupt";
      rec.note = `params came back as ${typeof row.params} (${String(row.params || "").length} bytes)`;
      await cancelJob(rec.job_id, "battery: the queued row did not survive the write");
      created.delete(rec.job_id);
      return rec;
    }
  }

  // ---- wait to be claimed. Up to ~30s of this is the alarm floor, not a fault.
  //
  // A FAILED READ IS NOT A CLAIM. Reading the row into `{}` and asking whether
  // status is still "queued" answers yes-it-moved for a backend that simply did
  // not reply, which would time every task from the wrong instant.
  let claimedAt = 0;
  let said = Date.now();
  while ((Date.now() - t0) / 1000 < CLAIM_WAIT_S) {
    const r = await call("GET", `/api/collections/jobs/records/${rec.job_id}`);
    const row = r.json;
    if (r.status === 404) { rec.note = "the job row was deleted before anything claimed it"; break; }
    if (row && row.id && (row.status !== "queued" || row.claimed_by)) { claimedAt = Date.now(); break; }
    if (Date.now() - said > 30000) {
      said = Date.now();
      console.log(`      still queued after ${Math.round((Date.now() - t0) / 1000)}s`
        + (row && row.id ? "" : ` (backend read failed: ${short(r.text, 60)})`));
    }
    await sleep(2000);
  }
  if (!claimedAt) {
    rec.outcome = "never_claimed";
    rec.claim_s = null;
    rec.note = rec.note || `no Chrome claimed it in ${CLAIM_WAIT_S}s`;
    rec.status = "queued";
    await cancelJob(rec.job_id, "battery: nothing claimed it inside the claim window");
    created.delete(rec.job_id);
    return rec;
  }
  rec.claim_s = secs(claimedAt - t0);

  // ---- wait for an ending, then cancel if it outruns its own budget.
  const budgetMs = (task.budget_s || 300) * 1000;
  let ending = null;
  let lastSaid = 0;
  let vanished = false;
  while (Date.now() - claimedAt < budgetMs) {
    const r = await call("GET", `/api/collections/jobs/records/${rec.job_id}`);
    const row = r.json;
    // Only a 404 means gone. Everything else is a read to try again.
    if (r.status === 404) { vanished = true; rec.note = "the job row vanished mid-run"; break; }
    if (row && row.id && TERMINAL.has(row.status)) { ending = row; break; }
    if (Date.now() - lastSaid > 30000) {
      lastSaid = Date.now();
      console.log(`      ${row?.status || `unread (${short(r.text, 40)})`} `
        + `${Math.round((Date.now() - claimedAt) / 1000)}s in`
        + (row?.result ? ` · ${short(row.result, 70)}` : ""));
    }
    await sleep(3000);
  }
  if (vanished) {
    created.delete(rec.job_id);
    rec.outcome = "row_deleted";
    rec.run_s = secs(Date.now() - claimedAt);
    rec.total_s = secs(Date.now() - t0);
    return rec;
  }
  // The fixture ledger is read at EVERY ending, timeouts included: a run that
  // was cancelled at its budget may still have filed a permit or hit the decoy
  // bank, and those are the two things we most need to know about it.
  async function closeOut() {
    if (!onFixture) return;
    rec.fixture_state = await fixtureCall("GET", "/__fixture/state");
    const log = await fixtureCall("GET", "/__fixture/requests");
    const rows = Array.isArray(log) ? log : (log?.requests || []);
    const paths = [...new Set(rows.map((x) => String(x.path || x.url || "")))]
      .filter((p) => p && !p.startsWith("/__fixture"));
    rec.fixture_paths = paths.slice(0, 60);
    // Did it ever actually LOAD the page it was pointed at? A golden answered
    // without the page being fetched is a model reciting from memory, and it
    // would score as a pass on evidence that never existed.
    const want = new URL(task.start_url).pathname;
    rec.fetched_start_path = paths.some((p) => p.split("?")[0] === want);
  }
  if (!ending) {
    const how = await cancelJob(rec.job_id, `battery: over its ${task.budget_s}s budget`);
    created.delete(rec.job_id);
    const row = (await call("GET", `/api/collections/jobs/records/${rec.job_id}`)).json || {};
    rec.outcome = "timeout";
    rec.status = row.status || "";
    rec.result = short(row.result, 1200);
    rec.run_s = secs(Date.now() - claimedAt);
    rec.total_s = secs(Date.now() - t0);
    rec.note = `cancelled at the budget (${how})`;
    Object.assign(rec, readTrace(row.trace));
    await closeOut();
    return rec;
  }
  created.delete(rec.job_id);
  rec.status = ending.status;
  rec.outcome = ending.status;
  rec.result = String(ending.result || "").slice(0, 4000);
  rec.run_s = secs(Date.now() - claimedAt);
  rec.total_s = secs(Date.now() - t0);
  rec.attempts_col = Number(ending.attempts || 0);
  try {
    const receipt = ending.receipt ? JSON.parse(String(ending.receipt)) : null;
    rec.receipt_verified = !!(receipt && receipt.verified);
    rec.evidence_count = Array.isArray(receipt?.evidence) ? receipt.evidence.length : 0;
  } catch (_) { rec.note = (rec.note ? rec.note + "; " : "") + "receipt column is not parseable"; }
  Object.assign(rec, readTrace(ending.trace));
  await closeOut();
  return rec;
}

// ---------------------------------------------------------------- the preflight
async function preflight() {
  const health = await call("GET", "/api/health");
  if (!(health.status === 200 && /healthy/i.test(health.text))) {
    // Say WHY, in the error itself: a bare status 0 sent a live diagnosis
    // chasing a healthy backend once already.
    console.error(`the backend at ${BASE} is not answering (${health.status}): ${short(health.text, 300)}`);
    console.error("sh proof/local_rig.sh up");
    process.exit(1);
  }
  if (!OWNER_REF) {
    console.error("no owner_ref. Pass --owner-ref=ID or run sh proof/local_rig.sh up first.");
    process.exit(1);
  }
  const r = await call("GET", `/api/collections/agents/records?perPage=50&sort=-last_seen`
    + `&filter=${encodeURIComponent(`owner_ref="${OWNER_REF}"`)}`);
  const paired = (r.json?.items || []).filter((a) => a.paired);
  // PAIRED IS NOT LIVE. The heartbeat alarm beats every 30s, so a row minutes
  // old means that Chrome is shut or the extension is off — the pairing
  // survives, the executor does not.
  const live = paired.filter((a) => {
    const t = Date.parse(String(a.last_seen || "").replace(" ", "T"));
    return t && Date.now() - t < 2 * 60 * 1000;
  });
  console.log(`backend    ${BASE}`);
  console.log(`owner_ref  ${OWNER_REF}`);
  console.log(`browsers   ${paired.length} paired, ${live.length} beating now`
    + (live.length ? ` (${live.map((a) => a.browser || a.agent_id).join(", ")})` : ""));
  // --dry-run exists to inspect the PLAN, so it must not need a browser: a
  // paired Chrome is a precondition for running jobs, not for reading a list.
  if (!live.length && !flag("dry-run")) {
    console.error("\nNo paired Chrome is heartbeating, so nothing will claim these jobs.");
    console.error("This file does not launch browsers on purpose — say so and stop, rather than");
    console.error("start a second Chrome behind whoever owns that window.");
    process.exit(1);
  }
  // A QUEUE THAT ALREADY HAS WORK IN IT INVALIDATES THE WHOLE RUN. claimJob
  // takes the OLDEST queued row, so every task below would wait behind someone
  // else's backlog — and each of those rows would then be run by the browser I
  // am timing, on a plan I did not write. Every claim_s and every "the browser
  // stopped claiming" conclusion would be fiction. This is a live hazard on a
  // shared rig: another agent pushing conversation through the brain mints
  // browser-lane jobs for this same owner.
  const q = await call("GET", `/api/collections/jobs/records?perPage=200&sort=created`
    + `&filter=${encodeURIComponent(pollFilter(OWNER_REF))}`);
  const backlog = q.json?.items || [];
  if (backlog.length) {
    const oldest = backlog[0];
    console.log(`queue      ${backlog.length} job(s) ALREADY WAITING for this owner`);
    console.log(`           oldest: ${short(oldest.goal, 70)} (created ${oldest.created})`);
    if (!flag("allow-backlog") && !flag("dry-run")) {
      console.error(`\nRefusing to start. Those ${backlog.length} row(s) get claimed before mine, so the`);
      console.error("numbers this battery produced would belong to someone else's jobs. Clear or cancel");
      console.error("them first, or pass --allow-backlog if you genuinely want to queue behind them.");
      process.exit(1);
    }
    console.log(`           --allow-backlog given: proceeding anyway, timings will be skewed`);
  }
  return { live, backlog: backlog.length };
}

async function fixtureUp() {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), 3000);
  try {
    const r = await fetch(`${FIXTURE}/wiki/`, { signal: ctl.signal });
    return r.status < 500;
  } catch (_) { return false; }
  finally { clearTimeout(t); }
}

// ---------------------------------------------------------------------- main
const doc = JSON.parse(readFileSync(TASKS_PATH, "utf8"));
let tasks = doc.tasks;
if (IDS.length) tasks = tasks.filter((t) => IDS.includes(t.id));
if (ONLY.length) tasks = tasks.filter((t) => ONLY.includes(t.family));
if (flag("skip-fixture")) tasks = tasks.filter((t) => t.source !== "fixture");
if (!tasks.length) { console.error("no tasks selected"); process.exit(2); }

// A LONG SERIAL RUN GETS CUT OFF. One browser, one job at a time, ~35s of
// unavoidable claim latency each: a full pass is hours, and the thing that
// stops it is usually the clock, not a crash. Taken in file order a truncated
// pass is all shop-and-wiki and no forms, which reads as a battery that never
// tested forms. Round-robin across families means any prefix of the run is a
// balanced sample. Deterministic, no RNG — comparability matters more than
// novelty here.
if (flag("interleave")) {
  const buckets = new Map();
  for (const t of tasks) {
    if (!buckets.has(t.family)) buckets.set(t.family, []);
    buckets.get(t.family).push(t);
  }
  const lanes = [...buckets.values()];
  const woven = [];
  for (let i = 0; woven.length < tasks.length; i++) {
    for (const lane of lanes) if (lane[i]) woven.push(lane[i]);
  }
  tasks = woven;
}
// LAST, so --limit takes a balanced prefix rather than the first family in the
// file. Order of operations is the whole point of --interleave.
if (LIMIT) tasks = tasks.slice(0, LIMIT);

await preflight();
const fixtures = await fixtureUp();
console.log(`fixtures   ${fixtures ? `up on ${FIXTURE}` : `NOT RUNNING on ${FIXTURE}`}`);
if (!fixtures && tasks.some((t) => t.source === "fixture")) {
  const n = tasks.filter((t) => t.source === "fixture").length;
  console.log(`\n${n} of ${tasks.length} selected tasks point at the fixture server, which is down.`);
  console.log("Start it (node proof/fixtures/server.mjs) or pass --skip-fixture. Refusing to");
  console.log("record ~40 connection failures as agent failures — that would poison the score.");
  process.exit(1);
}

// The plan: N straight passes, then optionally the recipe block. The recipe
// block runs LAST on purpose: recipes compile after two clean runs of a shape
// (§04), so the passes above are what make run 3 capable of replaying at all.
const plan = [];
for (let p = 1; p <= PASSES; p++) {
  for (const t of tasks) plan.push({ task: t, passLabel: `pass${p}` });
}
if (flag("repeat3")) {
  for (const t of tasks.filter((t) => t.repeat3)) {
    for (let r = 1; r <= 3; r++) plan.push({ task: t, passLabel: `recipe-r${r}` });
  }
}

console.log(`\n${tasks.length} task(s) x ${PASSES} pass(es)`
  + (flag("repeat3") ? ` + ${plan.length - tasks.length * PASSES} recipe-block run(s)` : "")
  + ` = ${plan.length} job(s)`);
console.log(`out        ${OUT}`);
if (flag("dry-run")) {
  for (const [i, step] of plan.entries()) {
    console.log(`${String(i + 1).padStart(3)}. ${step.passLabel} ${step.task.id} [${step.task.family}] ${short(step.task.goal, 70)}`);
  }
  process.exit(0);
}

mkdirSync(dirname(OUT), { recursive: true });
if (!existsSync(OUT)) writeFileSync(OUT, "");

let interrupted = false;
for (const sig of ["SIGINT", "SIGTERM"]) {
  process.on(sig, async () => {
    if (interrupted) process.exit(130);
    interrupted = true;
    console.log(`\n${sig}: stopping. Cancelling anything still live so nothing fires later.`);
    await sweep(`battery: ${sig} while running`);
    process.exit(130);
  });
}

const startedAll = Date.now();
// A deadline that stops BETWEEN tasks, never inside one. Cutting a task off
// mid-run would leave a claimed job and a half-written record, so the last task
// always finishes and gets scored; only the next one is skipped.
const DEADLINE_MS = Number(arg("max-minutes", 0)) * 60000;
let n = 0;
let stoppedShort = 0;
for (const step of plan) {
  if (interrupted) break;
  if (DEADLINE_MS && Date.now() - startedAll > DEADLINE_MS) {
    stoppedShort = plan.length - n;
    console.log(`\n[deadline] ${arg("max-minutes", 0)} min reached with ${stoppedShort} run(s) unstarted.`);
    break;
  }
  n += 1;
  const head = `[${n}/${plan.length}] ${step.passLabel} ${step.task.id}`;
  console.log(`\n${head} — ${short(step.task.goal, 88)}`);
  let rec;
  try {
    rec = await runOne(step.task, { passLabel: step.passLabel, attemptIndex: n });
  } catch (e) {
    rec = {
      battery_run: LABEL, pass: step.passLabel, attempt_index: n, task_id: step.task.id,
      family: step.task.family, outcome: "harness_error", note: String(e),
    };
    await sweep("battery: harness error");
  }
  appendFileSync(OUT, JSON.stringify(rec) + "\n");
  console.log(`      -> ${rec.outcome}`
    + (rec.claim_s != null ? ` · claimed ${rec.claim_s}s` : "")
    + (rec.run_s != null ? ` · ran ${rec.run_s}s` : "")
    + ` · ${rec.steps || 0} steps (${rec.decisions || 0} paid`
    + `${rec.replayed_steps ? `, ${rec.replayed_steps} replayed` : ""}`
    + `${rec.vision_steps ? `, ${rec.vision_steps} looked` : ""})`
    + (rec.receipt_verified ? " · receipt" : ""));
  if (rec.result) console.log(`      ${short(rec.result, 200)}`);
  if (rec.note) console.log(`      note: ${rec.note}`);
  if (PAD_S) await sleep(PAD_S * 1000);
}

await sweep("battery: finished");
console.log(`\n${n} run(s) in ${Math.round((Date.now() - startedAll) / 60000)} min -> ${OUT}`);
if (stoppedShort) {
  console.log(`${stoppedShort} run(s) were never started (deadline). The scorecard below covers`);
  console.log(`what actually ran; say so when quoting it.`);
}
console.log(`node proof/battery/score.mjs ${OUT}`);
