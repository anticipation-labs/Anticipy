// THE JOB LAYER. Everything that touches a jobs row lives here exactly once,
// because the two traps this module exists to avoid are both silent, and a
// second copy of "how to mint a job" is how one copy quietly stops matching
// the guard.
//
//   TRAP 1  `params` is a TEXT column. POST a nested object and PocketBase
//           stores "" without complaint; the agent then wakes with no task and
//           start_url=about:blank and reports it could not find anything.
//   TRAP 2  Every column must byte-match the plan embedded in params._workflow
//           or workflow_guard.pb.js refuses the write 409
//           (backend/pb_hooks/workflow_guard.pb.js:81-96).
//
// Both are proven, not assumed: proof/battery/selfcheck.mjs writes a real row
// through this module and re-reads it, and it also writes a deliberately wrong
// one to confirm the trap and the guard are still there to be fallen into.
import { createHash, randomUUID } from "node:crypto";

let CFG = { base: "http://127.0.0.1:8090", ownerRef: "", ownerId: "local-dev" };
export function configure(cfg) { CFG = { ...CFG, ...cfg }; }

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
export const short = (s, n = 200) => String(s ?? "").replace(/\s+/g, " ").trim().slice(0, n);
export const secs = (ms) => Math.round(ms / 100) / 10;

const headers = () => {
  const h = { "Content-Type": "application/json" };
  // Set on production, unset on the rig. Never printed.
  if (process.env.ANTICIPY_SERVICE_TOKEN) h["X-Anticipy-Token"] = process.env.ANTICIPY_SERVICE_TOKEN;
  return h;
};

async function once(method, path, { body, timeoutMs = 20000 } = {}) {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), timeoutMs);
  try {
    const r = await fetch(`${CFG.base}${path}`, {
      method, headers: headers(), signal: ctl.signal,
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    const text = await r.text();
    let json = null;
    try { json = text ? JSON.parse(text) : null; } catch (_) { /* not json */ }
    return { status: r.status, ok: r.ok, json, text };
  } catch (e) {
    // undici hides the real reason (ECONNREFUSED, EAI_AGAIN, aborted) in
    // `cause`; without it every network fault reads as the same three words.
    return { status: 0, ok: false, json: null, text: `${e}${e?.cause ? ` (${e.cause})` : ""}` };
  } finally { clearTimeout(t); }
}

// PocketBase RESTARTS ITSELF whenever a file in backend/pb_hooks changes, which
// on a shared rig happens while a multi-hour battery is running. For those few
// seconds every request refuses, and a read that gave up there would be
// recorded as "the job row vanished" — a harness artefact reported as an engine
// failure. A real HTTP answer, 404 and 409 included, is returned untouched.
export async function call(method, path, opts = {}) {
  let last = null;
  for (let attempt = 0; attempt < 6; attempt++) {
    last = await once(method, path, opts);
    if (last.status !== 0 && last.status !== 503) return last;
    // A POST is never retried: a refused connection may still have created the
    // row, and a second identical POST would queue two browser jobs.
    if (method === "POST") return last;
    await sleep(1000 + attempt * 1500);
  }
  return last;
}

// The brain's canonical form, so digests match byte for byte
// (brain/workflow.py:_canonical).
export const canonical = (value) => {
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === "object") {
    const out = {};
    for (const k of Object.keys(value).sort()) out[k] = canonical(value[k]);
    return out;
  }
  return value;
};
export const digest = (payload) =>
  createHash("sha256").update(JSON.stringify(canonical(payload)), "utf8").digest("hex");
// Python's datetime.isoformat(), which is what Plan.from_dict reads back.
export const stamp = (d = new Date()) => d.toISOString().replace("Z", "+00:00");

export const TERMINAL = new Set(["done", "failed", "cancelled", "needs_user"]);

// One row, canonical, exactly as the brain would queue it.
export function mintPayload(task, { source = "proof/battery/run.mjs" } = {}) {
  const planId = randomUUID();
  const lineage = `battery-${planId.slice(0, 8)}`;
  const goal = task.goal;
  const facts = task.facts && typeof task.facts === "object" ? { ...task.facts } : {};
  const consequence = task.consequence === "consequential" ? "consequential" : "read_only";
  const plan = {
    plan_id: planId,
    owner_ref: CFG.ownerRef,
    lineage_key: lineage,
    version: 1,
    goal,
    authority_text: goal,
    consequence,
    state: "queued",
    facts,
    // A fact the plan declares REQUIRED must be present or the guard refuses
    // the row (workflow_guard.pb.js:100). So only what we actually supplied is
    // required — the point of form-permit-missing-fact is that the engine must
    // notice the gap by itself, not that the database blocks it.
    required: Object.keys(facts),
    source_event_ids: [lineage],
    approval: null,
    lease: null,
    receipt: null,
    attempts: 0,
    reason: "",
    created_at: stamp(),
    updated_at: stamp(),
  };
  const scopePayload = {
    plan_id: planId, version: 1, goal, facts, consequence, authority_text: goal,
  };
  plan.scope_digest = digest(scopePayload);
  plan.effect_key = digest({ owner_ref: CFG.ownerRef, ...scopePayload });

  // Consequential work may only be queued with an approval bound to this exact
  // plan version and scope (workflow_guard.pb.js:167). In the product those are
  // the owner's own words out of a text message; in the battery they are the
  // battery's, and they SAY SO — a receipt reading "approved by the battery" is
  // the truth, and one reading "approved by Jose" would be a forgery.
  let approvalColumn = "";
  if (consequence === "consequential") {
    plan.approval = {
      plan_id: planId,
      plan_version: 1,
      scope_digest: plan.scope_digest,
      owner_words: `yes, go ahead — queued by proof/battery (${task.id})`,
      approved_at: stamp(),
    };
    approvalColumn = JSON.stringify(plan.approval);
  }

  const params = JSON.stringify({
    task: goal,
    start_url: task.start_url,
    authorized: true,
    source: `${source} ${task.id} at ${new Date().toISOString()}`,
    _workflow: plan,
  });
  return {
    planId, lineage, plan, params, consequence, approvalColumn,
    body: {
      goal,
      params,
      device_id: "anticipy",
      owner: CFG.ownerId,
      owner_ref: CFG.ownerRef,
      // NOT "research": research_lane.pb.js hides that lane from the
      // extension's poll on purpose (read-only goals run server-side).
      lane: "",
      workflow_id: planId,
      workflow_version: 1,
      workflow_state: "queued",
      consequence,
      lineage_key: lineage,
      effect_key: plan.effect_key,
      scope_digest: plan.scope_digest,
      approval: approvalColumn,
      receipt: "",
      lease_token: "",
      lease_until: "",
      source_event_ids: JSON.stringify([lineage]),
      attempts: 0,
      status: "queued",
    },
  };
}

// A cancel written the way workflowPatch writes one (extension/workflow_state.js:64)
// so the guard's redundancy check passes: new state, cleared lease, empty
// receipt. running -> cancelled is the one transition a non-executor may make
// without holding the lease (workflow_guard.pb.js:156).
export async function cancelJob(id, why) {
  for (let attempt = 0; attempt < 3; attempt++) {
    const got = await call("GET", `/api/collections/jobs/records/${id}`);
    if (got.status === 404) return "gone";
    const row = got.json;
    if (!row || !row.id) return `unreadable (${short(got.text, 80)})`;
    if (TERMINAL.has(row.status)) return row.status;
    let params = {};
    try { params = JSON.parse(String(row.params || "{}")); } catch (_) { params = {}; }
    const wf = params._workflow;
    if (!wf) return `no embedded plan on ${id}`;
    wf.state = "cancelled";
    wf.lease = null;
    wf.receipt = null;
    wf.reason = why;
    wf.updated_at = stamp();
    params._workflow = wf;
    const r = await call("PATCH", `/api/collections/jobs/records/${id}`, {
      body: {
        status: "cancelled",
        workflow_state: "cancelled",
        workflow_version: Number(row.workflow_version || wf.version || 1),
        lease_token: "",
        lease_until: "",
        claimed_by: "",
        claimed_at: null,
        receipt: "",
        effect_uncertain: false,
        result: why,
        params: JSON.stringify(params),
      },
    });
    if (r.ok) return "cancelled";
    // A 409 here is nearly always a race with the executor's own write:
    // re-read and try again rather than leave a live browser job behind.
    if (attempt === 2) return `cancel refused ${r.status} ${short(r.text, 160)}`;
    await sleep(1500);
  }
  return "cancel failed";
}

// ------------------------------------------------------------ trace archaeology
// Every string below is a line the agent loop writes into its own history, which
// background.js persists onto jobs.trace as the run works (background.js:1019).
// They are the only honest source for "what did this run cost" — the
// alternative is asking the model, which is not evidence.
const MARK = {
  // agent_loop.js:4125 — a step taken from a compiled recipe, no model call.
  replayed: /from a route I already know, no thinking needed/g,
  // agent_loop.js:4104 — the saved route stopped fitting; it reasons from here.
  stale: /the shortcut I learned no longer fits/g,
  // agent_loop.js:4139 — a vision model was billed for this step.
  vision: /looking at the page as well as reading it/g,
  // agent_loop.js:4141 onwards — a model call that did not come back.
  llmError: /llm error|llm_step timed out|rate limit/gi,
};
export function readTrace(trace) {
  const text = String(trace || "");
  const stepNumbers = new Set();
  for (const m of text.matchAll(/^step (\d+):/gm)) stepNumbers.add(Number(m[1]));
  const count = (re) => (text.match(re) || []).length;
  const steps = stepNumbers.size;
  const replayed = count(MARK.replayed);
  return {
    steps,
    replayed_steps: replayed,
    // What the run actually paid a model for: a replayed step is free, every
    // other step is one llmStep call (agent_loop.js:4140).
    decisions: Math.max(0, steps - replayed),
    stale_recipe: count(MARK.stale),
    vision_steps: count(MARK.vision),
    llm_errors: count(MARK.llmError),
    trace_chars: text.length,
    trace_tail: text.split("\n").slice(-14).join("\n").slice(-2400),
  };
}

// The filter from extension/background.js:claimJob, character for character. A
// row invisible to THIS query will never run, however healthy everything else
// looks.
export const pollFilter = (ownerRef) =>
  `status="queued" && owner_ref="${ownerRef}" && workflow_id!="" && lane!="research"`;
