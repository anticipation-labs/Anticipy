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
  // ========================================================= SHELF 2 =========
  //
  // READ THIS BEFORE YOU TOUCH `NO_APPROVAL_NEEDED` BELOW.  IT IS ONE EDIT
  // AWAY AND IT READS AS COMPLIANCE.
  //
  // Shelf 2 is the middle register: work that runs WITHOUT waiting for a tap
  // and is reported afterwards with a real undo.  A third `consequence` value
  // therefore arrives here with no approval, and the block below correctly
  // fails closed on it — "consequential work needs parseable approval".  The
  // cheapest way past that rejection is:
  //
  //     const NO_APPROVAL_NEEDED = ["read_only", "reversible_local"];  // NO
  //
  // That turns off database-level approval for the new lane and puts NOTHING
  // in its place.  `read_only`'s exemption is EARNED by a backstop this lane
  // does not have: extension/background.js `runSupervisedReadJob` fails any
  // job whose consequence !== "read_only" outright, and nothing in that lane
  // acts on the world.  Shelf 2 would inherit the exemption and none of the
  // backstop.
  //
  // So the exemption is not spelled anywhere.  It is EARNED, here, by passing
  // every leg below — and it is written this way round on purpose: delete the
  // leg and `shelf2Earned` is never set, so the lane goes back to demanding
  // approval instead of quietly running unattended.  A naked allowlist entry
  // fails the other way.
  //
  // WHAT THE LEGS ARE, and why there is no reversibility classifier among
  // them.  Nobody is asked "is this reversible?" — not a word list, not a
  // domain list, not a model returning a bit.  That is a question about the
  // future behaviour of a third party, the answer is one bit, and a wrong bit
  // in the unsafe direction is unrecoverable and invisible.  A bit cannot be
  // audited; it can only be believed.  Instead the model writes an ARTIFACT —
  // "what exactly would undo this?" — and this checks the artifact:
  //
  //   the act side (§5.4)   the declared reach and executor, persisted on the
  //                         row, must equal what the admitted set records for
  //                         the act type the plan claims.  Checked FIRST and
  //                         before the undo plan is even read, because the
  //                         attack arrives WITH a flawless undo plan: declare
  //                         `local_draft`, mint your own uuid, write a
  //                         provenance-clean undo, and open Gmail.
  //   the undo side (§5.2)  every input is a typed, provenance-tagged
  //                         reference, and this RESOLVES each one against the
  //                         values the row already holds.  It never reads a
  //                         field NAME and never parses prose — a checker
  //                         that read names is a word list wearing a coat,
  //                         and is beaten by calling a field
  //                         `owner_supplied_reference` and filling it from
  //                         the response.  Resolution is the mechanical form
  //                         of "known-good BEFORE acting": a reference that
  //                         can only resolve after the act fails here, now.
  //   the tell (§8.3)       the obligation to announce is on the row, and it
  //                         is addressed to the owner and nobody else.
  //   the order (§7.4)      a compensating plan may run only while nothing
  //                         later in its lineage has already run.
  //
  // POLARITY IS A FLOOR, everywhere.  Missing, unparseable, unresolvable,
  // unrecognised, or unreachable is a REJECTION, never a default.  There is
  // no fifth outcome that means "proceed".
  //
  // The vocabulary below is duplicated in brain/workflow.py on purpose and
  // tests/test_shelf2_guard_leg.py compares the two files, because the
  // approval fail-open this file already carries a scar about survived
  // exactly by the two layers disagreeing with nobody looking.
  const SHELF2 = "reversible_local";
  // PARALLEL ARRAYS, NOT AN OBJECT.  Same hazard the comment below spells
  // out for `consequence`: `{ local_draft: … }[name]` is truthy for
  // "constructor", "toString" and every other inherited property name, so an
  // object-as-set would ship an admitted set with undocumented members an
  // attacker can simply type.  indexOf has no prototype.
  const SHELF2_ACT_TYPES = ["local_draft"];
  const SHELF2_REACH = ["local_store"];
  const SHELF2_EXECUTOR = ["anticipy_store"];
  // What each act type's undo must actually bind.  `local_draft`'s undo is
  // "discard our row" and cannot be that without the id we minted first;
  // without this an undo plan with NO inputs resolves vacuously and every
  // other leg waves it through.
  const SHELF2_BINDS = [["minted_by_us"]];
  const PROVENANCE_TAGS = ["minted_by_us", "owner_supplied", "constant"];
  const GESTURE_KINDS = ["tap"];
  // Claimed, and therefore capable of having left something behind.  A queued
  // successor has changed nothing yet; a failed one is exactly the case
  // nobody can be sure about, so it counts.
  const HAS_RUN = ["running", "needs_user", "done", "failed"];
  const S2 = {
    act: "shelf2.act_type_not_admitted",
    reach: "shelf2.reach_disagrees",
    executor: "shelf2.executor_disagrees",
    noUndo: "shelf2.no_undo_plan",
    otherAct: "shelf2.undo_addresses_another_act",
    provenance: "shelf2.unknown_provenance",
    unresolved: "shelf2.unresolved_reference",
    bindsNothing: "shelf2.undo_binds_nothing",
    noTell: "shelf2.no_announce_obligation",
    tellLeaves: "shelf2.announce_leaves_the_owner",
    unordered: "shelf2.unordered_lineage",
    // Told apart from `unordered` on purpose: a database that would not
    // answer is not a database that said no, and §10.5(a) requires our own
    // outage to be distinguishable from a real refusal — "one outage on a
    // Tuesday kills the shelf permanently" otherwise.  §11 counts by cause.
    unreadable: "shelf2.lineage_unreadable",
    superseded: "shelf2.superseded_by_later_act",
  };
  const plainObject = (v) => !!v && typeof v === "object" && !Array.isArray(v);
  const ownValue = (o, k) => (plainObject(o)
    && Object.prototype.hasOwnProperty.call(o, k)) ? o[k] : undefined;

  const shelf2Refusal = () => {
    // ---- the act side, first and on its own (§5.4)
    const act = embedded.act;
    if (!plainObject(act)) return S2.act;
    const which = SHELF2_ACT_TYPES.indexOf(String(act.act_type || ""));
    if (which < 0) return S2.act;
    if (String(act.reach || "") !== SHELF2_REACH[which]) return S2.reach;
    if (String(act.executor || "") !== SHELF2_EXECUTOR[which]) return S2.executor;

    // ---- the undo side (§5.2): resolve, never read a name
    const undo = embedded.undo;
    if (!plainObject(undo)) return S2.noUndo;
    if (!Array.isArray(undo.steps) || undo.steps.length === 0) return S2.noUndo;
    if (String(undo.act_type || "") !== String(act.act_type || "")) {
      return S2.otherAct;
    }
    if (!Array.isArray(undo.inputs)) return S2.noUndo;
    for (const item of undo.inputs) {
      if (!plainObject(item)) return S2.noUndo;
      const tag = String(item.provenance || "");
      if (PROVENANCE_TAGS.indexOf(tag) < 0) return S2.provenance;
      const bucket = ownValue(undo.held, tag);
      if (!plainObject(bucket)) return S2.unresolved;
      const value = ownValue(bucket, String(item.ref || ""));
      if (value === undefined || value === null || value === "") {
        return S2.unresolved;
      }
    }

    const bound = [];
    for (const item of undo.inputs) bound.push(String(item.provenance || ""));
    for (const tag of (SHELF2_BINDS[which] || [])) {
      if (bound.indexOf(tag) < 0) return S2.bindsNothing;
    }

    // ---- the tell is part of the work (§8.3), and it goes to him alone
    const tell = embedded.announce;
    if (!plainObject(tell) || !String(tell.channel || "").trim()) {
      return S2.noTell;
    }
    const owner = String(rowValue("owner_ref", "") || "");
    if (!owner || String(tell.owner_ref || "") !== owner) return S2.tellLeaves;

    // ---- and it must have a position, or §7.4 has nothing to order by
    if (!(Number(embedded.lineage_seq) >= 1)) return S2.unordered;
    return "";
  };

  // §7.4 — LIFO within a lineage.  Keyed on `undo_of` and NOT on the
  // consequence: a compensating plan carries the owner's own gesture as
  // authority, so it is ordinary approved work, and a leg keyed on the Shelf
  // 2 consequence would never fire on the one row it exists for.
  //
  // An undo plan is written BEFORE its act runs, against the state as it was
  // then.  Two individually-undoable acts undone out of order produce an
  // outcome neither undo promised: undo(A) deletes the draft, undo(B)
  // RESTORES it, and a draft he was told forty seconds ago was gone is back
  // with both receipts honest.
  const orderRefusal = () => {
    const undoOf = embedded.undo_of;
    if (!plainObject(undoOf)) return "";
    const seq = Number(undoOf.act_seq);
    const target = String(undoOf.plan_id || "");
    const key = String(rowValue("lineage_key", "") || "");
    if (!target || !key || !(seq >= 1)) return S2.unordered;
    let rows = null;
    try {
      rows = e.app.findRecordsByFilter(
        "jobs", "lineage_key = {:k} && consequence = {:c}", "-created", 500, 0,
        { k: key, c: SHELF2 });
    } catch (_) { rows = null; }
    if (!rows || typeof rows.length !== "number") return S2.unreadable;
    const acts = [];
    for (const row of rows) {
      let plan = null;
      try {
        const parsed = JSON.parse(String(row.getString("params") || "{}"));
        plan = parsed && parsed._workflow;
      } catch (_) { return S2.unreadable; }
      if (!plainObject(plan)) return S2.unreadable;
      if (plainObject(plan.undo_of)) continue;   // a compensation is not an act
      const at = Number(plan.lineage_seq);
      if (!(at >= 1)) return S2.unreadable;
      acts.push({ id: String(plan.plan_id || ""), at: at,
                  status: String(row.getString("status") || "") });
    }
    // Locate the act being compensated before ordering anything against it:
    // an undo that names nothing findable is not the head of its lineage, it
    // is not anywhere.
    let located = false;
    for (const a of acts) {
      if (a.id !== target) continue;
      if (a.at !== seq) return S2.unordered;
      located = true;
    }
    if (!located) return S2.unordered;
    for (const a of acts) {
      if (a.at > seq && HAS_RUN.indexOf(a.status) >= 0) return S2.superseded;
    }
    return "";
  };

  let shelf2Earned = false;
  if (nextStatus === "queued") {
    if (consequence === SHELF2) {
      const why = shelf2Refusal();
      if (why) return reject(why);
      shelf2Earned = true;
    }
    const outOfOrder = orderRefusal();
    if (outOfOrder) return reject(outOfOrder);
  }

  // APPROVAL IS THE DEFAULT AND EXEMPTION IS THE EXCEPTION, not the other way
  // round. This read `consequence === "consequential"`, so owner approval was
  // demanded only when that one string was spelled exactly right. Anything
  // else skipped the whole block and reached `queued` UNAPPROVED, free to act
  // on the world: a typo, a truncated write, a row the brain never stamped, an
  // older client, or any third enum value added later. Driven, not reasoned
  // about — `tests/test_workflow_guard_fails_closed.py` sends "consequentia",
  // "" and "reversible" and every one of them was let through before this.
  //
  // The polarity here was ALSO the only one in the system pointing the wrong
  // way, which is the part that matters: this file's own first line calls
  // itself the final authority, and the final authority was the layer that
  // failed open.
  //   brain/workflow.py:64-68     unreadable -> CONSEQUENTIAL ("it gets every gate")
  //   extension/background.js:1062, 1300-1301   `!== "read_only"` -> allowlist
  //   app/ios/…/AnticipyApp.swift:1352          missing key -> "consequential"
  //
  // An ARRAY, not an object-as-set: `{ read_only: 1 }[consequence]` is truthy
  // for "constructor", "toString" and every other inherited property name, so
  // the obvious lookup hands an attacker an exemption keyword.
  const NO_APPROVAL_NEEDED = ["read_only"];
  if (nextStatus === "queued" && !shelf2Earned
      && NO_APPROVAL_NEEDED.indexOf(consequence) < 0) {
    let approval = {};
    try { approval = JSON.parse(String(body.approval || (old && old.getString("approval")) || "")); }
    catch (_) { return reject("consequential work needs parseable approval"); }
    const scope = String(body.scope_digest || (old && old.getString("scope_digest")) || "");
    // A TAP IS A GESTURE, NOT WORDING.
    //
    // `owner_words` exists because he said them, and refusing an empty one is
    // right for speech.  It is also the check that makes somebody write
    // `"owner_words": "tapped undo"` in app/ios/…/AnticipyApp.swift — one
    // line, in the layer closest to the gesture and furthest from the law —
    // which would put a sentence he never said into the one field whose whole
    // purpose is that he did.  So a gesture is admitted AS a gesture, and it
    // buys exactly what words buy and nothing more: it must name who made it,
    // be of a kind we recognise, and be bound to THIS plan, THIS version and
    // THIS scope.  An executor may not mint one — `an executor cannot rewrite
    // or approve its plan` above already refuses that, and this must not
    // become a hole in it.
    const words = String(approval.owner_words || "").trim();
    const gesture = approval.gesture;
    const tapped = !!(plainObject(gesture)
      && GESTURE_KINDS.indexOf(String(gesture.kind || "")) >= 0
      && String(gesture.actor || "").trim()
      && String(gesture.plan_id || "") === workflow
      && Number(gesture.plan_version) === nextVersion
      && String(gesture.scope_digest || "") === scope);
    if (approval.plan_id !== workflow || Number(approval.plan_version) !== nextVersion
        || !scope || approval.scope_digest !== scope || (!words && !tapped)) {
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
