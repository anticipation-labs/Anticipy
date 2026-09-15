// The bare-403 liveness grace belongs to ONE run.
//
// jobStillLive() treats a bare 403 as a hiccup rather than revocation, because
// a D1 blip inside recordOwner() answers a perfectly valid claimant with the
// guard's refusal — and until 2026-09-14 one such read ended a live errand and
// told the owner they had called it off. The budget that makes that safe
// (LIVENESS_REFUSAL_STOP) lived in a module global cleared only by a
// successful read, so a run whose LAST probe was a refusal handed the next
// errand a spent budget: one blip, and a fresh job was abandoned.
import assert from "node:assert/strict";
import { installRig, flush, until } from "./rig_lifecycle.mjs";

const rig = installRig();
await import("../background.js");
await flush(80);

const realFetch = globalThis.fetch;
let refuseFor = null, budget = 0;
const served = {};
globalThis.fetch = async (url, options) => {
  const path = new URL(String(url)).pathname;
  const isRead = !options?.method || options.method === "GET";
  const match = path.match(/\/jobs\/records\/(job-[ab])$/);
  if (match && isRead && match[1] === refuseFor && budget > 0) {
    budget -= 1;
    served[match[1]] = (served[match[1]] || 0) + 1;
    // A BARE refusal: the guard's own wording, with no explicit verdict about
    // the credential. claimJob and jobStillLive both act only on the explicit
    // "agent credential is not recognized".
    return rig.reply({ error: "agent is not allowed to access that record" }, 403);
  }
  return realFetch(url, options);
};

// Job A burns the whole budget: every liveness probe is refused, so the run
// abandons the errand with a refusal as the last thing the counter saw. It is
// deliberately NOT driven to a terminal row state -- a run that loses its
// liveness budget simply stops touching the row, which is the state that left
// the counter spent.
rig.seedJob("job-a", { task: "read the public opening hours" });
refuseFor = "job-a"; budget = 99;
rig.harness.fireAlarm("anticipy-poll");
await until(() => (served["job-a"] || 0) >= 3, { tries: 2000, step: 25,
  what: "job-a to spend the whole refusal budget" });
await flush(400);

// Job B now gets ONE blip. It must survive it: the grace is per run.
rig.seedJob("job-b", { task: "read the other public page" });
refuseFor = "job-b"; budget = 1;
rig.harness.fireAlarm("anticipy-poll");
await until(() => (served["job-b"] || 0) >= 1, { tries: 2000, step: 25,
  what: "job-b to be probed" });
await flush(1500);

// The assertion has to be that job B FINISHES. "Not cancelled" is too weak:
// a run that loses its liveness budget simply stops touching the row, so the
// row sits exactly as it was and a status check passes for the wrong reason.
const SETTLED = ["succeeded", "failed", "needs_user", "cancelled"];
try {
  await until(() => SETTLED.includes(rig.row("job-b").workflow_state),
    { tries: 2000, step: 25, what: "job-b to reach an end state despite one blip" });
} catch (_) {
  const row = rig.row("job-b");
  assert.fail("one bare 403 abandoned a fresh errand: the refusal budget carried over "
    + `from job-a, so the run stopped mid-flight and left the row at `
    + `status=${row.status} workflow_state=${row.workflow_state} — the owner's errand `
    + "simply never happens, and nothing says so");
}
assert.notEqual(rig.row("job-b").workflow_state, "cancelled",
  "a blip was read as revocation");
const mirror = String(rig.harness.storageData.currentJob?.result || "");
assert.ok(!/unpaired|called (it|this) off|no longer linked/i.test(mirror),
  `the owner was told the browser was unpaired after one blip: ${mirror.slice(0, 120)}`);

console.log("liveness budget: per run, not per browser — ok");
process.exit(0);
