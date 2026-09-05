// THE GATE'S OWN HALF THAT IS ANSWERABLE WITH NO KEY.
//
// `tasks/run_ten.ts` has two halves. The live half needs a Composio key, a
// connected account and a grader, and on this machine it correctly reports
// UNPROVEN. The other half — load the ten tasks, re-derive their hashes, fill
// the owner's answers into the placeholders, and REFUSE to run while one is
// still empty — is pure, runs here, and had never been tested at all.
//
// That is what let the defect below live: `substitute()` filled `{{TOKEN}}` in
// the prompt and in the string values of `signature.inputs`, and nothing else.
// `signature.expected_effect`, `signature.object` and the whole `how_to_grade`
// rubric went to the judge and to the grader verbatim, so the gate would run a
// task and SCORE it against a rubric that named `{{PERSON_A}}` — a person who
// does not exist — while the blocker that exists to prevent exactly that saw
// nothing, because it only ever looked at the two fields the filler knew about.
//
// The shape of the fix these tests pin: the filler walks the whole task, and
// the blocker is a sweep over the SERIALIZED task afterwards rather than a list
// of fields. A blocker written as a list of fields is only ever as complete as
// the last person who added a field to the task file.
//
// A SECOND ADVERSARIAL PASS FOUND THREE MORE, AND ALL THREE WERE IN THIS
// FILE'S OWN BLIND SPOT, which is why they are called out here rather than
// only at their legs:
//
//   1. The fixed blocker was UPPERCASE-ONLY, so `{{person_a}}` was still
//      neither filled nor reported — and `makeSignature` lower-cases `object`,
//      so mixed case is not an exotic way to author one. This file could not
//      have caught it: its `leftoverPlaceholders` oracle was a
//      character-for-character copy of the pattern under test, so the stub and
//      the code were wrong in the same direction and the leg reported clean.
//      The oracle is now deliberately WIDER than the code (`/\{\{[^{}]*\}\}/g`),
//      which is the one property a copy cannot have.
//   2. `{{ PERSON_A }}` — the padding every templating language accepts — was
//      invisible in every direction at once: unlisted by `tokensIn`, unfilled,
//      unreported, and shipped verbatim to the judge and the grader. It was
//      found BY the widened oracle, minutes after widening it, which is the
//      whole argument for widening it.
//   3. The SWEEP had no leg of its own. The test written for it exercised the
//      deep FILLER — delete the sweep and the suite stayed green. The sweep's
//      real cases are the two the filler cannot report by construction: a token
//      in a KEY, and an answer that is ITSELF a placeholder. Both are below,
//      both verified red with the sweep line deleted.
//
// Rule for the next person adding to this file: a test whose expectation is
// computed the same way the code computes it proves that the code is
// self-consistent, not that it is right.

import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import { makeSignature } from "../src/signature.ts";
import { TaskFileBroken, loadTasks, substitute, tokensIn } from "../tasks/run_ten.ts";
import type { TaskSpec } from "../tasks/run_ten.ts";

const TASKS_FILE = fileURLToPath(new URL("../tasks/ten_read_tasks.json", import.meta.url));

/** One task, in the shape the file carries, with whatever the case under test
 *  needs put where it needs it. The hash is computed, never typed. */
function taskWith(over: {
  prompt?: string;
  expected_effect?: string;
  object?: string;
  inputs?: Record<string, unknown>;
  right_is?: string;
  checkable?: string[];
  wrong_if?: string[];
  owner_confirms?: string[];
}): TaskSpec {
  const signature = makeSignature({
    app_hint: "gmail",
    verb: "read",
    object: over.object ?? "the owner's mail",
    inputs: over.inputs ?? { query: "is:unread" },
    expected_effect: over.expected_effect ?? "the unread mail is listed",
    side_effect: "read",
    account_hint: null,
  });
  return {
    id: "t-under-test",
    prompt: over.prompt ?? "what came in?",
    expected_effect: over.expected_effect ?? "the unread mail is listed",
    signature,
    how_to_grade: {
      right_is: over.right_is ?? "the unread mail is listed",
      checkable_from_the_response: over.checkable ?? ["the response is a list of messages"],
      wrong_if: over.wrong_if ?? ["the list is empty when mail exists"],
      only_the_owner_can_confirm: over.owner_confirms ?? ["whether anything was skipped"],
    },
  };
}

/** Everything that still looks like a placeholder, anywhere in the task.
 *
 *  THIS ORACLE IS DELIBERATELY NOT THE SOURCE'S PATTERN, and that is the whole
 *  point of it. It used to be `/\{\{([A-Z0-9_]+)\}\}/g` — a character-for-
 *  character copy of `run_ten.ts`'s own `PLACEHOLDER` — so it agreed with the
 *  code about what a placeholder IS, and the two of them were wrong together:
 *  neither could see `{{person_a}}`. A stub asserted against itself reports
 *  100% and proves nothing. So this asks the adversary's question instead —
 *  is there ANY brace-brace pair left in here — which is strictly wider than
 *  the pattern under test and cannot be satisfied by copying it.
 *
 *  It returns the matched TEXT, not the token name, so a failure prints the
 *  spelling that survived rather than a normalised guess at it. */
function leftoverPlaceholders(task: TaskSpec): string[] {
  return [...JSON.stringify(task).matchAll(/\{\{[^{}]*\}\}/g)].map((m) => m[0]).sort();
}

// ---------------------------------------------------------------------------
// THE RUBRIC — the field the grader is handed verbatim.
// ---------------------------------------------------------------------------
test("a placeholder in how_to_grade is filled, not shipped to the grader", () => {
  const task = taskWith({
    right_is: "the last mail from {{PERSON_A}} is shown",
    checkable: ["every message is from {{PERSON_A}}"],
    wrong_if: ["a message from anyone but {{PERSON_A}} appears"],
    owner_confirms: ["whether {{PERSON_A}} wrote from a second address"],
  });

  const { tasks, missing } = substitute([task], { PERSON_A: "Dana Whitfield" });

  assert.deepEqual(missing, [], "the owner answered this one, so nothing is missing");
  assert.deepEqual(
    leftoverPlaceholders(tasks[0]),
    [],
    "the rubric goes to the grader verbatim; a {{TOKEN}} in it grades the API hand against a person who does not exist",
  );
  assert.equal(tasks[0].how_to_grade.right_is, "the last mail from Dana Whitfield is shown");
  assert.equal(tasks[0].how_to_grade.checkable_from_the_response[0], "every message is from Dana Whitfield");
  assert.equal(tasks[0].how_to_grade.wrong_if[0], "a message from anyone but Dana Whitfield appears");
  assert.equal(
    tasks[0].how_to_grade.only_the_owner_can_confirm[0],
    "whether Dana Whitfield wrote from a second address",
  );
});

test("an UNFILLED placeholder in how_to_grade blocks the run", () => {
  const { missing } = substitute([taskWith({ right_is: "the last mail from {{PERSON_A}} is shown" })], {});
  assert.deepEqual(
    missing,
    ["PERSON_A"],
    "this is the whole point of the blocker: a rubric naming an invented colleague must stop the gate, not score it",
  );
});

// ---------------------------------------------------------------------------
// CASE. A placeholder is a placeholder whatever case it was typed in.
// ---------------------------------------------------------------------------
// The filler and the sweep shared one pattern — `[A-Z0-9_]` — while the
// hashed-field refusal used a SECOND, any-case copy. So `{{person_a}}` in the
// prompt or in the rubric was not a placeholder as far as the gate was
// concerned: not filled, not reported, not blocked. The run went out to the
// owner's real Gmail and the grader was handed a rubric naming a literal
// `{{person_a}}`, and the gate printed a number for the row.
//
// Mixed case is not an exotic way to author one, either: `makeSignature`
// lower-cases `object`, so a hand-typed {{PERSON_A}} comes back out of it as
// {{person_a}} without anybody choosing that.
test("a lower-case placeholder is a placeholder: filled when answered, blocking when not", () => {
  const task = taskWith({
    prompt: "did {{person_a}} reply?",
    right_is: "the last mail from {{Person_A}} is shown",
    checkable: ["every message is from {{person_a}}"],
  });

  const blocked = substitute([task], {});
  assert.deepEqual(
    blocked.missing,
    ["PERSON_A"],
    "an unanswered {{person_a}} must stop the gate; unseen, it is scored against a rubric naming a token",
  );

  // THE CONTROL. A blocker that refuses everything is an outage, not a guard:
  // the same token, answered, must fill in every case it was typed in and
  // leave nothing behind.
  const filled = substitute([task], { PERSON_A: "Dana Whitfield" });
  assert.deepEqual(filled.missing, []);
  assert.deepEqual(leftoverPlaceholders(filled.tasks[0]), []);
  assert.equal(filled.tasks[0].prompt, "did Dana Whitfield reply?");
  assert.equal(filled.tasks[0].how_to_grade.right_is, "the last mail from Dana Whitfield is shown");
  assert.equal(filled.tasks[0].how_to_grade.checkable_from_the_response[0], "every message is from Dana Whitfield");
});

// Found by the wider oracle above, which is the reason for widening it: a
// human writing `{{ PERSON_A }}` — the spacing every templating language on
// earth accepts — was invisible in EVERY direction at once. `tokensIn` did not
// list it, so the owner was never asked for it; `substitute` did not fill it
// and did not report it, so nothing blocked; and the literal went to the judge
// and to the GRADER. Same defect as the lower-case one, one variant over, and
// the only reason it is a separate leg is that it is a separate character
// class.
//
// The filler tolerates the padding rather than the blocker merely refusing it,
// because the owner has an answer for this token and the run can just work. It
// stays narrow: the inside must still be one word of `[A-Za-z0-9_]`, so this is
// not a step towards matching anything between two braces.
test("a placeholder padded with spaces is filled, and unanswered it blocks", () => {
  const task = taskWith({
    prompt: "did {{ PERSON_A }} reply?",
    right_is: "the last mail from {{  person_a  }} is shown",
  });

  assert.deepEqual(tokensIn([task]), ["PERSON_A"], "the owner is never asked for a token nobody lists");

  const blocked = substitute([task], {});
  assert.deepEqual(
    blocked.missing,
    ["PERSON_A"],
    "unanswered, it must stop the gate — it used to sail through to the grader verbatim",
  );

  const filled = substitute([task], { PERSON_A: "Dana Whitfield" });
  assert.deepEqual(filled.missing, []);
  assert.deepEqual(leftoverPlaceholders(filled.tasks[0]), []);
  assert.equal(filled.tasks[0].prompt, "did Dana Whitfield reply?");
  assert.equal(filled.tasks[0].how_to_grade.right_is, "the last mail from Dana Whitfield is shown");
});

test("tokensIn reports a lower-case token, in the case the owner is asked to fill", () => {
  // The owner is told to write PERSON_A in ten_read_tasks.local.json. If this
  // reported `person_a` he would fill a key nothing looks up, the run would be
  // refused for a token he can see with his own eyes in the file, and the only
  // way out would be guessing at the case.
  const task = taskWith({ prompt: "did {{person_a}} reply?", expected_effect: "mail from {{Person_B}} is listed" });
  assert.deepEqual(tokensIn([task]), ["PERSON_A", "PERSON_B"]);
});

test("a lower-case placeholder in a HASHED field is still refused by name", () => {
  // The refusal was already case-blind, through a second copy of the pattern
  // that the filler did not share. That copy is gone; this is the leg that
  // says deleting it did not take the case-blindness with it.
  const doc = JSON.parse(readFileSync(TASKS_FILE, "utf8"));
  const victim = doc.tasks[0];
  const sig = makeSignature({
    app_hint: victim.signature.app_hint,
    verb: victim.signature.verb,
    object: "the calendar of {{person_a}}",
    inputs: victim.signature.inputs,
    expected_effect: victim.signature.expected_effect,
    side_effect: victim.signature.side_effect,
    account_hint: victim.signature.account_hint,
  });
  doc.tasks[0] = { ...victim, signature: { ...sig } };

  const dir = mkdtempSync(join(tmpdir(), "two-hands-tasks-"));
  const file = join(dir, "ten_read_tasks.json");
  try {
    writeFileSync(file, JSON.stringify(doc));
    assert.throws(() => loadTasks(file), /hashed field/);
    assert.throws(() => loadTasks(file), /PERSON_A/,
      "reported in the case he fills, not the case makeSignature happened to leave it in");
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

// ---------------------------------------------------------------------------
// THE EXPECTED EFFECT — the field the judge AND the grader are both shown.
// ---------------------------------------------------------------------------
test("a placeholder in the expected effect is filled and, unanswered, blocks the run", () => {
  const answered = substitute(
    [taskWith({ expected_effect: "the last mail from {{PERSON_B}} is listed with its date" })],
    { PERSON_B: "Sam Okoye" },
  );
  assert.deepEqual(answered.missing, []);
  assert.equal(
    answered.tasks[0].signature.expected_effect,
    "the last mail from Sam Okoye is listed with its date",
    "judgeQuestion() and gradeQuestion() both print this line; unfilled, both models are asked about a placeholder",
  );
  assert.equal(answered.tasks[0].expected_effect, "the last mail from Sam Okoye is listed with its date");

  const unanswered = substitute(
    [taskWith({ expected_effect: "the last mail from {{PERSON_B}} is listed with its date" })],
    {},
  );
  assert.deepEqual(unanswered.missing, ["PERSON_B"]);
});

// ---------------------------------------------------------------------------
// NESTED INPUT VALUES.
// ---------------------------------------------------------------------------
test("a placeholder nested inside an input value is filled, not just a top-level string", () => {
  const task = taskWith({ inputs: { query: "is:unread", people: ["{{PERSON_A}}", "{{PERSON_B}}"] } });
  const { tasks, missing } = substitute([task], { PERSON_A: "Dana", PERSON_B: "Sam" });
  assert.deepEqual(missing, []);
  assert.deepEqual(tasks[0].signature.inputs.people, ["Dana", "Sam"]);
  assert.deepEqual(leftoverPlaceholders(tasks[0]), []);
});

// ---------------------------------------------------------------------------
// THE SWEEP — the blocker must not be a list of fields.
// ---------------------------------------------------------------------------
test("a field no filler was written for is still filled and still blocks", () => {
  // The next person to add a line to ten_read_tasks.json adds one of these,
  // and the harness has to cope without being edited — otherwise the fence is
  // only as wide as the last author's memory.
  //
  // NOTE what this proves and what it does NOT. The deep FILLER walks every
  // string value at any depth, so it is the filler, not the sweep, that
  // reports this one: delete the sweep and this test stays green. It is a leg
  // for `fillDeep`, and it was the only leg the sweep had. The two tests below
  // are the sweep's own, and they are the ones that go red without it.
  const task = { ...taskWith({}), note_to_the_grader: "ask about {{PERSON_A}}" } as unknown as TaskSpec;

  const { missing } = substitute([task], {});
  assert.deepEqual(
    missing,
    ["PERSON_A"],
    "the filler must walk the whole task, not consult a list of fields it knows",
  );

  const filled = substitute([task], { PERSON_A: "Dana" });
  assert.deepEqual(filled.missing, []);
  assert.deepEqual(leftoverPlaceholders(filled.tasks[0]), []);
});

test("THE SWEEP: an answer that is itself a placeholder does not walk through", () => {
  // The filler cannot see this one BY CONSTRUCTION. `String.replace` does not
  // re-scan what a replacement function returned, so the token is consumed,
  // `missing` never hears about it, and a literal `{{PERSON_B}}` is now in the
  // prompt and in the rubric with every field the filler knows about reporting
  // clean. Only a pass over the FINISHED task can catch it.
  //
  // Not hypothetical: `ten_read_tasks.local.json` is hand-written at 2am by
  // the one person who knows the names, and a half-pasted line is what a
  // half-pasted line looks like.
  const task = taskWith({ prompt: "did {{PERSON_A}} reply?", right_is: "the mail from {{PERSON_A}} is shown" });

  const { tasks, missing } = substitute([task], { PERSON_A: "{{PERSON_B}}" });
  assert.deepEqual(
    missing,
    ["PERSON_B"],
    "the blocker must ask the finished task, not the fields the filler walked past",
  );
  assert.deepEqual(leftoverPlaceholders(tasks[0]), ["{{PERSON_B}}", "{{PERSON_B}}"]);
});

test("THE SWEEP: a placeholder in a KEY is reported, because the filler is forbidden to touch keys", () => {
  // `fillDeep` leaves keys alone on purpose — input key names are in the
  // signature hash, so filling one would key the run to a capability nothing
  // else computes. The consequence is that a token in ANY key is invisible to
  // the filler, and this one is outside the hashed fields so `loadTasks`'s
  // refusal never sees it either. The sweep is the only thing left.
  const task = { ...taskWith({}), notes: { "{{PERSON_A}}": "who to ask about" } } as unknown as TaskSpec;

  const { missing } = substitute([task], { PERSON_A: "Dana" });
  assert.deepEqual(
    missing,
    ["PERSON_A"],
    "answered or not, a token in a key cannot be filled — it has to be reported, never silently shipped",
  );
});

test("THE SWEEP does not refuse a perfectly good answer that happens to carry braces", () => {
  // THE CONTROL. A sweep that fired on any brace would make the feature
  // unreachable for anyone whose name, channel or search string has one in it,
  // and an outage dressed as a guard is the failure this pass is here to
  // avoid. Only a brace-brace PAIR is a placeholder.
  const task = taskWith({ prompt: "did {{PERSON_A}} reply?", right_is: "the search {{SLACK_SEARCH}} is used" });
  const { tasks, missing } = substitute([task], {
    PERSON_A: "Dana {Whitfield}",
    SLACK_SEARCH: "has:link {from:dana}",
  });
  assert.deepEqual(missing, [], "single braces are text, not a hole");
  assert.deepEqual(leftoverPlaceholders(tasks[0]), []);
  assert.equal(tasks[0].prompt, "did Dana {Whitfield} reply?");
});

// ---------------------------------------------------------------------------
// tokensIn — what the harness says the owner has to fill in.
// ---------------------------------------------------------------------------
test("tokensIn reports every token in the task, not only the two the filler knew about", () => {
  const task = taskWith({
    prompt: "did {{PERSON_A}} reply?",
    expected_effect: "the last mail from {{PERSON_B}} is listed",
    right_is: "the thread with {{SENDER_INVOICE}} is shown",
  });
  assert.deepEqual(tokensIn([task]), ["PERSON_A", "PERSON_B", "SENDER_INVOICE"]);
});

// ---------------------------------------------------------------------------
// THE HASH IS NOT MOVED BY FILLING.
// ---------------------------------------------------------------------------
test("filling values never moves the signature hash", () => {
  const task = taskWith({ prompt: "did {{PERSON_A}} reply?", inputs: { from: "{{PERSON_A}}" } });
  const { tasks } = substitute([task], { PERSON_A: "Dana" });
  assert.equal(
    tasks[0].signature.signature_hash,
    task.signature.signature_hash,
    'values are excluded from the hash on purpose: "email Sam" and "email Dana" are one capability',
  );
});

test("a placeholder in a HASHED field is a broken task file, not a fillable hole", () => {
  // `object` and the input KEY NAMES are in the hash. A token in one of them
  // cannot be filled — filling it would key the run to a capability the ledger
  // never computes, and leaving it would ask the judge about a placeholder — so
  // the honest answer is BROKEN at load, with the reason named.
  const doc = JSON.parse(readFileSync(TASKS_FILE, "utf8"));
  const victim = doc.tasks[0];
  const sig = makeSignature({
    app_hint: victim.signature.app_hint,
    verb: victim.signature.verb,
    object: "the calendar of {{PERSON_A}}",
    inputs: victim.signature.inputs,
    expected_effect: victim.signature.expected_effect,
    side_effect: victim.signature.side_effect,
    account_hint: victim.signature.account_hint,
  });
  doc.tasks[0] = { ...victim, signature: { ...sig } };

  const dir = mkdtempSync(join(tmpdir(), "two-hands-tasks-"));
  const file = join(dir, "ten_read_tasks.json");
  try {
    writeFileSync(file, JSON.stringify(doc));
    // The stored hash agrees with the fields beside it, so the drift check
    // passes and this is the only leg that can catch it.
    assert.throws(() => loadTasks(file), TaskFileBroken);
    assert.throws(() => loadTasks(file), /hashed field/);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("the shipped ten still load, and every token in them is fillable", () => {
  const loaded = loadTasks(TASKS_FILE);
  assert.equal(loaded.tasks.length, 10);
  const answers: Record<string, string> = {};
  for (const token of loaded.tokens) answers[token] = `filled-${token}`;
  const { tasks, missing } = substitute(loaded.tasks, answers);
  assert.deepEqual(missing, [], "every token the harness reports must be one the filler can actually fill");
  for (const t of tasks) assert.deepEqual(leftoverPlaceholders(t), [], `${t.id} still carries a placeholder`);
});
