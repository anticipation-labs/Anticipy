import assert from "node:assert/strict";
import { installChrome } from "./chrome_mock.mjs";

const harness = installChrome();
Object.assign(harness.storageData, {
  agentId: "already-installed",
  agentToken: "already-installed-token",
  recordId: "already-installed-record",
  agentCredentialInstalled: true,
});
globalThis.fetch = async () => ({
  ok: false, status: 0, json: async () => ({}), text: async () => "",
});

await import("../background.js");
await new Promise((resolve) => setTimeout(resolve, 10));

for (const name of ["anticipy-poll", "anticipy-heartbeat"]) {
  const alarm = harness.alarms.get(name);
  assert.ok(alarm, `${name} is created on every worker boot`);
  assert.equal(alarm.delayInMinutes, 0.5, `${name} uses Chrome's supported delay`);
  assert.equal(alarm.periodInMinutes, 0.5, `${name} uses Chrome's supported period`);
  assert.equal(alarm.persistAcrossSessions, true, `${name} explicitly persists`);
}
console.log("PASS 1: supported persistent alarms exist on worker boot");

// Chrome documents that alarms can be cleared on restart. Simulate that loss
// and verify the explicit browser-start path repairs both clocks.
harness.alarms.clear();
harness.fireStartup();
await new Promise((resolve) => setTimeout(resolve, 10));
assert.ok(harness.alarms.has("anticipy-poll"));
assert.ok(harness.alarms.has("anticipy-heartbeat"));
console.log("PASS 2: browser startup recreates missing alarms");

// A legacy sub-minimum alarm must be replaced, not accepted as healthy.
harness.alarms.set("anticipy-poll", {
  name: "anticipy-poll", periodInMinutes: 5 / 60,
});
harness.fireStartup();
await new Promise((resolve) => setTimeout(resolve, 10));
assert.equal(harness.alarms.get("anticipy-poll").periodInMinutes, 0.5);
console.log("PASS 3: unsupported legacy schedule is upgraded");

console.log("test_background_scheduling: all 3 scenarios passed");
process.exit(0);
