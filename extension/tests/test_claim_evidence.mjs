// EVERY REFUSAL LEAVES EVIDENCE, and one bad row never freezes the queue.
//
// claimJob declines work on six different paths, and five of them used to be
// indistinguishable from "there is nothing to do": a bare `return null`, at
// best with a console.warn — and the service-worker console is not a place a
// person goes. The owner's whole experience of it was "she isn't doing
// anything", for six different reasons, with the phone showing "Chrome ready"
// throughout.
//
// Worse, the poll asked for exactly ONE row and gave up on it if it could not
// be run. So a single unrunnable job at the head of the queue — no plan
// attached, or three attempts already spent — stopped the browser lane dead
// for as long as it sat there. Nothing ran. Nothing said so.
//
// Run: node extension/tests/test_claim_evidence.mjs
import assert from "node:assert/strict";
import { installChrome } from "./chrome_mock.mjs";

const harness = installChrome();
globalThis.chrome.storage.session = { get: async () => ({}), set: async () => {} };
globalThis.fetch = async () => ({ ok: false, status: 0, json: async () => ({}), text: async () => "" });
const { claimJob } = await import("../background.js");
// The module polls on import, exactly as the real worker does on boot. Let that
// settle so its writes cannot land in the middle of a case below.
await new Promise((r) => setTimeout(r, 20));

const BASE = "http://127.0.0.1:8090";
const mirror = () => harness.storageData.currentJob || {};

// One place decides what the fake backend answers, so each case below is only
// the shape of its own queue.
let queue = [];        // rows the browser-lane filter returns
let research = [];     // rows the research-lane filter returns
let listStatus = 200;  // what a list read answers with
const patches = [];    // every PATCH this worker sent: {id, body}

function reset({ ownerRef = "owner-1", paired = true } = {}) {
  queue = [];
  research = [];
  listStatus = 200;
  patches.length = 0;
  for (const k of Object.keys(harness.storageData)) delete harness.storageData[k];
  Object.assign(harness.storageData, {
    backendUrl: BASE,
    agentId: "agent-1",
    agentToken: "t".repeat(64),
    ...(ownerRef ? { ownerRef } : {}),
    paired,
  });
}

const reply = (body, status = 200) => ({
  ok: status >= 200 && status < 300, status,
  json: async () => body, text: async () => JSON.stringify(body),
});

globalThis.fetch = async (url, opts = {}) => {
  const u = String(url);
  if (u.includes("/api/collections/jobs/records?")) {
    if (listStatus !== 200) return reply({ error: "no" }, listStatus);
    const filter = decodeURIComponent(u.match(/filter=([^&]*)/)?.[1] || "");
    return reply({ items: /lane="research"/.test(filter) ? research : queue });
  }
  if (u.includes("/api/collections/jobs/records/") && opts.method === "PATCH") {
    const id = u.split("/").pop();
    const body = JSON.parse(opts.body || "{}");
    patches.push({ id, body });
    const row = queue.find((j) => j.id === id) || {};
    // A claim is only a claim if the row comes back stamped — the same
    // read-back the real backend forces.
    return reply({ ...row, ...body });
  }
  if (u.includes("/agent/key")) {
    return reply({ llm_proxy: true, model: "m", owner_ref: harness.storageData.ownerRef || "" });
  }
  return reply({}, 404);
};

// A canonical, runnable row. The embedded plan is what makes it claimable at
// all: isWorkflowJob wants both the column and the plan inside params.
const plan = (id, extra = {}) => ({
  plan_id: `plan-${id}`, owner_ref: "owner-1", lineage_key: `lin-${id}`,
  version: 1, goal: `do ${id}`, consequence: "read_only", state: "queued",
  scope_digest: "sd", effect_key: "ek", facts: {}, required: [],
  approval: null, lease: null, receipt: null, attempts: 0, ...extra,
});
const good = (id, extra = {}) => ({
  id, status: "queued", goal: `do ${id}`, owner_ref: "owner-1", lane: "",
  workflow_id: `plan-${id}`, workflow_version: 1, workflow_state: "queued",
  consequence: "read_only", lineage_key: `lin-${id}`, attempts: 0,
  lease_token: "", lease_until: "", result: "",
  updated: new Date().toISOString(), created: new Date().toISOString(),
  params: JSON.stringify({ task: `do ${id}`, _workflow: plan(id) }),
  ...extra,
});

// ---- 1. paired, but the link carries no owner id --------------------------
{
  reset({ ownerRef: "", paired: true });
  assert.equal(await claimJob(), null, "no owner id means no work, always");
  const m = mirror();
  assert.equal(m.status, "needs_user", "the popup has to be able to show it");
  assert.ok(!m.id, "a diagnosis must carry no job id, or the popup offers Stop on nothing");
  assert.match(`${m.doing} ${m.result}`, /pair|link/i,
    "it must name the actual problem: this browser needs pairing again");
  console.log("PASS 1: linked-with-no-owner-id says so instead of refusing everything in silence");
}

// An install that was never paired already says so on its own face (the popup
// shows a pair code); a second line about it would be noise, not information.
{
  reset({ ownerRef: "", paired: false });
  assert.equal(await claimJob(), null);
  assert.deepEqual(mirror(), {}, "a fresh unpaired install needs no extra scolding");
  console.log("PASS 2: a never-paired install is left to its own pairing screen");
}

// ---- 3. one unrunnable row does not freeze the queue ----------------------
{
  reset();
  // Head of the queue: workflow_id set, but nothing canonical inside params.
  // The backend's workflow guard refuses EVERY patch to a row like this, so it
  // can never be annotated — only skipped, and reported.
  queue = [
    { ...good("poisoned"), params: JSON.stringify({ task: "no plan here" }) },
    good("real"),
  ];
  const claimed = await claimJob();
  assert.equal(claimed?.id, "real",
    "the runnable job behind the poisoned one MUST still run");
  assert.ok(patches.every((p) => p.id !== "poisoned"),
    "a row the guard would refuse must not be written to at all");
  console.log("PASS 3: an unrunnable row at the head of the queue no longer stops everything");
}

// ...and when it is the only thing waiting, the popup carries the account.
{
  reset();
  queue = [{ ...good("poisoned2"), params: JSON.stringify({ task: "no plan" }) }];
  assert.equal(await claimJob(), null);
  const m = mirror();
  assert.match(`${m.doing} ${m.result}`, /poisoned2/,
    "the row a person cannot find is the row that has to be named");
  assert.match(m.result, /called off|cancel/i, "and it must say what to do about it");
  console.log("PASS 4: a job that will never run says so, by id, in the popup");
}

// ---- 5. a legacy row with no workflow column is ended, not left queued ----
{
  reset();
  queue = [{ ...good("legacy"), workflow_id: "", params: JSON.stringify({ task: "old" }),
             result: "the requirement text the brain matches answers against" }];
  assert.equal(await claimJob(), null);
  const p = patches.find((x) => x.id === "legacy");
  assert.ok(p, "a writable row must be told why it is not running");
  assert.equal(p.body.status, "failed", "and it must leave the queue rather than sit there forever");
  assert.match(p.body.result, /requirement text the brain matches/,
    "the existing result is evidence the brain reads — append, never overwrite");
  console.log("PASS 5: a plan-less legacy row is ended on the record, keeping what was already there");
}

// ---- 6. a spent job and a stale job are accounted for, and skipped -------
{
  reset();
  const old = new Date(Date.now() - 20 * 3600 * 1000).toISOString();
  queue = [
    good("spent", { attempts: 3 }),
    good("stale", { updated: old, created: old }),
    good("fresh"),
  ];
  const claimed = await claimJob();
  assert.equal(claimed?.id, "fresh", "two dead rows must not cost the live one its turn");
  const spent = patches.find((p) => p.id === "spent");
  const stale = patches.find((p) => p.id === "stale");
  assert.equal(spent?.body.status, "cancelled", "three spent attempts is an ending, said plainly");
  assert.match(spent.body.result, /tried this 3 times/);
  assert.equal(stale?.body.status, "needs_user", "a day-old errand is asked about, not fired");
  assert.match(stale.body.result, /still stand/i);
  console.log("PASS 6: spent and stale rows are closed with a reason and the queue keeps moving");
}

// ---- 7. the half-minute wake is stated, not left looking like a stall ----
{
  reset();
  queue = [good("waiter")];
  await claimJob();
  const m = mirror();
  assert.equal(m.id, "waiter");
  assert.match(m.result, /30 seconds|half minute/,
    "the popup must say the wait, because the wait is the alarm floor and not a fault");
  console.log("PASS 7: a claimed-but-not-yet-started job explains the ~30s wake");
}

// ---- 8. a refused credential is not silence -------------------------------
{
  reset();
  listStatus = 403;
  assert.equal(await claimJob(), null);
  const m = mirror();
  assert.equal(m.status, "needs_user");
  assert.match(m.result, /403/, "the status code is the one fact a person can act on");
  assert.match(m.result, /Reload|pair/i);
  console.log("PASS 8: a permanently refused job poll surfaces instead of going quietly deaf");
}

// A single failed read is a blip and must not shout; three in a row is a queue
// nobody is reading.
{
  reset();
  listStatus = 500;
  await claimJob();
  assert.deepEqual(mirror(), {}, "one refused read is weather, not news");
  await claimJob();
  await claimJob();
  assert.match(mirror().result || "", /hasn't answered/,
    "three in a row is ninety seconds of a queue nobody is reading");
  // ...and the diagnosis must not outlive the problem.
  listStatus = 200;
  queue = [];
  await claimJob();
  assert.deepEqual(mirror(), {}, "a recovered backend must clear its own diagnosis");
  console.log("PASS 9: transient read failures stay quiet, sustained ones speak, recovery clears it");
}

// ---- 10. work waiting in the lane this browser may not touch -------------
{
  reset();
  research = [{
    ...good("res"), lane: "research",
    updated: new Date(Date.now() - 6 * 60 * 1000).toISOString(),
  }];
  assert.equal(await claimJob(), null);
  const m = mirror();
  assert.match(`${m.doing} ${m.result}`, /server/i,
    "a research job is Anticipy's own work, and the browser must say so rather than look dead");
  assert.match(m.result, /nothing here is broken/i,
    "and it must clear this browser of blame, because this browser is not the problem");
  assert.ok(!patches.length, "the browser may never write to a research row");
  console.log("PASS 10: work queued in the server's lane is named, and this browser is cleared");
}

// A research job that has only just been queued is not a symptom.
{
  reset();
  research = [{ ...good("res2"), lane: "research", updated: new Date().toISOString() }];
  assert.equal(await claimJob(), null);
  assert.deepEqual(mirror(), {}, "the worker takes those within seconds — do not cry about it");
  console.log("PASS 11: a just-queued research job is left alone");
}

console.log("test_claim_evidence: all passed");
