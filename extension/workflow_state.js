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
    // The durable receipt is a compact proof index. The complete human result
    // stays in jobs.result and the complete model exchange stays in the audit
    // ledger; duplicating both here can exceed PocketBase's text validation
    // limit and turn a verified browser success into HTTP 400.
    const evidence = Array.isArray(options.evidence)
      ? options.evidence.map((x) => String(x).trim().slice(0, 1000))
          .filter(Boolean).slice(0, 12) : [];
    if (!options.verified || !evidence.length || !job.effect_key) {
      throw new Error("success requires verified evidence for this effect");
    }
    const receipt = {
      effect_key: job.effect_key,
      summary: String(options.summary || "").trim().slice(0, 2000),
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
    // The approval HISTORY survives cancellation. Clearing it here made the
    // extension's own at-cap cancel a guaranteed 409 — the backend guard
    // (rightly) forbids an executor touching approval, so the cancel
    // retried silently every 30s forever while the job sat wedged
    // (live, 2026-08-15: 23 identical 409s on one Earls booking).
    patch.effect_uncertain = false;
  } else if (options.effectUncertain !== undefined) {
    patch.effect_uncertain = !!options.effectUncertain;
  }

  params[WORKFLOW_PARAM] = next;
  patch.params = JSON.stringify(params);
  return patch;
}

// THE INTENT, NOT JUST THE FLAG. docs/BRIEF.html promises "an intent journal
// written before every click, so 'did the send actually happen?' is
// answerable after any crash". Until 2026-09-05 this wrote one boolean. The
// control's label, the page, and the two keys the at-most-once gate refuses
// repeats by (the control signature and the submission digest) lived only in
// the worker's memory — and a Manifest V3 worker is reclaimed mid-run as a
// matter of course. So a crash between the click and the receipt left the
// owner a card saying "check the site" with nothing to look for, and a retry
// after it started with an EMPTY performedExternalEffects set, re-sending the
// same submission the flag had been set to prevent. That is the duplicate
// booking the loop's own comment calls the cardinal sin, and the Brief's
// moment 49 ("nothing is lost and nothing duplicates") names outright.
//
// `intent` is `{ doing, url, sig, digest, at, step, tab, session }`. `doing`
// is humanStep's sentence, which names the FIELD and never the value typed
// into it — the same rule _execution_journal keeps, because this row is
// exportable. `sig` and `digest` are hashes; `step` is the loop's step
// counter; `tab` is the Chrome tab id and `session` the browser-session stamp
// that says whether that id still means the same tab (background.js
// browserSessionId — the resume_tab rule, applied to the surviving tab).
// No form value is written here, and none may be added.
//
// Audit #90, the reconciliation half (2026-09-05): `step` is what lets the
// `after` half be written (effectIntentAfter below), and `tab` + `session`
// are what let a recovery find the SURVIVING tab after the worker died —
// without them the only thing a crash left behind was a sentence.
//
// A fresh intent is a fresh question: any `_reconciliation` answered for an
// earlier intent on this row is dropped here, so a verdict can never be read
// against a click it was not about.
//
// Written into params beside _workflow using the idiom heartbeatPatch uses,
// which the PocketBase guard already accepts: it compares _workflow's fields,
// and this touches none of them.
export function markEffectUncertainPatch(job, intent = null) {
  if (!isWorkflowJob(job)) return { effect_uncertain: true };
  if ((job.workflow_state || embeddedWorkflow(job).state) !== "running") {
    throw new Error("only running work can reach an external effect");
  }
  if (!intent || typeof intent !== "object") return { effect_uncertain: true };
  const params = parseJobParams(job);
  const step = Number(intent.step);
  const tab = Number(intent.tab);
  params._effect_intent = {
    doing: String(intent.doing || "").slice(0, 120),
    url: String(intent.url || "").slice(0, 200),
    sig: intent.sig ? String(intent.sig) : null,
    digest: intent.digest ? String(intent.digest) : null,
    at: intent.at || new Date().toISOString(),
    step: Number.isFinite(step) ? step : null,
    tab: Number.isFinite(tab) ? tab : null,
    session: intent.session ? String(intent.session).slice(0, 80) : "",
  };
  delete params._reconciliation;
  return { effect_uncertain: true, params: JSON.stringify(params) };
}

// THE `after` HALF OF THE INTENT: the first page the loop read AFTER the
// click, written exactly once. Audit #90 correction (B).
//
// Derived from the step's own checkpoint — `{ page: {url, title,
// fingerprint}, step }` handed over by agent_loop's trace call — and NEVER
// from the evidence journal's tail: the journal is appended only when the
// fingerprint changes, so after a click that left the page as it was, its
// tail is the pre-click form, and recording that as "the first page after the
// click" would hand the reconciliation model the wrong page with a straight
// face. The `step > intent.step` test is what keeps a checkpoint from the
// click's own step (whose page is the form BEFORE the click) out.
//
// Returns the record to write, or null when nothing is due: no intent, an
// `after` already written, a legacy intent with no step, or a checkpoint that
// is not yet past the click. url/title/fingerprint only — no text, no fields.
export function effectIntentAfter(intent, checkpoint) {
  if (!intent || typeof intent !== "object" || intent.after) return null;
  const page = checkpoint && checkpoint.page;
  const step = Number(checkpoint && checkpoint.step);
  const clickStep = Number(intent.step);
  if (!page || typeof page !== "object") return null;
  if (!Number.isFinite(step) || !Number.isFinite(clickStep) || step <= clickStep) return null;
  return {
    url: String(page.url || "").slice(0, 200),
    title: String(page.title || "").slice(0, 120),
    fingerprint: String(page.fingerprint || "").slice(0, 200),
    step,
    at: new Date().toISOString(),
  };
}

// What to tell the owner when an effect may have gone out and nothing can
// confirm it. One definition for the three places that used to carry the same
// sentence by hand — and now, when the intent was recorded, it says WHAT was
// about to be sent and WHERE, so "check the site" is an instruction he can
// actually follow rather than a shrug.
export function uncertainEffectMessage(job) {
  const base = "I may have already sent that before I lost the page — I could not "
    + "confirm either way. Check the site before I try again, so you don't end up with two.";
  const intent = parseJobParams(job)._effect_intent;
  if (!intent || typeof intent !== "object" || !intent.doing) return base;
  const where = intent.url ? ` at ${intent.url}` : "";
  return `${base} It was: ${intent.doing}${where}.`;
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
