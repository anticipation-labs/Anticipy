// A browser that cannot read a page has no receipt and therefore no right to
// say the errand is complete.  This drives the real loop with a Chrome error
// page for three consecutive reads: the run must park visibly, keep its tab,
// and return no completion receipt.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { installChrome } from "./chrome_mock.mjs";

const scenarios = JSON.parse(readFileSync(
  new URL("../../tests/fixtures/real_world_action_scenarios.json", import.meta.url),
  "utf8",
));
const scenario = scenarios.browser_cases.find(
  (row) => row.id === "browser_offline_never_completes",
);
assert.ok(scenario, "the shared field-rehearsal fixture must name the offline case");

const harness = installChrome();
const owner = harness.addTab({ url: "https://notes.example/meeting", active: true });
harness.mapPage = () => {
  throw new Error(scenario.map_error);
};

// The browser is offline, so the model endpoint is offline as well.  The page
// read fails before a decision is requested; this stub makes any accidental
// network path fail closed too.
globalThis.fetch = async () => ({
  ok: false,
  status: 0,
  json: async () => ({}),
  text: async () => "",
});

const { runAgentGoal } = await import("../agent_loop.js");
const out = await runAgentGoal(scenario.goal, {
  apiKey: "fixture-key",
  planning: false,
  startUrl: "https://reservations.example/",
  authorized: true,
  maxSteps: 3,
  budgetMs: 30_000,
  stillLive: async () => true,
});

assert.equal(out.status, "needs_user",
  `offline work must park, not complete: ${JSON.stringify(out)}`);
assert.equal(out.receipt, undefined,
  "a run that never read a page cannot mint a completion receipt");
assert.notEqual(out.status, "done",
  "a missing receipt must never be represented as completed work");
assert.match(String(out.result || ""), /unreadable|load|connection|page/i,
  "the hand-back must say what failed in language the card can show");
assert.equal(harness.activeTabId(), owner.id,
  "the offline run must not steal the owner's foreground");
assert.ok(harness.tabs.has(out.tabId),
  "needs_user keeps the working tab so a recovered connection can resume");

console.log("test_offline_completion_honesty: all passed");
process.exit(0);
