import assert from "node:assert/strict";
import {
  heartbeatPatch,
  markEffectUncertainPatch,
  parseJobParams,
  workflowPatch,
} from "../workflow_state.js";

function job(state = "queued") {
  const wf = {
    plan_id: "plan-1", owner_ref: "owner-1", lineage_key: "lineage-1",
    version: 3, goal: "submit the warranty claim", consequence: "consequential",
    state, facts: { serial: "ABC" }, required: ["serial"], source_event_ids: ["event-1"],
    approval: {
      plan_id: "plan-1", plan_version: 3, scope_digest: "scope-3",
      owner_words: "yes, submit that claim", approved_at: "2026-08-12T20:00:00.000Z",
    },
    lease: null, receipt: null, attempts: 0, reason: "approved by owner",
    created_at: "2026-08-12T19:00:00.000Z", updated_at: "2026-08-12T20:00:00.000Z",
  };
  if (state === "running") {
    wf.lease = { token: "lease-1", actor_id: "agent-1", acquired_at: "2026-08-12T20:01:00.000Z", expires_at: "2026-08-12T20:03:00.000Z", attempt: 1 };
    wf.attempts = 1;
  }
  return {
    id: "job-1", workflow_id: "plan-1", workflow_version: 3,
    workflow_state: state, effect_key: "effect-3", attempts: wf.attempts,
    lease_token: wf.lease?.token || "", params: JSON.stringify({ task: wf.goal, _workflow: wf }),
  };
}

{
  const p = workflowPatch(job(), "running", {
    actorId: "agent-1", leaseToken: "lease-1", attempt: 1,
    now: "2026-08-12T20:01:00.000Z", leaseUntil: "2026-08-12T20:03:00.000Z",
  });
  const wf = parseJobParams(p)._workflow;
  assert.equal(p.status, "running");
  assert.equal(p.lease_token, "lease-1");
  assert.equal(wf.state, "running");
  assert.equal(wf.lease.token, "lease-1");
  assert.equal(wf.attempts, 1);
  console.log("PASS: claim persists the same attempt and lease in both representations");
}

{
  const j = job("running");
  const p = heartbeatPatch(j, {
    leaseToken: "lease-1", now: "2026-08-12T20:02:00.000Z",
    leaseUntil: "2026-08-12T20:04:00.000Z",
  });
  assert.equal(p.lease_until, "2026-08-12T20:04:00.000Z");
  assert.equal(parseJobParams(p)._workflow.lease.expires_at, p.lease_until);
  assert.throws(() => heartbeatPatch(j, { leaseToken: "someone-else", leaseUntil: new Date() }), /mismatch/);
  console.log("PASS: only the matching executor can renew the durable lease");
}

{
  const j = job("running");
  assert.deepEqual(markEffectUncertainPatch(j), { effect_uncertain: true });
  const p = workflowPatch(j, "needs_user", {
    reason: "possible external effect; verify before retry", effectUncertain: true,
  });
  assert.equal(p.status, "needs_user");
  assert.equal(p.effect_uncertain, true);
  assert.equal(parseJobParams(p)._workflow.lease, null);
  console.log("PASS: an uncertain external effect parks without a retry lease");
}

{
  const j = job("running");
  const p = workflowPatch(j, "succeeded", {
    summary: "claim accepted", verified: true,
    evidence: ["url:https://vendor.example/confirmation", "page:confirmation #Q41"],
    now: "2026-08-12T20:02:30.000Z",
  });
  const receipt = JSON.parse(p.receipt);
  assert.equal(p.status, "done");
  assert.equal(receipt.effect_key, "effect-3");
  assert.equal(receipt.verified, true);
  assert.equal(parseJobParams(p)._workflow.receipt.effect_key, "effect-3");
  assert.throws(() => workflowPatch(j, "succeeded", { verified: true, evidence: [] }), /verified evidence/);
  console.log("PASS: done is impossible without evidence tied to the exact effect");
}

{
  assert.throws(() => workflowPatch(job("failed"), "queued", {}), /illegal workflow transition/);
  assert.throws(() => workflowPatch(job("cancelled"), "running", {}), /illegal workflow transition/);
  console.log("PASS: terminal work cannot be resurrected by the browser");
}

console.log("test_workflow_state: all passed");
