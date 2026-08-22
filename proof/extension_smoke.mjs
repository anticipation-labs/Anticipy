#!/usr/bin/env node
// IS THE BROWSER ARM ACTUALLY WORKING? One command, plain words, no deps.
//
//   sh proof/local_rig.sh up          # PocketBase + the brain
//   node proof/extension_smoke.mjs    # this
//
// It walks the exact path a real install walks — register, get claimed by the
// phone, fetch a model, have a queued job picked up and run — and then says
// WHICH ARM IS BROKEN. The exit code is the answer:
//
//   0  everything worked, including a real Chrome running the job
//   1  the BACKEND is the problem: one of the numbered checks below failed
//   2  the backend is fine and NOTHING IN CHROME acted on the job
//
// WHY THIS EXISTS: "she isn't doing anything" has at least seven causes that
// are indistinguishable from the outside, and every one of them has cost a
// live afternoon —
//   * the extension is not loaded in Chrome at all;
//   * it is loaded but the phone never claimed it (no owner_ref -> claimJob
//     returns null and says nothing);
//   * PocketBase has no model key, so /agent/key 503s and every claimed job
//     dies at "no LLM key" — the extension never holds a vendor key of its
//     own, it stores the marker "backend-proxy" and calls POST /agent/llm,
//     so a missing key on the BACKEND looks exactly like a broken extension;
//   * the job was written with a nested `params` OBJECT instead of a
//     JSON-encoded STRING, which PocketBase stores as "" — the agent then
//     runs with no task and start_url=about:blank;
//   * the job carries lane="research" or no workflow metadata, so the
//     extension's own poll filter can never see it;
//   * Chrome is running a stale build (an unpacked extension never
//     auto-updates and Reload re-reads Chrome's own copy — see
//     extension/sync-to-chrome.sh);
//   * nothing is wrong and it is simply the ~30s chrome.alarms floor.
// This asks all seven in about two minutes.
//
// Flags: --base=URL --owner-ref=ID --wait=SECONDS --claim-wait=SECONDS --keep
import { readFileSync } from "node:fs";
import { createHash, randomUUID } from "node:crypto";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const repo = join(here, "..");
// Accepts BOTH `--name=value` and `--name value`. It used to accept only the
// first, so `--claim-wait 150` was silently ignored and the run used the 45s
// default while printing nothing about it — a flag that quietly does nothing is
// precisely the class of failure this whole script exists to eliminate, and it
// wasted a real diagnosis (a healthy Chrome reported as the broken arm).
const arg = (name, fallback) => {
  const eq = process.argv.find((a) => a.startsWith(`--${name}=`));
  if (eq) return eq.slice(name.length + 3);
  const at = process.argv.indexOf(`--${name}`);
  if (at >= 0) {
    const next = process.argv[at + 1];
    if (next && !next.startsWith("--")) return next;
  }
  return fallback;
};
const flag = (name) => process.argv.includes(`--${name}`);
// A misspelled flag must not read as a default. Every option this script honours
// is listed here; anything else on the command line is a typo, and a typo that
// silently changes the meaning of a diagnostic is worse than a crash.
const KNOWN = ["base", "owner-ref", "owner", "claim-wait", "wait", "start-url", "task"];
for (const a of process.argv.slice(2)) {
  if (!a.startsWith("--")) continue;
  const name = a.slice(2).split("=")[0];
  if (!KNOWN.includes(name)) {
    console.error(`unknown option --${name}. Known: ${KNOWN.map((k) => "--" + k).join(" ")}`);
    process.exit(1);
  }
}

const BASE = (arg("base", process.env.ANTICIPY_PB || "http://127.0.0.1:8090")).replace(/\/+$/, "");
// Chrome refuses recurring extension alarms under 0.5 minutes, and that is the
// ONLY recurring wake (there is no push channel). So 30s of silence is normal
// and proves nothing; 45 is the floor plus enough slack to lose one tick.
const CLAIM_WAIT_S = Number(arg("claim-wait", 45));
const RUN_WAIT_S = Number(arg("wait", 180));
const START_URL = arg("start-url", "https://example.com/");
const TASK = arg("task", "open example.com and report the page heading");

// The rig writes the owner it created here; a person should not have to know
// their own PocketBase id to run a smoke test.
const ownerRefFile = join(process.env.ANTICIPY_RIG_DIR || join(homedir(), ".anticipy-rig"),
                          "state", "owner_ref");
let OWNER_REF = arg("owner-ref", process.env.ANTICIPY_OWNER_REF || "");
let ownerRefFrom = OWNER_REF ? "the command line or ANTICIPY_OWNER_REF" : "";
if (!OWNER_REF) {
  try {
    OWNER_REF = readFileSync(ownerRefFile, "utf8").trim();
    ownerRefFrom = ownerRefFile;
  } catch (_) { /* reported as a failed check below */ }
}
const OWNER_ID = arg("owner", process.env.ANTICIPY_OWNER_ID || "local-dev");
const EXT_VERSION = JSON.parse(
  readFileSync(join(repo, "extension", "manifest.json"), "utf8")).version;

// ------------------------------------------------------------------ plumbing
const headers = () => {
  const h = { "Content-Type": "application/json" };
  // Set on production, unset on the rig (guard.pb.js falls through to open
  // access when it is missing). Never printed.
  if (process.env.ANTICIPY_SERVICE_TOKEN) h["X-Anticipy-Token"] = process.env.ANTICIPY_SERVICE_TOKEN;
  return h;
};
async function call(method, path, { body, extra } = {}) {
  const r = await fetch(`${BASE}${path}`, {
    method,
    headers: { ...headers(), ...(extra || {}) },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  const text = await r.text();
  let json = null;
  try { json = text ? JSON.parse(text) : null; } catch (_) { /* not json */ }
  return { status: r.status, ok: r.ok, json, text };
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const short = (s, n = 220) => String(s || "").replace(/\s+/g, " ").trim().slice(0, n);

let n = 0;
const results = [];
function report(state, title, detail) {
  n += 1;
  results.push({ state, title });
  const mark = state === "PASS" ? "PASS" : state === "FAIL" ? "FAIL" : "SKIP";
  console.log(`${String(n).padStart(2)}. ${mark}  ${title}`);
  for (const line of [].concat(detail || []).filter(Boolean)) console.log(`         ${line}`);
  return state === "PASS";
}
const pass = (t, d) => report("PASS", t, d);
const fail = (t, d) => report("FAIL", t, d);
const skip = (t, d) => report("SKIP", t, d);
const note = (line) => console.log(`         ${line}`);
const ageWords = (iso) => {
  const t = Date.parse(String(iso || "").replace(" ", "T"));
  if (!t) return "never";
  const s = Math.round((Date.now() - t) / 1000);
  return s < 90 ? `${s}s ago` : s < 5400 ? `${Math.round(s / 60)} min ago` : `${Math.round(s / 3600)}h ago`;
};

// The brain's canonical form, so the row this writes is byte-identical in
// shape to one Anticipy queues herself (brain/workflow.py:_canonical).
const canonical = (value) => {
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === "object") {
    const out = {};
    for (const k of Object.keys(value).sort()) out[k] = canonical(value[k]);
    return out;
  }
  return value;
};
const digest = (payload) =>
  createHash("sha256").update(JSON.stringify(canonical(payload)), "utf8").digest("hex");
// Python's datetime.isoformat(), which is what brain/workflow.py wrote and
// what Plan.from_dict reads back.
const stamp = () => new Date().toISOString().replace("Z", "+00:00");

// The run's own state, declared up here because tidy() and verdict() close
// over it and may have to run from any failed check below — including one that
// aborts before a job exists.
const probeAgentId = randomUUID();
let probe = null;
let jobId = "";
let ending = null;   // the job row as it finished, if it finished

// ------------------------------------------------------------------ tidy-up
// A queued job left behind is not litter, it is a booking that fires tomorrow
// morning in his real Chrome. And a paired-looking probe row makes the phone
// say "Chrome ready" about a browser that does not exist.
let tidied = false;
async function tidy() {
  if (tidied) return;
  tidied = true;
  if (flag("keep")) { console.log("\n--keep: leaving the probe agent and the job in place."); return; }
  console.log("");
  if (jobId) {
    const row = (await call("GET", `/api/collections/jobs/records/${jobId}`)).json || {};
    if (["done", "failed", "cancelled"].includes(row.status)) {
      console.log(`tidy: job ${jobId} left as ${row.status} (it is the evidence)`);
    } else {
      // Cancel the way every other client must: the columns and the embedded
      // plan move together, or workflow_guard.pb.js refuses the write.
      let ok = false;
      try {
        const params = JSON.parse(row.params || "{}");
        const plan = { ...(params._workflow || {}), state: "cancelled", lease: null,
                       attempts: Number(row.attempts || 0),
                       reason: "tidied up by proof/extension_smoke.mjs",
                       updated_at: stamp() };
        const r = await call("PATCH", `/api/collections/jobs/records/${jobId}`, {
          body: {
            status: "cancelled",
            workflow_state: "cancelled",
            workflow_version: Number(row.workflow_version || 1),
            lease_token: "",
            lease_until: "",
            params: JSON.stringify({ ...params, _workflow: plan }),
            result: row.result || "smoke test finished; this job was cancelled so it can never fire later",
          },
        });
        ok = r.ok;
        if (!ok) {
          const d = await call("DELETE", `/api/collections/jobs/records/${jobId}`);
          ok = d.ok;
        }
      } catch (_) { ok = false; }
      console.log(ok
        ? `tidy: job ${jobId} cancelled so it cannot fire later`
        : `tidy: COULD NOT CLEAR job ${jobId} — it is still ${row.status}. Cancel it by hand (${BASE}/_/) or it may run later.`);
      if (!ok) results.push({ state: "FAIL", title: "tidy-up left a live job behind" });
    }
  }
  if (probe) {
    const d = await call("DELETE", `/api/collections/agents/records/${probe.recordId}`);
    console.log(d.ok
      ? "tidy: probe agent row deleted"
      : `tidy: COULD NOT DELETE the probe agent row ${probe.recordId} — the app will show a browser that is not there. Remove it at ${BASE}/_/`);
    if (!d.ok) results.push({ state: "FAIL", title: "tidy-up left a fake paired browser behind" });
  }
}

function verdict() {
  const failed = results.filter((r) => r.state === "FAIL");
  const skipped = results.filter((r) => r.state === "SKIP");
  const backendFailed = failed.some((r) => !/claims the job|reaches an ending/.test(r.title));
  console.log("");
  if (!failed.length && !skipped.length) {
    // A hand-back is a legitimate ending and the arm demonstrably worked — but
    // "everything works" is not a thing to print over a run that stopped. Say
    // which ending it was and let the reader judge the reason. (A backend
    // restart mid-run lands here too: PocketBase reloads itself when a hook
    // file changes, and a model call in that second comes back 502.)
    if (ending && ending.status !== "done") {
      console.log("VERDICT: the chain works — backend, pairing, model, queue, and a real Chrome ran the job.");
      console.log(`It ended by asking for you: ${short(ending.result) || "(no reason given)"}`);
      console.log("If that reason is not actually about you, it is a fault rather than a hand-back — but it is hers to report, and she reported it.");
      process.exit(0);
    }
    console.log("VERDICT: the whole chain works — backend, pairing, model, queue, and a real Chrome ran the job to a finish.");
    process.exit(0);
  }
  if (backendFailed) {
    console.log(`VERDICT: THE BACKEND IS THE PROBLEM — ${failed.map((r) => r.title).join("; ")}.`);
    console.log("The failed check above says what to do. Chrome is not at fault.");
    process.exit(1);
  }
  console.log("VERDICT: the backend arm is healthy (register, pair, model, queue and the poll filter all pass).");
  console.log(skipped.length && !failed.length
    ? "THE CHROME ARM WAS NOT TESTED: nothing is paired to this owner, so no browser could act. Load the extension as shown above and run this again."
    : "THE CHROME ARM IS THE PROBLEM: the job was there to take and Chrome did not finish it.");
  process.exit(2);
}

console.log(`Anticipy browser-arm smoke test`);
console.log(`backend   : ${BASE}`);
console.log(`repo build: extension ${EXT_VERSION}`);
console.log(`owner_ref : ${OWNER_REF || "(unknown)"}${ownerRefFrom ? `  (from ${ownerRefFrom})` : ""}`);
console.log("");

// 1 ------------------------------------------------------- backend reachable
const health = await call("GET", "/api/health").catch((e) => ({ status: 0, text: String(e) }));
if (!(health.status === 200 && /healthy/i.test(health.text))) {
  fail("the backend answers", [
    `GET ${BASE}/api/health -> ${health.status || "no connection"} ${short(health.text, 120)}`,
    "Start it: sh proof/local_rig.sh up",
  ]);
  verdict();
} else {
  pass("the backend answers", [`GET /api/health -> 200`]);
}

// 2 ------------------------------------------------------------- who the owner is
if (!OWNER_REF) {
  fail("this rig knows who the owner is", [
    `no owner_ref: ${ownerRefFile} is missing and --owner-ref was not given`,
    "Run sh proof/local_rig.sh up (it creates the local owner), or pass --owner-ref=<id>",
  ]);
  verdict();
}
{
  const profile = await call("GET",
    `/api/collections/owner_profile/records?perPage=1&filter=${encodeURIComponent(`owner_ref="${OWNER_REF}"`)}`);
  const row = profile.json?.items?.[0] || null;
  pass("this rig knows who the owner is", [
    `owner_ref ${OWNER_REF}`,
    row
      ? `owner card: ${["first_name", "last_name", "email", "phone"].filter((k) => row[k]).join(", ") || "(empty)"}`
      : "no owner_profile row — she has no name/email/phone to type into a form, so booking-style jobs will stop and ask",
  ]);
}

// 3 -------------------------------------------- a fresh install can register
{
  // Exactly what extension/background.js:ensureRegisteredOnce POSTs, including
  // the build marker it puts in `browser` so nobody has to guess which build
  // an install is running.
  const r = await call("POST", "/agent/register", {
    body: {
      agent_id: probeAgentId,
      browser: `Chrome/151 ext/${EXT_VERSION} anticipy-smoke probe`,
      last_seen: new Date().toISOString(),
    },
  });
  const token = r.json?.agent_token || "";
  const code = String(r.json?.pair_code || "");
  if (!r.ok || token.length < 40 || !/^\d{6}$/.test(code)) {
    fail("a fresh install can register", [
      `POST /agent/register -> ${r.status} ${short(r.text, 200)}`,
      "This is the very first thing a new Chrome does; nothing works without it.",
    ]);
    verdict();
  }
  // TRUST THE ROW, NOT THE STATUS CODE. A register that answers 200 while
  // nothing persists leaves an install holding a token no lookup can match,
  // and every later step fails with "not a paired agent" — seen live on this
  // rig once already.
  const back = await call("GET", `/api/collections/agents/records/${r.json.id}`);
  if (!back.ok || back.json?.agent_id !== probeAgentId) {
    fail("a fresh install can register", [
      `the row did not persist: GET /api/collections/agents/records/${r.json.id} -> ${back.status}`,
    ]);
    verdict();
  }
  probe = { recordId: r.json.id, token, code };
  pass("a fresh install can register", [
    `agents row ${probe.recordId} created, pair code ${probe.code}, token stored server-side`,
  ]);
}

// 4 --------------------------------------------------- the phone can pair it
{
  const r = await call("PATCH", `/api/collections/agents/records/${probe.recordId}`,
    { body: { owner: OWNER_ID, owner_ref: OWNER_REF, paired: true } });
  const back = await call("GET", `/api/collections/agents/records/${probe.recordId}`);
  if (!r.ok || back.json?.paired !== true || back.json?.owner_ref !== OWNER_REF) {
    fail("the phone can claim that pair code", [
      `PATCH -> ${r.status} ${short(r.text, 200)}`,
      `read back: paired=${back.json?.paired} owner_ref=${back.json?.owner_ref || "(blank)"}`,
      r.text.includes("validation_missing_rel_records")
        ? `owner_ref ${OWNER_REF} names no owners row — this rig's data was reset; delete ${ownerRefFile} and re-run sh proof/local_rig.sh up`
        : "This is what the iOS app does when you type the 6-digit code.",
    ]);
    await tidy();
    verdict();
  }
  pass("the phone can claim that pair code", ["paired=true, owner_ref written"]);
}

// 5 ------------------------------------------------- a paired browser gets a model
{
  const r = await call("GET", `/agent/key?agent_id=${encodeURIComponent(probeAgentId)}`,
    { extra: { "X-Anticipy-Agent-Token": probe.token } });
  const model = r.json?.model || "";
  if (!r.ok || !model) {
    fail("a paired browser is given a model", [
      `GET /agent/key -> ${r.status} ${short(r.text, 200)}`,
      r.status === 503
        ? "PocketBase itself has no OPENROUTER_API_KEY/GEMINI_API_KEY in its environment (backend/pb_hooks/agent_key.pb.js:24). Every job a browser claims then dies at \"no LLM key\" — see the env block in proof/local_rig.sh start_backend."
        : "Without a model the click-loop cannot take a single step.",
    ]);
    await tidy();
    verdict();
  }
  pass("a paired browser is given a model", [
    `model ${model}${r.json?.vision_model ? ` · vision ${r.json.vision_model}` : ""}`,
    `llm_proxy ${r.json?.llm_proxy ? "on (the key never leaves the backend)" : "OFF"}`,
  ]);
}

// Who could possibly do the work? Read this BEFORE queueing, so the wait below
// is measured against what was already there — and so the answer to "is it my
// Chrome?" is a fact, not a guess.
//
// PAIRED IS NOT LIVE. The heartbeat alarm beats every 30s, so a row whose
// last_seen is minutes old means that Chrome is shut or the extension is
// switched off — the pairing survives, the executor does not. Reporting those
// two states as one is exactly how "Chrome ready" ended up on the phone while
// nothing was consuming the queue.
const HEARTBEAT_LIVE_MS = 2 * 60 * 1000;
let candidates = [];
let live = [];
{
  const r = await call("GET",
    `/api/collections/agents/records?perPage=50&sort=-last_seen&filter=${encodeURIComponent(`owner_ref="${OWNER_REF}"`)}`);
  candidates = (r.json?.items || []).filter((a) => a.agent_id !== probeAgentId && a.paired);
  live = candidates.filter((a) => {
    const t = Date.parse(String(a.last_seen || "").replace(" ", "T"));
    return t && Date.now() - t < HEARTBEAT_LIVE_MS;
  });
  if (!candidates.length) {
    console.log("browsers paired to this owner: NONE (besides this probe)");
  } else {
    console.log(`browsers paired to this owner: ${candidates.length}, of which ${live.length} beating now`);
    for (const a of candidates) {
      const build = (String(a.browser || "").match(/ext\/([\d.]+)/) || [])[1] || "unknown";
      note(`${a.browser || "(no build reported)"} · heartbeat ${ageWords(a.last_seen)}`
        + (live.includes(a) ? "" : " <-- not beating: that Chrome is closed or the extension is off")
        + (build !== "unknown" && build !== EXT_VERSION
          ? `  <-- STALE BUILD: this repo builds ${EXT_VERSION}. Run sh extension/sync-to-chrome.sh, then Reload.`
          : ""));
    }
  }
  console.log("");
}

// 6 --------------------------------------------- a job can be queued as the brain queues it
const planId = randomUUID();
const lineage = `smoke-${randomUUID().slice(0, 8)}`;
{
  const facts = {};
  const plan = {
    plan_id: planId,
    owner_ref: OWNER_REF,
    lineage_key: lineage,
    version: 1,
    goal: TASK,
    authority_text: TASK,
    consequence: "read_only",
    state: "queued",
    facts,
    required: [],
    source_event_ids: [lineage],
    approval: null,
    lease: null,
    receipt: null,
    attempts: 0,
    reason: "",
    created_at: stamp(),
    updated_at: stamp(),
  };
  const scopePayload = { plan_id: planId, version: 1, goal: TASK, facts,
                         consequence: "read_only", authority_text: TASK };
  plan.scope_digest = digest(scopePayload);
  plan.effect_key = digest({ owner_ref: OWNER_REF, ...scopePayload });
  // THE PARAMS TRAP: `params` is a TEXT column, so a nested object is not the
  // structure you think you posted. JSON.stringify, always.
  //
  // Corrected 2026-08-20, because the original claim here was broader than the
  // truth and would have sent the next person hunting the wrong bug: on a
  // WORKFLOW row (one carrying workflow_id) an object is now REFUSED outright,
  // 409 "workflow params are not parseable", because workflow_guard.pb.js
  // parses params before it compares the columns. The silent "" - agent wakes
  // with no task, start_url=about:blank, opens a blank tab, reports finding
  // nothing - still happens, but only on rows WITHOUT workflow_id, which is
  // not the path the brain uses any more. Evidence: proof/battery/selfcheck.mjs
  // falls into both traps deliberately and records which one fires.
  const params = JSON.stringify({
    task: TASK,
    start_url: START_URL,
    authorized: true,
    source: `proof/extension_smoke.mjs at ${new Date().toISOString()}`,
    _workflow: plan,
  });
  const r = await call("POST", "/api/collections/jobs/records", {
    body: {
      goal: TASK,
      params,
      device_id: "anticipy",
      owner: OWNER_ID,
      owner_ref: OWNER_REF,
      // NOT "research": research_lane.pb.js hides that lane from the
      // extension's poll on purpose (read-only goals run server-side).
      lane: "",
      workflow_id: planId,
      workflow_version: 1,
      workflow_state: "queued",
      consequence: "read_only",
      lineage_key: lineage,
      effect_key: plan.effect_key,
      scope_digest: plan.scope_digest,
      approval: "",
      receipt: "",
      lease_token: "",
      lease_until: "",
      source_event_ids: JSON.stringify([lineage]),
      attempts: 0,
      status: "queued",
    },
  });
  if (!r.ok || !r.json?.id) {
    fail("a job can be queued the way the brain queues one", [
      `POST /api/collections/jobs/records -> ${r.status} ${short(r.text, 300)}`,
      r.status === 409
        ? "That is workflow_guard.pb.js refusing the row: the embedded plan and the columns must agree exactly."
        : "",
    ]);
    await tidy();
    verdict();
  }
  jobId = r.json.id;
  pass("a job can be queued the way the brain queues one", [
    `job ${jobId} · ${TASK}`,
    `start_url ${START_URL} · consequence read_only · lane "" (the browser lane)`,
  ]);
}

// 7 ------------------------------------------- the row survived the write intact
{
  const row = (await call("GET", `/api/collections/jobs/records/${jobId}`)).json || {};
  const raw = row.params;
  let parsed = null;
  try { parsed = JSON.parse(String(raw || "")); } catch (_) { /* reported below */ }
  if (typeof raw !== "string" || !raw || !parsed) {
    fail("the queued job survived the write", [
      `params came back as ${typeof raw} ${raw === "" ? "(empty string)" : short(raw, 80)}`,
      "PocketBase stores a nested object in a text column as \"\" — the agent would run with no task at all.",
    ]);
    await tidy();
    verdict();
  }
  if (parsed.start_url !== START_URL || parsed.task !== TASK || parsed._workflow?.plan_id !== planId) {
    fail("the queued job survived the write", [
      `task=${short(parsed.task, 60)} start_url=${parsed.start_url} plan=${parsed._workflow?.plan_id}`,
    ]);
    await tidy();
    verdict();
  }
  pass("the queued job survived the write", [
    `params is a ${raw.length}-byte JSON string; task, start_url and the canonical plan all read back`,
  ]);
}

// 8 ------------------------- the extension's own poll filter can see it
{
  // Character-for-character the filter in extension/background.js:claimJob.
  // A job invisible to THIS query will never be run, no matter how healthy
  // everything else looks — that is how lane="research" and rows without
  // workflow metadata used to disappear in silence.
  const cond = `status="queued" && owner_ref="${OWNER_REF}" && workflow_id!="" && lane!="research"`;
  const r = await call("GET",
    `/api/collections/jobs/records?filter=${encodeURIComponent(cond)}&perPage=50&sort=created`);
  const items = r.json?.items || [];
  const mine = items.findIndex((j) => j.id === jobId);
  if (!r.ok || mine < 0) {
    fail("Chrome's own poll filter finds the job", [
      `filter -> ${r.status}, ${items.length} row(s), this job not among them`,
      cond,
    ]);
    await tidy();
    verdict();
  }
  pass("Chrome's own poll filter finds the job", [
    mine === 0
      ? "it is first in line (claimJob takes the oldest queued job)"
      : `it is #${mine + 1} in line behind ${mine} older queued job(s) — those get claimed first`,
  ]);
}

// 9/10 ------------------------------------------------- does a Chrome act on it
let claimed = null;
// `ending` is hoisted above, so the closing verdict can name how it finished.
if (!candidates.length) {
  skip("a Chrome claims the job", [
    "No browser is paired to this owner, so there is nothing that could claim it.",
    "Load the extension: chrome://extensions -> Developer mode (top right) -> Load unpacked",
    `-> select ${join(repo, "extension")} -> open the setup page and type the 6-digit code into the app.`,
  ]);
  skip("the run reaches an ending", ["nothing claimed it"]);
} else {
  const startedAt = Date.now();
  // Not zero: the first line would otherwise print at 0s, where "still
  // queued" is not news, it is the expected state.
  let lastSay = Date.now();
  while ((Date.now() - startedAt) / 1000 < CLAIM_WAIT_S) {
    const row = (await call("GET", `/api/collections/jobs/records/${jobId}`)).json || {};
    if (row.status !== "queued" || row.claimed_by) { claimed = row; break; }
    if (Date.now() - lastSay > 9000) {
      lastSay = Date.now();
      note(`still queued after ${Math.round((Date.now() - startedAt) / 1000)}s `
        + `(Chrome wakes on a 30s alarm — up to half a minute of this is normal)`);
    }
    await sleep(2000);
  }
  if (!claimed) {
    // RE-READ THE CENSUS, because the one taken above is now stale by however
    // long the wait was. Observed live: a Chrome that had just been paired was
    // reported as "1 paired and NONE beating" from a snapshot taken before its
    // first heartbeat, and the whole verdict rested on that. Ninety seconds
    // later the same Chrome claimed a job in under five. A diagnostic that
    // reasons about a live system from an old snapshot will confidently blame
    // the wrong arm, which is the one thing this file must never do.
    {
      const again = await call("GET",
        `/api/collections/agents/records?perPage=50&sort=-last_seen&filter=${encodeURIComponent(`owner_ref="${OWNER_REF}"`)}`);
      const rows = (again.json?.items || []).filter((a) => a.agent_id !== probeAgentId && a.paired);
      if (rows.length) {
        candidates = rows;
        live = rows.filter((a) => {
          const t = Date.parse(String(a.last_seen || "").replace(" ", "T"));
          return t && Date.now() - t < HEARTBEAT_LIVE_MS;
        });
      }
    }
    fail("a Chrome claims the job", [
      `${CLAIM_WAIT_S}s and still queued, with ${candidates.length} browser(s) paired`
        + `${live.length ? ` and ${live.length} beating` : " and NONE beating"}.`,
      ...(live.length ? [
        // Only true if we actually waited it out. A shortened --claim-wait
        // must not be reported as proof of a fault it cannot see.
        CLAIM_WAIT_S >= 35
          ? "That is past the 30s alarm floor, so it is not slow polling. In order of likelihood:"
          : `That is INSIDE the 30s alarm floor — run this again without --claim-wait before believing it. If it holds up:`,
        "1) that install points at a different backend (setup page -> backend URL);",
        "2) the loaded build is older than this repo — sh extension/sync-to-chrome.sh, then Reload;",
        "3) the poll cycle is wedged on an earlier job: open chrome://extensions -> Anticipy ->",
        "   service worker and look for \"previous poll cycle never finished\";",
        "4) it is heartbeating but its job poll is being refused — the same console says so.",
      ] : [
        "The pairing is there but no browser has checked in for minutes, and the heartbeat runs",
        "every 30 seconds. So: that Chrome is closed, or the extension is toggled off, or it was",
        "removed. Open Chrome, check chrome://extensions, then run this again.",
      ]),
    ]);
    skip("the run reaches an ending", ["it was never claimed"]);
  } else {
    const who = candidates.find((a) => a.agent_id === claimed.claimed_by);
    pass("a Chrome claims the job", [
      `claimed ${Math.round((Date.now() - startedAt) / 1000)}s after queueing`,
      `by ${claimed.claimed_by || "(unnamed)"}${who ? ` · ${who.browser}` : ""}`,
      `attempt ${claimed.attempts || 1}, lease held until ${claimed.lease_until || "(none)"}`,
    ]);
    const deadline = Date.now() + RUN_WAIT_S * 1000;
    let saidAt = 0;
    while (Date.now() < deadline) {
      const row = (await call("GET", `/api/collections/jobs/records/${jobId}`)).json || {};
      if (["done", "failed", "cancelled", "needs_user"].includes(row.status)) { ending = row; break; }
      if (Date.now() - saidAt > 15000) {
        saidAt = Date.now();
        note(`working… status ${row.status}${row.result ? ` · ${short(row.result, 90)}` : ""}`);
      }
      await sleep(3000);
    }
    if (!ending) {
      fail("the run reaches an ending", [
        `still ${RUN_WAIT_S}s later. The row is not finished; look at the service-worker console`,
        "(chrome://extensions -> Anticipy -> service worker) and at the job's result field.",
      ]);
    } else if (ending.status === "done") {
      pass("the run reaches an ending", [`done: ${short(ending.result) || "(no result text)"}`]);
    } else if (ending.status === "needs_user") {
      pass("the run reaches an ending", [
        `it handed back and is waiting for the owner: ${short(ending.result) || "(no reason given)"}`,
        "A hand-back IS an ending — the badge on the extension icon is how you find it. Read the",
        "reason though: if it is not about you, it is a fault she is reporting, not a question.",
      ]);
    } else {
      fail("the run reaches an ending", [
        `${ending.status}: ${short(ending.result) || "(no result text)"}`,
        "Chrome did the work; something inside the run went wrong. The result line is her own account of it.",
      ]);
    }
  }
}

await tidy();
verdict();

