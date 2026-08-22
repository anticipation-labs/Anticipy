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

// A CHROME THAT HAS NEVER HEARD OF persistAcrossSessions (anything before
// 150) does not ignore the unknown key — it throws, so the alarm is never
// created, and every caller of ensureWakeAlarms swallows the rejection. There
// is no other recurring wake, so the browser arm silently becomes a button
// you press by opening the popup. Measured live in Chrome 148 on 2026-08-19:
// alarms.getAll() empty forever; a queued job untouched for 30s; the same job
// claimed 194ms after the popup opened.
{
  const { ensureWakeAlarms } = await import("../background.js");
  harness.alarms.clear();
  const create = globalThis.chrome.alarms.create;
  const asked = [];
  globalThis.chrome.alarms.create = async (name, info = {}) => {
    asked.push(Object.keys(info));
    if ("persistAcrossSessions" in info) {
      // Chrome's own words, from its argument validator.
      throw new TypeError("Error at parameter 'alarmInfo': Unexpected property: 'persistAcrossSessions'.");
    }
    return create(name, info);
  };
  try {
    await ensureWakeAlarms();
  } finally {
    globalThis.chrome.alarms.create = create;
  }
  for (const name of ["anticipy-poll", "anticipy-heartbeat"]) {
    const alarm = harness.alarms.get(name);
    assert.ok(alarm, `${name} must still exist on a Chrome without persistent alarms`);
    assert.equal(alarm.periodInMinutes, 0.5, `${name} keeps the supported period`);
    assert.ok(!("persistAcrossSessions" in alarm),
      "the fallback must not carry the property that made Chrome refuse it");
  }
  assert.ok(asked.some((keys) => keys.includes("persistAcrossSessions")),
    "persistence is still asked for first — a modern Chrome should keep it");
  console.log("PASS 4: a Chrome older than 150 still gets a working wake alarm");
}

console.log("test_background_scheduling: all 4 scenarios passed");
process.exit(0);
