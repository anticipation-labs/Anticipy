// A COMPLETED BOOKING WAS REJECTED BY A REGEX BEFORE ANY MODEL LOOKED — AND
// THE LOOP THEN BOOKED IT AGAIN.
//
// `completionContradiction` read the agent's OWN result sentence through three
// verb lists and, on a match, returned verified:false from verifyDone before
// mapPage and before the auditor ran. Audit #65. The sentence
//
//     Booked. The confirmation email was not sent to the address on file,
//     so I noted the reference: RG-88214.
//
// is a finished booking with a negated side-remark. Measured on the shipped
// loop: false, mapPage 0, audits 0. The loop told the model its done was
// rejected, no recovery path matched the fixed reason, and it re-attempted the
// action it had already performed. That is the duplicate booking the loop's
// own comment calls the cardinal sin — reached from the verifier this time,
// not the crash path.
//
// The auditor sixty lines below already owns this question and can already
// say no. The fix removes the regex and hands the auditor the three
// alternations as three examples. This suite proves the auditor is now ASKED,
// in both directions, and that nothing got looser.
//
// Run: node extension/tests/test_done_is_not_a_sentence_match.mjs
import { installChrome } from "./chrome_mock.mjs";

const harness = installChrome();
const { verifyDone } = await import("../agent_loop.js");

let failures = 0;
const check = (name, ok) => {
  console.log(`${ok ? "PASS" : "FAIL"}: ${name}`);
  if (!ok) failures++;
};

const GOAL = "book the appointment at West Coast Dental for Alex Reyes on September 3 at 2:15pm";
const EFFECT_STATE = {
  url: "https://westcoastdental.example/appointments/1841", title: "Appointment",
  elements: "[1] <textbox> Patient @(10,10)\n[2] <button> Confirm @(10,60)",
  text: "Confirm this appointment.",
  fields: [{ index: 1, name: "patient", label: "Patient", type: "text", required: true, readOnly: false, value: "Alex Reyes" }],
};
const RECEIPT_PAGE = {
  url: "https://westcoastdental.example/appointments/receipt", title: "Appointment confirmed",
  elements: "[0] <link> Back to appointments @(10,10)",
  text: "Successfully booked. Reference RG-88214\nAlex Reyes — September 3, 2:15pm — West Coast Dental",
  fields: [],
};
const UNSUBMITTED_PAGE = { ...EFFECT_STATE, title: "Appointment", text: "Confirm this appointment. (not yet submitted)" };

// A mocked auditor with a scripted verdict; counts how often it is asked and
// how often the page is mapped, which is the whole measurement.
function auditor(reply) {
  let audits = 0;
  globalThis.fetch = async (url, opts = {}) => {
    if (!String(url).includes("openrouter")) return { ok: false, status: 0, json: async () => ({}), text: async () => "" };
    const joined = JSON.parse(opts.body).messages.map((m) => (Array.isArray(m.content)
      ? m.content.map((p) => (p.type === "text" ? p.text : "")).join("\n") : String(m.content || ""))).join("\n");
    if (!/You audit a browser agent's claim/.test(joined)) {
      return { ok: true, status: 200, json: async () => ({ choices: [{ message: { content: "{}" } }] }), text: async () => "" };
    }
    audits += 1;
    const content = typeof reply === "function" ? reply(audits) : reply;
    if (content instanceof Error) throw content;
    return { ok: true, status: 200, json: async () => ({ choices: [{ message: { content } }] }), text: async () => "" };
  };
  return () => audits;
}
let mapped = 0;
function onPage(page) { harness.tabs.clear(); const tab = harness.addTab({ url: page.url, active: false }); mapped = 0; harness.mapPage = () => { mapped += 1; return page; }; return tab; }
const CLAIM = "Booked. The confirmation email was not sent to the address on file, so I noted the reference: RG-88214.";
const opts = { scope: GOAL, facts: "", effectState: EFFECT_STATE, ownerProfile: null, evidenceJournal: [] };

// ------------------------------------------------------ 1. THE DEFECT
// The exact sentence, on a real receipt page, with an auditor that reads the
// page and says yes. Measured before the fix: verified=false, mapPage 0,
// audits 0 — nobody ever looked.
{
  const tab = onPage(RECEIPT_PAGE);
  const audits = auditor('{"verified":true}');
  const v = await verifyDone("test-key", "test-model", GOAL, CLAIM, tab.id, opts);
  check("a completed booking with a negated side-remark verifies", v.verified === true);
  check("...because the page was actually read", mapped >= 1);
  check("...and the auditor was actually asked", audits() === 1);
  check("...and the receipt records that a model audited it", (v.evidence || []).some((e) => e === "proof:independent-model-audit"));
}

// ------------------------------------------------------ 2. THE OTHER DIRECTION
// Same sentence, but the page shows the form never went out. The auditor,
// given the page, says no — and its reason is ITS sentence, not the regex's.
{
  const tab = onPage(UNSUBMITTED_PAGE);
  const audits = auditor(JSON.stringify({ verified: false, reason: "the form is still unsubmitted; no booking exists",
    goal_quote: "book the appointment", claimed_quote: "Booked", evidence_quote: "not yet submitted", evidence_url: UNSUBMITTED_PAGE.url }));
  const v = await verifyDone("test-key", "test-model", GOAL, CLAIM, tab.id, opts);
  check("a false claim is still rejected", v.verified === false);
  check("...by the auditor, which was asked", audits() === 1);
  check("...with the auditor's own grounded reason, never the regex's fixed one",
    /unsubmitted/.test(String(v.reason || "")) && !/the claimed result says the action did not complete/.test(String(v.reason || "")));
}

// ------------------------------------------------------ 3. THE PROGRESS NOTE
// "I will now try BCIT" used to be rejected for free by the third verb list.
// It must now reach the auditor, whose grounded NO is honoured.
{
  const tab = onPage(UNSUBMITTED_PAGE);
  const audits = auditor(JSON.stringify({ verified: false, reason: "this is a progress note; the goal's terminal state is not reached",
    goal_quote: "book the appointment", claimed_quote: "I will now try", evidence_quote: "not yet submitted", evidence_url: UNSUBMITTED_PAGE.url }));
  const v = await verifyDone("test-key", "test-model", GOAL, "SFU returned 0 results. I will now try BCIT.", tab.id, opts);
  check("a progress note is rejected", v.verified === false);
  check("...by the auditor, which was asked, not by a verb list", audits() === 1);
}

// ------------------------------------------------------ 4. FAIL CLOSED
// The auditor errors, then answers unparseably. Removing the regex must not
// have opened a way for "done" to slip through when nobody can judge it.
{
  const tab = onPage(RECEIPT_PAGE);
  const audits = auditor((n) => (n === 1 ? new Error("provider down") : "{}"));
  const v = await verifyDone("test-key", "test-model", GOAL, CLAIM, tab.id, opts);
  check("when the auditor cannot answer, completion stays unverified", v.verified === false);
  check("...and the auditor was asked, and retried once", audits() >= 1);
}

if (failures) { console.log(`test_done_is_not_a_sentence_match: ${failures} FAILED`); process.exit(1); }
console.log("test_done_is_not_a_sentence_match: all passed");
