// CapSolver integration, added 2026-08-16 on the owner's explicit
// instruction after he was told the tradeoffs (Chrome Web Store risk,
// reCAPTCHA terms, and that real CAPTCHAs had blocked exactly ONE job in
// 220). The shape of the integration is what keeps it safe.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const loop = readFileSync(join(here, "../agent_loop.js"), "utf8");

// --- the key never ships to a user's machine -------------------------------
// A published extension is a zip anyone can read. The old dead solver was to
// hold the key here, which would have handed the owner's balance to anyone
// who unzipped a build.
assert.ok(!/CAP-[0-9A-F]{16}/i.test(loop), "no solver key may appear in the extension");
assert.ok(!/capsolver\.com/i.test(loop),
  "the extension must never call the solver directly — the backend holds the key");
assert.ok(/agent\/solve-captcha/.test(loop), "it asks the backend instead");

// --- solving is an attempt, never a requirement ----------------------------
// Every failure path must fall back to the behaviour that shipped before:
// stop, and fetch the person.
const fn = loop.match(/async function trySolveChallenge[\s\S]{0,3000}/)[0];
const returns = fn.match(/return (true|false|placed > 0)/g) || [];
assert.ok(returns.filter((r) => /false/.test(r)).length >= 5,
  "no sitekey, unavailable, failed, slow, or thrown must all hand back");
assert.ok(/handing it to the owner/.test(fn),
  "and must say so in the trace, so a hand-back is never mysterious");
// A failed solve no longer means ONE thing, so this asserts the rule rather
// than the old blanket claim, and reads to the end of the block instead of a
// character count. The window had already been widened once (900 -> 2400) and
// grew stale again the moment the block did; a fixed slice of a live file is a
// test that breaks for the wrong reason.
//
// The rule, added 2026-08-20: a wall on a site the OWNER named is terminal -
// no other site is his hydro account - so it hands back. A wall on a source the
// AGENT chose out of a search is one source among many on a read-only run, so
// it abandons that host and answers from somewhere else. The failure that
// prompted it: "I forgot to cook for my kids this afternoon" reached doordash,
// met a human check, and asked HIM to tick a box so she could read a menu.
// Audit #71: the block is entered on a model's BLOCKED verdict, never on a
// phrase; what it does once entered is unchanged and pinned below.
const site = loop.slice(loop.indexOf('if (verdict === CHALLENGE_BLOCKED)'));
const block = site.slice(0, site.indexOf('\n      // A WALL IS NOT A STALL'));
assert.ok(/trySolveChallenge/.test(block), "solving is still attempted first");
assert.ok(/needs_user/.test(block),
  "and a wall the owner pointed us at still hands back");
assert.ok(/readOnly && !ownerNamedIt/.test(block),
  "a chosen source is only abandoned on a read-only run");
assert.ok(/walledSources\.size < 3/.test(block),
  "abandoning sources must be bounded, or a run could wander forever");
assert.ok(/do not go back to it/.test(block),
  "the model must be told the host is dead, or it re-picks the top hit");

// The server half of this contract (the refuse list for money and identity
// hosts, the hourly ceiling, the account check) lived in a the backend hook
// that no longer exists; server-side solving was withdrawn on 2026-08-16 and
// the Worker carries no solver. What remains to pin is the browser's side.

// --- it only claims challenge types it can actually read -------------------
for (const t of ["recaptcha_v2", "recaptcha_v3", "hcaptcha", "turnstile"]) {
  assert.ok(loop.includes(t), `${t} must be detectable on the page`);
}

console.log("test_captcha_solving: all passed");
