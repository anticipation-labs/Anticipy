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
    const audit = body.messages.some((message) =>
      String(message?.content || "").startsWith("You audit"));
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

// ---- 4. What ELSE crosses the park: the consent offer's ref --------------
//
// A parked run's tab is its state; `_offer_ref` is the other half — WHICH
// QUESTION it is parked on. It is what proves, on the resume, that the question
// the owner answered was one of this extension's own consent offers rather than
// prose the step model composed while reading a page. A reviewer opened the
// owner's Gmail through exactly that gap on 2026-08-24 (side_trip.js,
// `mintOfferRef`), so the two rules below are load-bearing, not bookkeeping:
//
//   * it is WRITTEN on a hand-back that put one of our offers;
//   * it is CLEARED on every other hand-back, including a tabless one — a ref
//     that outlives its question is one the step model can read out of the
//     approved scope and forge a question with;
//   * it never reaches the step model as a "fact".
{
  const { handBackParamsPatch, ownerFactsFromParams } = await import("../background.js");
  const REF = "a1b2c3d4e5f60718293a4b5c6d7e8f90";

  const put = handBackParamsPatch({ status: "needs_user", offerRef: REF, tabId: 7 }, "sess-1");
  assert.equal(put._offer_ref, REF, "a hand-back that put our offer must record its ref");
  assert.equal(put.resume_tab, 7, "and still stamp the tab it parked");
  assert.equal(put.resume_session, "sess-1");

  const other = handBackParamsPatch({ status: "needs_user", tabId: 7 }, "sess-1");
  assert.equal(other._offer_ref, "",
    "a hand-back that is NOT our offer must CLEAR the ref, not leave the last one live");

  const tabless = handBackParamsPatch({ status: "needs_user" }, "");
  assert.equal(tabless._offer_ref, "",
    "a tabless park must clear it too — gating the clear on the tab leaves stale refs alive");
  assert.ok(!("resume_tab" in tabless), "and must not stamp a tab that does not exist");

  for (const junk of [null, undefined, 12345, { toString: () => REF }, ["x"]]) {
    assert.equal(handBackParamsPatch({ status: "needs_user", offerRef: junk }, "").
      _offer_ref, "", `a non-string offerRef (${typeof junk}) must be recorded as cleared`);
  }

  // FACTS ALREADY GIVEN is rendered into the step prompt. A ref that leaked in
  // there would be handed to the one model that must never reproduce it.
  const facts = ownerFactsFromParams({
    _offer_ref: REF, _doing: "looking", _workflow: { plan_id: "p" },
    party_size: 4, time: "7pm", approved_scope: "...", memory: "he likes window seats",
    owner_answer_1: "West van", resume_tab: 7,
  });
  assert.ok(!JSON.stringify(facts).includes(REF), `the ref must never reach the model: ${JSON.stringify(facts)}`);
  assert.deepEqual(facts, { party_size: 4, time: "7pm" },
    `only values the owner gave are facts: ${JSON.stringify(facts)}`);
  const wf = ownerFactsFromParams({ _workflow: { facts: { location: "West Vancouver", _offer_ref: REF, owner_answer: "x" } } });
  assert.deepEqual(wf, { location: "West Vancouver" },
    `the workflow branch excludes the same keys: ${JSON.stringify(wf)}`);
  console.log("PASS 4: the offer ref crosses the park, is cleared otherwise, and never reaches the model");
}

console.log("test_resume_tab: all passed");
