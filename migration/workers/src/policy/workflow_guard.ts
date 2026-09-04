/**
 * src/policy/workflow_guard.ts — backend/pb_hooks/workflow_guard.pb.js:6-673.
 * 395 code lines, the largest of the four, registered SIXTH and LAST.
 * migration/spec/CONTRACT.md §1 calls it "the file the whole migration turns
 * on" and spends 430 lines of the contract on it.
 *
 * ┌──────────────────────────────────────────────────────────────────────┐
 * │ THIS FILE IS TRANSCRIBED, NOT REDESIGNED.                            │
 * │                                                                      │
 * │ It is the safety system: it is what stops an executor approving its  │
 * │ own plan, what holds a consequential act for a human tap, and what   │
 * │ refuses a `done` that has no verified evidence. Every branch below   │
 * │ carries the file:line it came from. A branch that looks redundant is │
 * │ a branch whose incident is recorded in the original's comment —      │
 * │ read it there before removing it.                                    │
 * │                                                                      │
 * │ THE PORT ORDER IS: transcribe first, diff against the oracle, and    │
 * │ only then simplify. migration/spec/contract_tests.py §1 has          │
 * │ ~90 assertions on this file alone; they are the arbiter, not         │
 * │ anyone's reading of the code.                                        │
 * └──────────────────────────────────────────────────────────────────────┘
 *
 * WHAT IS ALREADY DIFFERENT AND MUST STAY THAT WAY:
 *   - `reject()` is 409, not 403 (:26). guard.ts refusing first is what makes
 *     403-vs-409 meaningful, which is why the chain order in chain.ts is
 *     load-bearing.
 *   - THE LEGACY ESCAPE HATCH IS FAIL-OPEN (:24 `if (!workflow) return next()`).
 *     A job with no workflow_id skips this entire file. That is deliberate —
 *     CONTRACT.md §1.2 — and porting it as fail-closed would refuse every
 *     pre-workflow row in production.
 */
import { refuse, json, pbTime } from "../pb/wire.ts";
import type { Ctx, Policy } from "./chain.ts";

const BASE = "/api/collections/jobs/records";

/** workflow_guard.pb.js:105-109 */
const STATE_FOR_STATUS: Record<string, string[]> = {
  awaiting_confirm: ["draft", "awaiting_approval"],
  queued: ["queued"], running: ["running"], needs_user: ["needs_user"],
  done: ["succeeded"], failed: ["failed"], cancelled: ["cancelled"],
};

/** workflow_guard.pb.js:123-131 — the legal transitions. */
const ALLOWED_TRANSITIONS: Record<string, string[]> = {
  awaiting_confirm: ["awaiting_confirm", "queued", "cancelled"],
  queued: ["queued", "running", "needs_user", "cancelled"],
  running: ["running", "needs_user", "done", "failed", "cancelled", "queued"],
  needs_user: ["needs_user", "queued", "cancelled"],
  failed: ["failed"],
  done: ["done"],
  cancelled: ["cancelled"],
};

/** workflow_guard.pb.js:217 */
const ENTRY_STATUSES = ["awaiting_confirm", "queued"];

// workflow_guard.pb.js:310 -- a tap, and nothing else, is a gesture.

// --- SHELF 2 ---------------------------------------------------------------
// workflow_guard.pb.js:286-360. The middle register: work that runs WITHOUT
// waiting for a tap and is reported afterwards with a real undo.
//
// There is deliberately NO reversibility classifier among these legs. Nobody is
// asked "is this reversible?" -- not a word list, not a domain list, not a model
// returning a bit. Reversibility is proven by STRUCTURE: a named act type whose
// reach and executor are fixed, a target whose provenance is minted by us, an
// undo that binds the same inputs and addresses that same target, an
// announcement that reaches the owner, and a position in a lineage.
const SHELF2_ACT_TYPES = ["local_draft"];
const SHELF2_REACH = ["local_store"];
const SHELF2_EXECUTOR = ["anticipy_store"];
const SHELF2_BINDS: readonly (readonly string[])[] = [["minted_by_us"]];
const SHELF2_TARGET_PROVENANCE = ["minted_by_us"];
const PROVENANCE_TAGS = ["minted_by_us", "owner_supplied", "constant"];
const S2 = {
  act: "shelf2.act_type_not_admitted",
  reach: "shelf2.reach_disagrees",
  executor: "shelf2.executor_disagrees",
  noUndo: "shelf2.no_undo_plan",
  otherAct: "shelf2.undo_addresses_another_act",
  provenance: "shelf2.unknown_provenance",
  unresolved: "shelf2.unresolved_reference",
  bindsNothing: "shelf2.undo_binds_nothing",
  targetUnbound: "shelf2.act_target_unbound",
  missesTarget: "shelf2.undo_misses_the_target",
  noTell: "shelf2.no_announce_obligation",
  tellLeaves: "shelf2.announce_leaves_the_owner",
  unordered: "shelf2.unordered_lineage",
} as const;

const plainObject = (v: unknown): v is Record<string, unknown> =>
  !!v && typeof v === "object" && !Array.isArray(v);
const ownValue = (o: unknown, k: string): unknown =>
  plainObject(o) && Object.prototype.hasOwnProperty.call(o, k) ? o[k] : undefined;

function shelf2Refusal(
  embedded: Record<string, unknown>,
  rowValue: (name: string, fallback: unknown) => unknown,
): string {
  const act = embedded.act;
  if (!plainObject(act)) return S2.act;
  const which = SHELF2_ACT_TYPES.indexOf(String(act.act_type ?? ""));
  if (which < 0) return S2.act;
  if (String(act.reach ?? "") !== SHELF2_REACH[which]) return S2.reach;
  if (String(act.executor ?? "") !== SHELF2_EXECUTOR[which]) return S2.executor;

  const target = act.target;
  if (!plainObject(target)) return S2.targetUnbound;
  const targetTag = String(target.provenance ?? "");
  const targetRef = String(target.ref ?? "");
  if (!PROVENANCE_TAGS.includes(targetTag)) return S2.provenance;
  if (targetTag !== SHELF2_TARGET_PROVENANCE[which]) return S2.targetUnbound;

  const undo = embedded.undo;
  if (!plainObject(undo)) return S2.noUndo;
  if (!Array.isArray(undo.steps) || undo.steps.length === 0) return S2.noUndo;
  // The undo must be an undo of THIS act, not of some other one.
  if (String(undo.act_type ?? "") !== String(act.act_type ?? "")) return S2.otherAct;
  if (!Array.isArray(undo.inputs)) return S2.noUndo;

  // Every reference the undo needs must already be HELD -- resolved at plan
  // time, not looked up later when the thing may be gone.
  const resolveRef = (tag: string, ref: string): string => {
    if (!PROVENANCE_TAGS.includes(tag)) return S2.provenance;
    const bucket = ownValue(undo.held, tag);
    if (!plainObject(bucket)) return S2.unresolved;
    const value = ownValue(bucket, ref);
    if (value === undefined || value === null || value === "") return S2.unresolved;
    return "";
  };
  for (const item of undo.inputs) {
    if (!plainObject(item)) return S2.noUndo;
    const why = resolveRef(String(item.provenance ?? ""), String(item.ref ?? ""));
    if (why) return why;
  }
  const bound = (undo.inputs as unknown[])
    .map((i) => String((i as Record<string, unknown>).provenance ?? ""));
  for (const tag of SHELF2_BINDS[which] ?? []) {
    if (!bound.includes(tag)) return S2.bindsNothing;
  }
  const targetUnresolved = resolveRef(targetTag, targetRef);
  if (targetUnresolved) return targetUnresolved;

  // An undo that binds the right KINDS but not the act's own target undoes
  // something else.
  const addressed = (undo.inputs as unknown[]).some((i) => {
    const it = i as Record<string, unknown>;
    return String(it.provenance ?? "") === targetTag && String(it.ref ?? "") === targetRef;
  });
  if (!addressed) return S2.missesTarget;

  // Running unattended is bought by TELLING him afterwards, so the obligation
  // is part of the plan and is addressed to him specifically.
  const tell = embedded.announce;
  if (!plainObject(tell) || !String(tell.channel ?? "").trim()) return S2.noTell;
  const owner = String(rowValue("owner_ref", "") ?? "");
  if (!owner || String(tell.owner_ref ?? "") !== owner) return S2.tellLeaves;

  if (!(Number(embedded.lineage_seq) >= 1)) return S2.unordered;
  return "";
}

const GESTURE_KINDS = ["tap"];

const reject = (why: string) => json(409, { error: "workflow violation", detail: why });

export const workflowGuard: Policy = async (ctx: Ctx): Promise<Response | null> => {
  const { path, method } = ctx;
  if (path !== BASE && !path.startsWith(`${BASE}/`)) return null;
  if (method !== "POST" && method !== "PATCH") return null;

  const body = ctx.body ?? {};
  // researchLane already loaded this row for the same request. Reusing it is
  // not merely an optimisation: two reads can straddle a concurrent write and
  // the two policies would then judge different rows.
  const old = ctx.storedRow ?? (method === "PATCH"
    ? await loadJob(ctx, path.split("/").pop() as string) : null);
  ctx.storedRow = old;

  const oldWorkflow = String(old?.workflow_id ?? "");
  const workflow = String(body.workflow_id ?? oldWorkflow ?? "");

  // :24 — THE LEGACY ESCAPE HATCH. Fail-open, deliberately. CONTRACT.md §1.2.
  if (!workflow) return null;

  const oldStatus = String(old?.status ?? "");
  const nextStatus = String(body.status ?? oldStatus ?? "");
  const oldVersion = Number(old?.workflow_version ?? 0);
  const nextVersion = Number(body.workflow_version ?? oldVersion);
  const oldState = String(old?.workflow_state ?? "");
  const nextState = String(body.workflow_state ?? oldState ?? "");
  const consequence = String(body.consequence ?? old?.consequence ?? "");
  const agentCaller = !!ctx.request.headers.get("X-Anticipy-Agent-ID");

  const rowValue = (name: string, fallback: unknown) =>
    body[name] != null ? body[name] : (old ? old[name] : fallback);

  // :44-54
  let params: Record<string, unknown>;
  let embedded: Record<string, unknown> | null;
  try {
    const raw = body.params != null ? String(body.params) : String(old?.params ?? "");
    params = JSON.parse(raw || "{}");
    embedded = (params?._workflow ?? null) as Record<string, unknown> | null;
  } catch { return reject("workflow params are not parseable"); }
  if (!embedded || typeof embedded !== "object") {
    return reject("canonical workflow is missing from params");
  }

  let rowApproval: unknown = null;
  let rowReceipt: unknown = null;
  try {
    const raw = String(rowValue("approval", "") ?? "");
    rowApproval = raw ? JSON.parse(raw) : null;
  } catch { return reject("row approval is not parseable"); }
  try {
    const raw = String(rowValue("receipt", "") ?? "");
    rowReceipt = raw ? JSON.parse(raw) : null;
  } catch { return reject("row receipt is not parseable"); }

  // :81-96 — THE REDUNDANCY CHECK. The embedded copy must agree with the row
  // on twelve fields. This is what makes the row un-editable piecemeal.
  if (String(embedded.plan_id ?? "") !== workflow
      || Number(embedded.version ?? 0) !== nextVersion
      || String(embedded.state ?? "") !== nextState
      || String(embedded.goal ?? "") !== String(rowValue("goal", "") ?? "")
      || String(embedded.consequence ?? "") !== consequence
      || String(embedded.lineage_key ?? "") !== String(rowValue("lineage_key", "") ?? "")
      || String(embedded.owner_ref ?? "") !== String(rowValue("owner_ref", "") ?? "")
      || String(embedded.scope_digest ?? "") !== String(rowValue("scope_digest", "") ?? "")
      || String(embedded.effect_key ?? "") !== String(rowValue("effect_key", "") ?? "")
      || !sameJSON(embedded.approval ?? null, rowApproval)
      || !sameJSON(embedded.receipt ?? null, rowReceipt)
      || Number(embedded.attempts ?? 0) !== Number(rowValue("attempts", 0) ?? 0)
      || String((embedded.lease as Record<string, unknown> | undefined)?.token ?? "")
           !== String(rowValue("lease_token", "") ?? "")) {
    return reject("job fields disagree with the embedded workflow");
  }

  // :97-103 — required facts
  const required = Array.isArray(embedded.required) ? embedded.required as string[] : [];
  const facts = (embedded.facts && typeof embedded.facts === "object"
    ? embedded.facts : {}) as Record<string, unknown>;
  if (["queued", "running", "succeeded"].includes(nextState)
      && required.some((n) => facts[n] == null || facts[n] === "")) {
    return reject("required facts are missing from the approved plan");
  }

  // :105-118
  if (!STATE_FOR_STATUS[nextStatus] || !STATE_FOR_STATUS[nextStatus].includes(nextState)) {
    return reject(`status ${nextStatus} disagrees with state ${nextState}`);
  }
  if (!workflow || nextVersion < 1
      || !String(body.lineage_key ?? old?.lineage_key ?? "")) {
    return reject("workflow id, version, and lineage are required");
  }
  if (!String(body.owner_ref ?? old?.owner_ref ?? "")) {
    return reject("owner_ref is required for workflow jobs");
  }

  if (old) {
    // :119-200 — THE PATCH LEG
    if (body.workflow_id && body.workflow_id !== oldWorkflow) return reject("workflow id is immutable");
    if (body.owner_ref && body.owner_ref !== old.owner_ref) return reject("owner is immutable");
    if (nextVersion < oldVersion) return reject("workflow version cannot move backwards");
    if (!(ALLOWED_TRANSITIONS[oldStatus] ?? []).includes(nextStatus)) {
      return reject(`illegal transition ${oldStatus} -> ${nextStatus}`);
    }

    const changesPlan = body.goal != null && body.goal !== old.goal;
    const changesScope = body.scope_digest != null && body.scope_digest !== old.scope_digest;
    const changesEffect = body.effect_key != null && body.effect_key !== old.effect_key;

    let oldEmbedded: Record<string, unknown> | null = null;
    try {
      const parsed = JSON.parse(String(old.params ?? "{}"));
      oldEmbedded = (parsed?._workflow ?? null) as Record<string, unknown> | null;
    } catch { oldEmbedded = null; }
    const changesShelf2 = !!(oldEmbedded && typeof oldEmbedded === "object") && (
      !sameJSON(embedded.act, oldEmbedded.act)
      || !sameJSON(embedded.undo, oldEmbedded.undo)
      || !sameJSON(embedded.announce, oldEmbedded.announce)
      || !sameJSON(embedded.undo_of, oldEmbedded.undo_of)
      || Number(embedded.lineage_seq ?? 0) !== Number(oldEmbedded.lineage_seq ?? 0));

    const changesApproval = body.approval != null
      && String(body.approval ?? "") !== String(old.approval ?? "");

    // :178-182 — AN EXECUTOR CANNOT REWRITE OR APPROVE ITS PLAN.
    if (agentCaller && (changesPlan || changesScope || changesEffect
                        || changesShelf2 || nextVersion !== oldVersion || changesApproval)) {
      return reject("an executor cannot rewrite or approve its plan");
    }
    if ((changesPlan || changesScope || changesEffect || changesShelf2)
        && nextVersion <= oldVersion) {
      return reject("changing a plan requires a new workflow version");
    }

    // :191-200 — LEASE POSSESSION. `pbTime` rather than `new Date()` because
    // an unparseable lease_until must not read as the far future (:160-161).
    if (oldStatus === "running" && nextStatus !== "cancelled") {
      const held = String(old.lease_token ?? "");
      const presented = ctx.request.headers.get("X-Anticipy-Lease") ?? "";
      if (!held || presented !== held) return reject("running update came from the wrong lease");
      const until = pbTime(old.lease_until);
      const expired = !(until > Date.now());
      if (expired && !["queued", "needs_user", "failed"].includes(nextStatus)) {
        return reject("expired executor may only recover, park, or fail");
      }
    }
  } else {
    // :217-220 — THE CREATE LEG
    if (!ENTRY_STATUSES.includes(nextStatus)) {
      return reject(`work cannot be created in ${nextStatus}`);
    }
  }

  // ======================================================================
  // THE APPROVAL GATE and SHELF 2 -- workflow_guard.pb.js:286-620,
  // CONTRACT.md §1.11 and §1.12.
  //
  // READ THIS BEFORE YOU TOUCH `NO_APPROVAL_NEEDED`. IT IS ONE EDIT AWAY AND
  // IT READS AS COMPLIANCE:
  //
  //     const NO_APPROVAL_NEEDED = ["read_only", "reversible_local"];  // NO
  //
  // That turns off database-level approval for a whole lane and puts NOTHING
  // in its place. read_only's exemption is EARNED by a backstop the other
  // lanes do not have: the extension's runSupervisedReadJob fails any job whose
  // consequence is not read_only, and nothing in that lane acts on the world.
  //
  // SHELF 2'S EXEMPTION IS NOT SPELLED ANYWHERE EITHER. It is EARNED, below, by
  // passing every leg -- and it is written this way round on purpose: delete a
  // leg and `shelf2Earned` is never set, so the lane falls back to DEMANDING
  // approval rather than quietly running unattended. A naked allowlist entry
  // fails the other way.
  const NO_APPROVAL_NEEDED = ["read_only"];
  const SHELF2 = "reversible_local";
  const LIVE_STATUSES = ["queued", "running"];

  const approvalRefusal = (): string => {
    let approval: Record<string, unknown>;
    try {
      approval = JSON.parse(String(rowValue("approval", "") ?? "")) as Record<string, unknown>;
    } catch { return "consequential work needs parseable approval"; }
    const scope = String(rowValue("scope_digest", "") ?? "");
    const words = String(approval.owner_words ?? "").trim();
    const g = approval.gesture;
    const gesture = plainObject(g) ? g as Record<string, unknown> : null;
    // A gesture is admitted AS a gesture, and it must be THIS owner's, on THIS
    // plan version, over THIS scope. Accepting any actor a caller could name --
    // another account, a service identity -- would let a plan approve itself
    // and buy exactly what a tap buys.
    const tapped = !!(gesture
      && GESTURE_KINDS.includes(String(gesture.kind ?? ""))
      && String(gesture.actor ?? "").trim() === String(rowValue("owner_ref", "") ?? "")
      && String(gesture.plan_id ?? "") === workflow
      && Number(gesture.plan_version) === nextVersion
      && String(gesture.scope_digest ?? "") === scope);
    if (approval.plan_id !== workflow
        || Number(approval.plan_version) !== nextVersion
        || !scope
        || approval.scope_digest !== scope
        || (!words && !tapped)) {
      return "approval is not bound to this exact plan version";
    }
    return "";
  };

  const live = LIVE_STATUSES.includes(nextStatus);
  let shelf2Earned = false;
  if (live && consequence === SHELF2) {
    if (approvalRefusal() !== "") {
      const why = shelf2Refusal(embedded, rowValue);
      if (why) return reject(why);
      shelf2Earned = true;
    }
  }
  if (live && !shelf2Earned && !NO_APPROVAL_NEEDED.includes(consequence)) {
    const why = approvalRefusal();
    if (why) return reject(why);
  }

  // ==========================================================================
  // WHAT IS STILL NOT PORTED, AND THE PORT IS NOT DONE UNTIL IT IS.
  //
  // shelf2Refusal above is the admission ladder and it is complete. Three legs
  // around it are not, and all three need to read SIBLING rows rather than this
  // one, which is why they are separate work rather than more of the same:
  //
  //   seqRefusal   (:439-455) one act per lineage position -- two acts claiming
  //                the same seq is a fork, and the later one must not run.
  //   orderRefusal (:509)     shelf2.superseded_by_later_act: an act whose
  //                lineage position is behind one that HAS ALREADY RUN is
  //                stale, and running it would undo somebody else's later work.
  //   reconciliation (§1.13)  a retry after an uncertain effect must prove the
  //                effect was reconciled, or it may act twice.
  //
  // Also absent: "done needs verified evidence for this exact effect" (§1.15).
  //
  // They are omitted rather than sketched: a half-transcribed safety ladder is
  // worse than an absent one because it looks finished. Until they land, this
  // Worker MUST NOT serve `jobs` in production. ARCHITECTURE.md §12, Phase 4.
  //
  // workflow_guard.pb.js:286-673 is SHELF 2 — the earned-not-spelled
  // reversibility ladder — plus the approval gate (:450 in CONTRACT.md §1.12),
  // reconciliation after an uncertain effect (§1.13), and "done needs verified
  // evidence for this exact effect" (§1.15). That is 36 named refusal codes
  // (the S2.* table at :315-335) and ~200 further lines.
  //
  // They are omitted from this SKELETON deliberately rather than sketched:
  // a half-transcribed safety ladder is worse than an absent one, because it
  // looks finished. CONTRACT.md §1.11 and §1.16 are the specification, and
  // migration/spec/contract_tests.py is the acceptance test.
  //
  // UNTIL THEY ARE PORTED, THIS WORKER MUST NOT SERVE THE `jobs` COLLECTION
  // IN PRODUCTION. ARCHITECTURE.md §12, Phase 4 gates on exactly that.
  // ==========================================================================
  return null;
};

const ordered = (v: unknown): unknown => {
  if (Array.isArray(v)) return v.map(ordered);
  if (v && typeof v === "object") {
    const out: Record<string, unknown> = {};
    for (const k of Object.keys(v as object).sort()) out[k] = ordered((v as Record<string, unknown>)[k]);
    return out;
  }
  return v;
};
const sameJSON = (a: unknown, b: unknown) =>
  JSON.stringify(ordered(a ?? null)) === JSON.stringify(ordered(b ?? null));

async function loadJob(ctx: Ctx, id: string): Promise<Record<string, unknown> | null> {
  if (!id) return null;
  const db = (ctx as unknown as { db: D1Database }).db;
  return db.prepare(`SELECT * FROM "jobs" WHERE "id" = ?1 LIMIT 1`)
    .bind(id).first<Record<string, unknown>>();
}

export { refuse };
