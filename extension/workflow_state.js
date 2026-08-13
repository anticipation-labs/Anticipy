// Deterministic browser-side projection of brain/workflow.py.
//
// The Python brain owns plan creation and approval.  Chrome owns only the
// execution attempt: claim a queued version, renew its lease, park/fail it, or
// attach independently verified evidence.  Every patch updates both the
// indexed PocketBase fields and the embedded canonical plan so a restarted
// process reconstructs one state instead of guessing from loose status text.

export const WORKFLOW_PARAM = "_workflow";

export const LEGACY_STATUS = Object.freeze({
  draft: "awaiting_confirm",
  awaiting_approval: "awaiting_confirm",
  queued: "queued",
  running: "running",
  needs_user: "needs_user",
  succeeded: "done",
  failed: "failed",
  cancelled: "cancelled",
});

const ALLOWED = Object.freeze({
  draft: new Set(["draft", "awaiting_approval", "cancelled"]),
  awaiting_approval: new Set(["awaiting_approval", "queued", "cancelled"]),
  queued: new Set(["queued", "running", "needs_user", "cancelled"]),
  running: new Set(["running", "queued", "needs_user", "succeeded", "failed", "cancelled"]),
  needs_user: new Set(["needs_user", "queued", "cancelled"]),
  succeeded: new Set(["succeeded"]),
  failed: new Set(["failed"]),
  cancelled: new Set(["cancelled"]),
});

function clone(value) {
  return value == null ? value : JSON.parse(JSON.stringify(value));
}

export function parseJobParams(job) {
  if (job && typeof job.params === "object" && job.params !== null) return clone(job.params);
  try { return JSON.parse((job && job.params) || "{}"); }
  catch (_) { return {}; }
}

export function embeddedWorkflow(job, params = parseJobParams(job)) {
  const value = params && params[WORKFLOW_PARAM];
  return value && typeof value === "object" && value.plan_id ? clone(value) : null;
}

export function isWorkflowJob(job) {
  return !!(job && job.workflow_id && embeddedWorkflow(job));
}

function iso(now) {
  return (now instanceof Date ? now : new Date(now || Date.now())).toISOString();
}

function assertedTransition(from, to) {
  if (!LEGACY_STATUS[to]) throw new Error(`unknown workflow state ${to}`);
  if (!ALLOWED[from] || !ALLOWED[from].has(to)) {
    throw new Error(`illegal workflow transition ${from} -> ${to}`);
  }
}

// Build one complete PATCH for a browser-owned workflow transition.
export function workflowPatch(job, nextState, options = {}) {
  const params = parseJobParams(job);
  const workflow = embeddedWorkflow(job, params);
  if (!job || !job.workflow_id || !workflow) {
    throw new Error("workflow metadata is required");
  }
  if (workflow.plan_id !== job.workflow_id) throw new Error("workflow identity mismatch");
  const from = workflow.state || job.workflow_state;
  assertedTransition(from, nextState);

  const at = iso(options.now);
  const next = clone(workflow);
  next.state = nextState;
  next.updated_at = at;
  if (options.reason !== undefined) next.reason = String(options.reason || "");
  if (options.paramsPatch) Object.assign(params, clone(options.paramsPatch));

  const patch = {
    status: LEGACY_STATUS[nextState],
    workflow_state: nextState,
    workflow_version: Number(job.workflow_version || next.version || 0),
  };

  if (nextState === "running") {
    const token = String(options.leaseToken || "");
    const actor = String(options.actorId || "");
    const until = iso(options.leaseUntil);
    if (!token || !actor || !options.leaseUntil) throw new Error("a running claim needs actor, token, and expiry");
    const attempt = Number(options.attempt || job.attempts || next.attempts || 0);
    if (attempt < 1) throw new Error("a running claim needs a positive attempt");
    const acquired = options.acquiredAt ? iso(options.acquiredAt) : at;
    next.lease = { token, actor_id: actor, acquired_at: acquired, expires_at: until, attempt };
    next.attempts = attempt;
    next.reason = options.reason || "claimed";
    patch.lease_token = token;
    patch.lease_until = until;
    patch.claimed_by = actor;
    patch.claimed_at = at;
    patch.attempts = attempt;
  } else {
    next.lease = null;
    patch.lease_token = "";
    patch.lease_until = "";
    patch.claimed_by = "";
    patch.claimed_at = null;
  }

  if (nextState === "succeeded") {
    const evidence = Array.isArray(options.evidence)
      ? options.evidence.map((x) => String(x).trim()).filter(Boolean) : [];
    if (!options.verified || !evidence.length || !job.effect_key) {
      throw new Error("success requires verified evidence for this effect");
    }
    const receipt = {
      effect_key: job.effect_key,
      summary: String(options.summary || "").trim(),
      evidence,
      verified: true,
      recorded_at: at,
    };
    next.receipt = receipt;
    next.reason = "verified complete";
    patch.receipt = JSON.stringify(receipt);
    patch.effect_uncertain = false;
  } else {
    next.receipt = null;
    patch.receipt = "";
  }

  if (nextState === "cancelled") {
    next.approval = null;
    patch.approval = "";
    patch.effect_uncertain = false;
  } else if (options.effectUncertain !== undefined) {
    patch.effect_uncertain = !!options.effectUncertain;
  }

  params[WORKFLOW_PARAM] = next;
  patch.params = JSON.stringify(params);
  return patch;
}

export function markEffectUncertainPatch(job) {
  if (!isWorkflowJob(job)) return { effect_uncertain: true };
  if ((job.workflow_state || embeddedWorkflow(job).state) !== "running") {
    throw new Error("only running work can reach an external effect");
  }
  return { effect_uncertain: true };
}

export function heartbeatPatch(job, { leaseToken, leaseUntil, now } = {}) {
  const params = parseJobParams(job);
  const workflow = embeddedWorkflow(job, params);
  if (!workflow || workflow.state !== "running" || !workflow.lease) {
    throw new Error("only running workflow work has a heartbeat");
  }
  if (!leaseToken || workflow.lease.token !== leaseToken || job.lease_token !== leaseToken) {
    throw new Error("heartbeat lease mismatch");
  }
  const at = iso(now);
  const until = iso(leaseUntil);
  workflow.lease.expires_at = until;
  workflow.updated_at = at;
  params[WORKFLOW_PARAM] = workflow;
  return {
    claimed_at: at,
    lease_until: until,
    params: JSON.stringify(params),
  };
}
