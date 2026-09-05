// A CANCELLATION VERIFIED A BOOKING AS DONE, AND NO MODEL EVER LOOKED.
//
// `verifyDone` (agent_loop.js:1773) is the last thing standing between a model
// saying "done" and the owner being told his table is booked. Four guards run
// in front of it and every one of them is fail-CLOSED: `completionShapeGap`,
// `completionEvidenceGap`, `officialRecordEvidenceGap` and
// `unsupportedApprovedFacts` can each return "no" and none of them can return
// "yes". (A fifth, `completionContradiction`, was here until 2026-09-05 —
// see test_done_is_not_a_sentence_match.mjs for why it went.)
//
// One thing in that function could return YES: `terminalReceiptEvidence`, two
// regexes over the live page's prose. When it matched and `effectState` was
// set, verifyDone returned `{verified:true}` and RETURNED — the model audit
// below it never ran. A regex was deciding that a task was finished, which is
// HARNESS-LAWS.md law 1, and it is not one of law 1's three exemptions: it is
// not a sense, not a seatbelt (it reads what the page SAYS, not what a plan
// TOUCHES), and not a gate.
//
// The failure, reproduced below verbatim. `success` matches
// booked|scheduled|registered AND cancelled|canceled out of the same
// alternation, and NOTHING in verifyDone compares the matched verb against the
// goal. So for the goal "book the appointment", a page reading
//
//     Successfully cancelled. Confirmation number: ABC-10023
//
// matched `success` and matched `receipt`, and the run reported the
// appointment booked. The approved facts (the patient, the date, the time) all
// appear on a cancellation receipt for that same appointment, so the one guard
// that could have caught it had no reason to fire.
//
// THE FIX IS NOT DELETING `cancelled` FROM THE LIST. That closes the instance
// and leaves the class: `renewed` against "cancel my subscription", `updated`
// against "delete the listing". The class is a lexical match trusted to answer
// a question about meaning, and the fix is to stop trusting it with the
// verdict — the observation now rides into the auditor's prompt as a signal
// and the model returns the answer.
//
// Run: node extension/tests/test_done_is_not_a_word_match.mjs
import { installChrome } from "./chrome_mock.mjs";

const harness = installChrome();
const { verifyDone, terminalReceiptEvidence } = await import("../agent_loop.js");

let failures = 0;
const check = (name, ok) => {
  console.log(`${ok ? "PASS" : "FAIL"}: ${name}`);
  if (!ok) failures++;
};

const GOAL = "book the appointment at West Coast Dental for Alex Reyes on September 3 at 2:15pm";
const SCOPE = "book the appointment at West Coast Dental for Alex Reyes on September 3 at 2:15pm";

// The page the browser is standing on when the model claims success. Every
// word of it is true; none of it is a booking.
const CANCELLED_PAGE = {
  url: "https://westcoastdental.example/appointments/receipt",
  title: "Appointment cancelled",
  elements: "[0] <link> Back to appointments @(10,10)",
  text: "Successfully cancelled. Confirmation number: ABC-10023\n"
    + "Alex Reyes — September 3, 2:15pm — West Coast Dental",
  fields: [],
};

// The form as it stood immediately before the button was pressed. These are
// the values `unsupportedScopeFields` and `unsupportedApprovedFacts` check,
// and they are all genuinely the owner's — which is the point: this errand
// looks correct right up until the verb.
const EFFECT_STATE = {
  url: "https://westcoastdental.example/appointments/1841",
  title: "Appointment",
  elements: "[1] <textbox> Patient @(10,10)\n[2] <button> Confirm @(10,60)",
  text: "Confirm this appointment.",
  fields: [
    { index: 1, name: "patient", label: "Patient", type: "text",
      required: true, readOnly: false, value: "Alex Reyes" },
  ],
};

check("the fixture really does trip the lexical match (or this suite tests nothing)",
  terminalReceiptEvidence(CANCELLED_PAGE) === true);

harness.tabs.clear();
const tab = harness.addTab({ url: CANCELLED_PAGE.url, active: false });
harness.mapPage = () => CANCELLED_PAGE;

// A competent auditor, given the goal and this page, rejects it. The whole
// question is whether it is ASKED.
let audits = 0;
let sawTerminalSignal = false;
globalThis.fetch = async (url, opts = {}) => {
  if (!String(url).includes("openrouter")) {
    return { ok: false, status: 0, json: async () => ({}), text: async () => "" };
  }
  const body = JSON.parse(opts.body);
  const all = body.messages.map((m) => (Array.isArray(m.content)
    ? m.content.map((p) => (p.type === "text" ? p.text : "")).join("\n")
    : String(m.content || "")));
  const joined = all.join("\n");
  if (!/You audit a browser agent's claim/.test(joined)) {
    return { ok: true, status: 200,
      json: async () => ({ choices: [{ message: { content: "{}" } }] }), text: async () => "" };
  }
  audits += 1;
  sawTerminalSignal = /receipt-shaped/i.test(joined);
  const content = JSON.stringify({
    verified: false,
    reason: "the page confirms a cancellation, and the goal was to book",
    goal_quote: "book the appointment",
    claimed_quote: "Booked",
    evidence_quote: "Successfully cancelled",
    evidence_url: CANCELLED_PAGE.url,
  });
  return { ok: true, status: 200,
    json: async () => ({ choices: [{ message: { content } }] }), text: async () => "" };
};

const verdict = await verifyDone("test-key", "test-model", GOAL,
  "Booked. Confirmation number ABC-10023.", tab.id,
  { scope: SCOPE, facts: "", effectState: EFFECT_STATE, ownerProfile: null,
    evidenceJournal: [] });

check("a cancellation does NOT verify a booking as done", verdict.verified === false);
check("...and the model was actually asked — the verdict is not a regex's",
  audits === 1);
check("...and it was given the mechanical observation as a signal, not asked to rediscover it",
  sawTerminalSignal === true);
check("the rejection says what is actually wrong",
  /cancel/i.test(String(verdict.reason || "")));

// The other direction, so the fix is not "reject everything". A real booking
// receipt, same shape, must still verify — through the model.
{
  const BOOKED_PAGE = {
    ...CANCELLED_PAGE,
    title: "Appointment confirmed",
    text: "Successfully booked. Confirmation number: ABC-10023\n"
      + "Alex Reyes — September 3, 2:15pm — West Coast Dental",
  };
  harness.mapPage = () => BOOKED_PAGE;
  let asked = 0;
  globalThis.fetch = async (url, opts = {}) => {
    if (!String(url).includes("openrouter")) {
      return { ok: false, status: 0, json: async () => ({}), text: async () => "" };
    }
    const joined = JSON.parse(opts.body).messages
      .map((m) => (Array.isArray(m.content)
        ? m.content.map((p) => (p.type === "text" ? p.text : "")).join("\n")
        : String(m.content || ""))).join("\n");
    if (!/You audit a browser agent's claim/.test(joined)) {
      return { ok: true, status: 200,
        json: async () => ({ choices: [{ message: { content: "{}" } }] }), text: async () => "" };
    }
    asked += 1;
    return { ok: true, status: 200,
      json: async () => ({ choices: [{ message: { content: '{"verified":true}' } }] }),
      text: async () => "" };
  };
  const good = await verifyDone("test-key", "test-model", GOAL,
    "Booked. Confirmation number ABC-10023.", tab.id,
    { scope: SCOPE, facts: "", effectState: EFFECT_STATE, ownerProfile: null,
      evidenceJournal: [] });
  check("a genuine booking receipt still verifies", good.verified === true);
  check("...through the model, which is the only thing that can tell them apart",
    asked === 1);
  check("...and the receipt records that a model audited it",
    (good.evidence || []).some((e) => e === "proof:independent-model-audit"));
}

// The class, not the instance. Same shape, a verb nobody thought to delete.
{
  const RENEWED_PAGE = {
    ...CANCELLED_PAGE,
    title: "Subscription renewed",
    text: "Successfully renewed. Reference number: RN-88120\nAlex Reyes — West Coast Dental",
  };
  harness.mapPage = () => RENEWED_PAGE;
  let asked = 0;
  globalThis.fetch = async (url, opts = {}) => {
    if (!String(url).includes("openrouter")) {
      return { ok: false, status: 0, json: async () => ({}), text: async () => "" };
    }
    const joined = JSON.parse(opts.body).messages
      .map((m) => (Array.isArray(m.content)
        ? m.content.map((p) => (p.type === "text" ? p.text : "")).join("\n")
        : String(m.content || ""))).join("\n");
    if (!/You audit a browser agent's claim/.test(joined)) {
      return { ok: true, status: 200,
        json: async () => ({ choices: [{ message: { content: "{}" } }] }), text: async () => "" };
    }
    asked += 1;
    return { ok: true, status: 200,
      json: async () => ({ choices: [{ message: { content: JSON.stringify({
        verified: false, reason: "the page confirms a renewal, and the goal was to cancel",
        goal_quote: "cancel my subscription", claimed_quote: "Cancelled",
        evidence_quote: "Successfully renewed", evidence_url: RENEWED_PAGE.url,
      }) } }] }), text: async () => "" };
  };
  // Its OWN pre-effect state. Reusing the dental one put "Alex Reyes" in a
  // form whose approved scope is "cancel my subscription", and
  // unsupportedScopeFields rejected the run three guards earlier — correctly,
  // and for a reason that has nothing to do with what this leg is about.
  const SUB_EFFECT_STATE = {
    url: "https://westcoastdental.example/account/subscription",
    title: "Subscription", elements: "[1] <button> Confirm @(10,60)",
    text: "Confirm.", fields: [],
  };
  const out = await verifyDone("test-key", "test-model", "cancel my subscription",
    "Cancelled. Reference RN-88120.", tab.id,
    { scope: "cancel my subscription", facts: "", effectState: SUB_EFFECT_STATE,
      ownerProfile: null, evidenceJournal: [] });
  check("a RENEWAL does not verify a cancellation either — the class is closed",
    out.verified === false && asked === 1);
}

console.log(failures === 0
  ? "test_done_is_not_a_word_match: a completion verdict is a model's, never a word list's"
  : `test_done_is_not_a_word_match: ${failures} FAILED`);
process.exit(failures === 0 ? 0 : 1);
