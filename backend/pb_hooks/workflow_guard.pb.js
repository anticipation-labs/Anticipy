/// <reference path="../pb_data/types.d.ts" />

// The database is the final authority for workflow transitions.  A stale app,
// extension, model, or worker may ask for an illegal state; this hook refuses
// it before a real-world action can be duplicated or falsely marked complete.
routerUse((e) => {
  const path = e.request.url.path;
  const method = e.request.method;
  const base = "/api/collections/jobs/records";
  if (path !== base && !path.startsWith(base + "/")) return e.next();
  if (method !== "POST" && method !== "PATCH") return e.next();

  let body = {};
  try { body = e.requestInfo().body || {}; } catch (_) { body = {}; }
  let old = null;
  if (method === "PATCH") {
    try { old = e.app.findRecordById("jobs", path.split("/").pop()); } catch (_) {}
  }
  const oldWorkflow = old ? old.getString("workflow_id") : "";
  const workflow = String(body.workflow_id || oldWorkflow || "");
  // Legacy rows continue during the migration window.  New code always
  // supplies workflow_id; once adoption telemetry reaches 100%, this branch
  // can be removed without changing the state law below.
  if (!workflow) return e.next();

  const reject = (why) => e.json(409, { error: "workflow violation", detail: why });
  const oldStatus = old ? old.getString("status") : "";
  const nextStatus = String(body.status || oldStatus || "");
  const oldVersion = old ? Number(old.get("workflow_version") || 0) : 0;
  const nextVersion = Number(body.workflow_version != null
    ? body.workflow_version : oldVersion);
  const oldState = old ? old.getString("workflow_state") : "";
  const nextState = String(body.workflow_state || oldState || "");
  const oldConsequence = old ? old.getString("consequence") : "";
  const consequence = String(body.consequence || oldConsequence || "");
  const agentCaller = !!(e.request.header.get("X-Anticipy-Agent-ID") || "");
  const uncertain = body.effect_uncertain != null
    ? !!body.effect_uncertain : !!(old && old.getBool("effect_uncertain"));

  // The row and its embedded plan are deliberately redundant: Python, Swift
  // and Chrome all need the state law locally, but the database must reject
  // a write that updates only the convenient half. Otherwise a client can
  // show one approved plan while the executor reads another.
  let params = {};
  let embedded = null;
  try {
    const raw = body.params != null
      ? String(body.params) : (old ? old.getString("params") : "");
    params = JSON.parse(raw || "{}");
    embedded = params && params._workflow;
  } catch (_) { return reject("workflow params are not parseable"); }
  if (!embedded || typeof embedded !== "object") {
    return reject("canonical workflow is missing from params");
  }
  const rowValue = (name, fallback) => body[name] != null
    ? body[name] : (old ? old.get(name) : fallback);
  const embeddedApproval = embedded.approval || null;
  const embeddedLease = embedded.lease || null;
  const embeddedReceipt = embedded.receipt || null;
  let rowApproval = null;
  let rowReceipt = null;
  try {
    const raw = String(rowValue("approval", "") || "");
    rowApproval = raw ? JSON.parse(raw) : null;
  } catch (_) { return reject("row approval is not parseable"); }
  try {
    const raw = String(rowValue("receipt", "") || "");
    rowReceipt = raw ? JSON.parse(raw) : null;
  } catch (_) { return reject("row receipt is not parseable"); }
  const ordered = (value) => {
    if (Array.isArray(value)) return value.map(ordered);
    if (value && typeof value === "object") {
      const out = {};
      for (const key of Object.keys(value).sort()) out[key] = ordered(value[key]);
      return out;
    }
    return value;
  };
  const sameJSON = (a, b) => JSON.stringify(ordered(a || null))
    === JSON.stringify(ordered(b || null));
  if (String(embedded.plan_id || "") !== workflow
      || Number(embedded.version || 0) !== nextVersion
      || String(embedded.state || "") !== nextState
      || String(embedded.goal || "") !== String(rowValue("goal", "") || "")
      || String(embedded.consequence || "") !== consequence
      || String(embedded.lineage_key || "") !== String(rowValue("lineage_key", "") || "")
      || String(embedded.owner_ref || "") !== String(rowValue("owner_ref", "") || "")
      || String(embedded.scope_digest || "") !== String(rowValue("scope_digest", "") || "")
      || String(embedded.effect_key || "") !== String(rowValue("effect_key", "") || "")
      || !sameJSON(embeddedApproval, rowApproval)
      || !sameJSON(embeddedReceipt, rowReceipt)
      || Number(embedded.attempts || 0) !== Number(rowValue("attempts", 0) || 0)
      || String((embeddedLease && embeddedLease.token) || "")
          !== String(rowValue("lease_token", "") || "")) {
    return reject("job fields disagree with the embedded workflow");
  }
  const required = Array.isArray(embedded.required) ? embedded.required : [];
  const facts = embedded.facts && typeof embedded.facts === "object"
    ? embedded.facts : {};
  if (["queued", "running", "succeeded"].includes(nextState)
      && required.some((name) => facts[name] == null || facts[name] === "")) {
    return reject("required facts are missing from the approved plan");
  }

  const stateForStatus = {
    awaiting_confirm: ["draft", "awaiting_approval"],
    queued: ["queued"], running: ["running"], needs_user: ["needs_user"],
    done: ["succeeded"], failed: ["failed"], cancelled: ["cancelled"],
  };
  if (!stateForStatus[nextStatus] || !stateForStatus[nextStatus].includes(nextState)) {
    return reject(`status ${nextStatus} disagrees with state ${nextState}`);
  }
  if (!workflow || nextVersion < 1 || !String(body.lineage_key || (old && old.getString("lineage_key")) || "")) {
    return reject("workflow id, version, and lineage are required");
  }
  if (!String(body.owner_ref || (old && old.getString("owner_ref")) || "")) {
    return reject("owner_ref is required for workflow jobs");
  }
  if (old) {
    if (body.workflow_id && body.workflow_id !== oldWorkflow) return reject("workflow id is immutable");
    if (body.owner_ref && body.owner_ref !== old.getString("owner_ref")) return reject("owner is immutable");
    if (nextVersion < oldVersion) return reject("workflow version cannot move backwards");
    const allowed = {
      awaiting_confirm: ["awaiting_confirm", "queued", "cancelled"],
      queued: ["queued", "running", "needs_user", "cancelled"],
      running: ["running", "needs_user", "done", "failed", "cancelled", "queued"],
      needs_user: ["needs_user", "queued", "cancelled"],
      failed: ["failed"],
      done: ["done"],
      cancelled: ["cancelled"],
    };
    if (!(allowed[oldStatus] || []).includes(nextStatus)) {
      return reject(`illegal transition ${oldStatus} -> ${nextStatus}`);
    }
    const changesPlan = body.goal != null && body.goal !== old.getString("goal");
    const changesScope = body.scope_digest != null
      && body.scope_digest !== old.getString("scope_digest");
    const changesEffect = body.effect_key != null
      && body.effect_key !== old.getString("effect_key");
    if ((changesPlan || changesScope || changesEffect) && nextVersion <= oldVersion) {
      return reject("changing a plan requires a new workflow version");
    }
    // A browser token is execution authority, never owner authority. It may
    // advance the approved version under its lease; it may not edit scope,
    // mint approval words, or create a new version for itself.
    const changesApproval = body.approval != null
      && String(body.approval || "") !== old.getString("approval");
    if (agentCaller && (changesPlan || changesScope || changesEffect
                        || nextVersion !== oldVersion || changesApproval)) {
      return reject("an executor cannot rewrite or approve its plan");
    }
    // A status string is not a claim.  Every write made by a running
    // executor must prove it holds the exact durable lease stored on the row.
    // An expired lease may only recover/park/fail; it may never keep acting or
    // manufacture a success receipt after another executor is free to claim.
    if (oldStatus === "running" && nextStatus !== "cancelled") {
      const held = old.getString("lease_token");
      const presented = e.request.header.get("X-Anticipy-Lease") || "";
      if (!held || presented !== held) return reject("running update came from the wrong lease");
      const rawUntil = old.getString("lease_until");
      const expired = !rawUntil || new Date(rawUntil).getTime() <= Date.now();
      if (expired && !["queued", "needs_user", "failed"].includes(nextStatus)) {
        return reject("expired executor may only recover, park, or fail");
      }
    }
  }
  if (nextStatus === "queued" && consequence === "consequential") {
    let approval = {};
    try { approval = JSON.parse(String(body.approval || (old && old.getString("approval")) || "")); }
    catch (_) { return reject("consequential work needs parseable approval"); }
    const scope = String(body.scope_digest || (old && old.getString("scope_digest")) || "");
    if (approval.plan_id !== workflow || Number(approval.plan_version) !== nextVersion
        || !scope || approval.scope_digest !== scope || !approval.owner_words) {
      return reject("approval is not bound to this exact plan version");
    }
  }
  if (nextStatus === "queued" && old && old.getBool("effect_uncertain")) {
    let reconciliation = {};
    try {
      reconciliation = JSON.parse(String(body.reconciliation || ""));
    } catch (_) { return reject("uncertain effect needs reconciliation before retry"); }
    const effect = String(body.effect_key || old.getString("effect_key") || "");
    if (uncertain || !reconciliation.verified
        || reconciliation.effect_key !== effect
        || reconciliation.conclusion !== "not_applied"
        || !reconciliation.owner_words
        || !Array.isArray(reconciliation.evidence)
        || reconciliation.evidence.length === 0) {
      return reject("uncertain effect was not proven safe to retry");
    }
  }
  if (nextStatus === "running") {
    const lease = String(body.lease_token || (old && old.getString("lease_token")) || "");
    const actor = String(body.claimed_by || (old && old.getString("claimed_by")) || "");
    const until = String(body.lease_until || (old && old.getString("lease_until")) || "");
    if (!lease || !actor || !until) return reject("running work needs an actor and lease");
    if (new Date(until).getTime() <= Date.now()) return reject("running lease must expire in the future");
  } else if (old && oldStatus === "running") {
    const lease = String(body.lease_token != null ? body.lease_token : old.getString("lease_token"));
    if (lease) return reject("non-running work may not retain an execution lease");
  }
  if (nextStatus === "done") {
    let receipt = {};
    try { receipt = JSON.parse(String(body.receipt || (old && old.getString("receipt")) || "")); }
    catch (_) { return reject("done needs a parseable receipt"); }
    const effect = String(body.effect_key || (old && old.getString("effect_key")) || "");
    if (!receipt.verified || receipt.effect_key !== effect
        || !Array.isArray(receipt.evidence) || receipt.evidence.length === 0) {
      return reject("done needs verified evidence for this exact effect");
    }
  }
  return e.next();
});
