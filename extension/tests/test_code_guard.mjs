// A verification code is never invented.
//
// Live, 2026-08-11: a job parked at an OTP form was resumed with the text
// "I told you to make it 6 dammit" riding along as the answer. The model
// typed "6" three times and then padded it into "666666" and SUBMITTED it.
// On a real site that is a lockout/fraud-flag risk. The guard is mechanical:
// a value bound for a code-shaped field must appear character-for-character
// in what the owner actually gave, and real codes are never under 4 chars.
//
// Run: node extension/tests/test_code_guard.mjs

import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const ext = join(here, "..");

globalThis.chrome = globalThis.chrome || {
  tabs: { query: async () => [], create: async () => ({ id: 1 }), remove: async () => {} },
  storage: { local: { get: async () => ({}), set: async () => {} } },
  runtime: {}, debugger: {}, tabGroups: {}, notifications: {}, alarms: {},
};

const { unquotedCode } = await import(join(ext, "agent_loop.js"));

let failed = 0;
const ok = (cond, name) => {
  if (cond) console.log(`PASS: ${name}`);
  else { failed++; console.error(`FAIL: ${name}`); }
};

const attrs = "otp code Verification code one-time-code";
const scope = 'Task: book dinner. You stopped and asked: "I need the ' +
  '6-digit verification code". They answered: "I told you to make it 6 dammit"';

ok(unquotedCode("666666", attrs, "book dinner", scope, ""),
  "an invented/padded code is refused");
ok(unquotedCode("6", attrs, "book dinner", scope, ""),
  "a fragment lifted from an unrelated correction is refused");
ok(unquotedCode("742913", attrs, "book dinner",
  scope + ' They answered: "742913"', "") === null,
  "the owner's actual code, quoted verbatim, goes through");
ok(unquotedCode("742913", attrs, "book dinner", scope, "verification_code: 742913") === null,
  "a code carried in facts goes through");
ok(unquotedCode("Omar", "first name given-name", "book dinner", scope, "") === null,
  "non-code fields are untouched by the guard");
ok(unquotedCode("V6B 1A1", "postal code zip", "ship it", scope, "") === null,
  "a postal code field is not an OTP field — no guard");

if (failed) process.exit(1);
console.log("test_code_guard: all passed");
