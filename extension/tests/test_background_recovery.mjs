// Four ways the browser arm lied about, or lost, the owner's work — none of
// which produced a single error the owner could see.
//
//   1. A registration reply lost mid-flight left storage holding an agentId
//      with no record. Every later boot re-POSTed it, got 409 forever, and the
//      extension was dead in every path while the setup page said "Connected".
//   2. A job parked on Friday resumed on Monday against tab id 847 — by then
//      the owner's own open page, driven by chrome.debugger.
//   3. Losing the lease (wifi drop, a second window) was reported as "you
//      called this off", accusing the owner of stopping their own booking.
//   4. The popup's job mirror was written when a run started and never again,
//      so a job finished yesterday still read "Working on this" with a Stop
//      button whose write the state machine refuses.
//
// Run: node extension/tests/test_background_recovery.mjs
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { installChrome } from "./chrome_mock.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(join(HERE, "../background.js"), "utf8");

const harness = installChrome();
// MV3 session storage: emptied when the BROWSER session ends, kept across
// service-worker restarts. chrome_mock only models storage.local, so the one
// surface these tests turn on lives here.
const sessionData = {};
globalThis.chrome.storage.session = {
  get: async (keys) => {
    const want = typeof keys === "string" ? [keys] : keys;
    const out = {};
    for (const k of want) if (k in sessionData) out[k] = sessionData[k];
    return out;
  },
  set: async (obj) => { Object.assign(sessionData, obj); },
};
const endBrowserSession = () => { for (const k of Object.keys(sessionData)) delete sessionData[k]; };

globalThis.fetch = async () => ({ ok: false, status: 0, json: async () => ({}), text: async () => "" });
const { ensureRegistered, resumableTabId, reconcileCurrentJob, withJobWrite } =
  await import("../background.js");
await new Promise((r) => setTimeout(r, 10));

// ---- 1. A 409 on register is recoverable, not a life sentence -------------
{
  for (const key of ["agentId", "agentToken", "recordId", "agentCredentialInstalled"])
    delete harness.storageData[key];
  // The half-finished install: the id was saved, the reply never landed.
  harness.storageData.agentId = "orphaned-agent-id-0123456789";

  const tried = [];
  globalThis.fetch = async (url, opts = {}) => {
    if (!String(url).endsWith("/agent/register")) {
      return { ok: false, status: 0, json: async () => ({}), text: async () => "" };
    }
    const id = JSON.parse(opts.body).agent_id;
    tried.push(id);
    if (id === "orphaned-agent-id-0123456789") {
      return { ok: false, status: 409, json: async () => ({ error: "agent already registered" }), text: async () => "" };
    }
    return {
      ok: true, status: 200, text: async () => "",
      json: async () => ({ id: "rec-2", agent_token: "tok-2", pair_code: "654321" }),
    };
  };

  const reg = await ensureRegistered();
  assert.ok(reg, "a 409 on the orphaned id must not leave this browser unregistered forever");
  assert.equal(tried.length, 2, "the 409 must be answered with exactly one fresh attempt");
  assert.notEqual(tried[1], tried[0], "the retry must use a NEW identity — the old one is taken");
  assert.equal(harness.storageData.recordId, "rec-2");
  assert.equal(harness.storageData.agentId, tried[1], "the fresh identity has to be the one we keep");
  assert.equal(harness.storageData.pairCode, "654321",
    "without a pair code the only recovery button stays hidden and the owner is stuck");
  console.log("PASS 1: an already-registered id recovers with a fresh identity and a real pair code");
}

// ---- 2. A parked tab id is only ours inside the session that parked it ----
{
  globalThis.fetch = async () => ({ ok: false, status: 0, json: async () => ({}), text: async () => "" });
  endBrowserSession();

  assert.equal(await resumableTabId({}), null, "no parked tab means nothing to resume");

  // The session id is minted on first use, exactly as the running worker mints
  // it; a stranger's stamp is refused on the way.
  assert.equal(await resumableTabId({ resume_tab: 1, resume_session: "someone-else" }), null,
    "a stamp from another session is not a resume ticket");
  const session = (await chrome.storage.session.get(["browserSession"])).browserSession;
  assert.ok(session, "this browser session needs an id to stamp a parked tab with");
  const parked = { resume_tab: 847, resume_session: session };

  assert.equal(await resumableTabId(parked), 847,
    "inside the session that parked it, tab 847 IS the parked tab — resume there");

  // The weekend: Chrome restarts, session storage is emptied, tab ids start over.
  endBrowserSession();
  assert.equal(await resumableTabId(parked), null,
    "after a browser restart, tab 847 is whatever the owner has open — never attach to it");

  // Rows parked by a build that never stamped a session are equally unprovable.
  assert.equal(await resumableTabId({ resume_tab: 847 }), null,
    "an unstamped parked tab cannot be proven ours");
  console.log("PASS 2: a parked tab id is honoured only in the session that parked it");
}

// The stamp is worthless unless it is written next to the tab id, and it must
// never reach the model as a 'fact' about the errand.
//
// RUN THE RULE, DO NOT LOOK FOR IT. Both halves used to be regexes over
// background.js source, and both went red the moment the expressions they
// matched were lifted into named functions — a check pinned to an
// implementation's shape rather than to what it does.
{
  const { handBackParamsPatch, ownerFactsFromParams } = await import("../background.js");
  const patch = handBackParamsPatch({ status: "needs_user", tabId: 847 }, "sess-A");
  assert.equal(patch.resume_tab, 847,
    "the parked tab id must be written on a hand-back that kept a tab");
  assert.equal(patch.resume_session, "sess-A",
    "the parked tab id must be written together with the session that owns it");
  const tabless = handBackParamsPatch({ status: "needs_user" }, "sess-A");
  assert.ok(!("resume_tab" in tabless) && !("resume_session" in tabless),
    "a hand-back with no tab must not stamp one");
  assert.deepEqual(
    ownerFactsFromParams({ resume_tab: 847, resume_session: "sess-A", party_size: 4 }),
    { party_size: 4 },
    "the session stamp is bookkeeping, not a fact about the task");
}
console.log("PASS 3: the session stamp is persisted with the tab id and kept out of facts");

// ---- 4. Lease lost is not "you called this off" ---------------------------
{
  let row = { id: "j1", workflow_id: "w1", workflow_state: "cancelled", status: "cancelled" };
  globalThis.fetch = async (url) => String(url).includes("/jobs/records/j1")
    ? { ok: true, status: 200, json: async () => row, text: async () => "" }
    : { ok: false, status: 0, json: async () => ({}), text: async () => "" };

  const cancelBranch = source.match(
    /if \(out\.status === "cancelled"\) \{[\s\S]{0,1400}?\n      \}/)[0];
  assert.ok(/ownerCancelled\(job\.id\)/.test(cancelBranch),
    "before telling the owner they cancelled, ask the row whether they did");
  assert.ok(/lost my hold on this one/.test(cancelBranch),
    "a lost claim must be described as a lost claim, not as their decision");
  assert.ok(/console\.warn\([^)]*lost its claim/.test(cancelBranch),
    "losing a claim mid-run wrote nothing anywhere — it has to be visible somewhere");
  // The two outcomes must be reachable from the same code, not a fixed string.
  assert.ok(/stoppedByOwner\s*\?/.test(cancelBranch),
    "the wording must be chosen by what the row says, not hardcoded");
  console.log("PASS 4: a lost lease is reported as a lost lease, and logged");
}

// ---- 5. The popup mirror is repaired from the row, not left frozen --------
{
  const finished = {
    id: "j2", workflow_id: "w2", workflow_state: "succeeded", status: "done",
    result: "Booked Earls for 4 at 7pm.",
    params: JSON.stringify({ _workflow: { plan_id: "w2", state: "succeeded" } }),
  };
  globalThis.fetch = async (url) => String(url).includes("/jobs/records/j2")
    ? { ok: true, status: 200, json: async () => finished, text: async () => "" }
    : { ok: false, status: 0, json: async () => ({}), text: async () => "" };

  // What quitting Chrome mid-booking leaves behind.
  harness.storageData.currentJob = { id: "j2", status: "running", doing: "book Earls for 4", result: "" };
  await reconcileCurrentJob();
  assert.equal(harness.storageData.currentJob.status, "done",
    "a job that finished yesterday must not still read 'Working on this'");
  assert.equal(harness.storageData.currentJob.result, "Booked Earls for 4 at 7pm.");
  assert.equal(harness.storageData.currentJob.doing, "book Earls for 4",
    "the errand's own words survive the repair — that is how the owner recognises it");

  // A row that is gone is 'called off', and a read that merely fails must not
  // invent a status: a network blip is not news about the job.
  harness.storageData.currentJob = { id: "j3", status: "running", doing: "email Priya" };
  globalThis.fetch = async () => ({ ok: false, status: 404, json: async () => ({}), text: async () => "" });
  await reconcileCurrentJob();
  assert.equal(harness.storageData.currentJob.status, "removed");

  harness.storageData.currentJob = { id: "j4", status: "running", doing: "email Priya" };
  globalThis.fetch = async () => ({ ok: false, status: 503, json: async () => ({}), text: async () => "" });
  await reconcileCurrentJob();
  assert.equal(harness.storageData.currentJob.status, "running",
    "a backend hiccup must not rewrite the owner's job status");
  console.log("PASS 5: the popup mirror is read back off the row instead of freezing at 'running'");
}

// The repair is worthless if nothing calls it.
assert.ok(/reconcileCurrentJob\(\);\s*$/m.test(source),
  "the mirror must be reconciled on worker boot, like refreshBadge already is");
assert.ok(/\.catch\(refused\("stop"\)\)/.test(source) && /\.catch\(refused\("retry"\)\)/.test(source),
  "a refused stop/retry must not answer ok — it must repair the mirror and say so");
console.log("PASS 6: boot and the refused-control paths both reconcile the mirror");

// ---- 7. Heartbeat and trace writes never interleave on one job ------------
{
  // The heartbeat and the trace writer both re-serialize the whole params
  // blob. Interleaved, the heartbeat's older snapshot lands last and the
  // journal silently reverts — this proves each write is BUILT from what the
  // previous one committed, not from a snapshot taken before it ran.
  let committed = "journal-0";
  const write = (value) => new Promise((r) => setTimeout(() => { committed = value; r(value); }, 15));
  const seen = [];

  const a = withJobWrite("j5", () => { seen.push(committed); return write("journal-1"); });
  const b = withJobWrite("j5", () => { seen.push(committed); return write("journal-2"); });
  await Promise.all([a, b]);
  assert.deepEqual(seen, ["journal-0", "journal-1"],
    "the second writer must build its patch from what the first one committed");
  assert.equal(committed, "journal-2", "the later write is the one that survives");

  // One refused write must not strand every later write for that job.
  await withJobWrite("j5", () => Promise.reject(new Error("409"))).catch(() => {});
  assert.equal(await withJobWrite("j5", () => write("journal-3")), "journal-3",
    "a 409 on one write cannot silence the lease renewal that follows it");
  console.log("PASS 7: per-job writes are serialized and survive a refusal");
}

assert.ok(/active\.job = await withJobWrite\(id, \(\) => \{/.test(source),
  "the heartbeat's patch must be built inside the chain, not before it");
assert.ok(/job = await withJobWrite\(job\.id, \(\) => updateJob\(job\.id,\n\s+\{ trace,/.test(source),
  "the trace/journal write must share the chain, or there is nothing to serialize against");
console.log("PASS 8: both writers on a live job go through the same chain");

console.log("test_background_recovery: all passed");
process.exit(0);
