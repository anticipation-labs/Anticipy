// ONE SUBMISSION, TWO KEYS ON THE SAME KEYBOARD — THE KEY ITSELF.
//
// 306 live browser-agent runs (102 tasks x 3 passes, 2026-08-21) recorded one
// breach of the at-most-once guarantee, and only repetition exposed it. Task
// `book-party-six`, pass 3 of 3 (2026-08-22) wrote TWO identical bookings to
// the fixture ledger where passes 1 and 2 wrote one:
//
//   step 13: BLOCKED DUPLICATE EFFECT — this same consequential control was
//            already dispatched once ... never repeat it to make sure.
//   step 15: {"action":"type","index":1,"text":"Alex","enter":true}
//   step 16: {"action":"done","result":"Table booked Reference MB-8941 ..."}
//
// The guard held for the CLICK and Enter in a text field of the same form sent
// the form again, because both gates keyed on the CONTROL:
// url|click|tag|label|action|name|id|index for the button against
// url|enter|… for the field. A submit button and a field inside its own form
// differ in the literal, the tag, the label, the element name, the id and the
// index, so performedExternalEffects could never see one effect.
//
// The repair landed in cf4b5e3f as submissionDigest (agent_loop.js :2920): one
// key built from what is actually being SENT — the page, the form's address,
// and the form's editable VALUES — consulted by the click gate (:5181, :5196)
// and the Enter gate (:5420, :5434), both adding it to the SAME
// performedExternalEffects set (:3905, added at :5282 and :5507).
//
// test_commit_once.mjs already drives that end to end through runAgentGoal.
// This suite pins the KEY, which is the part a future edit will touch: the
// value digest is the only thing separating "the same commit repeated" from
// "the next step of a wizard", and the obvious simplification of it — page
// plus form action — is measurably worse than the bug it fixes. Every step of
// the fixture's /forms/permit POSTs to /forms/permit with the same field
// names, so that key blocks the legitimate steps 2 and 3 and takes the `form`
// family from 43.6% (17/39, last of six families) to nothing. Case 3 is that
// measurement and it is the reason this file exists.
//
// What it would have caught: case 1 is the double booking, asserted directly
// on the two shapes the two gates hand the digest.
//
// Run: node extension/tests/test_one_submission_two_keys.mjs
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { submissionDigest, stableControlLabel } from "../agent_loop.js";

let failures = 0;
const check = (name, ok) => {
  console.log(`${ok ? "PASS" : "FAIL"}: ${name}`);
  if (!ok) failures++;
};

const src = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "../agent_loop.js"), "utf8");

// The field shape is mapPage's, not an invented one: page_map.js :298-306
// pushes {index, name, label, type, required, readOnly, value} and mapPage
// (agent_loop.js :2401, :2414) passes those objects through untouched. The
// gates then hand the digest stateForControl's narrowing of that list (:3013),
// which keeps only the fields the control's own form owns.
const field = (over = {}) => ({
  index: 1, name: "", label: "", type: "text",
  required: false, readOnly: false, value: "", ...over,
});

// ------------------------------------------------- 1. the recorded failure
// The booking page, as the two gates see it. Same url, same form, same values;
// the CONTROL differs in everything a per-control signature keys on. Both
// paths must produce one key, or the ledger takes two bookings.
{
  const url = "https://fixture.test/book?held=272";
  const guests = [
    field({ index: 1, name: "guest_name", label: "Name", value: "Alex Reyes",
            required: true }),
    field({ index: 2, name: "party_size", label: "Party size", value: "6",
            required: true }),
  ];
  // The click gate: controlContext for the submit button (:2858 reads
  // target.form.action, so a button and a field in one form report the same
  // one), stateForControl narrowing state.fields to that form's own.
  const clickContext = {
    label: "Complete Reservation", tag: "button", name: "",
    elementId: "complete-reservation",
    formAction: "https://fixture.test/book/submit", fieldIndexes: [1, 2],
  };
  // The Enter gate: the name field of that same form. Nothing here matches
  // above except the form and what it is carrying.
  const enterContext = {
    label: "Name", tag: "input", name: "guest_name", elementId: "guest-name",
    formAction: "https://fixture.test/book/submit", fieldIndexes: [1, 2],
  };
  const clickKey = submissionDigest(clickContext, { fields: guests }, url);
  const enterKey = submissionDigest(enterContext, { fields: guests }, url);

  check("the click gate produces a key at all", !!clickKey);
  check("a click on the submit button and Enter in a field of the SAME form "
    + "with the SAME values are ONE effect", clickKey === enterKey);

  // And the guard that let it through: the per-control signatures. Kept here
  // as the measurement of WHY the digest is needed — if these ever agree, the
  // digest has stopped being load-bearing and this file should be re-read.
  const sigOf = (c, kind) => [url, kind, c.tag, stableControlLabel(c),
    c.formAction, c.name, c.elementId, "x"].join("|");
  check("the per-control signatures still disagree, which is the bug",
    sigOf(clickContext, "click") !== sigOf(enterContext, "enter"));

  // A changed payload is the NEXT ATTEMPT, not a repeat: this is what the 422
  // permit retry depends on (test_form_retry_after_rejection.mjs) and it is
  // the same property case 3 measures from the other side.
  const corrected = [guests[0], field({ index: 2, name: "party_size",
    label: "Party size", value: "4", required: true })];
  check("changing a value makes it a different submission",
    submissionDigest(clickContext, { fields: corrected }, url) !== clickKey);
}

// ------------------------------------------------ 2. one set, both directions
// Both gates add their key to the same performedExternalEffects set (:3905,
// :5282, :5507). Whichever key sends first, the other must find it. Asserted
// on the source too, because a future refactor that gives the Enter path its
// own set would leave every behavioural assertion above passing.
{
  const url = "https://fixture.test/book";
  const context = { formAction: "https://fixture.test/book/submit" };
  const fields = [field({ name: "guest_name", value: "Alex Reyes" })];
  const performedExternalEffects = new Set();
  performedExternalEffects.add(submissionDigest(context, { fields }, url));
  check("Enter finds the key the click left behind",
    performedExternalEffects.has(submissionDigest(context, { fields }, url)));
  const adds = src.match(/if \(submitted\) performedExternalEffects\.add\(submitted\);/g) || [];
  check("both gates add the digest to the one shared set", adds.length === 2);
  check("both gates consult the digest before dispatching",
    (src.match(/performedExternalEffects\.has\(submissionKey\)/g) || []).length >= 1
    && (src.match(/performedExternalEffects\.has\(enterSubmissionKey\)/g) || []).length >= 1);
}

// ----------------------------------------------- 3. the wizard must survive
// THE ASSERTION THAT STOPS THE OBVIOUS SIMPLIFICATION. Someone will look at
// ["submission", url, formAction, values] and see the values as noise. They
// are the whole key. proof/fixtures/server.mjs serves /forms/permit as three
// steps behind ONE url, every one POSTing to /forms/permit with the same field
// names — so a key of page plus form action alone blocks steps 2 and 3, and
// the `form` family goes from 43.6% to zero. Three steps, three keys.
{
  const url = "https://fixture.council/forms/permit";
  const context = { label: "Review", tag: "button", name: "", elementId: "",
                    formAction: url, fieldIndexes: [1] };
  const step = (name, label, value) => submissionDigest(
    context, { fields: [field({ name, label, value, required: true })] }, url);
  const keys = [
    step("applicant", "Applicant", "Jose Cruz"),
    step("address", "Address", "18 Kestrel Row"),
    step("zone", "Zone", "Zone B"),
  ];
  check("every step of a one-url wizard produces a key", keys.every(Boolean));
  check("three steps of one form action are three different submissions",
    new Set(keys).size === 3);
  // Same field, different answer: the shape a corrected value takes after the
  // fixture's 422. It must not read as the attempt the server refused.
  check("the same field carrying a different answer is a new submission",
    step("zone", "Zone", "Zone B") !== step("zone", "Zone", "Zone A"));
}

// ---------------------------------------------------------- 4. abstention
// A form with no editable field has no content to compare, so the digest
// abstains rather than collapsing to page+action — which is the
// wizard-breaking key above, and would also fuse two different confirm
// buttons that happen to sit in one form. /forms/permit step 3 is exactly
// this: its answers ride in hidden inputs, which page_map.js does not index,
// so its confirm button owns no editable field at all.
{
  const url = "https://fixture.council/forms/permit";
  const context = { formAction: url, fieldIndexes: [] };
  check("a control owning no editable field abstains",
    submissionDigest(context, { fields: [] }, url) === "");
  check("a missing fields list abstains", submissionDigest(context, {}, url) === "");
  check("a null controlState abstains", submissionDigest(context, null, url) === "");
  check("a form of nothing but readonly fields abstains",
    submissionDigest(context, { fields: [
      field({ name: "reference", value: "PRM-4417", readOnly: true }),
    ] }, url) === "");
  check("a form of nothing but contentless controls abstains",
    submissionDigest(context, { fields: [
      field({ name: "go", type: "submit", value: "Confirm and submit" }),
    ] }, url) === "");

  // The other half, and the half that matters: an empty key must never be
  // treated as a match. One "" in performedExternalEffects would make every
  // abstaining control on every page in the run look already-spent, which is
  // a silent refusal to finish any wizard. Both gates therefore guard on
  // truthiness before consulting the set, and neither ever adds a falsy key.
  const performedExternalEffects = new Set([""]);
  const abstained = submissionDigest(context, { fields: [] }, url);
  check("a naive `has()` on an abstention would false-positive",
    performedExternalEffects.has(abstained));
  check("the guarded form the gates actually use does not",
    !(abstained && performedExternalEffects.has(abstained)));
  check("the click gate guards on truthiness before consulting the set",
    /if \(submissionKey && performedExternalEffects\.has\(submissionKey\)\)/.test(src));
  check("the Enter gate guards on truthiness before consulting the set",
    /if \(enterSubmissionKey && performedExternalEffects\.has\(enterSubmissionKey\)\)/.test(src));
  check("neither gate ever stores a falsy key",
    !/performedExternalEffects\.add\(submissionDigest/.test(src)
    && (src.match(/if \(submitted\) performedExternalEffects\.add\(submitted\);/g) || []).length === 2);
  // The precedence the retry fix installed: a payload never sent is the next
  // attempt, and an abstaining control has no payload, so it stays under the
  // absolute per-control block. `!!` is what keeps "" out of that decision.
  check("an abstention cannot claim to be a new payload",
    /!!submissionKey && !performedExternalEffects\.has\(submissionKey\)/.test(src)
    && /!!enterSubmissionKey\s*\n?\s*&& !performedExternalEffects\.has\(enterSubmissionKey\)/.test(src));
}

// ------------------------------------------------ 5. normalisation, on purpose
// The digest reads a page twice, through two different code paths, either side
// of a keystroke. Whitespace, case and field order are all things that can
// differ between those two reads without the submission differing, so they are
// collapsed. Digits are NOT: there the number IS the content.
{
  const url = "https://fixture.test/book";
  const context = { formAction: "https://fixture.test/book/submit" };
  const key = (fields) => submissionDigest(context, { fields }, url);

  check("whitespace is collapsed",
    key([field({ name: "guest_name", value: "  Alex   Reyes\n" })])
    === key([field({ name: "guest_name", value: "Alex Reyes" })]));
  check("case is collapsed",
    key([field({ name: "guest_name", value: "ALEX REYES" })])
    === key([field({ name: "guest_name", value: "alex reyes" })]));
  check("field order does not matter, because the values are sorted",
    key([field({ index: 1, name: "guest_name", value: "Alex Reyes" }),
         field({ index: 2, name: "party_size", value: "6" })])
    === key([field({ index: 2, name: "party_size", value: "6" }),
             field({ index: 1, name: "guest_name", value: "Alex Reyes" })]));
  check("a value moving to another field is still a different submission",
    key([field({ index: 1, name: "first", value: "6" }),
         field({ index: 2, name: "second", value: "2" })])
    !== key([field({ index: 1, name: "first", value: "2" }),
             field({ index: 2, name: "second", value: "6" })]));

  // THE ONE THAT COSTS MONEY. A party of 6 is not a party of 4.
  check("digits are KEPT: a party of 6 is not a party of 4",
    key([field({ name: "party_size", value: "6" })])
    !== key([field({ name: "party_size", value: "4" })]));
  check("digits are kept in amounts too",
    key([field({ name: "amount", value: "$1,240.00" })])
    !== key([field({ name: "amount", value: "$1,240.99" })]));

  // And the deliberate opposite, two functions up in agent_loop.js (:2881).
  // stableControlLabel STRIPS digits because a perishable-hold page renders
  // "Held for 4:32" and then "Held for 4:12" and that must not make one
  // button look like two. Both behaviours are pinned here so a future edit
  // cannot quietly unify them into one normaliser: they are opposites on
  // purpose, and each direction is a recorded booking defect.
  check("stableControlLabel strips digits, which is the opposite rule",
    stableControlLabel({ label: "Held for 4:32" })
    === stableControlLabel({ label: "Held for 4:12" }));
  check("the two rules are genuinely opposed and must stay separate",
    stableControlLabel({ label: "Party of 6" })
    === stableControlLabel({ label: "Party of 4" }));
}

// --------------------------------------- 6. what carries no content stays out
// submit/reset/button/image inputs ARE the control, and the control is what
// the per-control signature is for. Their labels also move ("Book table" ->
// "Processing…"), which is exactly the relabelling that made one button look
// like two in the first place.
{
  const url = "https://fixture.test/book";
  const context = { formAction: "https://fixture.test/book/submit" };
  const withControl = (type, value) => submissionDigest(context, { fields: [
    field({ index: 1, name: "guest_name", value: "Alex Reyes" }),
    field({ index: 2, name: "go", type, value }),
  ] }, url);
  const bare = submissionDigest(context, { fields: [
    field({ index: 1, name: "guest_name", value: "Alex Reyes" }),
  ] }, url);
  for (const type of ["submit", "reset", "button", "image"]) {
    check(`a ${type} input carries no content and stays out of the digest`,
      withControl(type, "Book table") === bare);
    check(`and relabelling that ${type} input changes nothing`,
      withControl(type, "Processing…") === withControl(type, "Book table"));
  }
  check("the type match is case-insensitive, as the DOM reports it",
    withControl("SUBMIT", "Book table") === bare);
  // A readonly field is the server's own answer echoed back (the fixture's
  // PRM-4417 reference); the agent cannot change it, so it cannot distinguish
  // one attempt from the next.
  check("a readonly field stays out of the digest",
    submissionDigest(context, { fields: [
      field({ index: 1, name: "guest_name", value: "Alex Reyes" }),
      field({ index: 2, name: "reference", value: "PRM-4417", readOnly: true }),
    ] }, url) === bare);
  check("but a checkbox is content: ticking the declaration is a new payload",
    submissionDigest(context, { fields: [
      field({ name: "declare", type: "checkbox", value: false }),
    ] }, url)
    !== submissionDigest(context, { fields: [
      field({ name: "declare", type: "checkbox", value: true }),
    ] }, url));
}

// ------------------------------- 7. the precondition the collapse rests on
// The cross-path collapse in case 1 is not a property of this function alone.
// It holds only because controlContext (:2832-2844) hands BOTH gates the same
// form scope, so both see the same owned field set. Written down here because
// it is the one way case 1 can be true and the guarantee still fail: a submit
// button associated to a form by the `form="…"` attribute while sitting
// OUTSIDE it reports the same formAction (:2858 reads target.form.action) but
// resolves a different scope (closest("form") misses, and the ancestor walk
// finds either nothing or some other container's fields). Two field sets, two
// keys, and nothing in this file or in test_commit_once.mjs would notice.
// Unverified against a live page as of 2026-08-24 — see the correction in
// TESTING-PASS-2026-08-21-ROUND2.md §3.
{
  const url = "https://fixture.test/book";
  const context = { formAction: "https://fixture.test/book/submit" };
  const guests = [
    field({ index: 1, name: "guest_name", value: "Alex Reyes" }),
    field({ index: 2, name: "party_size", value: "6" }),
  ];
  const both = submissionDigest(context, { fields: guests }, url);
  const partial = submissionDigest(context, { fields: [guests[0]] }, url);
  check("two gates given different field sets produce different keys",
    both !== partial);
  check("so the collapse depends on one shared form scope, not on the url",
    submissionDigest(context, { fields: guests }, url) === both);

  // And the two components that are NOT the values. A mutation sweep on
  // 2026-08-24 found the suite blind to dropping the form action from the key:
  // an errand list where every row is its own one-checkbox form would then
  // fuse all of them into one effect and the second row would never be
  // actioned. The page is pinned for the same reason in the other direction —
  // the same form action reached from two pages is two submissions.
  check("two different forms on one page are different submissions",
    submissionDigest({ formAction: "https://fixture.test/rows/1/confirm" },
                     { fields: guests }, url)
    !== submissionDigest({ formAction: "https://fixture.test/rows/2/confirm" },
                         { fields: guests }, url));
  check("the same form action reached from two pages is two submissions",
    submissionDigest(context, { fields: guests }, "https://fixture.test/book")
    !== submissionDigest(context, { fields: guests }, "https://fixture.test/rebook"));
  // …but the query string is not identity: evidenceUrlKey (:1476) drops it, so
  // a perishable hold ticking down in ?held=272 cannot make one submission
  // look like two.
  check("a changing query string on the same page is still one submission",
    submissionDigest(context, { fields: guests }, "https://fixture.test/book?held=272")
    === submissionDigest(context, { fields: guests }, "https://fixture.test/book?held=251"));
}

if (failures) {
  console.error(`test_one_submission_two_keys: ${failures} failed`);
  process.exit(1);
}
console.log("test_one_submission_two_keys: all passed");
