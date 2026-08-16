// Two hunt-confirmed P0s about the browser committing the WRONG thing.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const src = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "../agent_loop.js"), "utf8");

// --- 1. a countdown must not disguise a repeat commit as a new one ---------
// The "have I already done this?" signature included the button's live label
// and up to 300 chars of surrounding text. On a reservation page holding a
// perishable slot, "Held for 4:32" became "Held for 4:12" one step later, the
// signature changed, and a SECOND Complete Reservation click was not
// recognised as the same effect: a double booking, on exactly the pages the
// system is told to push through.
const sig = src.match(/const externalSig = \[[\s\S]{0,400}/)[0];
assert.ok(!/nearbyText/.test(sig),
  "page text must never be part of an effect's identity");
assert.ok(/formAction/.test(sig) && /elementId/.test(sig) && /context\.name/.test(sig),
  "the signature must key on stable element identity");
assert.ok(/replace\(\/\\d\+\/g, ""\)/.test(src),
  "digits in a control's label (timers, counters) must not enter the signature");
// and controlContext must actually supply that identity, including its
// empty-fallback shape, or the signature silently collapses to blanks.
const ctx = src.match(/async function controlContext[\s\S]{0,3000}/)[0];
for (const k of ["formAction:", "name:", "elementId:"]) {
  assert.ok(ctx.includes(k), `controlContext must return ${k}`);
}
assert.ok((ctx.match(/formAction: ""/g) || []).length >= 1,
  "the empty fallback must carry the same keys");

// --- 2. a refused correction has already touched the form ------------------
// applyFormCorrections CLEARS a field before typing. When the field itself
// rejects the value, `applied` is empty, nothing looped back, and every guard
// below judged a snapshot taken BEFORE the form was touched — so the submit
// went out with a blanked field and the receipt check audited a page that
// never existed.
const refused = src.match(/PRE-SUBMIT ALIGNMENT was refused by the field itself/g) || [];
assert.equal(refused.length, 2,
  "both the click path and the Enter path must re-read after a refused correction");
assert.ok(/corrections && corrections\.length && !applied\.length/.test(src),
  "a refused correction must force a re-read, not fall through");

console.log("test_commit_integrity: all passed");
