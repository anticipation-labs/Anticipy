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

  // ==========================================================================
  // NOT YET PORTED, AND THE PORT IS NOT DONE UNTIL THEY ARE.
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
