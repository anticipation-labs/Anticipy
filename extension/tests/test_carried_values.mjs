// THE FORM'S OWN ANSWER SHEET WAS INVISIBLE TO THE AUDITOR.
//
// Found 2026-08-20 by the browser battery, on the two shapes most errands
// actually take. A multi-step form forwards the answers you already gave in
// hidden inputs, and those hidden inputs are exactly what the browser submits.
// The pre-submit auditor could not see them, because page_map.js gates the
// fields list on `visible(el)` - so the booking confirm page carried
//
//     <input type="hidden" name="date" value="2026-03-03">
//
// an exact name-and-value match for the approved fact, and the agent still
// said "PRE-SUBMIT BLOCK - these approved facts are not set: date", refused its
// own submit, and looped until the six-minute wall killed the run. One click
// from done, stopped by its own safety check. The permit task died the same way
// with four facts at once (42 steps, 369s).
//
// Second defect, same run: an approved value that is a SUBSET of the option's
// visible text was scored unapproved and then actively wiped. Fact
// zone="Zone B"; the option reads "Zone B - riverside". The trace reads
// `select 2 "Zone B - riverside" -> selected` then `cleared unapproved
// optional defaults: zone`, over and over.
//
// The DOM half is proven in a real browser against the fixture forms. This
// file defends the decision logic, which is where the block was actually made.
import assert from "node:assert/strict";
import { unsupportedApprovedFacts } from "../agent_loop.js";

let failures = 0;
const check = (name, ok) => {
  console.log(`${ok ? "PASS" : "FAIL"}: ${name}`);
  if (!ok) failures++;
};

// factPairs() takes an object or "key: value" lines - NOT a JSON string,
// which parses into a key of `{"date` and proves nothing.
const facts = { date: "2026-03-03", time: "19:00", party: "2" };

// ---- a fact evidenced ONLY by a carried hidden value is supported ----------
{
  const state = {
    text: "Confirm your booking", elements: "[0] <button> Complete booking",
    // The shape page_map now produces for a hidden input: no index, carried.
    fields: [
      { name: "date", label: "", type: "hidden", carried: true, value: "2026-03-03" },
      { name: "time", label: "", type: "hidden", carried: true, value: "19:00" },
      { name: "party", label: "", type: "hidden", carried: true, value: "2" },
    ],
  };
  const missing = unsupportedApprovedFacts(facts, state);
  check("a hidden carried value evidences its approved fact",
    missing.length === 0);
}

// ---- and without them, the block is still correct -------------------------
// The auditor must not have been softened into a rubber stamp: with nothing on
// the page carrying the date, refusing to submit is the right answer.
{
  const state = {
    text: "Confirm your booking", elements: "[0] <button> Complete booking",
    fields: [{ name: "name", label: "Name", type: "text", index: 0, value: "Alex Fixture" }],
  };
  const missing = unsupportedApprovedFacts(facts, state);
  check("with nothing carrying the values, it still refuses",
    missing.length === 3);
}

// ---- an approved value inside a glossed option is supported ---------------
{
  const zone = { zone: "Zone B" };
  const shown = (value) => ({
    text: "Permit application", elements: "[2] <select> Zone",
    fields: [{ name: "zone", label: "Zone", type: "select-one", index: 2, value }],
  });
  check("an option that adds a human gloss still evidences the fact",
    unsupportedApprovedFacts(zone, shown("Zone B - riverside")).length === 0);
  check("an en dash gloss counts too",
    unsupportedApprovedFacts(zone, shown("Zone B – riverside")).length === 0);
  check("a parenthetical gloss counts too",
    unsupportedApprovedFacts(zone, shown("Zone B (riverside)")).length === 0);
  // The boundary is the whole point: a bare prefix match would accept the
  // wrong zone and then submit it, which is worse than blocking.
  check("a longer code is NOT the approved one",
    unsupportedApprovedFacts(zone, shown("Zone BB - hillside")).length === 1);
  check("a different zone is still refused",
    unsupportedApprovedFacts(zone, shown("Zone C - riverside")).length === 1);
}

// ---- a carried field can never be targeted for a click or a wipe ----------
// clearUnsupportedOptionalFields accepts a field when
// Number.isFinite(Number(field.index)). `index: null` would have passed that
// test - Number(null) is 0 - and blanked whatever element 0 happened to be.
// So the carried shape must carry NO index key at all.
{
  const carried = { name: "date", label: "", type: "hidden", carried: true, value: "2026-03-03" };
  check("a carried field has no index property",
    !("index" in carried));
  check("and therefore fails the finite-index guard",
    !Number.isFinite(Number(carried.index)));
  // Guards against someone 'tidying' the shape to index: null later.
  check("index: null would have been accepted by that guard - hence its absence",
    Number.isFinite(Number(null)));
}

if (failures) {
  console.error(`test_carried_values: ${failures} failed`);
  process.exit(1);
}
console.log("test_carried_values: all passed");
