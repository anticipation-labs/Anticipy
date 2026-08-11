// A parked run's tab IS its state. Live, 2026-08-11: a booking parked on
// "I need the verification code" resumed in a brand-new tab at the start
// URL — fresh session, empty form, the code the site had just sent now
// meaningless. A resume must reattach to the parked tab when it still
// exists, and only start fresh when it's truly gone.
// Run: node extension/tests/test_resume_tab.mjs

import assert from "node:assert/strict";
import { installChrome } from "./chrome_mock.mjs";

function scriptFetch(actions, verdicts = [{ verified: true }]) {
  const a = [...actions], v = [...verdicts];
  globalThis.fetch = async (url, opts = {}) => {
    if (!String(url).includes("openrouter")) return { ok: false, status: 0, json: async () => ({}), text: async () => "" };
    const body = JSON.parse(opts.body);
    const audit = String(body.messages[0].content).startsWith("You audit");
    const content = JSON.stringify(audit ? (v.shift() || { verified: true }) : (a.shift() || { action: "wait" }));
    return { ok: true, status: 200, json: async () => ({ choices: [{ message: { content } }] }), text: async () => "" };
  };
}

const harness = installChrome();
const { runAgentGoal } = await import("../agent_loop.js");

function freshWorld() {
  harness.tabs.clear();
  harness.focusGrants.length = 0;
  harness.activationLog.length = 0;
  harness.onCdp = null;
  delete harness.storageData.agentTabs;
  return harness.addTab({ url: "https://news.site/read", active: true });
}

// ---- 1. Resume reattaches to the parked tab, exactly where it stopped ----
{
  freshWorld();
  const parked = harness.addTab({ url: "https://site.example/checkout/otp" });
  harness.mapPage = (tabId) => ({
    url: harness.tabs.get(tabId)?.url || "",
    title: "Verify", elements: "[0] <input> code", text: "Enter the code we sent you." });
  scriptFetch([{ action: "done", result: "code entered, booking confirmed" }]);
  const before = harness.tabs.size;
  const out = await runAgentGoal("finish the booking with the code", {
    apiKey: "k", maxSteps: 4, resumeTabId: parked.id });

  assert.equal(out.status, "done", `resume must complete: ${out.result}`);
  assert.equal(out.tabId, parked.id, "the run must operate the PARKED tab, not a fresh one");
  assert.ok(harness.tabs.size <= before, "no new working tab may be opened on resume");
  assert.equal(harness.tabs.get(parked.id)?.url ?? "https://site.example/checkout/otp",
    "https://site.example/checkout/otp");
  console.log("PASS 1: resume reattached to the parked tab — session and page kept");
}

// ---- 2. Parked tab gone (Chrome restarted): start fresh, don't die -------
{
  freshWorld();
  harness.mapPage = (tabId) => ({
    url: harness.tabs.get(tabId)?.url || "",
    title: "Search", elements: "[0] <input> search", text: "search page" });
  scriptFetch([{ action: "done", result: "started over and finished" }]);
  const out = await runAgentGoal("finish the booking", {
    apiKey: "k", maxSteps: 4, resumeTabId: 9999, startUrl: "https://site.example/" });

  assert.equal(out.status, "done", `fresh start must still work: ${out.result}`);
  assert.notEqual(out.tabId, 9999, "a vanished parked tab means a fresh one");
  console.log("PASS 2: vanished parked tab — run started fresh instead of dying");
}

// ---- 3. The sweep must never close the tab being resumed -----------------
{
  freshWorld();
  const parked = harness.addTab({ url: "https://site.example/checkout/otp" });
  harness.storageData.agentTabs = [parked.id];
  harness.mapPage = (tabId) => ({
    url: harness.tabs.get(tabId)?.url || "",
    title: "Verify", elements: "[0] <input> code", text: "Enter the code." });
  scriptFetch([{ action: "done", result: "confirmed" }]);
  const out = await runAgentGoal("finish the booking with the code", {
    apiKey: "k", maxSteps: 4, resumeTabId: parked.id });

  assert.equal(out.status, "done", `resume must complete: ${out.result}`);
  assert.equal(out.tabId, parked.id, "the swept-tab list must spare the resume target");
  console.log("PASS 3: leftover-tab sweep spared the tab being resumed");
}

console.log("test_resume_tab: all passed");
