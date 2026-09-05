// A RETRY AFTER A CRASH RE-SENT THE SUBMISSION THE FLAG EXISTED TO PREVENT.
//
// docs/BRIEF.html promises "an intent journal written before every click, so
// 'did the send actually happen?' is answerable after any crash". What was
// written before the click, until 2026-09-05, was one boolean:
// effect_uncertain=true. The control's signature and the submission digest —
// the two keys the at-most-once gate refuses repeats by — lived only in
// `performedExternalEffects`, a Set created empty on every run. A Manifest V3
// worker is reclaimed mid-run as a matter of course; the run that resumed the
// job afterwards started with that Set empty, and the same submission went out
// again. The loop's own comment calls the duplicate booking the cardinal sin.
// The board marked the intent journal DONE, so nobody was looking.
//
// The fix carries the intent into the durable row beside the flag and seeds
// the Set from it on resume. This suite proves the seeding is the only thing
// standing between a resumed run and a second send — by running the same
// fixture three times and changing nothing but the seed.
//
// Run: node extension/tests/test_effect_intent_survives_crash.mjs
import { installChrome } from "./chrome_mock.mjs";

const harness = installChrome();
const FAKE_JPEG = Buffer.from("x".repeat(9000)).toString("base64");
const { runAgentGoal } = await import("../agent_loop.js");

let failures = 0;
const check = (name, ok) => {
  console.log(`${ok ? "PASS" : "FAIL"}: ${name}`);
  if (!ok) failures++;
};

let page = null;
let controls = {};
const realExecuteScript = chrome.scripting.executeScript;
chrome.scripting.executeScript = async (opts) => {
  const src = opts?.func ? String(opts.func) : "";
  const index = Array.isArray(opts?.args) ? Number(opts.args[0]) : null;
  if (src.includes("navigationLink")) return [{ frameId: 0, result: !!controls[index]?.commit }];
  if (src.includes("fieldsIn")) {
    const c = controls[index];
    if (!c) return [{ frameId: 0, result: null }];
    return [{ frameId: 0, result: {
      label: c.label, tag: c.tag, href: "", nearbyText: c.label,
      formAction: c.formAction, name: c.name || "", elementId: c.elementId || "",
      fieldIndexes: c.fieldIndexes,
    } }];
  }
  return realExecuteScript(opts);
};

function fresh() {
  harness.tabs.clear();
  harness.focusGrants.length = 0;
  harness.onCdp = (tabId, method) => (method === "Page.captureScreenshot" ? { data: FAKE_JPEG } : undefined);
  harness.onInject = null;
  for (const key of Object.keys(harness.storageData)) delete harness.storageData[key];
  harness.mapPage = () => page;
  harness.addTab({ url: "https://news.site/read", active: true });
}

function scripted(actions) {
  const queue = [...actions];
  globalThis.fetch = async (url, opts = {}) => {
    if (!String(url).includes("openrouter")) return { ok: false, status: 0, json: async () => ({}), text: async () => "" };
    const joined = JSON.parse(opts.body).messages.map((m) => (Array.isArray(m.content)
      ? m.content.map((p) => (p.type === "text" ? p.text : "[image]")).join("\n")
      : String(m.content || ""))).join("\n");
    let content;
    if (/pre-submit form auditor/.test(joined)) content = JSON.stringify({ values: [] });
    else if (/You audit a browser agent's claim/.test(joined)) content = JSON.stringify({ verified: true, evidence: ["confirmed"] });
    else if (/reading the open web to learn HOW/.test(joined)) content = JSON.stringify({ steps: [] });
    else content = JSON.stringify(queue.shift() || { action: "wait" });
    return { ok: true, status: 200, json: async () => ({ choices: [{ message: { content } }] }), text: async () => "" };
  };
}

// The same booking every time. One form, one submit button, one name field.
const GOAL = "book a table for 6 under the name Alex Reyes";
page = {
  url: "https://fixture.test/book",
  title: "Reserve a table",
  elements: "[1] <textbox> Name @(10,10)\n[2] <textbox> Party size @(10,40)\n[3] <button> Book table @(10,70)",
  text: "Held for 4:32. Review your reservation and book the table.",
  fields: [
    { index: 1, name: "guest_name", label: "Name", type: "text", required: true, readOnly: false, value: "Alex Reyes" },
    { index: 2, name: "party_size", label: "Party size", type: "text", required: true, readOnly: false, value: "6" },
  ],
};
const form = { formAction: "https://fixture.test/book/submit", fieldIndexes: [1, 2] };
controls = { 3: { ...form, commit: true, label: "Book table", tag: "button", name: "", elementId: "book-table" } };
const SCRIPT = [{ action: "click", index: 3 }, { action: "done", result: "Table booked" }];

async function run({ seed, capture }) {
  fresh();
  scripted(SCRIPT);
  let effects = 0;
  let trace = [];
  const out = await runAgentGoal(GOAL, {
    apiKey: "test-key", scope: GOAL, authorized: true, planning: false,
    maxSteps: 5, startUrl: page.url, stillLive: async () => true,
    initialEffectIntent: seed,
    onTrace: (history) => { trace = history; },
    onBeforeExternalEffect: async (_decision, _state, intent) => { effects += 1; if (capture) capture(intent); },
  });
  return { out, effects, trace: trace.join("\n") };
}

// ------------------------------------------------ 1. the original run
// The click goes out once, and the loop hands its intent to the callback.
let intent = null;
const first = await run({ seed: null, capture: (i) => { intent = i; } });
check("the original run dispatched the booking once", first.effects === 1);
check("...and handed the callback an intent record", !!intent && typeof intent === "object");
// Seven keys, all structure: the sentence, the page, the two gate keys, the
// time, and — for the crash recovery (audit #90) — the step and the tab id.
check("the intent carries exactly doing/url/sig/digest/at/step/tab",
  !!intent && JSON.stringify(Object.keys(intent).sort())
    === JSON.stringify(["at", "digest", "doing", "sig", "step", "tab", "url"]));
check("the intent names the control and the page", !!intent && /Book table/.test(intent.doing) && intent.url === page.url);
check("the intent says which step clicked and in which tab",
  !!intent && Number.isInteger(intent.step) && Number.isInteger(intent.tab));
check("the intent carries the control signature", !!intent && typeof intent.sig === "string" && intent.sig.length > 0);
// THE PRIVACY RULE, pinned at the loop, not only in workflow_state: this row
// is exportable, and the name typed into the form must never ride on it.
check("the intent carries NO form value", !!intent && !JSON.stringify(intent).includes("Alex Reyes"));

// ------------------------------------------------ 2. the resume after a crash
// Same fixture, same script, and the previous run's intent seeded in — the
// shape of a worker reclaimed between the click and the receipt, then handed
// the job back. The gate must refuse; nothing may go out.
const resumed = await run({ seed: intent });
check("a resumed run seeded with the intent dispatches NOTHING", resumed.effects === 0);
check("...because the at-most-once gate refused it as a duplicate",
  /BLOCKED DUPLICATE EFFECT/.test(resumed.trace));

// ------------------------------------------------ 3. the control
// Same fixture, same script, NO seed. If this also dispatched nothing, case 2
// would be proving the fixture, not the seeding.
const control = await run({ seed: null });
check("an unseeded run of the identical fixture still dispatches once — so the seed is what stopped case 2",
  control.effects === 1);

if (failures) { console.log(`test_effect_intent_survives_crash: ${failures} FAILED`); process.exit(1); }
console.log("test_effect_intent_survives_crash: all passed");
