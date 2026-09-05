/**
 * Runs with no dependencies, no network and no D1:
 *
 *   node --experimental-strip-types migration/workers/test/workflow-guard-empties.test.ts
 *
 * THE THREE PLACES AN EXPLICIT "" MEANT TWO DIFFERENT THINGS (audit F42).
 *
 * backend/pb_hooks/workflow_guard.pb.js is the oracle and it reads all three
 * with `||`:
 *
 *   :28   String(body.status || oldStatus || "")
 *   :113  body.lineage_key || old.getString("lineage_key")
 *   :541  body.approval || old.getString("approval")
 *
 * The port used `??`, which stops at an empty string instead of falling
 * through to the stored row. Same request, same row, two verdicts: the oracle
 * judges the job it has, the Worker refuses a job whose status, lineage or
 * approval is sitting in the row it just read. The file's own header says
 * TRANSCRIBED, NOT REDESIGNED, so the drift is a defect against its contract
 * however defensible the stricter reading looks.
 *
 * Every body below is built the way the oracle's own redundancy check
 * (:81-96, ported at workflow_guard.ts:320) demands: the embedded `_workflow`
 * mirrors the row on twelve fields, with `rowValue`'s `!= null` semantics —
 * which treat "" as PRESENT on BOTH backends. That is why an "" in the body
 * forces "" in the embedded copy too, and it is exactly the shape a client
 * that re-sends a blank field produces.
 *
 * MUTATIONS THIS FILE MUST GO RED ON:
 *   - any of the three `||` reverted to `??` (the named fix);
 *   - the fallback never consulted at all (`String(body.status || "")`);
 *   - the polarity inverted (an ABSENT key reading as "" rather than the row's
 *     value), which would make every ordinary PATCH refuse.
 */
import assert from "node:assert/strict";
import { workflowGuard } from "../src/policy/workflow_guard.ts";
import type { Ctx } from "../src/policy/chain.ts";

let failures = 0;
let passes = 0;
async function check(what: string, fn: () => void | Promise<void>): Promise<void> {
  try { await fn(); passes++; }
  catch (err) { failures++; console.error("FAIL " + what + "\n     " + (err as Error).message); }
}

const JOB = "job000000000001";
const BASE = `/api/collections/jobs/records/${JOB}`;

interface Parts {
  row: Record<string, unknown>;
  body: Record<string, unknown>;
  plan: Record<string, unknown>;
}

/**
 * A stored row and a PATCH body that agree on all twelve redundancy fields.
 * `over` edits the body, `plan` edits the embedded copy, `rowOver` the row.
 */
function parts(o: {
  consequence?: string; approvalOnRow?: unknown;
  body?: Record<string, unknown>; plan?: Record<string, unknown>;
  row?: Record<string, unknown>;
} = {}): Parts {
  const consequence = o.consequence ?? "read_only";
  const common = {
    goal: "collect the boarding pass",
    consequence,
    lineage_key: "ln-real-0001",
    owner_ref: "owner0undertest",
    scope_digest: "sd-real-0001",
    effect_key: "ek-real-0001",
    attempts: 0,
  };
  const row: Record<string, unknown> = {
    id: JOB, status: "queued", workflow_id: "wf-real-0001", workflow_version: 1,
    workflow_state: "queued", lease_token: "", receipt: "", approval: "",
    effect_uncertain: 0, params: "", ...common, ...(o.row ?? {}),
  };
  const plan: Record<string, unknown> = {
    plan_id: row.workflow_id, version: row.workflow_version, state: row.workflow_state,
    required: [], facts: {}, lease: { token: "" }, ...common, ...(o.plan ?? {}),
  };
  const body: Record<string, unknown> = {
    status: row.status, workflow_id: row.workflow_id, workflow_version: row.workflow_version,
    workflow_state: row.workflow_state, ...common,
    params: JSON.stringify({ _workflow: plan }),
    ...(o.body ?? {}),
  };
  // params always carries the plan as edited, even when `body` overrode fields.
  if (!(o.body ?? {}).params) body.params = JSON.stringify({ _workflow: plan });
  return { row, body, plan };
}

async function verdict(p: Parts): Promise<{ ok: boolean; detail: string }> {
  const ctx = {
    request: new Request("https://api.anticipy.ai" + BASE, { method: "PATCH" }),
    url: new URL("https://api.anticipy.ai" + BASE),
    method: "PATCH",
    path: BASE,
    body: p.body,
    principal: { kind: "service" },
    worker: { fromWorker: true },
    forcedScope: null,
    extraAst: null,
    storedRow: p.row,
    // Never reached by these cases: orderRefusal returns before it reads the
    // database when the plan carries no `undo_of`. A stub that THROWS is the
    // honest fake — if a case ever does reach D1, the test says so loudly
    // rather than passing on a silent empty read.
    db: { prepare() { throw new Error("this case must not read D1"); } },
  } as unknown as Ctx;
  const res = await workflowGuard(ctx, {});
  if (!res) return { ok: true, detail: "" };
  const parsed = await res.json() as { detail?: string };
  return { ok: false, detail: String(parsed.detail ?? "") };
}

// ---------------------------------------------------------------------------
// The control: with nothing blank, this exact row and body are ADMITTED. Every
// case below changes ONE field to "", so a refusal can only come from that.
// ---------------------------------------------------------------------------

await check("the control body is admitted, so a refusal below is about the blank field", async () => {
  const v = await verdict(parts());
  assert.equal(v.ok, true, "the control was refused: " + v.detail);
});

// --- :28  status ------------------------------------------------------------

await check("a PATCH re-sending status:\"\" is judged on the row's status, not on \"\"", async () => {
  // workflow_guard.pb.js:28. Before the fix: nextStatus was "", STATE_FOR_STATUS
  // had no entry for it, and the answer was `status  disagrees with state queued`
  // — note the double space where the status should be, which is what an empty
  // status looks like in a refusal an owner never sees.
  const v = await verdict(parts({ body: { status: "" }, plan: {} }));
  assert.equal(v.ok, true, "a blank status was taken literally: " + v.detail);
});

await check("a blank status does NOT become a licence: an illegal transition still refuses", async () => {
  // The fallback must resolve to the ROW's status and then be judged. A row
  // that has already finished cannot move, and reading "" as "queued" (or as
  // anything convenient) would let a done row be re-driven.
  const p = parts({ row: { status: "done", workflow_state: "succeeded" },
                    body: { status: "", workflow_state: "queued" },
                    plan: { state: "queued" } });
  const v = await verdict(p);
  assert.equal(v.ok, false, "a done row accepted a blank-status PATCH into queued");
  assert.match(v.detail, /disagrees with state|illegal transition/);
});

await check("a status the body DOES name still wins over the row's", async () => {
  // The fallback is a fallback. If `||` were read as "always the row", every
  // real transition would be judged against the status it is leaving.
  const p = parts({ row: { status: "queued" },
                    body: { status: "running", workflow_state: "running" },
                    plan: { state: "running" } });
  const v = await verdict(p);
  // running needs an actor and a lease — which proves the guard read `running`
  // from the body and not `queued` from the row.
  assert.equal(v.ok, false);
  assert.equal(v.detail, "running work needs an actor and lease");
});

// --- :113  lineage_key ------------------------------------------------------

await check("a PATCH re-sending lineage_key:\"\" keeps the row's lineage", async () => {
  // workflow_guard.pb.js:113. The embedded copy must ALSO be "" or the
  // redundancy check fires first — that is rowValue's `!= null` on both sides,
  // and it is the same on both backends.
  const v = await verdict(parts({ body: { lineage_key: "" }, plan: { lineage_key: "" } }));
  assert.equal(v.ok, true, "a blank lineage_key was taken literally: " + v.detail);
});

await check("a job whose lineage is blank in BOTH the body and the row is still refused", async () => {
  // The floor stays a floor: the fallback may not manufacture a lineage that
  // exists in neither place.
  const v = await verdict(parts({ body: { lineage_key: "" }, plan: { lineage_key: "" },
                                  row: { lineage_key: "" } }));
  assert.equal(v.ok, false, "a job with no lineage anywhere was admitted");
  assert.equal(v.detail, "workflow id, version, and lineage are required");
});

// --- :541  approval ---------------------------------------------------------

const APPROVAL = {
  plan_id: "wf-real-0001", plan_version: 1, scope_digest: "sd-real-0001",
  owner_words: "yes, book it",
};

await check("consequential work with approval:\"\" in the body reads the row's approval", async () => {
  // workflow_guard.pb.js:541. Before the fix `JSON.parse("")` threw and the
  // answer was `consequential work needs parseable approval` — refusing work
  // the owner had already approved, with the approval in the row.
  const v = await verdict(parts({
    consequence: "consequential",
    row: { approval: JSON.stringify(APPROVAL) },
    body: { approval: "" },
  }));
  assert.equal(v.ok, true, "a blank approval was taken literally: " + v.detail);
});

await check("consequential work with approval:\"\" and NOTHING on the row is still refused", async () => {
  // The approval gate is a FLOOR — no verdict must mean no. If the fallback
  // ever resolved to something truthy on its own, this is the case that goes
  // quiet, and quiet here is unapproved work running.
  const v = await verdict(parts({ consequence: "consequential", body: { approval: "" } }));
  assert.equal(v.ok, false, "consequential work ran with no approval anywhere");
  assert.equal(v.detail, "consequential work needs parseable approval");
});

await check("an approval bound to another plan version still buys nothing", async () => {
  // Falling back to the row must not weaken what the row has to prove.
  const stale = { ...APPROVAL, plan_version: 0 };
  const v = await verdict(parts({
    consequence: "consequential",
    row: { approval: JSON.stringify(stale) },
    body: { approval: "" },
  }));
  assert.equal(v.ok, false, "an approval for another version was accepted");
  assert.equal(v.detail, "approval is not bound to this exact plan version");
});

console.log(`workflow-guard-empties: ${passes} checks passed, ${failures} failed`);
if (failures) process.exit(1);
