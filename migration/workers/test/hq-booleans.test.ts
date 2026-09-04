/**
 * Runs with no dependencies:
 *
 *   node --experimental-strip-types migration/workers/test/hq-booleans.test.ts
 *
 * THE BUG THIS EXISTS TO STOP, which was live in a draft of hq_data.ts:
 *
 * internal_hq.pb.js decides a notification preference with
 *
 *     email_on: person.get("email_on") !== false
 *
 * In the PocketBase JSVM that field is a real boolean, so somebody who switched
 * email OFF stores `false`, and `false !== false` is false. Correct.
 *
 * In D1 the same field is INTEGER 0. And `0 !== false` is TRUE in JavaScript.
 * Transcribing the idiom literally -- which is the natural thing to do when
 * porting line by line -- silently flips every opt-OUT back to opt-IN. The only
 * symptom is email arriving for a person who turned it off, which nobody
 * reports as a bug against a migration.
 *
 * Nothing in production currently has email_on = 0, so the live data would NOT
 * have caught this. It becomes wrong the first time somebody unticks the box.
 * That is exactly why it is pinned here instead of being left to a smoke test.
 */
import assert from "node:assert/strict";
import { boolDefaultTrue, boolDefaultFalse, parsePbTime, timingEqual } from "../src/routes/hq_data.ts";

let failures = 0;
function check(what: string, fn: () => void) {
  try { fn(); } catch (err) {
    failures++;
    console.error("FAIL " + what + "\n     " + (err as Error).message);
  }
}

// --- the naive transcription, demonstrated to be wrong ---------------------
check("the literal `!== false` idiom is wrong on a D1 integer", () => {
  const fromD1 = 0;                       // what "off" looks like after migration
  assert.equal(fromD1 !== false, true,    "JS says 0 !== false");
  assert.equal(boolDefaultTrue(fromD1), false,
    "...so the helper must NOT be that expression");
});

// --- opt-out is preserved --------------------------------------------------
for (const off of [0, false, "0", "false"]) {
  check("boolDefaultTrue(" + JSON.stringify(off) + ") is false", () => {
    assert.equal(boolDefaultTrue(off), false);
  });
}

// --- and the "absent means on" meaning the idiom was written for survives ---
for (const on of [1, true, "1", "true", null, undefined]) {
  check("boolDefaultTrue(" + JSON.stringify(on) + ") is true", () => {
    assert.equal(boolDefaultTrue(on), true);
  });
}

// --- the other polarity: !!record.get(...), which defaults to OFF -----------
for (const off of [0, false, null, undefined, "", "0", "false"]) {
  check("boolDefaultFalse(" + JSON.stringify(off) + ") is false", () => {
    assert.equal(boolDefaultFalse(off), false);
  });
}
for (const on of [1, true, "1", "true"]) {
  check("boolDefaultFalse(" + JSON.stringify(on) + ") is true", () => {
    assert.equal(boolDefaultFalse(on), true);
  });
}

// --- is_admin and active must NOT default to on ----------------------------
check("a person row with no is_admin is not an admin", () => {
  assert.equal(boolDefaultFalse(undefined), false,
    "defaulting is_admin to true would hand HQ admin to everybody");
});

// --- datetimes: the missing Z ----------------------------------------------
check("a PocketBase datetime without a zone is read as UTC", () => {
  // PocketBase stores "2026-09-04 12:00:00.000Z"; some rows carry no Z at all.
  // Parsed as LOCAL time, a session expires hours early or late depending on
  // where the process runs -- and workerd is UTC while a developer's laptop is
  // not, so this would behave differently in dev and prod.
  const withZone = parsePbTime("2026-09-04 12:00:00.000Z");
  const without  = parsePbTime("2026-09-04 12:00:00.000");
  assert.equal(without, withZone, "a bare datetime must be read as UTC");
  assert.equal(withZone, Date.parse("2026-09-04T12:00:00.000Z"));
});
check("an unparseable datetime is NaN, never 0", () => {
  // 0 would be 1970 -- in the past -- which for an expiry check reads as
  // "expired" and is the safe direction, but for anything else is a silent
  // wrong answer. NaN forces the caller to decide.
  assert.ok(Number.isNaN(parsePbTime("")));
  assert.ok(Number.isNaN(parsePbTime(null)));
  assert.ok(Number.isNaN(parsePbTime("not a date")));
});

// --- the timing-safe compare -----------------------------------------------
check("timingEqual matches $security.equal", () => {
  assert.equal(timingEqual("abc", "abc"), true);
  assert.equal(timingEqual("abc", "abd"), false);
  assert.equal(timingEqual("abc", "ab"), false);
  assert.equal(timingEqual("", ""), true);
});
check("timingEqual does not treat a prefix as a match", () => {
  assert.equal(timingEqual("secret", "secretlonger"), false);
  assert.equal(timingEqual("secretlonger", "secret"), false);
});

if (failures) {
  console.error("\n" + failures + " failed");
  process.exit(1);
}
console.log("hq-booleans: all cases pass");
