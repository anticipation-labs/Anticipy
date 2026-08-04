// Brief 03 — behavioral proof, offline: a browser job runs start-to-finish
// while the owner sits on a different tab, and that tab keeps the foreground
// the whole way — including when a target=_blank popup steals focus (the mock
// reproduces Chrome foregrounding it AND Chrome's close-hands-focus-to-opener
// successor rule). Run: node extension/tests/test_agent_loop_focus.mjs

import assert from "node:assert/strict";
import { installChrome } from "./chrome_mock.mjs";

// The LLM, scripted: action replies in order, then verify verdicts.
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
  // The owner's tab: active before the run, must be active after every twist.
  return harness.addTab({ url: "https://news.site/read", active: true });
}
const agentTabId = () => (harness.storageData.agentTabs || [])[0]
  ?? [...harness.tabs.values()].find((t) => t.id !== 1 && t.openerTabId === undefined)?.id;

// ---- 1. Research-style job where a click spawns a FOCUS-STEALING popup ----
{
  const owner = freshWorld();
  let spawned = false;
  harness.onCdp = (tabId, method, params) => {
    if (!spawned && method === "Input.dispatchMouseEvent" && params.type === "mousePressed") {
      spawned = true; // the page pops a target=_blank tab and Chrome foregrounds it
      harness.addTab({ url: "https://example.com/more", active: true, openerTabId: tabId });
    }
  };
  harness.mapPage = (tabId) => {
    const t = harness.tabs.get(tabId);
    return { url: t?.url || "", title: "Example Domain", elements: "[0] <a> More information", text: "Example Domain. This domain is for use in illustrative examples." };
  };
  scriptFetch([
    { action: "click", index: 0 },
    { action: "done", result: "Example Domain — used in illustrative examples" },
  ]);
  const out = await runAgentGoal("read the example.com heading", { apiKey: "k", maxSteps: 6, startUrl: "https://example.com/" });

  assert.equal(out.status, "done", `job must still complete: ${out.result}`);
  assert.equal(harness.activeTabId(), owner.id, "the owner's tab must hold the foreground at the end");
  // The popup DID take focus (Chrome's doing) — but the agent's own working
  // tab must never have been activated, by us or by successor fallout.
  assert.ok(!harness.activationLog.includes(out.tabId), "the working tab must never become active");
  // Every focus grant the extension issued went to the OWNER's tab (restores).
  for (const g of harness.focusGrants) assert.equal(g.tabId, owner.id, `focus grant to non-owner tab: ${JSON.stringify(g)}`);
  assert.equal(harness.tabs.size, 1, "working tab and popup are both gone; only the owner's tab remains");
  console.log("PASS 1: focus-stealing popup — owner tab kept the foreground, job completed");
}

// ---- 2. Plain job, no popups: zero focus effects of any kind --------------
{
  const owner = freshWorld();
  harness.mapPage = (tabId) => ({ url: harness.tabs.get(tabId)?.url || "", title: "Example Domain", elements: "[0] <a> More information", text: "Example Domain. This domain is for use in illustrative examples." });
  scriptFetch([{ action: "done", result: "Example Domain — used in illustrative examples" }]);
  const out = await runAgentGoal("read the example.com heading", { apiKey: "k", maxSteps: 4, startUrl: "https://example.com/" });

  assert.equal(out.status, "done", `job must complete: ${out.result}`);
  assert.equal(harness.focusGrants.length, 0, "an undisturbed run issues NO focus calls at all");
  assert.deepEqual(harness.activationLog, [owner.id], "nothing but the owner's own tab was ever active");
  assert.equal(harness.activeTabId(), owner.id);
  console.log("PASS 2: quiet run — zero focus calls, owner tab never blinked");
}

// ---- 3. needs_user hand-back: the tab is KEPT but never surfaces itself ---
{
  const owner = freshWorld();
  harness.mapPage = (tabId) => ({ url: harness.tabs.get(tabId)?.url || "", title: "Login", elements: "[0] <input> username", text: "Please sign in to continue." });
  scriptFetch([{ action: "needs_user", reason: "a login wall only you can pass" }]);
  const out = await runAgentGoal("check the account page", { apiKey: "k", maxSteps: 4, startUrl: "https://example.com/account" });

  assert.equal(out.status, "needs_user");
  const kept = harness.tabs.get(out.tabId);
  assert.ok(kept, "the hand-back tab is kept for the owner");
  assert.equal(kept.active, false, "the hand-back must NOT activate the tab");
  assert.ok(kept.groupId > 0, "the kept tab stays in its collapsed group until the owner clicks");
  assert.equal(harness.activeTabId(), owner.id, "the owner's tab still holds the foreground");
  assert.equal(harness.focusGrants.length, 0, "a hand-back issues no focus calls — the notification click does that, later");
  assert.deepEqual(harness.storageData.agentTabs, [], "kept tab is off the sweep list so the next run won't close it");
  console.log("PASS 3: needs_user hand-back — tab kept, grouped, background; no focus stolen");
}

console.log("test_agent_loop_focus: all 3 scenarios passed");
// agent_loop's withTimeout leaves its rejection timers running (fine in a
// service worker); don't let them hold the test process open for 90s.
process.exit(0);
