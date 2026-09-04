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
import { boolDefaultTrue, boolDefaultFalse, parsePbTime, timingEqual,
         isoNow, pbNowFormat } from "../src/routes/hq_data.ts";

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

// --- the two datetime formats, which must not be interchanged -------------
//
// internal_sessions holds `created` as "2026-09-03 18:25:45.103Z" (space, a
// PocketBase autodate) and `expires` as "2026-10-03T18:25:45.093Z" (T, written
// by the hook with toISOString()) IN THE SAME ROW. Verified against migrated
// data. Text comparison is how both are used, and " " sorts below "T", so a
// value written in the wrong format does not merely look odd -- it sorts into
// the wrong half of every ORDER BY and drops out of every range filter.
//
// A first draft of hq_data.ts wrote `created` with toISOString(). The keep-ten
// session trim orders by `created DESC`, so every new row would have sorted
// above all 31 migrated ones and the trim would have deleted genuinely recent
// sessions while believing it dropped the oldest.
check("isoNow() carries a T and pbNowFormat() carries a space", () => {
  const at = new Date("2026-09-04T12:34:56.789Z");
  assert.equal(isoNow(at), "2026-09-04T12:34:56.789Z");
  assert.equal(pbNowFormat(at), "2026-09-04 12:34:56.789Z");
});
check("the two formats sort against each other the wrong way", () => {
  const at = new Date("2026-09-04T12:34:56.789Z");
  // The point of the rule: identical instants, opposite sort order.
  assert.ok(pbNowFormat(at) < isoNow(at),
    "space sorts below T, so mixing formats reorders a column by format "
    + "rather than by time");
});
check("both formats still parse to the same instant", () => {
  const at = new Date("2026-09-04T12:34:56.789Z");
  assert.equal(parsePbTime(pbNowFormat(at)), at.getTime());
  assert.equal(parsePbTime(isoNow(at)), at.getTime());
});

if (failures) {
  console.error("\n" + failures + " failed");
  process.exit(1);
}
console.log("hq-booleans: all cases pass");
