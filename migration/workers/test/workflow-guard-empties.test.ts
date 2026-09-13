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
import { guard } from "../src/policy/guard.ts";
import { researchLane } from "../src/policy/research_lane.ts";
import { runChain, type Ctx } from "../src/policy/chain.ts";

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

async function verdict(p: Parts, headers: Record<string, string> = {}): Promise<{ ok: boolean; detail: string }> {
  const ctx = {
    request: new Request("https://api.anticipy.ai" + BASE, { method: "PATCH", headers }),
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

// ---------------------------------------------------------------------------
// CANCELLATION REVOKES APPROVAL, SERVER-SIDE (2026-09-12, integration map
// disagreement 6). The phone and the brain null approval when they cancel;
// the extension keeps it, because rule 5 forbids an executor touching
// approval. The row is the owner's standing word, so the Worker now writes
// the revocation itself on every transition into `cancelled`.
// ---------------------------------------------------------------------------
const STANDING = { plan_id: "wf-real-0001", plan_version: 1, scope_digest: "sd-real-0001",
  owner_words: "yes, book it", gesture: "tap", at: "2026-09-12T10:00:00Z" };
const EXECUTOR = { "X-Anticipy-Agent-ID": "agent0undertest" };
/** A running, approved, leased row — and a body that cancels it the way the
 *  extension's workflowPatch does: lease released, approval left alone. */
function approvedRunning(over: { body?: Record<string, unknown>; plan?: Record<string, unknown> } = {}): Parts {
  return parts({
    consequence: "external",
    row: { status: "running", workflow_state: "running", approval: JSON.stringify(STANDING),
      lease_token: "lease-real-0001", lease_until: "2099-01-01 00:00:00.000Z", claimed_by: "agent0undertest" },
    plan: { state: "cancelled", approval: STANDING, lease: null, ...(over.plan ?? {}) },
    body: { status: "cancelled", workflow_state: "cancelled", lease_token: "", ...(over.body ?? {}) },
  });
}
const embeddedApproval = (p: Parts) =>
  (JSON.parse(String(p.body.params)) as { _workflow: { approval: unknown } })._workflow.approval;

await check("the extension's cancel — approval left on the row and in the plan — is admitted, and leaves with both revoked", async () => {
  const p = approvedRunning();
  const v = await verdict(p, EXECUTOR);
  assert.equal(v.ok, true, "an executor's cancel was refused: " + v.detail);
  assert.equal(p.body.approval, "", "the row's approval was not revoked");
  assert.equal(embeddedApproval(p), null, "the embedded approval was not revoked");
});
await check("the phone's cancel — approval already cleared — is admitted unchanged", async () => {
  const p = approvedRunning({ plan: { approval: null }, body: { approval: "" } });
  const v = await verdict(p);
  assert.equal(v.ok, true, v.detail);
  assert.equal(p.body.approval, "");
  assert.equal(embeddedApproval(p), null);
});
await check("a cancel that sent no params is given the row's, revoked", async () => {
  const p = approvedRunning();
  // The row carries the plan the body would otherwise have repeated.
  p.row.params = p.body.params;
  delete p.body.params;
  const v = await verdict(p, EXECUTOR);
  assert.equal(v.ok, true, v.detail);
  assert.equal(p.body.approval, "");
  assert.equal(typeof p.body.params, "string", "no params were written back");
  assert.equal(embeddedApproval(p), null);
});
await check("an executor that clears approval WITHOUT cancelling is still refused (the control for rule 5)", async () => {
  const p = approvedRunning({ plan: { state: "running", approval: null, lease: { token: "lease-real-0001" } },
    body: { status: "running", workflow_state: "running", approval: "", lease_token: "lease-real-0001" } });
  const v = await verdict(p, { ...EXECUTOR, "X-Anticipy-Lease": "lease-real-0001" });
  assert.equal(v.ok, false, "an executor cleared an approval mid-run and was admitted");
  assert.equal(v.detail, "an executor cannot rewrite or approve its plan");
});
await check("an executor that smuggles a DIFFERENT approval onto a cancel leaves with none", async () => {
  const p = approvedRunning({ plan: { approval: { ...STANDING, owner_words: "do it twice" } },
    body: { approval: JSON.stringify({ ...STANDING, owner_words: "do it twice" }) } });
  const v = await verdict(p, EXECUTOR);
  assert.equal(v.ok, true, v.detail);
  assert.equal(p.body.approval, "");
  assert.equal(embeddedApproval(p), null);
});
await check("a cancel does not touch a row that is not becoming cancelled", async () => {
  const p = approvedRunning({ plan: { state: "running", lease: { token: "lease-real-0001" } },
    body: { status: "running", workflow_state: "running", lease_token: "lease-real-0001" } });
  const v = await verdict(p, { ...EXECUTOR, "X-Anticipy-Lease": "lease-real-0001" });
  assert.equal(v.ok, true, v.detail);
  assert.equal(p.body.approval, undefined, "approval was written on a non-cancel");
  assert.deepEqual(embeddedApproval(p), STANDING);
});

// ---------------------------------------------------------------------------
// RECEIPT SHAPE IS A FLOOR (2026-09-12, resumed receipt-contract review).
// JSON.parse("null") used to throw below the parse catch, and truthy strings
// or numbers used to buy exactly the verified receipt that only `true` earns.
// These exercise the production guard with matching indexed/embedded copies,
// a real state transition, and the correct lease, not an isolated validator.
// ---------------------------------------------------------------------------
const COMPLETION_HEADERS = {
  ...EXECUTOR, "X-Anticipy-Lease": "lease-real-0001",
};
const VERIFIED_RECEIPT = {
  effect_key: "ek-real-0001", verified: true,
  evidence: ["url:https://receipt.fixture.invalid/confirmed"],
};

function completion(receipt: unknown): Parts {
  return parts({
    row: { status: "running", workflow_state: "running",
      lease_token: "lease-real-0001", lease_until: "2099-01-01 00:00:00.000Z",
      claimed_by: "agent0undertest" },
    plan: { state: "succeeded", receipt, lease: null },
    body: { status: "done", workflow_state: "succeeded", lease_token: "",
      receipt: JSON.stringify(receipt) },
  });
}

await check("a genuine verified receipt completes the leased job", async () => {
  const v = await verdict(completion(VERIFIED_RECEIPT), COMPLETION_HEADERS);
  assert.equal(v.ok, true, v.detail);
});

for (const raw of [null, [], true, false, 1, "receipt", {}]) {
  await check(`a non-receipt JSON value ${JSON.stringify(raw)} refuses without throwing`, async () => {
    const v = await verdict(completion(raw), COMPLETION_HEADERS);
    assert.equal(v.ok, false, "a non-receipt value completed the job");
    assert.equal(v.detail, "done needs verified evidence for this exact effect");
  });
}

for (const verified of [false, 1, 0, "true", "false", "1", [], {}, null]) {
  await check(`verified=${JSON.stringify(verified)} is not genuine verification`, async () => {
    const v = await verdict(completion({ ...VERIFIED_RECEIPT, verified }), COMPLETION_HEADERS);
    assert.equal(v.ok, false, "a coerced verification completed the job");
    assert.equal(v.detail, "done needs verified evidence for this exact effect");
  });
}

for (const evidence of [[], [""], [" \n\t"], [null], [7], [{}], [false],
  ["url:https://receipt.fixture.invalid", null], ["known-reference", ""],
  "known-reference", { 0: "known-reference", length: 1 }, null]) {
  await check(`unusable evidence ${JSON.stringify(evidence)} cannot complete a job`, async () => {
    const v = await verdict(completion({ ...VERIFIED_RECEIPT, evidence }), COMPLETION_HEADERS);
    assert.equal(v.ok, false, "unusable evidence completed the job");
    assert.equal(v.detail, "done needs verified evidence for this exact effect");
  });
}

for (const evidence of [
  ["url:https://receipt.fixture.invalid/confirmed", "title:Confirmation", "evidence:photo-id"],
  ["vendor-log:connector-execution-id"],
  ["vendor-run:toolkit/tool@connected-account"],
  ["text-sha256:" + "a".repeat(64), "https://source.fixture.invalid/page"],
  ["future-tag:opaque-reference", "same-reference", "same-reference", " padded-reference \n"],
]) {
  await check(`supported evidence dialect remains intact: ${evidence[0]}`, async () => {
    const p = completion({ ...VERIFIED_RECEIPT, evidence });
    const before = p.body.receipt;
    const v = await verdict(p, COMPLETION_HEADERS);
    assert.equal(v.ok, true, v.detail);
    assert.equal(p.body.receipt, before, "the guard rewrote receipt evidence");
    assert.deepEqual(p.plan.receipt, { ...VERIFIED_RECEIPT, evidence });
  });
}

for (const [label, blank] of [["NEL", "\u0085"], ["BOM", "\uFEFF"],
  ["mixed wire whitespace", " \n\u0085\uFEFF\t"]]) {
  await check(`${label}-only evidence is empty under the shared wire contract`, async () => {
    const v = await verdict(completion({ ...VERIFIED_RECEIPT, evidence: [blank] }), COMPLETION_HEADERS);
    assert.equal(v.ok, false, "wire whitespace completed a job without a readable reference");
    assert.equal(v.detail, "done needs verified evidence for this exact effect");
  });
}

const WIRE_BLANK_CODEPOINTS = [
  0x0009, 0x000A, 0x000B, 0x000C, 0x000D, 0x0020, 0x0085, 0x00A0,
  0x1680, 0x2000, 0x2001, 0x2002, 0x2003, 0x2004, 0x2005, 0x2006,
  0x2007, 0x2008, 0x2009, 0x200A, 0x200B, 0x2028, 0x2029, 0x202F,
  0x205F, 0x3000, 0xFEFF,
];
for (const codepoint of WIRE_BLANK_CODEPOINTS) {
  await check(`shared wire blank U+${codepoint.toString(16).toUpperCase().padStart(4, "0")} cannot be sole evidence`, async () => {
    const evidence = [String.fromCodePoint(codepoint)];
    const v = await verdict(completion({ ...VERIFIED_RECEIPT, evidence }), COMPLETION_HEADERS);
    assert.equal(v.ok, false, "one runtime accepted a reference the other renders empty");
    assert.equal(v.detail, "done needs verified evidence for this exact effect");
  });
}

await check("nonblank references padded with either wire whitespace dialect remain verbatim", async () => {
  const padding = String.fromCodePoint(...WIRE_BLANK_CODEPOINTS);
  const evidence = [padding + "vendor-log:execution-reference" + padding];
  const p = completion({ ...VERIFIED_RECEIPT, evidence });
  const before = p.body.receipt;
  const v = await verdict(p, COMPLETION_HEADERS);
  assert.equal(v.ok, true, v.detail);
  assert.equal(p.body.receipt, before);
});

await check("valid receipt structure cannot bless evidence for another effect", async () => {
  const v = await verdict(completion({ ...VERIFIED_RECEIPT, effect_key: "another-effect" }), COMPLETION_HEADERS);
  assert.equal(v.ok, false);
  assert.equal(v.detail, "done needs verified evidence for this exact effect");
});

await check("missing verification remains unverified", async () => {
  const v = await verdict(completion({ effect_key: VERIFIED_RECEIPT.effect_key,
    evidence: VERIFIED_RECEIPT.evidence }), COMPLETION_HEADERS);
  assert.equal(v.ok, false);
  assert.equal(v.detail, "done needs verified evidence for this exact effect");
});

await check("the documented pre-workflow compatibility path is unchanged", async () => {
  const p = completion(null);
  p.row.workflow_id = "";
  p.body.workflow_id = "";
  const v = await verdict(p, COMPLETION_HEADERS);
  assert.equal(v.ok, true, v.detail);
});

// An existing workflow may not erase its id to borrow the legacy escape hatch.
// This is the actual authorization/policy chain for a paired browser principal;
// the database seam only reads our synthetic row and never writes or connects.
async function browserChainVerdict(p: Parts, headers: Record<string, string> = COMPLETION_HEADERS) {
  const ctx = {
    request: new Request("https://api.fixture.invalid" + BASE, { method: "PATCH", headers }),
    url: new URL("https://api.fixture.invalid" + BASE), path: BASE, method: "PATCH",
    body: p.body,
    principal: { kind: "agent", agentRowId: "agent0undertest", agentId: "agent0undertest",
      ownerRef: p.row.owner_ref },
    worker: { fromWorker: false }, forcedScope: null, extraAst: null,
    db: { prepare(sql: string) {
      assert.match(sql, /^\s*SELECT\b/i, "this policy test must only read its fixture");
      return { bind() { return { first: async () => p.row }; } };
    } },
  } as unknown as Ctx;
  const response = await runChain([guard, researchLane, workflowGuard], ctx,
    { ANTICIPY_SERVICE_TOKEN: "synthetic-fixture-not-a-credential" });
  const detail = response ? (await response.json() as { detail?: string }).detail ?? "" : "";
  return { ok: response === null, status: response?.status ?? null, detail, scope: ctx.forcedScope };
}

for (const workflowId of ["", null, 0, false, [], {}, ["wf-real-0001"], "another-workflow"]) {
  await check(`a paired executor cannot change an existing workflow id to ${JSON.stringify(workflowId)}`, async () => {
    const p = completion(VERIFIED_RECEIPT);
    p.row.lane = "";
    p.body.workflow_id = workflowId;
    const v = await browserChainVerdict(p);
    assert.equal(v.ok, false, "an existing workflow was erased or reidentified");
    assert.equal(v.status, 409);
    assert.equal(v.detail, "workflow id is immutable");
    assert.equal(p.row.workflow_id, "wf-real-0001", "the policy changed the stored identity");
  });
}

await check("empty workflow id cannot turn a no-lease/no-proof PATCH into legacy work", async () => {
  const p = completion(null);
  p.row.lane = "";
  p.row.params = JSON.stringify({ _workflow: { ...p.plan, state: "running",
    receipt: null, lease: { token: "lease-real-0001" } } });
  p.body.workflow_id = "";
  p.body.params = "{}";
  const v = await browserChainVerdict(p, EXECUTOR);
  assert.equal(v.ok, false, "paired browser bypassed the workflow/lease/receipt gates");
  assert.equal(v.status, 409);
  assert.equal(v.detail, "workflow id is immutable");
});

for (const includeId of [true, false]) {
  await check(`a legitimate paired completion keeps its workflow (${includeId ? "explicit" : "omitted"} id)`, async () => {
    const p = completion(VERIFIED_RECEIPT);
    p.row.lane = "";
    if (!includeId) delete p.body.workflow_id;
    const v = await browserChainVerdict(p);
    assert.equal(v.ok, true, v.detail);
    assert.deepEqual(v.scope, { column: "owner_ref", value: p.row.owner_ref });
  });
}

await check("keeping the row id does not permit a mismatched embedded workflow id", async () => {
  const p = completion(VERIFIED_RECEIPT);
  p.row.lane = "";
  p.plan.plan_id = "different-embedded-workflow";
  p.body.params = JSON.stringify({ _workflow: p.plan });
  const v = await browserChainVerdict(p);
  assert.equal(v.ok, false);
  assert.equal(v.detail, "job fields disagree with the embedded workflow");
});

for (const includeId of [true, false]) {
  await check(`genuinely pre-workflow paired rows remain compatible (${includeId ? "empty" : "omitted"} id)`, async () => {
    const p = completion(null);
    p.row.lane = "";
    p.row.workflow_id = "";
    if (includeId) p.body.workflow_id = "";
    else delete p.body.workflow_id;
    p.body.params = "{}";
    const v = await browserChainVerdict(p, EXECUTOR);
    assert.equal(v.ok, true, v.detail);
    assert.deepEqual(v.scope, { column: "owner_ref", value: p.row.owner_ref });
  });
}

console.log(`workflow-guard-empties: ${passes} checks passed, ${failures} failed`);
if (failures) process.exit(1);
