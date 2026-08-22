// A REJECTED SUBMISSION IS NOT A SPENT ONE.
//
// 306 live browser-agent runs (102 tasks x 3 passes, 2026-08-21) put the `form`
// family dead last:
//
//   BY FAMILY   form  43.6%  17/39   median done 2m46s   median decisions 7
//               (next worst: work_ops 56.3%; best: lookup 87.2%)
//
// Every loss was the same shape — `needs_user` on a task whose expect.status is
// ["done"]. ext-b-permit-riverside-commit passed 1 of 3, form-permit-file 1 of
// 3, both "ended needs_user, task allows done".
//
// The fixture makes the reason unavoidable. proof/fixtures/server.mjs serves
// /forms/permit as three steps behind ONE URL, and the two obstacles are
// deliberate. Driven with curl exactly as the agent drives it:
//
//   POST step=2&...&zone=B          -> 422 "You must confirm the details are accurate."
//   POST step=2&...&zone=B&declare=yes -> 200 "Step 3 of 3: confirm"
//
// The 422 re-renders step 2 at the SAME url, from the SAME <form
// action="/forms/permit">, with the SAME unnamed, id-less <button>Review</button>
// at the SAME element index — the only thing the error page adds is a
// <p class="err">, which page_map.js never indexes because it is not
// interactive. So after the server refuses, the agent ticks the box and presses
// Review again, and the loop recognised that second press as a REPEAT:
//
//   * actionCounts is keyed ["click", index, ""] and only reset when the URL
//     changes, which on this wizard it never does;
//   * externalSig is url|click|tag|label|action|name|id|index, every component
//     of which survives a 422 unchanged.
//
// Both then called deadIdx.add(index), which deletes the button from every
// later element map. Correcting the value could not help: there was nothing
// left to press. Hand-back was the only exit.
//
// The repair is the same principle the double-booking fix already established
// one function away — CONTENT is what separates a repeat from the next attempt.
// Nothing here loosens the at-most-once guard: case 2 is the measurement.
//
// Run: node extension/tests/test_form_retry_after_rejection.mjs
import { installChrome } from "./chrome_mock.mjs";

const harness = installChrome();
// screenshot() reads anything under 4000 chars as a blank frame, and this run
// earns a vision step (the loop gives itself eyes after a step that got
// nowhere), so the fixture must hand back something believable.
const FAKE_JPEG = Buffer.from("x".repeat(9000)).toString("base64");
// Imported AFTER installChrome(): config.js reads chrome.storage at evaluation.
const { runAgentGoal } = await import("../agent_loop.js");

let failures = 0;
const check = (name, ok) => {
  console.log(`${ok ? "PASS" : "FAIL"}: ${name}`);
  if (!ok) failures++;
};

// --------------------------------------------------------------- the fixture
// /forms/permit, reproduced from proof/fixtures/server.mjs: the same three
// steps, the same one URL, the same seeded-invalid email, the same required
// checkbox, and — the part that matters — the same element indexes on step 1
// and step 2, because both pages are three visible controls above one submit
// button. Step 3 carries its answers in hidden inputs, which page_map.js does
// not index, so its button owns NO editable field at all.
const URL_PERMIT = "https://fixture.council/forms/permit";
const SEEDED_EMAIL = "alex.fixture@localhost";
const EMAIL_RE = /^[^@\s]+@[^@\s.]+\.[^@\s]+$/;
const REFERENCE = "PRM-4417";

// The owner's words, and every value that reaches a field is in them: this
// suite is about the repeat guards, not about the scope auditor.
const GOAL = "file the parking permit as Jose Cruz, email jose@example.com,"
  + " vehicle 7XKD221, at 18 Kestrel Row in Zone B";

let form;        // what the server currently holds
let stepNo;      // 1, 2, 3 or 4 (the receipt)
let errorText;   // the inline 422 message, "" when the last POST was accepted
let permits;     // the fixture's state.permits
let page;        // what mapPage hands the loop
let controls;    // controlContext / commitControl answers, by element index

function render() {
  if (stepNo === 1) {
    page = {
      url: URL_PERMIT,
      title: "Parking permit",
      elements: "[1] <textbox> Full name @(10,10)\n"
        + "[2] <textbox> Email address @(10,40)\n"
        + "[3] <textbox> Vehicle registration @(10,70)\n"
        + "[4] <button> Continue @(10,100)",
      text: `Residential parking permit. Step 1 of 3: applicant.${errorText}`,
      fields: [
        { index: 1, name: "name", label: "Full name", type: "text",
          required: false, readOnly: false, value: form.name },
        { index: 2, name: "email", label: "Email address", type: "text",
          required: false, readOnly: false, value: form.email },
        { index: 3, name: "vehicle", label: "Vehicle registration", type: "text",
          required: false, readOnly: false, value: form.vehicle },
      ],
    };
    // "Continue" is reversible by externalControlSemantics, so step 1 never
    // reaches a commit gate. It is here because it is what makes the indexes
    // on step 2 a re-run of indexes already spent.
    controls = { 4: { commit: false, label: "Continue", tag: "button", name: "",
                      elementId: "", formAction: URL_PERMIT, fieldIndexes: [1, 2, 3] } };
    return;
  }
  if (stepNo === 2) {
    page = {
      url: URL_PERMIT,
      title: "Parking permit",
      elements: "[1] <textbox> Street address @(10,10)\n"
        + "[2] <combobox> Parking zone @(10,40)\n"
        + "[3] <checkbox> I confirm the details above are accurate @(10,70)\n"
        + "[4] <button> Review @(10,100)",
      text: `Residential parking permit. Step 2 of 3: address and declaration.${errorText}`,
      fields: [
        { index: 1, name: "address", label: "Street address", type: "text",
          required: false, readOnly: false, value: form.address },
        { index: 2, name: "zone", label: "Parking zone", type: "select-one",
          required: false, readOnly: false, value: form.zone },
        { index: 3, name: "declare", label: "I confirm the details above are accurate",
          type: "checkbox", required: false, readOnly: false, value: form.declare },
      ],
    };
    // Same index, same form action, same page as step 1's Continue — and
    // <button type="submit">Review</button> IS consequential (explicitSubmit),
    // so this is the first control the commit gates ever see.
    controls = { 4: { commit: true, label: "Review", tag: "button", name: "",
                      elementId: "", formAction: URL_PERMIT, fieldIndexes: [1, 2, 3] } };
    return;
  }
  if (stepNo === 3) {
    page = {
      url: URL_PERMIT,
      title: "Parking permit",
      elements: "[1] <button> Confirm and submit @(10,10)",
      text: `Residential parking permit. Step 3 of 3: confirm.`
        + ` Name ${form.name}. Email ${form.email}. Vehicle ${form.vehicle}.`
        + ` Address ${form.address}. Zone ${form.zone}.`
        + " Nothing is submitted until you confirm.",
      // Every answer travels in a hidden input, and page_map.js indexes none of
      // them: this button owns no editable field, so submissionDigest abstains
      // and the per-control guard is the ONLY thing standing between the owner
      // and two permits. Case 2 leans on exactly that.
      fields: [],
    };
    controls = { 1: { commit: true, label: "Confirm and submit", tag: "button",
                      name: "", elementId: "", formAction: URL_PERMIT,
                      fieldIndexes: [] } };
    return;
  }
  page = {
    url: URL_PERMIT,
    title: "Application submitted",
    elements: "",
    text: `Application submitted. Your reference is ${REFERENCE}.`
      + ` The permit for ${form.vehicle} in zone ${form.zone} starts on Mon 9 Mar 2026.`
      + ` A copy has been sent to ${form.email}.`,
    fields: [],
  };
  controls = {};
}

// The server's own rules, transcribed from proof/fixtures/server.mjs. A POST is
// what a click on the current step's submit button means.
function post() {
  if (stepNo === 1) {
    if (!EMAIL_RE.test(form.email)) {
      errorText = " Please correct 1 field(s) below. Enter an email address like name@example.com";
      return;
    }
    errorText = ""; stepNo = 2; return;
  }
  if (stepNo === 2) {
    if (form.declare !== true) {
      errorText = " Please correct 1 field(s) below. You must confirm the details are accurate.";
      return;
    }
    errorText = ""; stepNo = 3; return;
  }
  if (stepNo === 3) {
    permits.push({ reference: REFERENCE, ...form });
    errorText = ""; stepNo = 4;
  }
}

// The window the at-most-once guard exists for: a server that has TAKEN the
// final submission but has not painted the receipt yet, so the page still
// shows the confirm button and pressing it again looks like the sensible
// thing to do. Case 2 opens it deliberately; case 1 leaves it shut.
let confirmIsSlow = false;
let receiptDelay = 0;

function reset() {
  harness.tabs.clear();
  harness.focusGrants.length = 0;
  harness.onInject = null;
  for (const key of Object.keys(harness.storageData)) delete harness.storageData[key];
  form = { name: "", email: SEEDED_EMAIL, vehicle: "", address: "", zone: "", declare: false };
  stepNo = 1; errorText = ""; permits = []; receiptDelay = 0;
  render();
  harness.mapPage = () => {
    if (receiptDelay > 0 && --receiptDelay === 0) render();
    return page;
  };
  harness.addTab({ url: URL_PERMIT, active: true });
}

// ------------------------------------------------------------- the page, live
// controlContext, commitControl, inputMeta and the select/checkbox setter are
// all injected page functions; the mock's `onInject` hook cannot tell them
// apart by index because the index arrives in `args`, not in the source. Wrap
// the API so one fixture can answer for whichever element was asked about.
const realExecuteScript = chrome.scripting.executeScript;
let lastCenterIndex = null;   // which element trustedClick is about to hit
let typingIndex = null;       // which field trustedType is filling
const fieldAt = (index) => (page.fields || []).find((f) => f.index === Number(index));
const setField = (index, value) => {
  const field = fieldAt(index);
  if (!field) return;
  field.value = value;
  form[field.name] = value;
};

chrome.scripting.executeScript = async (opts) => {
  const src = opts?.func ? String(opts.func) : "";
  const index = Array.isArray(opts?.args) ? Number(opts.args[0]) : null;
  if (src.includes("navigationLink")) {                 // commitControl
    return [{ frameId: 0, result: !!controls[index]?.commit }];
  }
  if (src.includes("fieldsIn")) {                       // controlContext
    const c = controls[index];
    if (!c) return [{ frameId: 0, result: null }];
    return [{ frameId: 0, result: {
      label: c.label, tag: c.tag, href: "", nearbyText: c.label,
      formAction: c.formAction, name: c.name || "", elementId: c.elementId || "",
      fieldIndexes: c.fieldIndexes,
    } }];
  }
  if (src.includes("el.labels")) {                      // inputMeta
    const field = fieldAt(index);
    return [{ frameId: 0, result: field
      ? { type: field.type, autocomplete: "", attrs: `${field.name} ${field.label}` }
      : {} }];
  }
  if (src.includes("role: String(el.getAttribute")) {   // select's target probe
    const field = fieldAt(index);
    if (!field) return [{ frameId: 0, result: {} }];
    return [{ frameId: 0, result: {
      tag: field.type === "select-one" ? "SELECT" : "INPUT", type: field.type, role: "" } }];
  }
  if (src.includes("not a dropdown or input")) {        // the select/checkbox setter
    const field = fieldAt(index);
    const want = String(opts.args[1] ?? "");
    if (!field) return [{ frameId: 0, result: "element not found" }];
    if (field.type === "checkbox") {
      setField(index, !/^(false|no|off|0|uncheck\w*)$/i.test(want.trim()));
      return [{ frameId: 0, result: `${field.value ? "checked" : "unchecked"} the box` }];
    }
    setField(index, want.trim());
    return [{ frameId: 0, result: `selected "${field.value}"` }];
  }
  if (src.includes("__anticipyClear")) {                // trustedType clears first
    typingIndex = index;
    setField(index, "");
    return [{ frameId: 0, result: true }];
  }
  if (src.includes("__anticipyCenter")) {
    lastCenterIndex = index;
    return [{ frameId: 0, result: { x: 5, y: 5 } }];
  }
  return realExecuteScript(opts);
};

// Typing is per-character CDP, and a click is a mouse event with no index on
// it — so the index recorded by the calls immediately above is what tells the
// fixture which control was operated.
harness.onCdp = (tabId, method, params) => {
  if (method === "Page.captureScreenshot") return { data: FAKE_JPEG };
  if (method === "Input.dispatchKeyEvent" && params?.type === "char"
      && typingIndex != null && params.text && params.text !== "\r") {
    const field = fieldAt(typingIndex);
    if (field) setField(typingIndex, String(field.value ?? "") + params.text);
  }
  if (method === "Input.dispatchMouseEvent" && params?.type === "mouseReleased") {
    const index = lastCenterIndex;
    // Only the current step's submit button posts anything; a click on a
    // control this page does not have is what the real server sees as nothing
    // at all, and it must not silently advance the wizard.
    if (!controls[index]) return undefined;
    const wasFinalStep = stepNo === 3;
    if ((stepNo <= 2 && index === 4) || (wasFinalStep && index === 1)) {
      post();
      // Taken, but not yet shown: the next page read still offers the confirm
      // button, and only the read after that carries the reference.
      if (wasFinalStep && confirmIsSlow) { receiptDelay = 2; return undefined; }
    }
    render();
  }
  return undefined;
};

// A model answering from a queue. The pre-submit form auditor is answered
// separately so it never eats a scripted step ("no corrections" is honest: the
// values come verbatim from the goal). The completion verifier is NOT a
// rubber stamp — it reads the live page, so a run that claims a reference it
// never obtained cannot pass by asserting it did.
function scripted(actions) {
  const queue = [...actions];
  globalThis.fetch = async (url, opts = {}) => {
    if (!String(url).includes("openrouter")) {
      return { ok: false, status: 0, json: async () => ({}), text: async () => "" };
    }
    const body = JSON.parse(opts.body);
    const joined = body.messages.map((m) => (Array.isArray(m.content)
      ? m.content.map((p) => (p.type === "text" ? p.text : "[image]")).join("\n")
      : String(m.content || ""))).join("\n");
    let content;
    if (/pre-submit form auditor/.test(joined)) content = JSON.stringify({ values: [] });
    else if (/You audit a browser agent's claim/.test(joined)) {
      content = JSON.stringify(page.text.includes(REFERENCE)
        ? { verified: true, evidence: [`the page reads "Your reference is ${REFERENCE}"`] }
        : { verified: false, reason: "the live page shows no reference", evidence: [] });
    } else if (/reading the open web to learn HOW/.test(joined)) content = JSON.stringify({ steps: [] });
    else if (/You plan a task/.test(joined)) content = JSON.stringify({ steps: [] });
    else content = JSON.stringify(queue.shift() || { action: "wait" });
    return { ok: true, status: 200,
      json: async () => ({ choices: [{ message: { content } }] }), text: async () => "" };
  };
}

const run = (actions, maxSteps = 26) => {
  scripted(actions);
  let effects = 0;
  return runAgentGoal(GOAL, {
    apiKey: "test-key", scope: GOAL, authorized: true, planning: false,
    maxSteps, startUrl: URL_PERMIT, stillLive: async () => true,
    onTrace: process.env.TRACE ? async (h, fin) => { if (fin) console.log(h.join("\n")); } : null,
    onBeforeExternalEffect: async () => { effects += 1; },
  }).then((out) => ({ out, effectCount: () => effects }));
};

// ------------------------------------------- 1. the 422 the fixture guarantees
// The whole permit, driven the way the live traces drive it. The only unusual
// step is the ninth: press Review a second time, after the declaration box has
// been ticked, on a page whose URL, form action, button and element index are
// all exactly what they were when the server refused.
{
  reset();
  confirmIsSlow = false;
  const { out, effectCount } = await run([
    { action: "type", index: 1, text: "Jose Cruz" },
    // The seeded address is overwritten, never resubmitted.
    { action: "type", index: 2, text: "jose@example.com" },
    { action: "type", index: 3, text: "7XKD221" },
    { action: "click", index: 4 },                       // step 1 -> step 2
    { action: "type", index: 1, text: "18 Kestrel Row" },
    { action: "select", index: 2, option: "Zone B" },
    { action: "click", index: 4 },                       // declaration unticked -> 422
    { action: "select", index: 3, option: "yes" },       // read the error, tick the box
    { action: "click", index: 4 },                       // the corrected resend
    { action: "click", index: 1 },                       // step 3 -> filed
    { action: "done", result: `Permit filed, reference ${REFERENCE}` },
  ]);

  check("the permit was actually filed with the fixture",
    permits.length === 1 && permits[0].reference === REFERENCE);
  check("a form the server rejected is corrected and carried to completion, not handed back",
    !!out && out.status === "done");
  check("the corrected email went out, not the seeded one",
    permits[0]?.email === "jose@example.com");
  check("the declaration the 422 asked for was actually sent",
    permits[0]?.declare === true);
  // Two Review presses (the refused one and the corrected one) plus the final
  // confirm. The refused POST is a real external effect: it reached the server.
  check("every consequential press was dispatched exactly once", effectCount() === 3);
}

// ------------------------------------------------ 2. and the guard still holds
// The measurement that the fix above is not a licence to resend. Two presses
// this run must go nowhere: Review again with the declaration still untouched
// (identical payload), and a second Confirm and submit (a control that owns no
// editable field at all, so content cannot speak for it and the per-control
// signature is absolute).
{
  reset();
  // The receipt lags the submission by one page read, so the confirm button is
  // still on screen after the permit has already been filed.
  confirmIsSlow = true;
  const { out, effectCount } = await run([
    { action: "type", index: 1, text: "Jose Cruz" },
    { action: "type", index: 2, text: "jose@example.com" },
    { action: "type", index: 3, text: "7XKD221" },
    { action: "click", index: 4 },                       // step 1 -> step 2
    { action: "type", index: 1, text: "18 Kestrel Row" },
    { action: "select", index: 2, option: "Zone B" },
    { action: "click", index: 4 },                       // -> 422
    { action: "click", index: 4 },                       // NOTHING changed: must be blocked
    { action: "select", index: 3, option: "yes" },
    { action: "click", index: 4 },                       // now it may go
    { action: "click", index: 1 },                       // step 3 -> filed
    { action: "click", index: 1 },                       // still on step 3: must be blocked
    { action: "done", result: `Permit filed, reference ${REFERENCE}` },
  ]);

  check("a form the server rejected still reaches completion when the guard also fires",
    !!out && out.status === "done");
  check("one permit reached the fixture, not two", permits.length === 1);
  // Same three as case 1: the two extra presses were both blocked before
  // dispatch — one by content (an unchanged payload), one by the per-control
  // signature (a confirm button that owns no editable field at all).
  check("the repeat presses were blocked before dispatch", effectCount() === 3);
}

if (failures) {
  console.error(`test_form_retry_after_rejection: ${failures} failed`);
  process.exit(1);
}
console.log("test_form_retry_after_rejection: all passed");
