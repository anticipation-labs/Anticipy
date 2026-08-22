// ONE SUBMISSION MUST COST ONE COMMIT, WHICHEVER KEY SENDS IT.
//
// Live fixture run book-party-six, pass 3 of 3 (2026-08-22) recorded TWO
// identical bookings where passes 1 and 2 recorded one:
//
//   step 13: BLOCKED DUPLICATE EFFECT — this same consequential control was
//            already dispatched once ... never repeat it to make sure.
//   step 15: {"action":"type","index":1,"text":"Alex","enter":true}
//   step 16: {"action":"done","result":"Table booked Reference MB-8941 ..."}
//
// The at-most-once guard held for the CLICK and then Enter in a text field of
// the same form sent it again, because the two gates keyed on the CONTROL:
// url|click|tag|label|action|name|id|index versus url|enter|…. Five of the
// eight components differ between a submit button and a field inside its form,
// so performedExternalEffects never saw one effect.
//
// The naive repair — one key of url + form action — is measurably worse than
// the bug. Case 2 is that measurement: every step of the fixture's
// /forms/permit POSTs to /forms/permit, so a form-scoped key blocks the
// legitimate steps 2 and 3 and takes the whole form family to nothing.
//
// Run: node extension/tests/test_commit_once.mjs
import { installChrome } from "./chrome_mock.mjs";

const harness = installChrome();
// screenshot() treats anything under 4000 chars as a blank frame, so a vision
// step on a fixture page must be given something believable or it reads as the
// loop refusing to look.
const FAKE_JPEG = Buffer.from("x".repeat(9000)).toString("base64");
// Imported AFTER installChrome(): config.js reads chrome.storage at evaluation.
const { runAgentGoal } = await import("../agent_loop.js");

let failures = 0;
const check = (name, ok) => {
  console.log(`${ok ? "PASS" : "FAIL"}: ${name}`);
  if (!ok) failures++;
};

// The page fixture the whole suite reads from. Each case installs its own.
let page = null;
// controlContext / commitControl answers, by element index.
let controls = {};

const realExecuteScript = chrome.scripting.executeScript;
// controlContext and commitControl are injected page functions, and the mock's
// `onInject` hook cannot see which element they were asked about — the index
// arrives in `args`, not in the source. Wrap the API instead so one fixture can
// describe a button and the field inside its form as the different DOM objects
// they are; that difference is exactly what the per-control signatures key on,
// and therefore exactly what must NOT be enough to authorise a second send.
chrome.scripting.executeScript = async (opts) => {
  const src = opts?.func ? String(opts.func) : "";
  const index = Array.isArray(opts?.args) ? Number(opts.args[0]) : null;
  if (src.includes("navigationLink")) {               // commitControl
    return [{ frameId: 0, result: !!controls[index]?.commit }];
  }
  if (src.includes("fieldsIn")) {                     // controlContext
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
  harness.onCdp = (tabId, method) => (method === "Page.captureScreenshot"
    ? { data: FAKE_JPEG } : undefined);
  harness.onInject = null;
  for (const key of Object.keys(harness.storageData)) delete harness.storageData[key];
  harness.mapPage = () => page;
  harness.addTab({ url: "https://news.site/read", active: true });
}

// A model answering from a queue, with the pre-submit form auditor answered
// separately so it never eats a scripted step. "No corrections" is the honest
// answer for a fixture whose values already come verbatim from the scope.
function scripted(actions) {
  const queue = [...actions];
  const asked = [];
  globalThis.fetch = async (url, opts = {}) => {
    if (!String(url).includes("openrouter")) {
      return { ok: false, status: 0, json: async () => ({}), text: async () => "" };
    }
    const body = JSON.parse(opts.body);
    const all = body.messages.map((m) => (Array.isArray(m.content)
      ? m.content.map((p) => (p.type === "text" ? p.text : "[image]")).join("\n")
      : String(m.content || "")));
    const joined = all.join("\n");
    let kind = "step";
    if (/You plan a task/.test(joined)) kind = "plan";
    else if (/reading the open web to learn HOW/.test(joined)) kind = "learn";
    else if (/You audit a browser agent's claim/.test(joined)) kind = "verify";
    else if (/pre-submit form auditor/.test(joined)) kind = "form-audit";
    asked.push(kind);
    let content;
    if (kind === "form-audit") content = JSON.stringify({ values: [] });
    else if (kind === "verify") content = JSON.stringify({ verified: true, evidence: ["confirmed"] });
    else if (kind === "learn") content = JSON.stringify({ steps: [] });
    else content = JSON.stringify(queue.shift() || { action: "wait" });
    return { ok: true, status: 200,
      json: async () => ({ choices: [{ message: { content } }] }), text: async () => "" };
  };
  return asked;
}

// ---------------------------------------------------------------- 1. a repeat
// The booking. One form, one submit button, one name field. The button is
// clicked and the reservation goes out; the model then types the same name
// back into the same field and asks for Enter. Nothing about the form changed,
// so nothing new can be sent — and the run must dispatch exactly one effect.
{
  fresh();
  const GOAL = "book a table for 6 under the name Alex Reyes";
  page = {
    url: "https://fixture.test/book",
    title: "Reserve a table",
    elements: "[1] <textbox> Name @(10,10)\n"
      + "[2] <textbox> Party size @(10,40)\n"
      + "[3] <button> Book table @(10,70)",
    text: "Held for 4:32. Review your reservation and book the table.",
    fields: [
      { index: 1, name: "guest_name", label: "Name", type: "text",
        required: true, readOnly: false, value: "Alex Reyes" },
      { index: 2, name: "party_size", label: "Party size", type: "text",
        required: true, readOnly: false, value: "6" },
    ],
  };
  const form = { formAction: "https://fixture.test/book/submit", fieldIndexes: [1, 2] };
  controls = {
    // The submit button and the field inside its form: different tag,
    // different label, different name, different id, different index.
    3: { ...form, commit: true, label: "Book table", tag: "button",
         name: "", elementId: "book-table" },
    1: { ...form, commit: true, label: "Name", tag: "input",
         name: "guest_name", elementId: "guest-name" },
  };

  let effects = 0;
  scripted([
    // The reservation goes out here.
    { action: "click", index: 3 },
    // The same name back into the same field, with Enter: the exact walk-around
    // the fixture caught. Nothing about the submission changed.
    { action: "type", index: 1, text: "Alex Reyes", enter: true },
    { action: "done", result: "Table booked" },
  ]);
  const out = await runAgentGoal(GOAL, {
    apiKey: "test-key", scope: GOAL, authorized: true, planning: false,
    maxSteps: 6, startUrl: page.url, stillLive: async () => true,
    onBeforeExternalEffect: async () => { effects += 1; },
  });
  check("the booking run finished without erroring", !!out && !!out.status);
  check("a click then Enter on the SAME form with the SAME values commits once",
    effects === 1);
}

// ------------------------------------------------------- 2. a three-step form
// The permit wizard. Every step POSTs to the same /forms/permit and carries a
// different answer, which is the only thing that makes it a next step rather
// than a repeat. All three must go through: a form-scoped key would stop after
// the first and quietly delete the largest task family in the battery.
{
  fresh();
  const GOAL = "apply for the permit as Jose Cruz at 940 Howe Street for the third of September";
  const ACTION = "https://fixture.test/forms/permit";
  const steps = [
    { index: 3, field: { index: 1, name: "applicant", label: "Applicant", type: "text",
                         required: true, readOnly: false, value: "Jose Cruz" },
      label: "Save applicant", elementId: "save-applicant" },
    { index: 4, field: { index: 1, name: "address", label: "Address", type: "text",
                         required: true, readOnly: false, value: "940 Howe Street" },
      label: "Save address", elementId: "save-address" },
    { index: 5, field: { index: 1, name: "starts", label: "Start", type: "text",
                         required: true, readOnly: false, value: "third of September" },
      label: "File permit", elementId: "file-permit" },
  ];
  let at = 0;
  const install = () => {
    const s = steps[Math.min(at, steps.length - 1)];
    page = {
      // Same URL and same form action on every step: this is the shape that
      // makes page+action a wrong key, so the fixture must keep it.
      url: ACTION,
      title: "Permit application",
      elements: `[1] <textbox> ${s.field.label} @(10,10)\n`
        + `[${s.index}] <button> ${s.label} @(10,40)`,
      text: `Permit application, step ${Math.min(at, steps.length - 1) + 1} of 3.`,
      fields: [s.field],
    };
    controls = { [s.index]: { commit: true, label: s.label, tag: "button", name: "",
                              elementId: s.elementId, formAction: ACTION,
                              fieldIndexes: [1] } };
  };
  install();

  let effects = 0;
  scripted([
    { action: "click", index: 3 },
    { action: "click", index: 4 },
    { action: "click", index: 5 },
    { action: "done", result: "Permit filed" },
  ]);
  await runAgentGoal(GOAL, {
    apiKey: "test-key", scope: GOAL, authorized: true, planning: false,
    maxSteps: 8, startUrl: ACTION, stillLive: async () => true,
    onBeforeExternalEffect: async () => { effects += 1; at += 1; install(); },
  });
  check("a three-step wizard on one form action completes every step",
    effects === 3);
}

if (failures) { console.error(`test_commit_once: ${failures} failed`); process.exit(1); }
console.log("test_commit_once: all passed");
