#!/usr/bin/env node
// DOES THE BATTERY MINT A REAL JOB? Runs with no browser and no LLM, in about
// four seconds, and answers the one question that otherwise costs an afternoon:
// is the row this harness writes byte-identical in shape to one Anticipy queues
// herself, or is it a row nothing will ever run?
//
//   node proof/battery/selfcheck.mjs
//
// Exit 0 means proof/battery/run.mjs can be trusted to be measuring the agent.
// Exit 1 means it would have been measuring its own broken paperwork.
//
// It also POSITIVELY CONFIRMS THE TWO TRAPS ARE STILL TRAPS, by falling into
// them on purpose:
//   * a nested `params` OBJECT is stored as "" — so the read-back assertion in
//     run.mjs is load-bearing, not superstition;
//   * a row whose columns disagree with its embedded plan is refused 409 — so
//     the guard is live and a passing mint means something.
// Every row it creates is cancelled and deleted before it exits. A queued
// browser job left behind is not litter, it is an errand that fires later.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { homedir } from "node:os";
import { fileURLToPath } from "node:url";
import { call, cancelJob, configure, mintPayload, pollFilter, short } from "./job.mjs";

const here = dirname(fileURLToPath(import.meta.url));
// Loopback only, and ANTICIPY_PB is deliberately ignored — this file WRITES job
// rows, and an inherited environment variable pointing at the Railway
// production backend is how a self-check becomes an incident. Same rule as
// run.mjs; the reason is written out there.
const BASE = (process.argv.find((a) => a.startsWith("--base="))?.slice(7)
  || "http://127.0.0.1:8090").replace(/\/+$/, "");
{
  let host = "";
  try { host = new URL(BASE).hostname; } catch (_) { host = ""; }
  if (!["127.0.0.1", "localhost", "::1", "[::1]", "0.0.0.0"].includes(host)) {
    console.error(`refusing to write job rows to ${BASE}: local rig only.`);
    process.exit(2);
  }
}
let OWNER_REF = process.env.ANTICIPY_OWNER_REF || "";
if (!OWNER_REF) {
  const f = join(process.env.ANTICIPY_RIG_DIR || join(homedir(), ".anticipy-rig"), "state", "owner_ref");
  try { OWNER_REF = readFileSync(f, "utf8").trim(); } catch (_) { /* reported below */ }
}
const OWNER_ID = process.env.ANTICIPY_OWNER_ID || "local-dev";
configure({ base: BASE, ownerRef: OWNER_REF, ownerId: OWNER_ID });

const doc = JSON.parse(readFileSync(join(here, "tasks.json"), "utf8"));
const readOnlyTask = doc.tasks.find((t) => t.consequence !== "consequential" && t.expect);
const consequentialTask = doc.tasks.find((t) => t.consequence === "consequential");

let failures = 0;
const bin = [];   // rows to remove, whatever happens
let n = 0;
const ok = (title, detail) => {
  console.log(`${String(++n).padStart(2)}. PASS  ${title}`);
  for (const d of [].concat(detail || []).filter(Boolean)) console.log(`         ${d}`);
};
const bad = (title, detail) => {
  failures += 1;
  console.log(`${String(++n).padStart(2)}. FAIL  ${title}`);
  for (const d of [].concat(detail || []).filter(Boolean)) console.log(`         ${d}`);
};

console.log(`battery self-check`);
console.log(`backend   ${BASE}`);
console.log(`owner_ref ${OWNER_REF || "(none — pass ANTICIPY_OWNER_REF)"}`);
console.log(`corpus    ${doc.tasks.length} tasks\n`);

const health = await call("GET", "/api/health");
if (!(health.status === 200)) {
  console.error(`the backend is not answering (${health.status}): ${short(health.text, 200)}`);
  process.exit(1);
}
if (!OWNER_REF) { console.error("no owner_ref, nothing to queue against"); process.exit(1); }

// The same canonicalisation workflow_guard.pb.js applies before comparing the
// row to its embedded plan (workflow_guard.pb.js:70).
const ordered = (v) => {
  if (Array.isArray(v)) return v.map(ordered);
  if (v && typeof v === "object") {
    const out = {};
    for (const k of Object.keys(v).sort()) out[k] = ordered(v[k]);
    return out;
  }
  return v;
};
const sameJSON = (a, b) => JSON.stringify(ordered(a ?? null)) === JSON.stringify(ordered(b ?? null));

// Every equality the guard demands, checked against the row AS STORED rather
// than against what we meant to send. Storage is where the silence happens.
function guardAgreement(row) {
  const problems = [];
  let params = null;
  try { params = JSON.parse(String(row.params || "")); } catch (_) { /* below */ }
  const wf = params?._workflow;
  if (!wf) return ["params holds no _workflow at all"];
  const eq = (name, a, b) => { if (String(a ?? "") !== String(b ?? "")) problems.push(`${name}: plan ${JSON.stringify(a)} vs column ${JSON.stringify(b)}`); };
  eq("plan_id/workflow_id", wf.plan_id, row.workflow_id);
  eq("version", wf.version, row.workflow_version);
  eq("state", wf.state, row.workflow_state);
  eq("goal", wf.goal, row.goal);
  eq("consequence", wf.consequence, row.consequence);
  eq("lineage_key", wf.lineage_key, row.lineage_key);
  eq("owner_ref", wf.owner_ref, row.owner_ref);
  eq("scope_digest", wf.scope_digest, row.scope_digest);
  eq("effect_key", wf.effect_key, row.effect_key);
  eq("attempts", Number(wf.attempts || 0), Number(row.attempts || 0));
  eq("lease token", wf.lease?.token || "", row.lease_token || "");
  let rowApproval = null;
  try { rowApproval = row.approval ? JSON.parse(String(row.approval)) : null; } catch (_) { problems.push("approval column is not parseable"); }
  if (!sameJSON(wf.approval, rowApproval)) problems.push("embedded approval and the approval column differ");
  let rowReceipt = null;
  try { rowReceipt = row.receipt ? JSON.parse(String(row.receipt)) : null; } catch (_) { problems.push("receipt column is not parseable"); }
  if (!sameJSON(wf.receipt, rowReceipt)) problems.push("embedded receipt and the receipt column differ");
  const required = Array.isArray(wf.required) ? wf.required : [];
  const missing = required.filter((k) => wf.facts?.[k] == null || wf.facts?.[k] === "");
  if (missing.length) problems.push(`required facts absent from the plan: ${missing.join(", ")}`);
  return problems;
}

// 1/2 ------------------------------------------- a read-only job mints cleanly
for (const [label, task] of [["read-only", readOnlyTask], ["consequential", consequentialTask]]) {
  if (!task) { bad(`a ${label} task exists in the corpus`, ["tasks.json has none"]); continue; }
  const minted = mintPayload(task, { source: "proof/battery/selfcheck.mjs" });
  const posted = await call("POST", "/api/collections/jobs/records", { body: minted.body });
  if (!posted.ok || !posted.json?.id) {
    bad(`a ${label} job can be queued the way the brain queues one`, [
      `POST -> ${posted.status} ${short(posted.text, 300)}`,
      posted.status === 409
        ? "That is workflow_guard.pb.js refusing it: the columns and the embedded plan must agree exactly."
        : "",
    ]);
    continue;
  }
  const id = posted.json.id;
  bin.push(id);
  const row = (await call("GET", `/api/collections/jobs/records/${id}`)).json || {};
  const raw = row.params;
  let parsed = null;
  try { parsed = JSON.parse(String(raw || "")); } catch (_) { /* below */ }
  if (typeof raw !== "string" || !raw || !parsed) {
    bad(`the ${label} row survived the write`, [
      `params came back as ${typeof raw} ${raw === "" ? "(empty string)" : short(raw, 60)}`,
      "PocketBase stores a nested object in a text column as \"\" — the agent would run with no task at all.",
    ]);
    continue;
  }
  if (parsed.task !== task.goal || parsed.start_url !== task.start_url
      || parsed._workflow?.plan_id !== minted.planId) {
    bad(`the ${label} row survived the write`, [
      `task=${short(parsed.task, 50)} start_url=${parsed.start_url} plan=${parsed._workflow?.plan_id}`,
    ]);
    continue;
  }
  ok(`a ${label} job mints and reads back intact`, [
    `job ${id} · params is a ${raw.length}-byte JSON STRING`,
    `start_url ${parsed.start_url}`,
    label === "consequential"
      ? `approval bound to plan ${parsed._workflow.approval?.plan_id?.slice(0, 8)} v${parsed._workflow.approval?.plan_version}`
        + ` · owner words present: ${!!parsed._workflow.approval?.owner_words}`
      : `consequence read_only, so the engine will refuse any submit control`,
  ]);
  const problems = guardAgreement(row);
  if (problems.length) bad(`the ${label} row agrees with its embedded plan`, problems);
  else ok(`the ${label} row agrees with its embedded plan on every field the guard compares`, [
    "plan_id, version, state, goal, consequence, lineage, owner, both digests, attempts, lease, approval, receipt, required facts",
  ]);

  // The extension's own poll filter, character for character. A row invisible
  // here will never run however healthy everything else looks.
  const seen = await call("GET", `/api/collections/jobs/records?perPage=100&sort=created`
    + `&filter=${encodeURIComponent(pollFilter(OWNER_REF))}`);
  const items = seen.json?.items || [];
  const at = items.findIndex((j) => j.id === id);
  if (at < 0) bad(`Chrome's own poll filter can see the ${label} job`, [pollFilter(OWNER_REF)]);
  else ok(`Chrome's own poll filter can see the ${label} job`,
    [at === 0 ? "first in line" : `#${at + 1} in line behind ${at} older queued job(s)`]);
}

// 3 ------------------------------------------------- the params trap is real
{
  const task = readOnlyTask;
  const minted = mintPayload(task, { source: "proof/battery/selfcheck.mjs" });
  // Deliberately wrong: the nested OBJECT instead of the JSON string.
  const body = { ...minted.body, params: JSON.parse(minted.params) };
  const posted = await call("POST", "/api/collections/jobs/records", { body });
  if (posted.ok && posted.json?.id) {
    bin.push(posted.json.id);
    const row = (await call("GET", `/api/collections/jobs/records/${posted.json.id}`)).json || {};
    if (row.params === "" || row.params == null) {
      ok("the params trap is still a trap", [
        "a nested params OBJECT was accepted and stored as \"\" — silently, with no error",
        "so run.mjs's read-back assertion is load-bearing, not superstition",
      ]);
    } else {
      // Not a failure of ours: PocketBase would have started coercing objects.
      ok("the params trap has changed shape", [
        `a nested object came back as ${typeof row.params} (${String(row.params).length} bytes) — note it and re-read run.mjs's assertion`,
      ]);
    }
  } else if (posted.status === 409 || posted.status === 400) {
    ok("the params trap is now caught at the door", [
      `a nested params object was refused ${posted.status}: ${short(posted.text, 140)}`,
    ]);
  } else {
    bad("the params trap check could not run", [`POST -> ${posted.status} ${short(posted.text, 200)}`]);
  }
}

// 4 --------------------------------------------------- the guard is switched on
{
  const minted = mintPayload(readOnlyTask, { source: "proof/battery/selfcheck.mjs" });
  // One column disagreeing with the embedded plan is the whole 409 class.
  const body = { ...minted.body, goal: `${readOnlyTask.goal} (tampered)` };
  const posted = await call("POST", "/api/collections/jobs/records", { body });
  if (posted.status === 409) {
    ok("workflow_guard.pb.js is switched on", [
      "a row whose goal disagreed with its embedded plan was refused 409",
      "so a job that DOES mint has been checked, not merely accepted",
    ]);
  } else {
    if (posted.json?.id) bin.push(posted.json.id);
    bad("workflow_guard.pb.js is switched on", [
      `a tampered row was accepted with ${posted.status} — the redundancy check is not running`,
      "every 'the row is canonical' claim in this directory rests on it",
    ]);
  }
}

// 5 ------------------------------------------- the harness can stop what it starts
{
  const minted = mintPayload(readOnlyTask, { source: "proof/battery/selfcheck.mjs" });
  const posted = await call("POST", "/api/collections/jobs/records", { body: minted.body });
  if (!posted.ok || !posted.json?.id) {
    bad("a queued job can be cancelled by the harness", [`could not queue one: ${posted.status}`]);
  } else {
    const id = posted.json.id;
    bin.push(id);
    const how = await cancelJob(id, "battery self-check");
    const row = (await call("GET", `/api/collections/jobs/records/${id}`)).json || {};
    if (how === "cancelled" && row.status === "cancelled" && row.workflow_state === "cancelled"
        && !row.lease_token) {
      ok("the harness can stop what it starts", [
        "queued -> cancelled, lease cleared, embedded plan updated with it",
        "which is what makes the exit sweep real rather than hopeful",
      ]);
    } else {
      bad("the harness can stop what it starts", [
        `cancelJob said "${how}", row is status=${row.status} state=${row.workflow_state} lease=${row.lease_token || "(none)"}`,
        "a battery that cannot cancel leaves live browser errands behind",
      ]);
    }
  }
}

// ------------------------------------------------------------------ tidy up
let removed = 0;
for (const id of bin) {
  await cancelJob(id, "battery self-check tidy-up");
  const r = await call("DELETE", `/api/collections/jobs/records/${id}`);
  if (r.ok || r.status === 404) removed += 1;
}
console.log(`\ncleaned up ${removed}/${bin.length} row(s) this check created`);
if (removed !== bin.length) {
  console.log("SOME ROWS SURVIVED. Check them by hand: a queued job is an errand that fires later.");
  failures += 1;
}
console.log(failures ? `\n${failures} check(s) failed — run.mjs would not be measuring the agent.`
  : `\nall clear: the row this harness writes is one a real Chrome will run.`);
process.exit(failures ? 1 : 0);
