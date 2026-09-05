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
  unreadable: "shelf2.lineage_unreadable",
  superseded: "shelf2.superseded_by_later_act",
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


/** Statuses that mean the act has already touched the world. */
const HAS_RUN = ["running", "needs_user", "done", "failed"];
const SHELF2_CONSEQUENCE = "reversible_local";

interface LineageAct { id: string; at: number; status: string; }

/**
 * Every Shelf 2 act sharing this lineage, read from SIBLING rows.
 *
 * A compensation is NOT an act: a row carrying `undo_of` is undoing one, so it
 * holds no lineage position of its own and must not occupy one.
 *
 * UNREADABLE IS A REFUSAL, NOT AN EMPTY LIST. A lineage that cannot be parsed,
 * or whose rows disagree about ordering, is exactly the state in which running
 * anything might undo somebody's later work -- so it fails closed. Returning
 * `[]` on a failed read would have made every ordering leg silently pass.
 */
async function readLineage(
  db: D1Database, key: string,
): Promise<{ why: string; acts: LineageAct[] }> {
  if (!key) return { why: S2.unordered, acts: [] };
  let rows: Record<string, unknown>[];
  try {
    const res = await db.prepare(
      `SELECT params, status FROM "jobs"
        WHERE "lineage_key" = ?1 AND "consequence" = ?2
        ORDER BY "created" DESC LIMIT 500`)
      .bind(key, SHELF2_CONSEQUENCE).all<Record<string, unknown>>();
    rows = res.results ?? [];
  } catch {
    return { why: S2.unreadable, acts: [] };
  }
  const acts: LineageAct[] = [];
  const positions: number[] = [];
  for (const row of rows) {
    let plan: unknown;
    try {
      const parsed = JSON.parse(String(row.params ?? "{}")) as Record<string, unknown>;
      plan = parsed?._workflow;
    } catch { return { why: S2.unreadable, acts: [] }; }
    if (!plainObject(plan)) return { why: S2.unreadable, acts: [] };
    if (plainObject(plan.undo_of)) continue;          // a compensation is not an act
    const at = Number(plan.lineage_seq);
    if (!(at >= 1)) return { why: S2.unreadable, acts: [] };
    // Two acts claiming one position is a FORK, and neither may proceed.
    if (positions.includes(at)) return { why: S2.unordered, acts: [] };
    positions.push(at);
    acts.push({ id: String(plan.plan_id ?? ""), at, status: String(row.status ?? "") });
  }
  return { why: "", acts };
}

/** One act per lineage position, and this one must be the newest. */
async function seqRefusal(
  db: D1Database, embedded: Record<string, unknown>, key: string, workflow: string,
): Promise<string> {
  const at = Number(embedded.lineage_seq);
  if (!(at >= 1)) return "";                    // shelf2Refusal owns that refusal
  const read = await readLineage(db, key);
  if (read.why) return read.why;
  for (const a of read.acts) {
    if (a.id === workflow) continue;
    if (a.at >= at) return S2.unordered;
  }
  return "";
}

/**
 * A compensation must name a real act at the position it claims, and must not
 * run once a LATER act has already run -- undoing something underneath work
 * that has already happened on top of it is how a tidy-up becomes damage.
 */
async function orderRefusal(
  db: D1Database, embedded: Record<string, unknown>,
  rowValue: (n: string, f: unknown) => unknown,
): Promise<string> {
  const undoOf = embedded.undo_of;
  if (!plainObject(undoOf)) return "";
  const seq = Number(undoOf.act_seq);
  const target = String(undoOf.plan_id ?? "");
  const key = String(rowValue("lineage_key", "") ?? "");
  if (!target || !key || !(seq >= 1)) return S2.unordered;
  const read = await readLineage(db, key);
  if (read.why) return read.why;
  let located = false;
  for (const a of read.acts) {
    if (a.id !== target) continue;
    if (a.at !== seq) return S2.unordered;
    located = true;
  }
  if (!located) return S2.unordered;
  for (const a of read.acts) {
    if (a.at > seq && HAS_RUN.includes(a.status)) return S2.superseded;
  }
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
  // `||`, NOT `??`, and the difference is a refusal. workflow_guard.pb.js:28 is
  // `String(body.status || oldStatus || "")`: an EXPLICIT EMPTY STRING falls
  // back to the stored row on the oracle, and `??` takes it literally. A PATCH
  // carrying `status: ""` was therefore judged against the empty status here
  // and against the row's status there — `status  disagrees with state queued`
  // on one backend, admitted on the other. WHAT WAS HERE UNTIL 2026-09-05:
  // `String(body.status ?? oldStatus ?? "")`. F13/F15/F27/F39/F42 audit, F42.
  const nextStatus = String(body.status || oldStatus || "");
  const oldVersion = Number(old?.workflow_version ?? 0);
  const nextVersion = Number(body.workflow_version ?? oldVersion);
  const oldState = String(old?.workflow_state ?? "");
  const nextState = String(body.workflow_state ?? oldState ?? "");
  const consequence = String(body.consequence ?? old?.consequence ?? "");
  // workflow_guard.pb.js:37 -- the incoming value wins, else the row's. In D1 a
  // bool is INTEGER 0/1, so the row side needs Number(), not a truthiness test
  // on the string "0".
  const uncertain = body.effect_uncertain != null
    ? !!body.effect_uncertain
    : Number(old?.effect_uncertain ?? 0) === 1;
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
  // Same `||`-not-`??` rule as nextStatus above; the oracle is
  // workflow_guard.pb.js:113 `body.lineage_key || old.getString("lineage_key")`.
  // WHAT WAS HERE UNTIL 2026-09-05: `body.lineage_key ?? old?.lineage_key ?? ""`,
  // which read an explicit "" as "this row has no lineage" and refused a job
  // whose stored lineage was intact.
  if (!workflow || nextVersion < 1
      || !String(body.lineage_key || old?.lineage_key || "")) {
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
      // `body.approval || old.approval`, the oracle's own expression
      // (workflow_guard.pb.js:541). WHAT WAS HERE UNTIL 2026-09-05:
      // `rowValue("approval", "") ?? ""`, whose `!= null` test hands back an
      // explicit "" — JSON.parse("") throws, so a write that re-sent an empty
      // approval string was refused as unparseable while the stored approval
      // sat right there. NOTE the redundancy check at :318 keeps rowValue on
      // purpose: the oracle (:63) uses the `!= null` form on BOTH sides there,
      // so "" and absent are one thing to it, and changing that half would be
      // the redesign this file's header forbids.
      approval = JSON.parse(String(body.approval || old?.approval || "")) as Record<string, unknown>;
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
  // ORDERING, read from sibling rows. Only on the way IN to the queue: once a
  // row is running the lineage question has already been settled for it.
  if (nextStatus === "queued") {
    const db = (ctx as unknown as { db: D1Database }).db;
    const key = String(rowValue("lineage_key", "") ?? "");
    if (consequence === SHELF2 && !plainObject(embedded.undo_of)) {
      const clash = await seqRefusal(db, embedded, key, workflow);
      if (clash) return reject(clash);
    }
    const outOfOrder = await orderRefusal(db, embedded, rowValue);
    if (outOfOrder) return reject(outOfOrder);
  }

  if (live && !shelf2Earned && !NO_APPROVAL_NEEDED.includes(consequence)) {
    const why = approvalRefusal();
    if (why) return reject(why);
  }

  // AN UNCERTAIN EFFECT MAY NOT SIMPLY BE RETRIED. effect_uncertain means we do
  // not know whether the world changed, so re-queueing without proof is how one
  // booking becomes two. The proof must be about THIS effect, must conclude the
  // effect was NOT applied, must carry the owner's own words, and must cite
  // evidence -- a bare `verified: true` buys nothing.
  if (nextStatus === "queued" && old && Number(old.effect_uncertain ?? 0) === 1) {
    let reconciliation: Record<string, unknown>;
    try {
      reconciliation = JSON.parse(String(body.reconciliation ?? "")) as Record<string, unknown>;
    } catch { return reject("uncertain effect needs reconciliation before retry"); }
    const effect = String(body.effect_key ?? old.effect_key ?? "");
    if (uncertain
        || !reconciliation.verified
        || reconciliation.effect_key !== effect
        || reconciliation.conclusion !== "not_applied"
        || !reconciliation.owner_words
        || !Array.isArray(reconciliation.evidence)
        || reconciliation.evidence.length === 0) {
      return reject("uncertain effect was not proven safe to retry");
    }
  }

  // THE LEASE IS THE CLAIM. A status string is not one.
  //
  // `running` without an actor and a lease is an executor asserting it holds
  // work it never claimed; a lease already in the past is one that another
  // executor is free to take, so honouring it would let two run at once.
  if (nextStatus === "running") {
    const lease = String(rowValue("lease_token", "") ?? "");
    const actor = String(rowValue("claimed_by", "") ?? "");
    const until = String(rowValue("lease_until", "") ?? "");
    if (!lease || !actor || !until) return reject("running work needs an actor and lease");
    if (Date.parse(String(until).replace(" ", "T")) <= Date.now()) {
      return reject("running lease must expire in the future");
    }
  } else if (!old || oldStatus === "running") {
    // Coming to rest RELEASES the lease. A parked or finished row still
    // carrying one is a row another executor cannot pick up.
    const lease = String(body.lease_token != null
      ? body.lease_token : (old?.lease_token ?? "")) || "";
    if (lease) return reject("non-running work may not retain an execution lease");
  }

  // CONTRACT.md §1.15 -- DONE IS A CLAIM ABOUT THE WORLD, AND IT NEEDS PROOF.
  //
  // Without this an executor can mark work finished it never did, and "done =
  // evidence" becomes "done = said so". The receipt must be verified, must name
  // THIS effect_key -- proof of some other effect is not proof of this one --
  // and must cite at least one piece of evidence.
  if (nextStatus === "done") {
    let receipt: Record<string, unknown>;
    try {
      receipt = JSON.parse(String(rowValue("receipt", "") ?? "")) as Record<string, unknown>;
    } catch { return reject("done needs a parseable receipt"); }
    const effect = String(rowValue("effect_key", "") ?? "");
    if (!receipt.verified
        || receipt.effect_key !== effect
        || !Array.isArray(receipt.evidence)
        || receipt.evidence.length === 0) {
      return reject("done needs verified evidence for this exact effect");
    }
  }

  // ==========================================================================
  // SHELF 2 AND THE WORKFLOW LAW ARE NOW COMPLETE against CONTRACT.md §1.1-1.16:
  // the state table, the create leg, the lease protocol, the approval gate,
  // Shelf 2's admission ladder, the two sibling-row ordering legs,
  // reconciliation after an uncertain effect, and done-needs-evidence.
  //
  // The acceptance test is migration/spec/contract_tests.py, run against BOTH
  // backends and diffed -- not this comment.
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
