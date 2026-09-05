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

/** Everything that still looks like a placeholder, anywhere in the task. This
 *  is the adversary's view: it does not care which fields the filler knows
 *  about. */
function leftoverPlaceholders(task: TaskSpec): string[] {
  return [...JSON.stringify(task).matchAll(/\{\{([A-Z0-9_]+)\}\}/g)].map((m) => m[1]).sort();
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
test("nothing that still looks like a placeholder survives substitution unreported", () => {
  // A field no filler was written for. The next person to add a line to
  // ten_read_tasks.json adds one of these, and the blocker has to see it
  // without being edited — otherwise the fence is only as wide as the last
  // author's memory.
  const task = { ...taskWith({}), note_to_the_grader: "ask about {{PERSON_A}}" } as unknown as TaskSpec;

  const { tasks, missing } = substitute([task], {});
  assert.deepEqual(
    missing,
    ["PERSON_A"],
    "the blocker must sweep the whole task after filling, not consult a list of fields it knows",
  );

  const filled = substitute([task], { PERSON_A: "Dana" });
  assert.deepEqual(filled.missing, []);
  assert.deepEqual(leftoverPlaceholders(filled.tasks[0]), []);
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
