// Round three of the adversarial hunt, verified against the live file before
// anything was touched. Every case here is a way the browser arm either
// commits the WRONG thing twice, or refuses to commit the RIGHT thing at all
// — the two failures the owner watched on real bookings.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const ext = join(here, "..");
const src = readFileSync(join(ext, "agent_loop.js"), "utf8");
const {
  calendarCellDate, isAuthored, loopbackTarget, pageFingerprint,
  samePhoneDigits, schemaBoundaryCorrections, stableControlLabel,
  stallFingerprint, unapprovedCalendarClick, unsupportedApprovedFacts,
  unsupportedScopeFields,
} = await import(join(ext, "agent_loop.js"));

// --- 1. the Enter path still keyed a commit on the words around it ----------
// The click path was rebuilt on stable DOM identity after the double-booking
// finding. Pressing Enter on a form was left on the old text fingerprint, so
// a ticking hold ("Held for 4:32" -> "4:12") or a button relabelling itself
// "Processing…" made the SAME submission look brand new and the at-most-once
// guard let a second one through.
const enterSig = src.match(/const enterSig = [\s\S]{0,500}/)[0];
assert.ok(!/nearbyText/.test(enterSig),
  "page text must never be part of a submission's identity, on either path");
assert.ok(/formAction/.test(enterSig) && /elementId/.test(enterSig)
  && /enterContext\.name/.test(enterSig),
  "the Enter signature must key on stable element identity");
assert.equal(
  stableControlLabel({ label: "Held for 4:32 — Complete Reservation" }),
  stableControlLabel({ label: "Held for 4:12 — Complete Reservation" }),
  "a countdown ticking must not mint a new identity for the same button");
assert.notEqual(stableControlLabel({ label: "Complete Reservation" }),
  stableControlLabel({ label: "Cancel Reservation" }),
  "and two genuinely different controls must stay different");
console.log("PASS 1: a countdown cannot disguise a repeat submit on the Enter path either");

// --- 2. select was a second, unguarded way to write into a text field -------
// Only protectedInput sat here. A model parked at an OTP form whose typed
// "666666" the code guard refused could re-offer the same invention as
// {"action":"select","option":"666666"} and it landed in the field.
const selectBlock = src.slice(
  src.indexOf('if (decision.action === "select") {'),
  src.indexOf('if (decision.action === "click" || decision.action === "type") {'));
assert.ok(selectBlock.length > 500, "the select action block was found");
assert.ok(/unquotedCode\(\s*\n?\s*decision\.option/.test(selectBlock),
  "the one-time-code guard must cover the select path too");
assert.ok(/await composedByTheAgent\(decision\.option,/.test(selectBlock),
  "composed text written through select must still be shown to the owner");
assert.ok(/fieldRejects\(tab\.id, decision\.index\)/.test(selectBlock),
  "the field's own constraint validation must run on the select path");
console.log("PASS 2: select carries the same stops as typing");

// --- 3. the required agreement checkbox blocked its own booking ------------
// approvedBoolean returns null for "I agree to the terms" on a task whose
// words never contain "terms", and the guard read null as a violation. The
// optional-field clear skips checkboxes, so nothing could ever resolve it:
// PRE-SUBMIT BLOCK on every attempt, then the cycle guard walked off the
// page and the table hold expired. The only mechanical way past was to
// UNTICK the agreement, which is exactly what AUTHORITY forbids.
assert.deepEqual(
  unsupportedScopeFields("Book a table at 7:30 tomorrow for 3", { fields: [
    { name: "terms", label: "I agree to the terms of service",
      type: "checkbox", value: true, required: true },
    { name: "offers", label: "Send me offers", type: "checkbox", value: true },
  ] }),
  [],
  "a ticked box the owner never mentioned is not a scope violation");
// The signal that survives: a box that reverses something they DID say.
assert.ok(unsupportedScopeFields("Do not request a refund", { fields: [
  { name: "refund", label: "Request refund", value: true },
] }).includes("refund"), "a checked box still cannot reverse an explicit negation");
assert.ok(unsupportedScopeFields("Submit an urgent request", { fields: [
  { name: "urgent", label: "Urgent", value: false },
] }).includes("urgent"), "and an unticked box still cannot ignore an explicit request");
console.log("PASS 3: consent boxes stop blocking, negations still bite");

// --- 4. an input mask made the owner's own phone unapprovable --------------
// "+1 604 555 0142" reduces to 16045550142; the site's mask renders it back
// as "(604) 555-0142" -> 6045550142. Never equal, so the scope gate flagged
// the field on every audit, the correction retyped it, the mask undid that,
// and the third identical click abandoned a fully filled form.
assert.ok(samePhoneDigits("16045550142", "6045550142"),
  "a country code in front of the same national number is the same phone");
assert.ok(samePhoneDigits("6045550142", "16045550142"), "in both directions");
assert.ok(!samePhoneDigits("5550142", "6045550142"),
  "but seven digits must not match every area code in the country");
assert.ok(!samePhoneDigits("6045550142", "6045550143"), "and two real phones stay different");
assert.deepEqual(
  unsupportedScopeFields("Book for Omar, phone +1 604 555 0142", { fields: [
    { name: "phone", label: "Phone", type: "tel", value: "(604) 555-0142" },
  ] }),
  [], "the masked phone is the approved phone");
assert.deepEqual(
  unsupportedApprovedFacts({ phone: "+1 604 555 0142" },
    { text: "", elements: "", fields: [{ name: "phone", value: "(604) 555-0142" }] }),
  [], "and it is evidenced, so completion can actually be verified");
assert.deepEqual(
  schemaBoundaryCorrections(
    [{ index: 1, name: "phone", label: "Phone", type: "tel", value: "(604) 555-0142" }],
    "Book for Omar, phone +1 604 555 0142",
    [{ index: 1, name: "phone", label: "Phone", type: "tel" }]),
  [], "and nothing retypes it into a loop with the site's own mask");
console.log("PASS 4: a reformatted phone is the same phone");

// --- 5. a countdown defeated every stall detector --------------------------
// "you have 4:59 to complete your booking" re-rendered every second, so the
// fingerprint changed every step: the 18-step wedge never fired and the
// state+action cycle key was never repeated. A model alternating two useless
// actions on a held reservation burned all 80 steps.
const hold = { url: "https://example.test/checkout",
               elements: "[1] <button> Complete Reservation @(10,10)",
               text: "Your table is held. You have 4:32 remaining to finish." };
const ticked = { ...hold, text: "Your table is held. You have 4:12 remaining to finish." };
assert.notEqual(pageFingerprint(hold), pageFingerprint(ticked),
  "the evidence fingerprint still records the page exactly as it was");
assert.equal(stallFingerprint(hold), stallFingerprint(ticked),
  "but a clock ticking is the page counting, not the agent getting anywhere");
assert.notEqual(stallFingerprint(hold),
  stallFingerprint({ ...hold, text: "Your reservation is confirmed." }),
  "real page change is still progress");
assert.notEqual(stallFingerprint(hold),
  stallFingerprint({ ...hold, elements: "[1] <button> Complete Reservation @(10,10)\n[2] <textbox> Name @(10,40)" }),
  "and a new control appearing is still progress");
assert.ok(/const stallPrint = stallFingerprint\(state\);/.test(src),
  "the loop computes the steady fingerprint");
assert.ok(/if \(stallPrint !== lastFingerprint\)/.test(src),
  "and judges the stall on it");
assert.ok(/const stateAction = `\$\{stallPrint\}\|/.test(src),
  "and so does the repeated-action cycle guard");
console.log("PASS 5: a hold page can no longer burn a whole run undetected");

// --- 6. a menu item is where the real commit verbs live --------------------
// Everything inside role=menu short-circuited to "just a choice", so Delete
// on a mail row, "Delete file", "Cancel order" in an account menu all
// dispatched with no authorization gate, no pre-submit audit and no
// at-most-once guard.
const commit = src.slice(src.indexOf("async function commitControl"),
                         src.indexOf("// WHEN IT GETS STUCK, GO FIND OUT HOW"));
assert.ok(!/closest\('select,\[role="listbox"\],\[role="menu"\]'\)/.test(commit),
  "role=menu must not blanket-exempt its contents from the commit test");
assert.ok(/closest\('\[role="menu"\]'\) && !commitVerb\.test\(sourceLabel\)/.test(commit),
  "a menu item is a choice only while its own label names no mutation");
console.log("PASS 6: a menu item that says Delete is treated as one");

// --- 7. the calendar guard steered toward the cancelled date --------------
// Relative wording is resolved for native date inputs but never for picker
// clicks. "Cancel the August 3 booking and book tomorrow instead" has one
// explicit date — the one being cancelled — so the tomorrow cell was blocked
// and deadIdx removed it, leaving August 3 as the only approved date left.
const day = (offset) => {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() + offset);
  return { month: d.toLocaleDateString("en-US", { month: "long" }), number: d.getDate() };
};
const soon = day(1), cancelled = day(40), unrelated = day(20);
const pickerState = { overlay: true, elements: [
  `[5] <button> ${soon.month} ${soon.number} [calendar=${soon.month} ${soon.number}] @(10,10)`,
  `[6] <button> ${cancelled.month} ${cancelled.number} [calendar=${cancelled.month} ${cancelled.number}] @(20,10)`,
  `[7] <button> ${unrelated.month} ${unrelated.number} [calendar=${unrelated.month} ${unrelated.number}] @(30,10)`,
].join("\n") };
const cancelAndRebook =
  `Cancel the ${cancelled.month} ${cancelled.number} booking and book tomorrow instead`;
// AUDIT #69, fixed 2026-08-24. The finding this scenario was written for is
// now the whole guard: the day is resolved structurally, and WHICH day he
// asked for is read by a model — because "tomorrow" was the only relative
// wording the old arithmetic could reach, and "the Tuesday after next" or "a
// week on Friday" blocked the cell he meant while leaving the cancelled date
// clickable. Here the model plays the part it plays live.
const meantTomorrow = async ({ named }) =>
  (named === `${soon.month} ${soon.number}` ? "YES" : "NO");
assert.equal((await unapprovedCalendarClick({ action: "click", index: 5 }, pickerState,
  cancelAndRebook, meantTomorrow)).blocked, false,
  "tomorrow's cell is approved by the owner's own relative wording");
assert.equal((await unapprovedCalendarClick({ action: "click", index: 7 }, pickerState,
  cancelAndRebook, meantTomorrow)).reason.includes(`${unrelated.month} ${unrelated.number}`), true,
  "a date the task never names is still refused");
// The whole point of the original finding: before it, the ONLY approved cell
// here was the booking being cancelled, so the guard steered the run into
// rebooking exactly the date the owner was getting rid of. That is fixed by
// tomorrow's cell being reachable, NOT by making the cancelled one
// unreachable — cancelling an appointment means opening its own day in the
// picker, and this guard cannot see which step of the errand a click belongs
// to. So both days the errand refers to stay clickable and the day it never
// mentions does not.
const bothDaysNamed = async ({ named }) =>
  ([`${soon.month} ${soon.number}`, `${cancelled.month} ${cancelled.number}`]
    .includes(named) ? "YES" : "NO");
assert.equal((await unapprovedCalendarClick({ action: "click", index: 6 },
  pickerState, cancelAndRebook, bothDaysNamed)).blocked, false,
  "the explicitly named date stays clickable — it has to be, to cancel it");
assert.equal((await unapprovedCalendarClick({ action: "click", index: 7 },
  pickerState, cancelAndRebook, bothDaysNamed)).blocked, true,
  "and the day the errand never mentions is still refused");
assert.equal(calendarCellDate(2, 30), "", "February 30 is not a date");
assert.match(calendarCellDate(new Date().getMonth() + 1, 15), /^\d{4}-\d{2}-15$/,
  "a real cell resolves to a concrete dated day");
console.log("PASS 7: relative dates reach the picker");

// --- 8. the loopback guard could not spell half of localhost ---------------
// new URL("http://[::1]:8080/").hostname is "[::1]", so the host === "::1"
// arm could never match a real URL and every IPv6 loopback walked past.
assert.equal(loopbackTarget("http://[::1]:5000/"), true);
assert.equal(loopbackTarget("http://localhost./"), true);
assert.equal(loopbackTarget("http://app.localhost:3000/admin"), true);
assert.equal(loopbackTarget("http://0.0.0.0:8080/"), true);
assert.equal(loopbackTarget("http://127.1/"), true);
assert.equal(loopbackTarget("http://2130706433/"), true);
assert.equal(loopbackTarget("http://127.0.0.1:18092/_/#/login"), true);
assert.equal(loopbackTarget("http://localhost:8090/_/"), true);
assert.equal(loopbackTarget("https://zoom.us/pricing"), false);
assert.equal(loopbackTarget("https://mylocalhost.com/"), false);
assert.equal(loopbackTarget("https://localhost.example.com/"), false);
console.log("PASS 8: every spelling of the owner's own machine is recognised");

// --- 9. the model could switch the loopback guard off ---------------------
// allowLoopback was computed from openAt, and openAt is the PLANNER's
// start_url. One stored fact mentioning a local dev server was enough to make
// the planner answer "http://localhost:3000/admin", which then authorized
// itself for the whole run.
assert.ok(/const allowLoopback = taskAllowsLoopback\(goal, scope, startUrl\);/.test(src),
  "loopback authorization comes from the owner's words and the caller only");
assert.ok(!/taskAllowsLoopback\([^)]*openAt/.test(src),
  "model output must never be one of the values that authorizes it");
// 2026-09-05: the guard at this site widened from loopback to the whole
// internal network (Omi teardown item #04 — 192.168.x, 10.x, 169.254.x and
// IPv4-mapped IPv6 all walked past loopbackTarget). The PROPERTY is unchanged
// and pinned the same way for the wider pair: authorization comes from the
// owner's words and the caller's start URL only, never from a value the
// planner produced, and an unauthorized start_url is replaced, not opened.
assert.ok(/const allowInternal = taskAllowsInternalNetwork\(goal, scope, startUrl\);/.test(src),
  "internal-network authorization comes from the owner's words and the caller only");
assert.ok(!/taskAllowsInternalNetwork\([^)]*openAt/.test(src),
  "model output must never be one of the values that authorizes the internal network");
assert.ok(/const firstUrl = \(internalNetworkTarget\(openAt\) && !allowInternal\) \? startUrl : openAt;/.test(src),
  "and an unauthorized planner start_url is not what gets opened");
// The narrow guard still exists and is still composed by the wide one; a
// site that quietly fell back to it would be a site that lost the network
// ranges, so no consult site may use it directly any more.
assert.ok(!/loopbackTarget\((?:openAt|target|state\.url|decision\.url)\) && !allowLoopback/.test(src),
  "no navigation gate consults the narrow loopback guard directly — all four go through internalNetworkTarget");
// Every navigation, not only the model's `navigate` action.
assert.ok(/function navigationRefusal\(url\)/.test(src), "one gate exists");
const fallback = src.slice(src.indexOf("async function advanceFallback"),
                           src.indexOf("async function scrollForRejectedEvidence"));
assert.ok(/navigationRefusal\(next\)/.test(fallback),
  "a plan fallback URL goes through it");
const research = src.slice(src.indexOf("async function researchCompletionGap"),
                           src.indexOf("// The ONE liveness check"));
assert.ok(/navigationRefusal\(next\)/.test(research),
  "so does a URL quoted out of the model's own rejected result");
assert.ok(/navigationRefusal\(found\.goTo\)/.test(src),
  "so does the stuck researcher's destination");
assert.ok(/if \(internalNetworkTarget\(state\.url\) && !allowInternal\) \{/.test(src),
  "and the LANDED page is re-checked every step, as blockedDomain already was");
console.log("PASS 9: nothing model-authored can reach the owner's own machine");

// --- 10. badFields was written on every rejection and read nowhere --------
// "Three is not a typo, it is a task that cannot be completed with what we
// know" — and the hand-back that comment promises never once fired.
assert.ok(/const parkOnRepeatedFieldRejections = \(bad\) => \{/.test(src),
  "the three-strikes hand-back exists");
assert.ok(/if \(badFields < 3\) return null;/.test(src), "and reads the counter");
assert.equal((src.match(/parkOnRepeatedFieldRejections\(/g) || []).length, 2,
  "both the type path and the select path call it");
console.log("PASS 10: repeated field rejections hand back instead of grinding");

// --- 11. corrections 2..N all landed in field 1 ---------------------------
// Writes resolve through the page's ACTIVE element, and a synthetic
// frameClick — the only click available inside an embedded widget whose
// position is unknown — cannot move focus.
const apply = src.slice(src.indexOf("async function applyFormCorrections"),
                        src.indexOf("// Remove only optional, editable"));
assert.ok(/if \(!\(await focusedMappedField\(tabId, correction\.index\)\)\) continue;/.test(apply),
  "no keystroke goes out until the mapped field actually holds focus");
assert.ok(/active\.blur\(\)/.test(src),
  "and focus is dropped first, because __anticipyFocus deliberately keeps it");
console.log("PASS 11: a pre-submit correction cannot overwrite the previous field");

// --- 12. an index only means something against the map that produced it ---
assert.ok(/const frameTableSignature = \(\) => frameSlots\.join\(","\);/.test(src),
  "the frame table has an identity");
assert.equal((src.match(/frameTableSignature\(\) !== framesAtMap/g) || []).length, 3,
  "every pre-submit re-map re-checks it before dispatching a trusted click");
console.log("PASS 12: a re-map cannot silently re-point a submit at another element");

// --- 13. rearranged words can invert the owner's meaning -----------------
// "Tell the clinic I will NOT attend at 3pm, ask to move it to Friday" ->
// "Hi, I will attend at 3pm on Friday and look forward to it" — every token
// is the owner's, and until 2026-08-24 a 0.6 overlap ratio waved it through
// and the message went out in their name saying the opposite.
//
// AUDIT #66: the ratio also waved through inversions that KEEP the negation
// ("Friday morning but not Thursday afternoon" -> "Thursday afternoon but not
// Friday morning"), which the negation escape hatch could never catch, because
// nothing was missing — the meaning had simply been swapped. That is what a
// sentence MEANS, so a model reads it. test_authored_draft.mjs owns the
// boundary; these pin that the inversion no longer walks past on its own.
const inverted = "Hi, I will attend at 3pm on Friday and I look forward to it";
const SAYS = (v) => ({ judge: async () => v });
assert.ok(await isAuthored(inverted,
  "Tell the clinic I will not attend at 3pm, ask to move it to Friday", "", SAYS("COMPOSED")),
  "a dropped negation is composition, whatever the token overlap says");
assert.ok(await isAuthored(
  "Hi, I can do Thursday afternoon but not Friday morning, thanks.", "send a message",
  "Tell the clinic I can do Friday morning but not Thursday afternoon.", SAYS("COMPOSED")),
  "an inversion that KEEPS the negation is composition too — the escape hatch missed these");
assert.ok(await isAuthored(inverted,
  "Tell the clinic I will not attend at 3pm, ask to move it to Friday", ""),
  "and with no model to read it, it is shown rather than sent");
assert.ok(!(await isAuthored(
  "noise cancelling headphones under 400 dollars for travel and commuting on long flights",
  "Research the best noise cancelling headphones under 400 dollars for travel and "
  + "commuting on long flights", "", SAYS("COMPOSED"))),
  "his own words, verbatim, are carried and never reach the model");
console.log("PASS 13: an inverted message is shown before it goes out");

// --- 14. the end-of-run sweep closed the owner's own tabs ----------------
// `!t.active` was never a test of ownership. A run lasting several minutes is
// exactly when the owner middle-clicks links into background tabs: not
// preexisting, not active, and destroyed at the end of every single run.
const teardown = src.slice(src.indexOf("// Late-spawned duplicates"));
assert.ok(!/!t\.active \|\| t\.openerTabId === tab\.id/.test(teardown),
  "an inactive tab is not thereby ours");
assert.ok(/ours\.has\(t\.id\)/.test(teardown),
  "a stray is closed only when it descends from the working tab");
console.log("PASS 14: the owner's background tabs survive the run");

console.log("test_hunt_round3: all passed");
