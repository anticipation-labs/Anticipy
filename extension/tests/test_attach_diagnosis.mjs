// Live 2026-08-16: his dinner job failed with "could not attach the automation
// session to the tab" — a sentence that names no cause and suggests no action.
// He read it, correctly, as the whole product failing. Chrome allows exactly
// ONE debugger client per tab, and he runs three things that want it.
//
// Two defects were in that path:
//   1. "already attached" was treated as success — but Chrome says "ANOTHER
//      debugger is already attached" when a RIVAL holds the tab, so we sailed
//      on believing we were attached and then failed every command.
//   2. The failure carried neither the cause nor the remedy.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const src = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "../agent_loop.js"), "utf8");
const fn = src.match(/async function attachDebugger[\s\S]{0,1400}/)[0];

// Ours is fine; a rival's is not.
assert.ok(/!\/another\/i\.test\(msg\)/.test(fn),
  "another debugger holding the tab must never count as a successful attach");
assert.ok(/chrome\.debugger\.detach/.test(fn),
  "a session left behind by a killed run must be released before retrying");
assert.ok(/lastAttachError = msg/.test(fn),
  "the real Chrome error must be captured, not discarded");

// The failure the owner reads has to name a cause and an action.
const fail = src.match(/const rival = [\s\S]{0,900}/)[0];
assert.ok(/close DevTools/.test(fail) && /browser-control extensions/.test(fail),
  "a rival attachment must tell him exactly what to close");
assert.ok(/Chrome refused the automation session: \$\{lastAttachError/.test(fail),
  "any other refusal must quote Chrome's own words");
assert.ok(!/result: "could not attach the automation session to the tab"/.test(src),
  "the cause-free message must be gone");

// Exercise the branch logic itself against the strings Chrome actually returns.
const isOurs = (msg) => /already attached/i.test(msg) && !/another/i.test(msg);
assert.equal(isOurs("Debugger is already attached to this target"), true);
assert.equal(isOurs("Another debugger is already attached to the tab with id: 42"), false);
assert.equal(isOurs("Cannot access a chrome:// URL"), false);

console.log("test_attach_diagnosis: all passed");
