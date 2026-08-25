// The brain's recalled memory must reach the agent's eyes as BACKGROUND, and
// must never become a value the agent may type. Both halves are load-bearing:
// showing it and letting it fill fields would let something merely overheard
// enter a form that spends his money; showing it and silently wiping whatever
// it produced would be a maddening ghost bug. This suite pins both.
//
// Run: node extension/tests/test_memory_context.mjs
import assert from "node:assert";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { unsupportedScopeFields } from "../agent_loop.js";

const here = dirname(fileURLToPath(import.meta.url));
const loop = readFileSync(join(here, "..", "agent_loop.js"), "utf8");
const worker = readFileSync(join(here, "..", "background.js"), "utf8");

const MEMORY = "he always books the Coal Harbour location; his usual table is by the window";

// ---------------------------------------------------------------- 1. plumbing
// The value has to survive every hop, or the prompt block renders empty and the
// whole feature is a no-op that still reads as done.
// PINNED ON PRESENCE, NOT ARITY. These used to require `memory` to be the LAST
// parameter and the call to end exactly there, which meant adding any further
// context block — the researched procedure did precisely this — broke a test
// about memory. A test that fails when unrelated code improves teaches people to
// edit tests instead of read them, so what is asserted now is that memory is a
// declared parameter and that every call site passes it.
assert.match(
  loop,
  /async function llmStep\([^)]*\bmemory = ""/,
  "llmStep must declare a memory parameter",
);
assert.match(
  loop,
  /llmStep\(apiKey, model, goal, state, history, 0, eyes, visionModel, authorized, scope, ownerProfile, plan, factsText, evidenceJournal, memory\b/,
  "the step loop must pass memory into llmStep",
);
assert.match(
  loop,
  /llmStep\(apiKey, model, goal, state, history, \(_retries \|\| 0\) \+ 1[^)]*\bmemory\b/,
  "the self-repair retry must carry memory too, or a reparse silently drops it",
);
assert.match(
  loop,
  /export async function planRun\(apiKey, model, goal, ownerProfile, scope, memory = ""\)/,
  "planRun must accept memory — it is what picks the right start_url",
);
assert.match(
  loop,
  /await planRun\(apiKey, model, goal, ownerProfile, scope, memory\)/,
  "runAgentGoal must pass memory to the planner",
);
assert.match(
  loop,
  /const \{ apiKey,[^}]*\bmemory = "",/,
  "runAgentGoal must destructure a memory option",
);
assert.match(
  worker,
  /memory: typeof params\.memory === "string"/,
  "the worker must read params.memory off the job row",
);
console.log("PASS: memory is plumbed brain-row -> worker -> planner -> every step");

// ------------------------------------------------------- 2. read from the row
// params.memory, never params._workflow.memory: the plan is what his approval
// is digest-bound to (brain/workflow.py scope_digest), so background knowledge
// riding inside it would 409 his own yes.
assert.ok(
  !/_workflow[?.]*\.memory/.test(worker),
  "memory must NOT be read from params._workflow — that blob is digest-bound",
);
console.log("PASS: memory rides outside the approval-digested plan");

// --------------------------------------------- 3. never rendered as authority
// The facts fallback branch sweeps unknown params keys into FACTS ALREADY
// GIVEN, whose prompt text says "set form fields to these". A short
// recollection is under the 200-char cut, so without an explicit exclusion it
// lands there and becomes typeable by the back door.
//
// RUN THE RULE, DO NOT LOOK FOR IT. This used to slice background.js between
// two source landmarks and grep the slice for `"memory",`; it went red the
// moment the expression was lifted into a named function, having never once
// exercised the behaviour it is named for.
{
  const { installChrome } = await import("./chrome_mock.mjs");
  installChrome();
  const { ownerFactsFromParams } = await import("../background.js");
  const facts = ownerFactsFromParams({ memory: MEMORY, party_size: 4, time: "7:30 PM" });
  assert.ok(!("memory" in facts) && !JSON.stringify(facts).includes("Coal Harbour"),
    `memory must be excluded from the facts fallback sweep: ${JSON.stringify(facts)}`);
  assert.deepEqual(facts, { party_size: 4, time: "7:30 PM" },
    "...and the values he actually gave must still get through");
}
console.log("PASS: memory cannot leak into FACTS ALREADY GIVEN");

// ---------------------------------------- 4. the prompt says choose, not fill
const memoryBlock = loop.slice(loop.indexOf("const memoryBlock = memory"), loop.indexOf("const matching ="));
assert.ok(
  /NOT approved values/.test(memoryBlock),
  "the memory block must label itself as not-approved",
);
assert.ok(
  /Do NOT type any of it into a field/.test(memoryBlock),
  "the memory block must forbid typing it — the mechanism below wipes it anyway",
);
assert.ok(
  /needs_user/.test(memoryBlock),
  "the memory block must name the way out when a form needs a remembered value",
);
console.log("PASS: the prompt tells the truth about what memory may be used for");

// ------------------------------------- 5. the mechanism, not just the wording
// A value that traces ONLY to memory is still an unsupported field. This is the
// half that holds even if a model ignores every instruction above.
const bookingField = [{ name: "location", label: "Location", value: "Coal Harbour" }];
const flagged = unsupportedScopeFields(
  "book a table for two tomorrow at 7",
  { fields: bookingField },
  { first_name: "Omar", email: "omar@example.com" },
  "",
);
assert.deepStrictEqual(
  flagged,
  ["location"],
  "a value appearing only in memory must still be flagged unsupported",
);

// Control: the same value IS supported once it is in his approved words, which
// proves the assertion above is measuring provenance and not just flagging
// every field it sees.
assert.deepStrictEqual(
  unsupportedScopeFields(
    "book a table for two tomorrow at 7 at the Coal Harbour location",
    { fields: bookingField },
    { first_name: "Omar", email: "omar@example.com" },
    "",
  ),
  [],
  "the same value must pass once the owner's own words carry it",
);
console.log("PASS: memory alone cannot supply a submittable field value");

// And the guarantee is structural: memory is not a parameter of the boundary
// function at all, so no call site can accidentally widen it.
assert.strictEqual(
  unsupportedScopeFields.length,
  2,
  "unsupportedScopeFields takes (scope, currentState) plus two defaults — "
    + "if memory was added as a parameter, the prompt text must change with it",
);
assert.ok(
  /RECALLED MEMORY IS DELIBERATELY ABSENT FROM approvedText/.test(loop),
  "the decision must stay written down at the mechanism that enforces it",
);
console.log("PASS: the authority boundary cannot be widened by a call site");

console.log("test_memory_context: all passed");
