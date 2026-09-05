import assert from "node:assert/strict";
import {
  heartbeatPatch,
  markEffectUncertainPatch,
  uncertainEffectMessage,
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

// THE INTENT, NOT JUST THE FLAG. The Brief promises an intent journal written
// before every click; the flag alone left a crash-then-retry able to re-send.
{
  const j = job("running");
  const before = JSON.stringify(parseJobParams(j)._workflow);
  const patch = markEffectUncertainPatch(j, {
    doing: "Clicking Book table on fixture.test", url: "https://fixture.test/book",
    sig: "https://fixture.test/book|click|button|Book table|||book|3",
    digest: "d1gest", at: "2026-09-05T00:00:00.000Z",
    step: 4, tab: 17, session: "sess-1",
    // A caller cannot smuggle anything else in: only the named keys are copied.
    fields: [{ label: "Name", value: "Alex Reyes" }],
  });
  assert.equal(patch.effect_uncertain, true);
  const written = parseJobParams(patch)._effect_intent;
  assert.deepEqual(Object.keys(written).sort(),
    ["at", "digest", "doing", "session", "sig", "step", "tab", "url"],
    "exactly these keys and no other — no form value may ever ride here");
  assert.ok(!JSON.stringify(written).includes("Alex Reyes"), "a value handed in is not copied");
  assert.equal(written.sig, "https://fixture.test/book|click|button|Book table|||book|3");
  assert.equal(written.digest, "d1gest");
  assert.equal(written.step, 4);
  assert.equal(written.tab, 17);
  assert.equal(written.session, "sess-1");
  // The PocketBase guard compares _workflow's fields against the row; this
  // write must leave every one of them untouched.
  assert.equal(JSON.stringify(parseJobParams(patch)._workflow), before,
    "_workflow is byte-identical after the intent is written beside it");
  // And the owner's card now says what to look for.
  const parked = { ...j, ...patch };
  const msg = uncertainEffectMessage(parked);
  assert.ok(msg.includes("Clicking Book table on fixture.test"), "the card names what was about to be sent");
  assert.ok(msg.includes("https://fixture.test/book"), "and where");
  assert.ok(/Check the site before I try again/.test(msg), "on top of the standing warning, not instead of it");
  // No intent recorded (a pre-2026-09-05 row, or a non-workflow job) -> the
  // old sentence, unchanged, so nothing that read it before breaks.
  assert.equal(uncertainEffectMessage(j), uncertainEffectMessage({ params: "{}" }));
  assert.ok(!/It was:/.test(uncertainEffectMessage(j)));
  console.log("PASS: the pre-click write carries the intent, keeps _workflow intact, and the card can say what to look for");
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
  const j = job("running");
  const p = workflowPatch(j, "succeeded", {
    summary: "s".repeat(7000), verified: true,
    evidence: Array.from({ length: 20 }, (_, index) =>
      `page-${index}:` + "e".repeat(2500)),
    now: "2026-08-12T20:02:30.000Z",
  });
  const receipt = JSON.parse(p.receipt);
  assert.equal(receipt.summary.length, 2000);
  assert.equal(receipt.evidence.length, 12);
  assert.ok(receipt.evidence.every((entry) => entry.length <= 1000));
  console.log("PASS: verified receipts stay bounded while the full result remains separate");
}

{
  assert.throws(() => workflowPatch(job("failed"), "queued", {}), /illegal workflow transition/);
  assert.throws(() => workflowPatch(job("cancelled"), "running", {}), /illegal workflow transition/);
  console.log("PASS: terminal work cannot be resurrected by the browser");
}

console.log("test_workflow_state: all passed");
