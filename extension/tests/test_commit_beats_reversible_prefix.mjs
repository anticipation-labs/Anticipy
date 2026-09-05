// "CONTINUE AND PAY" WAS NOT A COMMIT, AND THAT SWITCHED THE SEATBELT OFF.
//
// F08. `commitControl` decides whether a click is capable of an external
// effect, and everything protective in the loop hangs off that one boolean:
// the read-only refusal, the `authorized` hand-back, the at-most-once
// externalSig/submissionKey guards, the pre-submit form auditors, the
// approved-facts floor, the intent journal. A `false` skips all of them.
//
// Inside it, `if (reversible.test(label)) return false;` ran BEFORE the commit
// test and before `explicitSubmit`. The regex is start-anchored with `(?:\b|\s)`
// after next|continue|back|previous, so ANY label beginning with one of those
// words was reversible whatever else it said. Measured on the shipped regexes
// with explicitSubmit true:
//
//     "Continue"           -> false      (correct: the exemption's real job)
//     "Continue and pay"   -> false      (wrong)
//     "Next: Place order"  -> false      (wrong)
//
// A consent dialog did the same thing from the other side: `cookieLike` reads
// 1200 characters of any enclosing dialog/aside, so a checkout modal that
// happens to carry the word "consent" made every button inside it a cookie
// button.
//
// Audit row #80 dispositions these lists as a LEGAL seatbelt — they read what
// a control DOES, HARNESS-LAWS law 1's second exemption — and that is not what
// this suite disputes. It disputes the PRECEDENCE, which nobody had examined:
// the reversible half could turn the seatbelt off.
//
// HOW THE COMMIT LEGS ARE MEASURED. `commitControl`'s body is a function
// injected into the page, so it cannot be imported. The mock below captures
// the REAL function the loop hands to chrome.scripting and runs it over a
// fixture element — the shipped bytes, not a restatement of them. A test that
// re-implemented the precedence would be green whatever the loop did.
//
// Run: node extension/tests/test_commit_beats_reversible_prefix.mjs
import { installChrome } from "./chrome_mock.mjs";

const harness = installChrome();
const FAKE_JPEG = Buffer.from("x".repeat(9000)).toString("base64");
const { runAgentGoal, externalControlSemantics } = await import("../agent_loop.js");
const { actionSignature } = await import("../recipes.js");

let failures = 0;
const check = (name, ok, detail = "") => {
  console.log(`${ok ? "PASS" : "FAIL"}: ${name}${ok || !detail ? "" : `  -> ${detail}`}`);
  if (!ok) failures++;
};

// ---------------------------------------------------------------------------
// A fixture control, shaped like the DOM element the injected function reads:
// a <button type=submit> inside a form, optionally inside a dialog whose prose
// the function is allowed to sample.
// ---------------------------------------------------------------------------
function fixtureElement({ label, tag = "BUTTON", type = "submit", dialogText = null }) {
  const form = {
    querySelector: () => null,
    querySelectorAll: () => [],
    getAttribute: () => null,
    action: "/checkout",
  };
  const dialog = dialogText == null ? null : {
    innerText: dialogText,
    querySelector: () => null,
    querySelectorAll: () => [],
  };
  const el = {
    innerText: label, value: "", type, name: "", id: "", placeholder: "", title: "",
    href: "", tagName: tag, form,
    getAttribute: () => null,
    closest: (sel) => {
      const s = String(sel);
      if (dialog && /\[role="dialog"\]|aria-modal|aside/.test(s)) return dialog;
      return null;
    },
  };
  return el;
}

// The REAL injected decision, captured off the wire the first time the loop
// asks for it, then callable directly.
let realCommitControl = null;
const realExecuteScript = chrome.scripting.executeScript;
let controls = {};          // fixture elements, by element index
chrome.scripting.executeScript = async (opts) => {
  const src = opts?.func ? String(opts.func) : "";
  const index = Array.isArray(opts?.args) ? Number(opts.args[0]) : null;
  if (src.includes("navigationLink")) {
    realCommitControl = opts.func;
    const el = controls[index];
    if (!el) return [{ frameId: 0, result: false }];
    globalThis.window = { __anticipyMap: { [index]: el } };
    return [{ frameId: 0, result: !!opts.func(index, !!opts.args[1]) }];
  }
  if (src.includes("fieldsIn")) {
    const el = controls[index];
    if (!el) return [{ frameId: 0, result: null }];
    return [{ frameId: 0, result: { label: el.innerText, tag: "button", href: "",
      nearbyText: el.innerText, formAction: "/checkout", name: "", elementId: "", fieldIndexes: [] } }];
  }
  return realExecuteScript(opts);
};

// Ask the captured real function about one fixture control.
function commitsAccordingToTheLoop(spec) {
  if (!realCommitControl) throw new Error("the loop's own commit test was never captured");
  const el = fixtureElement(spec);
  globalThis.window = { __anticipyMap: { 0: el } };
  return !!realCommitControl(0, false);
}

// ---------------------------------------------------------------------------
// (a) THE PURE TWIN, both directions. externalControlSemantics is the exported
//     half of the same rule; the fixtures are the measured cases.
// ---------------------------------------------------------------------------
const semantics = (label, over = {}) => externalControlSemantics({ label, explicitSubmit: true, ...over });
for (const [label, want, why] of [
  ["Continue and pay", true, "a payment named beside a reversible prefix"],
  ["Next: Place order", true, "an order named beside a reversible prefix"],
  ["Continue to checkout and purchase", true, "purchase, however far into the label"],
  ["Back and delete the booking", true, "a deletion behind a reversible prefix"],
  ["Continue", false, "a bare Continue is still the multi-step form's own button"],
  ["Next", false, "so is a bare Next"],
  ["Next step", false, "and a bare Next step"],
  ["Back", false, "and Back"],
  ["Search flights", false, "a search is still a search"],
]) {
  check(`(a) "${label}" is ${want ? "a commit" : "reversible"} — ${why}`,
    semantics(label) === want, String(semantics(label)));
}

// ---------------------------------------------------------------------------
// (b) NOTHING GOT LOOSER. The whole-label reversible forms are the entire
//     gesture and still win outright — "Apply filters" collides with
//     `\bapply\b` in the commit list and must NOT flip, or every faceted
//     search becomes an approval prompt.
// ---------------------------------------------------------------------------
for (const label of ["Apply filters", "Update search", "Apply search",
                     "See 3,631 results", "Show 12 results", "View 40 results",
                     "Cancel", "Close", "Dismiss"]) {
  check(`(b) "${label}" stays reversible`, semantics(label) === false, String(semantics(label)));
}
check("(b) ...while 'Cancel reservation' is still the commit it always was",
  semantics("Cancel reservation") === true);
check("(b) ...and the cookie/calendar/choice exemptions are untouched",
  externalControlSemantics({ label: "Accept all cookies", cookieLike: true }) === false
    && externalControlSemantics({ label: "Confirm choices", cookieLike: true }) === false
    && externalControlSemantics({ label: "17", explicitSubmit: true, calendarLike: true }) === false);

// ---------------------------------------------------------------------------
// (c) THE REPLAY SIDE. recipes.js carries a deliberate copy of the same
//     vocabulary and its comment says it must be the STRICTER of the two. A
//     step compiled as non-committing is one `nextStep` replays without
//     asking, so the same precedence has to hold there.
// ---------------------------------------------------------------------------
const sig = (label) => actionSignature({ action: "click", index: 3, label });
check("(c) a replayed 'Continue and pay' is marked a commit in its signature",
  sig("Continue and pay").startsWith("commit:"), sig("Continue and pay"));
check("(c) ...and 'Next: Place order' too",
  sig("Next: Place order").startsWith("commit:"), sig("Next: Place order"));
check("(c) ...while a bare 'Continue' is still replayable",
  !sig("Continue").startsWith("commit:"), sig("Continue"));
check("(c) ...and 'Apply filters' is still replayable",
  !sig("Apply filters").startsWith("commit:"), sig("Apply filters"));
check("(c) the two files agree on every fixture above",
  ["Continue and pay", "Next: Place order", "Cancel reservation", "Continue",
   "Apply filters", "See 3,631 results", "Cancel"]
    .every((label) => sig(label).startsWith("commit:") === externalControlSemantics({ label })));

// ---------------------------------------------------------------------------
// (d) THE BLAST RADIUS, THROUGH THE REAL LOOP. A read-only run must refuse to
//     press a button that pays. Before the fix commitControl said false, so
//     the read-only refusal never ran and the click went through.
// ---------------------------------------------------------------------------
const clicks = [];
const STEP_SENTINEL = /You are Anticipy's browser agent/;
const AUDIT_SENTINEL = /You audit a browser agent's claim/;

async function pressButton(label, { readOnly = true, dialogText = null } = {}) {
  harness.tabs.clear();
  harness.focusGrants.length = 0;
  clicks.length = 0;
  for (const key of Object.keys(harness.storageData)) delete harness.storageData[key];
  harness.addTab({ url: "https://shop.example/cart", active: true });
  const page = {
    url: "https://shop.example/cart",
    title: "Cart",
    elements: `[0] <button> ${label} @(10,10)`,
    text: `Your cart.${dialogText ? ` ${dialogText}` : ""}`,
    fields: [],
  };
  controls = { 0: fixtureElement({ label, dialogText }) };
  harness.mapPage = () => page;
  harness.onCdp = (tabId, method, params) => {
    if (method === "Page.captureScreenshot") return { data: FAKE_JPEG };
    if (method === "Input.dispatchMouseEvent" && params?.type === "mousePressed") clicks.push(label);
    return undefined;
  };
  const steps = [{ action: "click", index: 0 }, { action: "done", result: "pressed" }];
  let at = 0;
  const trace = [];
  globalThis.fetch = async (url, opts = {}) => {
    if (!String(url).includes("openrouter")) return { ok: false, status: 0, json: async () => ({}), text: async () => "" };
    const joined = JSON.parse(opts.body).messages.map((m) => (Array.isArray(m.content)
      ? m.content.map((p) => (p.type === "text" ? p.text : "")).join("\n") : String(m.content || ""))).join("\n");
    let content = "{}";
    if (AUDIT_SENTINEL.test(joined)) content = '{"verified":true}';
    else if (STEP_SENTINEL.test(joined)) content = JSON.stringify(steps[Math.min(at++, steps.length - 1)]);
    return { ok: true, status: 200, json: async () => ({ choices: [{ message: { content } }] }), text: async () => "" };
  };
  const out = await runAgentGoal("empty the cart", {
    apiKey: "test-key", scope: "empty the cart", readOnly, authorized: false, planning: false,
    startUrl: "https://shop.example/cart", maxSteps: 4, budgetMs: 60_000,
    stillLive: async () => true,
    onTrace: (history) => { trace.length = 0; trace.push(...history); },
  });
  return { out, trace, pressed: clicks.length > 0 };
}

{
  const { out, trace, pressed } = await pressButton("Continue and pay");
  check("(d) a read-only run does not press 'Continue and pay'", !pressed,
    trace.join(" | ").slice(0, 300));
  check("(d) ...it ends at the owner saying the task was read-only",
    out.status === "needs_user" && /read-only task/.test(String(out.result)),
    `${out.status}: ${String(out.result).slice(0, 160)}`);
  check("(d) ...and the sentence names the button it refused to press",
    /Continue and pay/.test(String(out.result)), String(out.result).slice(0, 160));
}
{
  const { out, pressed } = await pressButton("Next: Place order");
  check("(d) nor 'Next: Place order'", !pressed && out.status === "needs_user",
    `${out.status}: ${String(out.result).slice(0, 160)}`);
}
{
  // THE CONTROL. The same run, the same everything, a genuinely reversible
  // label: it must still be pressed, or (d) passes on a loop that clicks
  // nothing at all.
  const { pressed } = await pressButton("Continue");
  check("(d) THE CONTROL: a bare 'Continue' is still pressed on the same run", pressed);
}
{
  const { pressed } = await pressButton("Apply filters");
  check("(d) ...and so is 'Apply filters'", pressed);
}

// ---------------------------------------------------------------------------
// (e) THE LOOP'S OWN TEST, asked directly about the labels that matter. These
//     run the bytes captured in (d), over fixture elements.
// ---------------------------------------------------------------------------
{
  check("(e) the loop's own commit test was captured from a live run", !!realCommitControl);
  for (const [label, want] of [
    ["Continue and pay", true], ["Next: Place order", true], ["Back and delete the booking", true],
    ["Continue", false], ["Next", false], ["Apply filters", false], ["Cancel", false],
    ["Cancel reservation", true], ["See 3,631 results", false],
  ]) {
    check(`(e) the loop says "${label}" is ${want ? "a commit" : "reversible"}`,
      commitsAccordingToTheLoop({ label }) === want,
      String(commitsAccordingToTheLoop({ label })));
  }
}

// ---------------------------------------------------------------------------
// (f) THE CONSENT DIALOG. A checkout modal carrying the word "consent" must
//     not turn a purchase button into a cookie button — while a real cookie
//     banner keeps its exemption.
// ---------------------------------------------------------------------------
{
  const consent = "We and our partners ask for your consent to store cookies on this device.";
  // The two arms of `cookieLike`, each with a money label. Arm 2 reads the
  // BOX's prose and keys on the banner's own verbs, so "Accept and pay" in a
  // checkout modal carrying the word consent was a cookie button. Arm 1 reads
  // the CONTROL's own label, so a button that says "consent" was one wherever
  // it stood.
  check("(f) 'Accept and pay' in a box that says consent is NOT a cookie button",
    commitsAccordingToTheLoop({ label: "Accept and pay", dialogText: consent }) === true);
  check("(f) ...nor is 'Accept and place order'",
    commitsAccordingToTheLoop({ label: "Accept and place order", dialogText: consent }) === true);
  check("(f) ...nor is a button whose OWN label says consent and names a payment",
    commitsAccordingToTheLoop({ label: "I consent — pay now" }) === true);
  check("(f) ...nor 'Consent and checkout'",
    commitsAccordingToTheLoop({ label: "Consent and checkout" }) === true);
  check("(f) 'Confirm purchase' in that box is a commit too",
    commitsAccordingToTheLoop({ label: "Confirm purchase", dialogText: consent }) === true);
  check("(f) a real cookie banner keeps its exemption: 'Accept all cookies'",
    commitsAccordingToTheLoop({ label: "Accept all cookies", dialogText: consent }) === false);
  check("(f) ...and 'Confirm choices'",
    commitsAccordingToTheLoop({ label: "Confirm choices", dialogText: consent }) === false);
  check("(f) ...and 'Manage preferences'",
    commitsAccordingToTheLoop({ label: "Manage preferences", dialogText: consent }) === false);
  check("(f) with no consent prose in the box, 'Confirm choices' is judged on its own words",
    commitsAccordingToTheLoop({ label: "Confirm choices", dialogText: "Choose a delivery slot." }) === true);
  const { pressed } = await pressButton("Confirm purchase", { dialogText: consent });
  check("(f) and a read-only run does not press it", !pressed);
}

// ---------------------------------------------------------------------------
// (g) THE RECORD. The precedence is written where the next reader of this
//     function will find it, with what it cost and what stays open.
// ---------------------------------------------------------------------------
{
  const { readFileSync } = await import("node:fs");
  const src = readFileSync(new URL("../agent_loop.js", import.meta.url), "utf8");
  check("(g) the single reversible alternation that ran first is gone from both sites",
    !/const reversible = \/\^\\s\*\(\?:\(\?:search\|find/.test(src));
  check("(g) both halves exist in both live sites",
    (src.match(/const reversibleWhole = /g) || []).length === 2
      && (src.match(/const reversiblePrefix = /g) || []).length === 2);
  check("(g) the record names the measured labels and what a false skips",
    /"Continue and pay"\s+-> false/.test(src) && /Next: Place order/.test(src)
      && /at-most-once/.test(src));
  check("(g) ...and records the bare-Continue case as OPEN rather than widening the vocabulary",
    /STILL OPEN, deliberately/.test(src) && /Continue to payment/.test(src));
  const marker = "TA" + "PE:";
  check("(g) no tape marker was added for this — the seatbelt stayed a seatbelt",
    !new RegExp(marker + "[^\\n]*(?:F08|reversible|commit)", "i").test(src));
}

if (failures) { console.log(`test_commit_beats_reversible_prefix: ${failures} FAILED`); process.exit(1); }
console.log("test_commit_beats_reversible_prefix: a commit verb beats a reversible prefix, in both files");
process.exit(0);
