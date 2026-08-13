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

const { ensureRegistered } = await import("../background.js");
await new Promise((resolve) => setTimeout(resolve, 10));

for (const key of ["agentId", "agentToken", "recordId", "agentCredentialInstalled"])
  delete harness.storageData[key];

let registrations = 0;
globalThis.fetch = async (url) => {
  if (String(url).endsWith("/agent/register")) {
    registrations += 1;
    await new Promise((resolve) => setTimeout(resolve, 20));
    return {
      ok: true,
      status: 200,
      json: async () => ({
        id: "one-record",
        agent_token: "one-private-token",
        pair_code: "123456",
      }),
      text: async () => "",
    };
  }
  return { ok: false, status: 0, json: async () => ({}), text: async () => "" };
};

const [first, second] = await Promise.all([
  ensureRegistered(), ensureRegistered(),
]);
assert.equal(registrations, 1, "concurrent first-install wakeups register only once");
assert.deepEqual(first, second);
assert.equal(harness.storageData.recordId, "one-record");
assert.equal(harness.storageData.agentToken, "one-private-token");
console.log("test_registration_singleflight: concurrent first install registered once");
process.exit(0);
