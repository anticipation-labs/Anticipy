// THE WEEK-1 GATE. Can the API hand do ten ordinary reads, correctly, fast?
//
// Two questions, deliberately kept apart, because conflating them is how this
// repo has been burned before (overnight/firmware_gate.py is the house pattern
// and this file is modelled on it line for line):
//
//   1. Is the harness itself sound — do the ten signatures still hash to what
//      the hashing function computes, are they all reads, do the two copies of
//      the gate's numbers agree?  Answerable here, with no key and no account.
//   2. Did ten real calls against the owner's real accounts happen, and were
//      the answers right?  NOT answerable here today, and the honest answer is
//      no: there is no COMPOSIO_API_KEY on this machine and no connected
//      account behind one.
//
// SO THIS GATE HAS THREE STATES, NOT TWO.
//
//   exit 0  CLEAN     ten calls happened, >= 9 were right, p50 under 3s.
//   exit 1  BROKEN    something answerable here is wrong — a drifted hash, a
//                     write in a read-only task list, a gate softened in one
//                     file and not the other — or the run happened and failed.
//   exit 2  UNPROVEN  the run COULD NOT HAPPEN. No key, no connection, no
//                     grader, or a vendor that was down. This is not a soft
//                     fail and it is not a pass; it is the absence of a
//                     measurement, and HARNESS-LAWS law 3 is explicit that a
//                     fix nobody ran against the live system is not done.
//
// WHAT THIS FILE REFUSES TO DO, and the reason it is written down rather than
// merely intended: it will never print a table. Not a table of zeros, not a
// table of dashes, not a table of numbers from a previous run, unless ten real
// calls produced them in this process. `printTable` throws on an empty row set
// rather than rendering an empty header, because a formatted table is what a
// person screenshots, and a screenshot of an empty gate is indistinguishable
// from a screenshot of a passing one after a week. A run that could not happen
// prints the word UNPROVEN and the list of things the owner must do.
//
// WHERE THE MEANING DECISIONS ARE. Three, all of them model calls, all of them
// one question answered on its own in an explicit set of states, and none of
// them decided by a pattern in this file:
//
//   - "does this tool do this step?"    — the MatchJudge, per candidate, four
//     states, and only "yes" licenses the API hand (contract.ts judgeLicensesApi).
//   - "what arguments does this tool need for this step?" — mapping the
//     planner's inputs onto a vendor's schema is a meaning question, so it is
//     asked of the model rather than solved with a key-name table.
//   - "is this answer right?"           — the grader, four states, floor
//     polarity: only "yes" counts. `unclear`, `no-verdict` and an unreachable
//     grader are NOT correct, because a gate that scored the absence of an
//     objection as a pass would go green on a dead model.
//
// The only pattern-matching here is plumbing and gate: reading env vars,
// substituting {{TOKENS}}, parsing JSON out of a model reply, hashing a
// response so a results file can identify it without quoting it, and one
// redaction pass over the grader's prose. HARNESS-LAWS law 1, clauses
// "senses" and "gates and evals".
//
// PRIVACY, stated because this is the first thing in the spike that touches
// the owner's real mail:
//   - Tool RESPONSES — his actual inbox, calendar and Slack — are sent to the
//     grader model. That is the same trust boundary the brain already crosses
//     every time it hears him, and it is the only way to grade an answer. It
//     is written here so nobody discovers it later.
//   - The judge is NOT sent input values, only input KEY NAMES, matching what
//     provider_composio.ts sends to retrieval. His recipient, his subject and
//     his body have no business in a "which tool is this" question.
//   - results/*.json carries NO response body. A sha256 prefix and a byte
//     count identify a response; the grader's prose is truncated and passed
//     through one redactor. A results file is a record that gets committed,
//     and a committed record must not be his mailbox.
//
// Usage:
//   COMPOSIO_API_KEY=... OPENROUTER_API_KEY=... \
//     node --experimental-strip-types tasks/run_ten.ts

import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { tightenSideEffect } from "../src/contract.ts";
import type {
  CapabilitySignature,
  ConnectedApp,
  Provider,
  ExecResult,
  MatchAnswer,
  MatchJudge,
  MatchVerdict,
  SideEffect,
  ToolCandidate,
  UserCtx,
} from "../src/contract.ts";
import { apiOutcome, makeTwoHands } from "../src/index.ts";
import type { RouteDecision } from "../src/index.ts";
import { percentile } from "../src/ledger.ts";
import { ComposioProvider } from "../src/provider_composio.ts";
import { makeSignature } from "../src/signature.ts";

// ---------------------------------------------------------------------------
// The gate, in this file. The other copy is in tasks/ten_read_tasks.json, and
// they are cross-checked at startup.
// ---------------------------------------------------------------------------
// Two books that must agree, for the reason HARNESS-LAWS law 2 gives about
// tape: the only cost of a number nobody can check is a comment. Softening
// this gate should cost two edits in two files in one diff, and be visible in
// both.
const GATE_MIN_CORRECT = 9;
const GATE_OF = 10;
const GATE_P50_MS = 3000;

const CLEAN = 0;
const BROKEN = 1;
const UNPROVEN = 2;

function env(name: string): string {
  const raw = process.env[name];
  return typeof raw === "string" ? raw.trim() : "";
}

const HERE = dirname(fileURLToPath(import.meta.url));
const SPIKE = resolve(HERE, "..");
const TASKS_FILE = join(HERE, "ten_read_tasks.json");
const LOCAL_FILE = join(HERE, "ten_read_tasks.local.json");
const RESULTS_DIR = join(SPIKE, "results");

const OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions";
const COMPOSIO_LIVE_URL = "https://backend.composio.dev/api/v3.1";

// ---------------------------------------------------------------------------
// STAND-INS, and why they can never produce a pass.
// ---------------------------------------------------------------------------
// Both endpoints can be pointed somewhere else. That exists for exactly one
// reason: without it the measuring half of this harness — the ten-task loop,
// the seatbelt, the argument fill, the grade, the table, the results file —
// could never be executed until the day a real key arrived, and a 700-line gate
// that has never run once is the thing this repo keeps getting burned by.
//
// The danger is obvious and is closed structurally rather than by a warning: a
// run that talked to a stand-in CANNOT exit 0. `simulated` forces UNPROVEN
// whatever the ten rows say, the banner is printed at the top and the bottom,
// and the results file carries `simulated: true` in its own field so a file
// found later cannot be mistaken for a measurement. HARNESS-LAWS law 3 says a
// fix is not done until its leg is green against the LIVE system; a green leg
// against a fixture would be that law defeated by its own instrument.
const COMPOSIO_BASE_URL = env("COMPOSIO_BASE_URL") || COMPOSIO_LIVE_URL;
const MODEL_URL = env("TWO_HANDS_OPENROUTER_URL") || OPENROUTER_URL;
const SIMULATED = COMPOSIO_BASE_URL !== COMPOSIO_LIVE_URL || MODEL_URL !== OPENROUTER_URL;
// The brain's own default (brain/llm.py DEFAULT_MODEL), read from the same env
// var, so the gate measures the model the product actually ships with rather
// than a better one chosen for the demo.
const MODEL = process.env.ANTICIPY_MODEL || "deepseek/deepseek-v3.2";

// How many candidates the judge is asked about per step. The router's own
// default; named here only so the results file can record what it was.
const CANDIDATE_LIMIT = 5;

// A vendor schema can be tens of kilobytes of JSON Schema. The judge needs its
// shape, not its every enum member, and an untruncated one turns one gate run
// into a bill. Truncation is visible to the model (the marker is left in) so it
// can answer "unclear" rather than guess about a field it cannot see.
const SCHEMA_CHARS = 4000;
// The grader sees the response. Same reasoning, plus: the longer this is, the
// more of the owner's mailbox crosses the boundary.
const RESPONSE_CHARS = 6000;

// ---------------------------------------------------------------------------
// Shapes.
// ---------------------------------------------------------------------------
export interface GradeRubric {
  right_is: string;
  checkable_from_the_response: string[];
  wrong_if: string[];
  only_the_owner_can_confirm: string[];
}

export interface TaskSpec {
  id: string;
  prompt: string;
  expected_effect: string;
  signature: CapabilitySignature;
  how_to_grade: GradeRubric;
}

/** What a task ended up being, in the results file and in the table.
 *
 *  `unmeasured` is the state that keeps this gate honest. A task whose grader
 *  could not be reached, or whose vendor search threw, produced no evidence
 *  about the API hand — and scoring it as wrong would let a network blip read
 *  as a product failure, while scoring it as right would be a lie. One
 *  unmeasured task takes the whole run to UNPROVEN. */
type RowStatus = "correct" | "wrong" | "unmeasured";

interface Row {
  id: string;
  app_hint: string | null;
  status: RowStatus;
  /** The grader's four-state verdict, or null when nothing was graded. */
  verdict: MatchVerdict | null;
  tool_slug: string | null;
  /** ExecResult.ms — the API hand's own latency, and the leg the gate reads. */
  api_ms: number | null;
  /** Wall clock for the whole step: search, judge, argument fill, execute,
   *  grade. Printed beside api_ms because it is what the OWNER waits, and a
   *  gate that only ever reported the fast half would be measuring the hand
   *  with the executor's costs hidden. */
  total_ms: number;
  /** null, never 0, when Composio declared no price. A ledger that totals
   *  unknown as zero reports the API hand as free. */
  api_cost_usd: number | null;
  model_cost_usd: number | null;
  note: string;
  response_sha256: string | null;
  response_bytes: number | null;
  rung_after: number | null;
}

// ---------------------------------------------------------------------------
// Small plumbing.
// ---------------------------------------------------------------------------
function say(mark: string, title: string, detail = ""): void {
  console.log(`  [${mark}] ${title}`);
  if (detail) console.log(`        ${detail}`);
}

function sha16(text: string): string {
  return createHash("sha256").update(text).digest("hex").slice(0, 16);
}

/** One redaction pass over model prose before it is written to a file that
 *  gets committed. Addresses and long digit runs only — this is the same class
 *  of check as provider_composio's `#safe`, string plumbing over a machine's
 *  output, not a rule about what a sentence means. It is a second line of
 *  defence: the grader is asked in its prompt not to quote content, and a
 *  prompt is a request, not a guarantee. */
function redact(text: unknown): string {
  return String(text ?? "")
    .replace(/[^\s@]+@[^\s@]+\.[^\s@]+/g, "[address]")
    .replace(/\b\d{7,}\b/g, "[number]")
    .slice(0, 240);
}

function money(v: number | null): string {
  // "—" and not "0.0000". The difference between "this call was free" and
  // "nobody told us what this call cost" is the whole of the premium-tool
  // argument, and a zero in a cost column erases it.
  return v === null ? "—" : `$${v.toFixed(4)}`;
}

/** Pull one JSON object out of a model reply. Models fence their JSON, prefix
 *  it with "Sure!", or both. A parse failure is NOT recovered from with a
 *  regex over the prose — it returns null, and every caller treats null as
 *  "the model did not answer", which is a different thing from "the model said
 *  no". */
function jsonFromReply(text: string): Record<string, unknown> | null {
  const trimmed = String(text ?? "").trim();
  const fenced = trimmed.replace(/^```(?:json)?/i, "").replace(/```$/, "").trim();
  const start = fenced.indexOf("{");
  const end = fenced.lastIndexOf("}");
  if (start < 0 || end <= start) return null;
  try {
    const parsed = JSON.parse(fenced.slice(start, end + 1));
    return parsed !== null && typeof parsed === "object" && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : null;
  } catch {
    return null;
  }
}

/** The four states, read strictly. Anything the model invented — "YES",
 *  "probably", a missing field — becomes "no-verdict", which every caller here
 *  treats as NOT a licence and NOT a pass. Coercing "YES" to "yes" would be
 *  this file deciding what the model meant. */
function asVerdict(raw: unknown): MatchVerdict {
  return raw === "yes" || raw === "no" || raw === "unclear" ? raw : "no-verdict";
}

// ---------------------------------------------------------------------------
// The model wire. One function, three callers.
// ---------------------------------------------------------------------------
// Not imported from brain/llm.py: the spike fence (test/no_production_imports.ts)
// forbids it, and week 1 is a spike. It is the same endpoint, the same env var,
// the same default model and the same fixed seed, so the gate measures the
// brain's model even though it cannot use the brain's code.
interface ModelReply {
  text: string;
  costUsd: number | null;
  ms: number;
}

class ModelUnreachable extends Error {
  readonly op: string;
  constructor(op: string, detail: string) {
    super(`${op}: ${detail}`);
    this.name = "ModelUnreachable";
    this.op = op;
  }
}

async function callModel(apiKey: string, op: string, system: string, user: string): Promise<ModelReply> {
  const started = performance.now();
  let res: Response;
  try {
    res = await fetch(MODEL_URL, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "HTTP-Referer": "https://anticipy.ai",
        "X-Title": "Anticipy two-hands spike",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: MODEL,
        temperature: 0,
        // Ask for the price of the call with the call. Without it, `usage`
        // carries token counts and no money, and the cost column in the
        // results file would have to be reconciled against the account ledger
        // by hand — which means it would not be.
        usage: { include: true },
        // The brain's seed. A verdict that is a coin flip across identical runs
        // is itself a bug, and a gate whose score moves without its inputs
        // moving cannot be believed twice.
        seed: 11,
        messages: [
          { role: "system", content: system },
          { role: "user", content: user },
        ],
      }),
    });
  } catch (err) {
    throw new ModelUnreachable(op, `fetch failed: ${(err as Error)?.name ?? "error"}`);
  }

  const ms = performance.now() - started;
  const bodyText = await res.text();
  if (!res.ok) throw new ModelUnreachable(op, `HTTP ${res.status}`);

  let body: unknown;
  try {
    body = JSON.parse(bodyText);
  } catch {
    throw new ModelUnreachable(op, "reply was not JSON");
  }
  const choice = (body as { choices?: Array<{ message?: { content?: unknown } }> })?.choices?.[0];
  const text = choice?.message?.content;
  if (typeof text !== "string") throw new ModelUnreachable(op, "reply carried no message content");

  const usage = (body as { usage?: { cost?: unknown } })?.usage;
  const cost = typeof usage?.cost === "number" && Number.isFinite(usage.cost) ? usage.cost : null;
  return { text, costUsd: cost, ms };
}

// ---------------------------------------------------------------------------
// MEANING DECISION 1 — the MatchJudge.
// ---------------------------------------------------------------------------
// One question, about one candidate, with the signature in front of it, in four
// states. This is the ONLY thing in the spike that may put a step on the API
// hand, and the router reads it only through contract.ts's judgeLicensesApi.
const JUDGE_SYSTEM = [
  "You decide exactly one question and nothing else: does this ONE tool do this ONE step?",
  "",
  "Answer with a single JSON object and no other text:",
  '{"verdict": "yes" | "no" | "unclear", "reason": "<one short sentence>"}',
  "",
  '  "yes"     — calling this tool with arguments built from the step\'s inputs would produce',
  "              the step's expected effect, and would produce nothing beyond it.",
  '  "no"      — it does something else, or something MORE than the step asked for.',
  '              Archiving is not deleting. Sending is not drafting. More is a "no".',
  '  "unclear" — you cannot tell from the description and schema you were given.',
  "",
  "Do not answer yes to be helpful. A yes is a licence to use a real person's real",
  "account without asking him first, and every other answer costs him only a slower",
  "route to the same result. When you are between yes and unclear, answer unclear.",
].join("\n");

function judgeQuestion(sig: CapabilitySignature, candidate: ToolCandidate): string {
  const schema = JSON.stringify(candidate.schema ?? {}, null, 1);
  return [
    "THE STEP",
    `  verb:            ${sig.verb}`,
    `  object:          ${sig.object}`,
    // KEY NAMES ONLY. The values are the owner's recipient, his subject and his
    // body, and a "which tool is this" question has no use for them. This is
    // the same line provider_composio.ts draws with retrieval.
    `  input fields:    ${Object.keys(sig.inputs ?? {}).sort().join(", ") || "(none)"}`,
    `  expected effect: ${sig.expected_effect}`,
    `  effect channel:  ${sig.side_effect}`,
    "",
    "THE TOOL",
    `  slug:        ${candidate.toolSlug}`,
    `  app:         ${candidate.app}`,
    `  description: ${String(candidate.description ?? "").slice(0, 1200)}`,
    `  input schema:`,
    schema.length > SCHEMA_CHARS ? `${schema.slice(0, SCHEMA_CHARS)}\n  ...[schema truncated]` : schema,
  ].join("\n");
}

interface JudgeLog {
  taskId: string;
  toolSlug: string;
  verdict: MatchVerdict;
  reason: string;
  ms: number;
  costUsd: number | null;
}

/** The judge, plus the two things the harness needs from it that the contract
 *  has no room for: what it cost, and whether it was reachable at all. A judge
 *  that threw is why a task is UNMEASURED rather than wrong — the router turns
 *  an unreachable judge into a browser decision, and without this flag the
 *  harness would file a dead model as "the API hand could not do it". */
class OpenRouterJudge implements MatchJudge {
  readonly log: JudgeLog[] = [];
  unreachable = 0;
  #apiKey: string;
  #taskId = "";

  constructor(apiKey: string) {
    this.#apiKey = apiKey;
  }

  forTask(taskId: string): void {
    this.#taskId = taskId;
  }

  async matches(sig: CapabilitySignature, candidate: ToolCandidate): Promise<MatchAnswer> {
    let reply: ModelReply;
    try {
      reply = await callModel(this.#apiKey, "judge", JUDGE_SYSTEM, judgeQuestion(sig, candidate));
    } catch (err) {
      this.unreachable++;
      // Rethrown on purpose. The router reads a throw as "the judge is
      // unreachable" and stops asking about the remaining candidates, which is
      // right: it is a property of the judge, not of candidate #1, and asking
      // four more times costs the owner four more timeouts.
      throw err;
    }
    const parsed = jsonFromReply(reply.text);
    const verdict = asVerdict(parsed?.verdict);
    const reason = redact(parsed?.reason ?? "");
    this.log.push({
      taskId: this.#taskId,
      toolSlug: candidate.toolSlug,
      verdict,
      reason,
      ms: reply.ms,
      costUsd: reply.costUsd,
    });
    return { verdict, reason };
  }
}

// ---------------------------------------------------------------------------
// MEANING DECISION 2 — the arguments.
// ---------------------------------------------------------------------------
// Nothing in this spike fills a vendor schema from a signature, and nothing
// should: "which of this tool's twelve fields carries 'tomorrow' " is a
// question about what the owner meant, and a key-name table that answered it
// would be the exact list-of-names this whole exercise is forbidden to build.
// So it is asked, once, of the model, with the clock in front of it.
const ARGS_SYSTEM = [
  "You are building the arguments for one API call. Answer with a single JSON object",
  "and no other text:",
  '{"arguments": { ... }, "confident": true | false, "note": "<one short sentence>"}',
  "",
  "Rules:",
  "  - Use only fields the schema declares. An invented field is rejected by the vendor",
  "    and the owner sees a failed errand.",
  "  - Resolve every relative time ('tomorrow', 'this week', 'since yesterday') against",
  "    the clock and timezone you are given, not against UTC and not against a date in",
  "    the example inputs. The example values are stale on purpose.",
  "  - This is a READ. Do not set any field that writes, sends, deletes, marks as read,",
  "    moves a read cursor, or changes a label. If the only way to satisfy the step is",
  "    to set such a field, answer with confident:false and say so.",
  "  - If you cannot build arguments you believe in, answer confident:false rather than",
  "    guessing. A wrong window returns a confident, complete, wrong answer, and that is",
  "    worse than no answer.",
].join("\n");

function argsQuestion(task: TaskSpec, tool: ToolCandidate, nowIso: string, tz: string): string {
  const schema = JSON.stringify(tool.schema ?? {}, null, 1);
  return [
    `THE OWNER SAID: ${task.prompt}`,
    "",
    "THE STEP",
    `  verb:            ${task.signature.verb}`,
    `  object:          ${task.signature.object}`,
    `  expected effect: ${task.signature.expected_effect}`,
    `  example inputs (SHAPE ONLY — the values are stale):`,
    `    ${JSON.stringify(task.signature.inputs ?? {})}`,
    "",
    "THE CLOCK",
    `  now:      ${nowIso}`,
    `  timezone: ${tz}`,
    "",
    "THE TOOL",
    `  slug:   ${tool.toolSlug}`,
    `  app:    ${tool.app}`,
    `  schema:`,
    schema.length > SCHEMA_CHARS ? `${schema.slice(0, SCHEMA_CHARS)}\n  ...[schema truncated]` : schema,
  ].join("\n");
}

// ---------------------------------------------------------------------------
// MEANING DECISION 3 — the grade.
// ---------------------------------------------------------------------------
// Same four states and the same FLOOR polarity as the judge: only "yes" counts.
// A grader that is down, confused, or silent scores zero, because a gate whose
// missing state passed would go green the day the model stopped answering.
const GRADE_SYSTEM = [
  "You are grading one API read against a rubric written before the call was made.",
  "Answer with a single JSON object and no other text:",
  '{"verdict": "yes" | "no" | "unclear", "reason": "<one short sentence>"}',
  "",
  '  "yes"     — every line of "checkable_from_the_response" holds, and no line of',
  '              "wrong_if" holds.',
  '  "no"      — any "wrong_if" line holds, or a "checkable" line plainly fails.',
  '  "unclear" — the response does not contain what you would need to tell.',
  "",
  'The rubric\'s "only_the_owner_can_confirm" lines are NOT yours to grade. They are',
  "about completeness — whether something is missing — and the response cannot show you",
  "that. Ignore them entirely; a human settles those.",
  "",
  "An empty result is not automatically wrong. 'It has not arrived' and 'you have nothing",
  "booked' are correct answers to the questions that ask them, and the rubric says which.",
  "",
  "YOUR REASON IS WRITTEN TO A FILE THAT GETS COMMITTED. Describe the SHAPE of what you",
  "saw — 'three events, all inside the window' — and never quote a name, an address, a",
  "subject line or a message body.",
].join("\n");

function gradeQuestion(task: TaskSpec, args: Record<string, unknown>, responseText: string): string {
  return [
    `THE OWNER ASKED: ${task.prompt}`,
    "",
    `THE EXPECTED EFFECT: ${task.signature.expected_effect}`,
    "",
    "THE RUBRIC",
    JSON.stringify(task.how_to_grade, null, 1),
    "",
    "THE CALL THAT WAS MADE",
    JSON.stringify(args),
    "",
    "THE RESPONSE",
    responseText.length > RESPONSE_CHARS
      ? `${responseText.slice(0, RESPONSE_CHARS)}\n...[response truncated]`
      : responseText,
  ].join("\n");
}

// ---------------------------------------------------------------------------
// LOADING — the half that is answerable with no key.
// ---------------------------------------------------------------------------
export interface LoadedTasks {
  tasks: TaskSpec[];
  tokens: string[];
}

export class TaskFileBroken extends Error {}

export function loadTasks(tasksFile: string = TASKS_FILE): LoadedTasks {
  let doc: {
    gate?: { min_correct?: unknown; of?: unknown; p50_ms_max?: unknown };
    tasks?: unknown;
  };
  try {
    doc = JSON.parse(readFileSync(tasksFile, "utf8"));
  } catch (err) {
    throw new TaskFileBroken(`ten_read_tasks.json could not be read: ${(err as Error).message}`);
  }

  // The gate's two books must agree. Softening the run in one file and leaving
  // the documented number in the other is how a scoreboard starts lying while
  // still printing a threshold nobody re-reads.
  const g = doc.gate ?? {};
  if (g.min_correct !== GATE_MIN_CORRECT || g.of !== GATE_OF || g.p50_ms_max !== GATE_P50_MS) {
    throw new TaskFileBroken(
      `the gate is written twice and the copies disagree: json says ${JSON.stringify(g)}, ` +
        `run_ten.ts says {min_correct:${GATE_MIN_CORRECT}, of:${GATE_OF}, p50_ms_max:${GATE_P50_MS}}`,
    );
  }

  const raw = doc.tasks;
  if (!Array.isArray(raw) || raw.length !== GATE_OF) {
    throw new TaskFileBroken(`expected ${GATE_OF} tasks, found ${Array.isArray(raw) ? raw.length : "none"}`);
  }

  const tasks: TaskSpec[] = [];
  const ids = new Set<string>();
  for (const entry of raw as TaskSpec[]) {
    if (!entry || typeof entry.id !== "string" || typeof entry.prompt !== "string") {
      throw new TaskFileBroken("a task is missing its id or its prompt");
    }
    if (ids.has(entry.id)) throw new TaskFileBroken(`two tasks share the id ${entry.id}`);
    ids.add(entry.id);

    // Re-derive the hash from the fields beside it. A task file whose hashes
    // have drifted from `signature.ts` measures capabilities keyed to nothing:
    // the ledger would file every run under a hash the router never computes,
    // ten rungs would be earned and none of them would ever be read, and every
    // row here would still be green.
    const rebuilt = makeSignature({
      app_hint: entry.signature?.app_hint ?? null,
      verb: entry.signature?.verb,
      object: entry.signature?.object,
      inputs: entry.signature?.inputs ?? {},
      expected_effect: entry.signature?.expected_effect,
      side_effect: entry.signature?.side_effect,
      account_hint: entry.signature?.account_hint ?? null,
    });
    if (rebuilt.signature_hash !== entry.signature?.signature_hash) {
      throw new TaskFileBroken(
        `${entry.id}: stored hash ${entry.signature?.signature_hash} but makeSignature computes ${rebuilt.signature_hash}`,
      );
    }
    // A {{TOKEN}} in a HASHED field is a broken task file, not a hole the owner
    // fills. The hash is sha1(verb + object + sorted input KEY names): fill the
    // token and the run is filed under a hash the router never computes, so ten
    // rungs are earned and none is ever read; leave it and the judge is asked
    // whether a tool does a step about "{{PERSON_A}}". Neither is a
    // measurement, so the file is refused with the reason named.
    //
    // Both spellings of the field. makeSignature lower-cases the object, so a
    // hand-written {{PERSON_A}} reads as {{person_a}} once it has been through
    // it — and the task file stores the normalised form, so which of the two a
    // token turns up in depends only on how the entry was authored. A check
    // that saw one spelling and not the other would be a check that passes on
    // half the ways of committing the mistake. The case-blindness this needs
    // now lives in PLACEHOLDER itself, which is what the filler and the sweep
    // read too; it used to be a second regex only this line had, and the gap
    // between the two copies is the hole described at PLACEHOLDER.
    const hashedText = [
      String(entry.signature?.object ?? ""),
      rebuilt.object,
      ...Object.keys(entry.signature?.inputs ?? {}),
      ...Object.keys(rebuilt.inputs ?? {}),
    ].join(" ");
    const inHash = [...new Set(placeholdersIn(hashedText))];
    if (inHash.length > 0) {
      throw new TaskFileBroken(
        `${entry.id}: {{${inHash.join("}}, {{")}}} sits in a hashed field (the object, or an input KEY name); ` +
          "a placeholder there cannot be filled without moving the signature hash, and left in place it asks " +
          "the judge whether a tool does a step about a token",
      );
    }
    // THE SEATBELT, at the earliest possible moment. This gate runs against the
    // owner's real Gmail with no confirmation step and no undo; a write that
    // got into this file — by an edit, by a merge, by a well-meaning "let's
    // also test send" — would be executed silently. Effect channels are what
    // HARNESS-LAWS law 1 permits a structural check to read.
    if (rebuilt.side_effect !== "read") {
      throw new TaskFileBroken(`${entry.id} declares side_effect ${rebuilt.side_effect}; this gate runs reads only`);
    }
    const rubric = entry.how_to_grade;
    if (!rubric || typeof rubric.right_is !== "string" || !Array.isArray(rubric.checkable_from_the_response)) {
      throw new TaskFileBroken(`${entry.id}: how_to_grade is missing, so grading it would be vibes`);
    }
    tasks.push({ ...entry, signature: rebuilt });
  }

  return { tasks, tokens: tokensIn(tasks) };
}

/** The gate's placeholder syntax, written once. The filler, the blocker and
 *  the hashed-field refusal read the same constant on purpose: two copies of
 *  this regex is how a hole gets filled by one and reported by neither.
 *
 *  IT IS CASE-BLIND, and there used to be two of these. The filler and the
 *  sweep shared `[A-Z0-9_]` while the hashed-field refusal kept a second,
 *  any-case copy for itself. The gap between the two copies is exactly the
 *  hole the shared-constant comment above says cannot happen: `{{person_a}}`
 *  in the prompt, in `expected_effect` or in the grading rubric was not a
 *  placeholder as far as the gate was concerned, so it was neither filled nor
 *  reported — the run went out to the owner's real Gmail and the GRADER was
 *  handed a rubric naming a literal `{{person_a}}`, and the gate printed a
 *  score for that row. Mixed case is not an exotic way to author one either:
 *  `makeSignature` lower-cases `object`, so a hand-typed {{PERSON_A}} comes
 *  back out of it as {{person_a}} without anyone choosing that.
 *
 *  IT TOLERATES PADDING — `{{ PERSON_A }}` — for the same reason and from the
 *  same defect. Every templating language a person has ever met accepts those
 *  spaces, and before this the padded form was invisible in EVERY direction at
 *  once: `tokensIn` did not list it, so the owner was never asked for it;
 *  `substitute` neither filled nor reported it, so nothing blocked; and the
 *  literal reached the judge and the grader. The padding is tolerated rather
 *  than merely refused because the owner HAS an answer for that token and the
 *  run can simply work.
 *
 *  The inside stays one word of `[A-Za-z0-9_]`. This is not a step towards
 *  matching anything between two braces: a pattern that loose starts reading
 *  ordinary prose as a hole, and a gate that refuses on prose gets deleted by
 *  the next person in a hurry. The KNOWN residual is a brace pair the filler
 *  cannot name at all (`{{first-name}}`, `{{PERSON A}}`, `{{}}`): it is not
 *  filled and not reported, because there is no key the owner could write to
 *  close it — see RESULTS.md §9.
 *
 *  Shared as one `/g` object safely, and only because of how it is used:
 *  `String.replace` resets `lastIndex` to 0 on a global regex and leaves it
 *  there, and `matchAll` matches against a clone. Anything that called
 *  `.exec()` on this object would leave state behind and the next scan would
 *  start mid-string — the shape where a check skips the very text it exists to
 *  read. Do not add one. */
const PLACEHOLDER = /\{\{\s*([A-Za-z0-9_]+)\s*\}\}/g;

/** One spelling for a token, everywhere it is compared, reported or looked up.
 *
 *  Uppercase because that is the spelling the owner is told to write in
 *  `ten_read_tasks.local.json` (RESULTS.md §3 step 5). Normalising anywhere
 *  else would make `{{person_a}}` a hole he cannot close: the harness would ask
 *  him for `person_a`, the answer he already wrote under `PERSON_A` would not
 *  be found, and the only way out would be guessing at the case. */
function tokenName(raw: string): string {
  return raw.toUpperCase();
}

function placeholdersIn(text: string): string[] {
  return [...text.matchAll(PLACEHOLDER)].map((m) => tokenName(m[1]));
}

/** Every {{TOKEN}} anywhere in the task list.
 *
 *  Over the SERIALIZED task, deliberately, rather than over a list of fields.
 *  This used to read the prompt and the input values only, so a token in
 *  `how_to_grade` or in `expected_effect` — both handed to a model verbatim —
 *  was not a token as far as the harness was concerned. A list of fields is
 *  only ever as complete as the last person who added one to
 *  ten_read_tasks.json, and the cost of it being short is a gate that runs and
 *  SCORES a task whose rubric names a colleague who does not exist. */
export function tokensIn(tasks: TaskSpec[]): string[] {
  const found = new Set<string>();
  for (const t of tasks) for (const name of placeholdersIn(JSON.stringify(t))) found.add(name);
  return [...found].sort();
}

/** Fill every string in a value, however deep, leaving KEYS alone.
 *
 *  Keys are left alone because input key names are in the signature hash: a
 *  token in one cannot be filled without moving the hash, so loadTasks refuses
 *  the file instead. Values are free — the hash excludes them by design. */
function fillDeep<T>(value: T, fill: (text: string) => string): T {
  if (typeof value === "string") return fill(value) as unknown as T;
  if (Array.isArray(value)) return value.map((v) => fillDeep(v, fill)) as unknown as T;
  if (value !== null && typeof value === "object") {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) out[k] = fillDeep(v, fill);
    return out as unknown as T;
  }
  return value;
}

/** Fill the owner's answers in, EVERYWHERE a placeholder can appear. Returns
 *  the tokens still empty; the caller refuses to run while that list is
 *  non-empty, because a task asking about a colleague who does not exist grades
 *  the API hand wrong for a fact about the fixture.
 *
 *  This filled the prompt and the top-level string values of `signature.inputs`
 *  and nothing else, which left three fields carrying `{{PERSON_A}}` straight
 *  into a live run: `expected_effect` (printed to the judge AND to the grader),
 *  `object` (printed to the judge) and the whole `how_to_grade` rubric (handed
 *  to the grader verbatim). The blocker looked at the same two fields, so it
 *  could not see them either — the gate would call the owner's real Gmail and
 *  then score the answer against a rubric about a person who does not exist,
 *  and report a number for it.
 *
 *  Three changes keep that shut. The filler walks the whole task rather than a
 *  list of fields; `PLACEHOLDER` is case-blind, so a hand-typed `{{person_a}}`
 *  is the same hole as `{{PERSON_A}}`; and the blocker is a SWEEP over the
 *  serialized result: if anything anywhere still looks like a placeholder after
 *  filling, the run is refused, whether or not this function knew the field
 *  existed.
 *
 *  The sweep earns its place on the two cases the filler CANNOT report, and
 *  both have legs in `test/run_ten.test.ts`: a token in a KEY, which `fillDeep`
 *  is forbidden to touch because input key names are hashed; and an answer that
 *  is ITSELF a placeholder, because `String.replace` does not re-scan what a
 *  replacement function returned. In both the filler finishes reporting
 *  nothing missing while a literal `{{TOKEN}}` sits in the text a model is
 *  about to be handed. */
export function substitute(
  tasks: TaskSpec[],
  answers: Record<string, string>,
): { tasks: TaskSpec[]; missing: string[] } {
  const missing = new Set<string>();
  const fill = (text: string): string =>
    text.replace(PLACEHOLDER, (all: string, raw: string) => {
      const name = tokenName(raw);
      const value = answers[name];
      if (typeof value !== "string" || value.trim() === "") {
        missing.add(name);
        // The ORIGINAL spelling back, unedited. Rewriting an unanswered
        // {{person_a}} to {{PERSON_A}} would quietly change a task the owner
        // is about to be shown the refusal for, and the sweep below reads it
        // the same either way.
        return all;
      }
      return value;
    });

  const filled = tasks.map((t) => {
    const inputs = fillDeep(t.signature.inputs ?? {}, fill) as Record<string, unknown>;
    // Rebuilt rather than mutated: `makeSignature` freezes what it returns, and
    // the whole point of that freeze is that a step cannot be edited into
    // something its hash no longer describes. Substituting VALUES cannot change
    // the hash (values are excluded by design) and this asserts it below.
    const signature = makeSignature({
      app_hint: t.signature.app_hint,
      verb: t.signature.verb,
      object: fill(t.signature.object),
      inputs,
      expected_effect: fill(t.signature.expected_effect),
      side_effect: t.signature.side_effect,
      account_hint: t.signature.account_hint,
    });
    if (signature.signature_hash !== t.signature.signature_hash) {
      // Reachable one way only: a {{TOKEN}} in a HASHED field — the object, or
      // an input key name — that this call has just filled in. loadTasks
      // refuses such a file by name; this is the same refusal for a task that
      // did not come through it.
      throw new TaskFileBroken(
        `${t.id}: filling a placeholder moved the signature hash, so a {{TOKEN}} sits in a hashed field ` +
          "(the object, or an input KEY name); the ledger would key the run to a capability nothing else computes",
      );
    }
    return { ...(fillDeep(t, fill) as TaskSpec), signature };
  });

  // THE SWEEP. `missing` above only knows about tokens the filler walked past.
  // This asks the finished task the adversary's question instead — is there
  // anything left in here that looks like a placeholder — so a field added to
  // the task file next month is covered without editing this function.
  for (const t of filled) for (const name of placeholdersIn(JSON.stringify(t))) missing.add(name);

  return { tasks: filled, missing: [...missing].sort() };
}

function readAnswers(): Record<string, string> {
  try {
    const parsed = JSON.parse(readFileSync(LOCAL_FILE, "utf8"));
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      const out: Record<string, string> = {};
      for (const [k, v] of Object.entries(parsed)) if (typeof v === "string") out[k] = v;
      return out;
    }
  } catch {
    // Absent is the normal state on a fresh clone, and it is a precondition the
    // owner fills, not an error in the harness.
  }
  return {};
}

// ---------------------------------------------------------------------------
// The provider, wrapped so a vendor outage is visible.
// ---------------------------------------------------------------------------
// `gatherCandidates` in router.ts swallows a search throw and returns an empty
// list, which is right for the ROUTER (a dead vendor is a reason to use the
// other hand, not to fail the owner) and wrong for a GATE: an empty list from a
// vendor that is down and an empty list from a catalog with no such tool are
// the same array, and one of them is a measurement while the other is not.
class WatchedProvider implements Provider {
  readonly name: "composio";
  searchErrors = 0;
  lastError = "";
  #inner: ComposioProvider;

  constructor(inner: ComposioProvider) {
    this.#inner = inner;
    this.name = "composio";
  }

  async search(sig: CapabilitySignature, userId: string, opts: { connectedOnly: boolean; limit: number }) {
    try {
      return await this.#inner.search(sig, userId, opts);
    } catch (err) {
      this.searchErrors++;
      this.lastError = `${(err as Error)?.name ?? "Error"}: ${(err as Error)?.message ?? ""}`.slice(0, 160);
      throw err;
    }
  }
  connections(userId: string) {
    return this.#inner.connections(userId);
  }
  connectLink(userId: string, app: string, scopes?: string[]) {
    return this.#inner.connectLink(userId, app, scopes);
  }
  execute(userId: string, toolSlug: string, args: Record<string, unknown>, accountId?: string) {
    return this.#inner.execute(userId, toolSlug, args, accountId);
  }
}

// ---------------------------------------------------------------------------
// The table.
// ---------------------------------------------------------------------------
/** Markdown, ten rows, and it throws rather than render zero of them.
 *
 *  This is the guard the header promises. A table is what gets screenshotted
 *  and pasted into a status update, and an empty one is indistinguishable from
 *  a full one at a glance a week later. A run that could not happen prints the
 *  word UNPROVEN instead, which cannot be mistaken for a result.
 *
 *  A row exists only for a task that was actually attempted, and every number
 *  in it was measured on this process. An `unmeasured` row shows a dash where
 *  a latency or a cost would be — never a zero — because zero is a measurement
 *  and "we never got that far" is not. */
function noteCell(note: string): string {
  const flat = String(note ?? "").replace(/\|/g, "/").replace(/\s+/g, " ").trim();
  return flat.length <= 96 ? flat : `${flat.slice(0, 95)}…`;
}

function printTable(rows: Row[]): void {
  if (rows.length === 0) {
    throw new Error("printTable was asked to render an empty gate; a run that did not happen has no table");
  }
  const head = "| task | tool | api ms | total ms | api cost | model cost | verdict | note |";
  const sep = "|---|---|---:|---:|---:|---:|---|---|";
  console.log(head);
  console.log(sep);
  for (const r of rows) {
    const mark = r.status === "correct" ? "right" : r.status === "wrong" ? "WRONG" : "unmeasured";
    console.log(
      [
        "",
        r.id,
        r.tool_slug ?? "—",
        r.api_ms === null ? "—" : String(Math.round(r.api_ms)),
        String(Math.round(r.total_ms)),
        money(r.api_cost_usd),
        money(r.model_cost_usd),
        `${mark}${r.verdict ? ` (${r.verdict})` : ""}`,
        // Truncated with a marker, never silently: the note is where "connect
        // notion" and "the call failed: auth" live, and a note that stops
        // mid-word reads as a corrupted row rather than a shortened one.
        noteCell(r.note),
        "",
      ].join(" | ").trim(),
    );
  }
}

// ---------------------------------------------------------------------------
// The run.
// ---------------------------------------------------------------------------
async function main(): Promise<number> {
  console.log("");
  console.log("  THE WEEK-1 GATE — ten reads through the API hand");
  console.log("  --------------------------------------------------------------");
  if (SIMULATED) {
    console.log("  !! STAND-IN RUN — an endpoint was redirected by an env var.");
    console.log(`  !!   composio: ${COMPOSIO_BASE_URL}`);
    console.log(`  !!   model:    ${MODEL_URL}`);
    console.log("  !! This exercises the harness. It CANNOT pass, whatever the rows say.");
    console.log("  --------------------------------------------------------------");
  }

  // ---- PART 1: what is answerable here, with no key --------------------
  let loaded: LoadedTasks;
  try {
    loaded = loadTasks();
    say("PASS", "THE TASK FILE HOLDS", `${loaded.tasks.length} reads, every hash re-derived, no writes`);
  } catch (err) {
    if (err instanceof TaskFileBroken) {
      say("FAIL", "THE TASK FILE HOLDS", err.message);
      console.log("  --------------------------------------------------------------");
      console.log("  BROKEN — a source-level check failed. Fix that before anything");
      console.log("  else; a live key cannot rescue a task list that is wrong on the");
      console.log("  page.");
      return BROKEN;
    }
    throw err;
  }

  // ---- PART 2: can the run happen at all -------------------------------
  const composioKey = env("COMPOSIO_API_KEY");
  const openrouterKey = env("OPENROUTER_API_KEY");
  const userId = env("TWO_HANDS_OWNER") || env("ANTICIPY_OWNER") || "owner";
  const tz = env("TWO_HANDS_TZ") || Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";

  const blockers: string[] = [];
  if (!composioKey) blockers.push("COMPOSIO_API_KEY is not set — there is no vendor to call.");
  if (!openrouterKey) {
    blockers.push("OPENROUTER_API_KEY is not set — nothing can judge a tool or grade an answer.");
  }

  const { tasks, missing } = substitute(loaded.tasks, readAnswers());
  if (missing.length > 0) {
    blockers.push(
      `these placeholders are unfilled in tasks/ten_read_tasks.local.json: ${missing.join(", ")} — ` +
        "the gate will not ask the owner's accounts about invented people.",
    );
  }

  let connections: ConnectedApp[] = [];
  let provider: WatchedProvider | null = null;
  if (composioKey) {
    provider = new WatchedProvider(new ComposioProvider({ apiKey: composioKey, baseUrl: COMPOSIO_BASE_URL }));
    try {
      connections = await provider.connections(userId);
    } catch (err) {
      blockers.push(
        `Composio would not answer connections() for owner "${userId}": ` +
          `${(err as Error)?.name ?? "Error"} — a vendor that is down is an absent measurement, not a failing one.`,
      );
    }
    const active = connections.filter((c) => c.status === "active");
    if (blockers.length === 0 && active.length === 0) {
      blockers.push(
        `owner "${userId}" has no ACTIVE connection on Composio (${connections.length} row(s) returned) — ` +
          "either connect Google Calendar, Gmail, Notion and Slack through a Connect Link, or set " +
          "TWO_HANDS_OWNER to the Composio user_id the connections were actually made under. " +
          "An empty list reads the same either way, so check the id before assuming the connections are missing.",
      );
    }
  }

  if (blockers.length > 0) {
    say("fail", "THE RUN CAN HAPPEN AT ALL", `${blockers.length} thing(s) missing`);
    console.log("  --------------------------------------------------------------");
    console.log("  UNPROVEN — no call was made, so there is nothing to report.");
    console.log("  This is the honest steady state for week 1, not a soft fail and");
    console.log("  not a pass. HARNESS-LAWS law 3: repo-green is not done, and this");
    console.log("  is further back than repo-green — it is a gate that has never");
    console.log("  had a live system to run against.");
    console.log("");
    console.log("  To move it, in this order:");
    for (const b of blockers) console.log(`    - ${b}`);
    console.log("");
    console.log("  No table is printed and no numbers are written. A run that could");
    console.log("  not happen is not a pass and must never be reported as one.");
    return UNPROVEN;
  }

  say(
    "PASS",
    "THE RUN CAN HAPPEN AT ALL",
    `${connections.filter((c) => c.status === "active").length} active connection(s): ` +
      [...new Set(connections.filter((c) => c.status === "active").map((c) => c.app))].sort().join(", "),
  );

  // ---- PART 3: ten calls -----------------------------------------------
  const judge = new OpenRouterJudge(openrouterKey);
  const hands = makeTwoHands({ provider: provider!, judge, candidateLimit: CANDIDATE_LIMIT });

  const startedAt = new Date();
  const rows: Row[] = [];

  for (const task of tasks) {
    judge.forTask(task.id);
    const searchErrorsBefore = provider!.searchErrors;
    const judgeFailuresBefore = judge.unreachable;
    const stepStarted = performance.now();
    let modelCost: number | null = null;
    const addCost = (c: number | null) => {
      if (c === null) return;
      modelCost = (modelCost ?? 0) + c;
    };

    const row: Row = {
      id: task.id,
      app_hint: task.signature.app_hint,
      status: "unmeasured",
      verdict: null,
      tool_slug: null,
      api_ms: null,
      total_ms: 0,
      api_cost_usd: null,
      model_cost_usd: null,
      note: "",
      response_sha256: null,
      response_bytes: null,
      rung_after: null,
    };

    const finish = (status: RowStatus, note: string) => {
      row.status = status;
      row.note = note;
      row.total_ms = performance.now() - stepStarted;
      row.model_cost_usd = modelCost;
      rows.push(row);
    };

    // The whole assembled system decides, not this file. `deviceOnline: false`
    // is the truth and not a shortcut: there is no Chrome extension attached to
    // a headless gate run, so the browser hand genuinely cannot run — which is
    // exactly the condition rule 3 was written for, and the reason a read is
    // allowed on the API hand at any rung.
    const ctx: UserCtx = { userId, deviceOnline: false, now: Date.now() };
    let decision: RouteDecision;
    try {
      decision = await hands.router.decide(task.signature, ctx);
    } catch (err) {
      finish("unmeasured", `the router threw: ${(err as Error)?.name ?? "Error"}`);
      continue;
    }

    // Costs and verdicts for THIS task's judge asks.
    for (const entry of judge.log.filter((l) => l.taskId === task.id)) addCost(entry.costUsd);

    if (judge.unreachable > judgeFailuresBefore) {
      finish("unmeasured", "the judge could not be reached; no verdict was ever given");
      continue;
    }
    if (provider!.searchErrors > searchErrorsBefore) {
      finish("unmeasured", `Composio search failed: ${provider!.lastError}`);
      continue;
    }
    if (typeof decision.nudgeApp === "string" && decision.nudgeApp !== "") {
      // Rule 2: a tool matched and its app is not connected. THIS IS NOT A
      // MEASUREMENT of the API hand — it is a missing precondition, and
      // scoring it as wrong would report "Composio cannot read Notion" when
      // the truth is "he never connected Notion". It is also why the preflight
      // only requires ONE active connection rather than four: which apps the
      // ten tasks need is a question about `app_hint`, which is advisory and
      // may never be a routing key, so the harness lets the router discover it
      // and names the app the router itself surfaced.
      finish("unmeasured", `not connected: connect ${decision.nudgeApp} through a Connect Link and re-run`);
      continue;
    }
    if (decision.hand === "browser" || !decision.tool) {
      // A real measurement: the vendor had candidates and the judge licensed
      // none of them, or it had none at all. The API hand cannot do this step
      // today, and that is exactly what the gate is here to find out.
      finish("wrong", `no API hand: ${decision.reason}`);
      continue;
    }

    row.tool_slug = decision.tool.toolSlug;

    // THE SEATBELT, second time. The task file said read; the tool gets to make
    // that STRICTER and never looser (contract.ts tightenSideEffect). A tool
    // that declares itself a write is not executed here at all, whatever the
    // judge said, because this gate has no confirmation step and no undo.
    const effect: SideEffect = tightenSideEffect(task.signature.side_effect, decision.tool.sideEffectHint);
    if (effect !== "read") {
      finish("wrong", `refused: the matched tool declares "${effect}", and this gate executes reads only`);
      continue;
    }

    // Arguments.
    let args: Record<string, unknown>;
    try {
      const reply = await callModel(
        openrouterKey,
        "arguments",
        ARGS_SYSTEM,
        argsQuestion(task, decision.tool, new Date().toISOString(), tz),
      );
      addCost(reply.costUsd);
      const parsed = jsonFromReply(reply.text);
      const candidateArgs = parsed?.arguments;
      if (parsed?.confident === false) {
        finish("wrong", `arguments: the model would not commit — ${redact(parsed?.note)}`);
        continue;
      }
      if (!candidateArgs || typeof candidateArgs !== "object" || Array.isArray(candidateArgs)) {
        finish("wrong", "arguments: the model's reply carried no usable argument object");
        continue;
      }
      args = candidateArgs as Record<string, unknown>;
    } catch (err) {
      if (err instanceof ModelUnreachable) {
        finish("unmeasured", `the model was unreachable while building arguments (${err.message})`);
        continue;
      }
      throw err;
    }

    // The call.
    let result: ExecResult;
    try {
      result = await hands.provider.execute(userId, decision.tool.toolSlug, args, decision.accountId);
    } catch (err) {
      // ComposioProvider maps transport failures into ExecResult rather than
      // throwing, so reaching here means something outside its contract broke.
      finish("unmeasured", `execute threw outside the provider contract: ${(err as Error)?.name ?? "Error"}`);
      continue;
    }
    row.api_ms = Number.isFinite(result.ms) ? result.ms : null;
    row.api_cost_usd = typeof result.costUsd === "number" && Number.isFinite(result.costUsd) ? result.costUsd : null;

    if (!result.ok) {
      await hands.ledger.record(
        apiOutcome({
          sig: task.signature,
          ctx,
          app: decision.tool.app,
          toolSlug: decision.tool.toolSlug,
          result,
          verifierResult: "unknown",
        }),
      );
      row.rung_after = await hands.ledger.rung(userId, task.signature.signature_hash, decision.tool.app);
      finish("wrong", `the call failed: ${result.error?.kind ?? "other"}`);
      continue;
    }

    const responseText = JSON.stringify(result.data ?? null);
    row.response_sha256 = sha16(responseText);
    row.response_bytes = responseText.length;

    // The grade.
    let verdict: MatchVerdict;
    let reason: string;
    try {
      const reply = await callModel(openrouterKey, "grade", GRADE_SYSTEM, gradeQuestion(task, args, responseText));
      addCost(reply.costUsd);
      const parsed = jsonFromReply(reply.text);
      verdict = asVerdict(parsed?.verdict);
      reason = redact(parsed?.reason ?? "");
    } catch (err) {
      if (err instanceof ModelUnreachable) {
        // The call happened and its latency is real; only the correctness is
        // unknown. Recorded as unmeasured so the run cannot go green on a
        // grader that was down.
        finish("unmeasured", `the grader was unreachable (${err.message}); the call itself succeeded`);
        continue;
      }
      throw err;
    }

    row.verdict = verdict;
    const correct = verdict === "yes";
    await hands.ledger.record(
      apiOutcome({
        sig: task.signature,
        ctx,
        app: decision.tool.app,
        toolSlug: decision.tool.toolSlug,
        result,
        // The grader is a verifier over the expected effect, which is what the
        // contract says parity is judged on. `unclear` is a no-verdict and is
        // recorded as "unknown" rather than as a failure: demotion is a
        // punishment and needs positive evidence.
        verifierResult: correct ? "verified" : verdict === "no" ? "unverified" : "unknown",
      }),
    );
    row.rung_after = await hands.ledger.rung(userId, task.signature.signature_hash, decision.tool.app);
    finish(correct ? "correct" : "wrong", reason || `grader said ${verdict}`);
  }

  // ---- PART 4: the verdict ---------------------------------------------
  const finishedAt = new Date();
  const unmeasured = rows.filter((r) => r.status === "unmeasured");
  const correct = rows.filter((r) => r.status === "correct").length;
  const apiLatencies = rows.map((r) => r.api_ms).filter((v): v is number => typeof v === "number");
  const p50Api = apiLatencies.length > 0 ? percentile(apiLatencies, 50) : null;
  // Over the SAME rows as the api p50, so the two numbers are comparable. A
  // whole-step median that included ten tasks which never made a call would be
  // an average of abandonments.
  const executedTotals = rows.filter((r) => r.api_ms !== null).map((r) => r.total_ms);
  const p50Total = executedTotals.length > 0 ? percentile(executedTotals, 50) : null;

  console.log("");
  printTable(rows);
  console.log("");

  const gateMet =
    !SIMULATED &&
    unmeasured.length === 0 &&
    rows.length === GATE_OF &&
    correct >= GATE_MIN_CORRECT &&
    p50Api !== null &&
    p50Api < GATE_P50_MS;

  const verdictWord = SIMULATED || unmeasured.length > 0 ? "UNPROVEN" : gateMet ? "CLEAN" : "BROKEN";
  const exitCode = SIMULATED || unmeasured.length > 0 ? UNPROVEN : gateMet ? CLEAN : BROKEN;

  const record = {
    harness: "spike/two-hands/tasks/run_ten.ts",
    started_at: startedAt.toISOString(),
    finished_at: finishedAt.toISOString(),
    verdict: verdictWord,
    exit_code: exitCode,
    gate: {
      min_correct: GATE_MIN_CORRECT,
      of: GATE_OF,
      p50_ms_max: GATE_P50_MS,
      correct,
      measured: rows.length - unmeasured.length,
      p50_api_ms: p50Api,
      p50_total_ms: p50Total,
      met: gateMet,
    },
    // Not a footnote. A results file that reached a stand-in and did not say so
    // is worse than no results file: it is a measurement-shaped object that
    // somebody will cite.
    simulated: SIMULATED,
    environment: {
      model: MODEL,
      composio_base_url: COMPOSIO_BASE_URL,
      model_url: MODEL_URL,
      candidate_limit: CANDIDATE_LIMIT,
      owner: userId,
      timezone: tz,
      node: process.version,
      connected_apps: [...new Set(connections.filter((c) => c.status === "active").map((c) => c.app))].sort(),
      // Presence only. A gate record must never carry a credential, and "we
      // had one" is the whole of what a later reader needs.
      composio_key_present: true,
      openrouter_key_present: true,
    },
    rows,
    judge_asks: judge.log,
    // Printed and stored, never scored. These are the completeness questions
    // the response cannot answer, and pretending a model settled them is how a
    // gate certifies a calendar read that quietly skipped a calendar.
    owner_must_confirm: tasks.map((t) => ({
      id: t.id,
      questions: t.how_to_grade.only_the_owner_can_confirm,
    })),
    privacy:
      "No response body is stored. response_sha256 is a 16-hex prefix of sha256 over the serialized " +
      "response and identifies a payload without quoting it. Model prose is truncated and redacted.",
  };

  mkdirSync(RESULTS_DIR, { recursive: true });
  // Seconds in the filename, unlike proof/watch-b122's minute stamp: two gate
  // runs a minute apart is normal while a key is being debugged, and a
  // collision would overwrite a measured run with a later one.
  const iso = finishedAt.toISOString();
  const stamp = `${iso.slice(0, 10)}T${iso.slice(11, 13)}${iso.slice(14, 16)}${iso.slice(17, 19)}Z`;
  const outFile = join(RESULTS_DIR, `${stamp}.json`);
  writeFileSync(outFile, JSON.stringify(record, null, 2) + "\n");

  console.log("  --------------------------------------------------------------");
  say(
    correct >= GATE_MIN_CORRECT ? "PASS" : "FAIL",
    `${correct} OF ${GATE_OF} CORRECT`,
    `the gate wants ${GATE_MIN_CORRECT}; a verdict of exactly "yes" is the only thing that counts`,
  );
  say(
    p50Api !== null && p50Api < GATE_P50_MS ? "PASS" : "FAIL",
    "P50 UNDER 3 SECONDS",
    p50Api === null
      ? "no call completed, so there is no p50"
      : `api p50 ${Math.round(p50Api)}ms over ${apiLatencies.length} call(s); ` +
        `whole-step p50 ${p50Total === null ? "—" : Math.round(p50Total)}ms including judge, arguments and grading`,
  );
  if (p50Total !== null && p50Total >= GATE_P50_MS && p50Api !== null && p50Api < GATE_P50_MS) {
    say(
      "note",
      "THE HAND IS FAST AND THE STEP IS NOT",
      "the gate reads the API call's own latency, which is what rule 5 compares; the owner waits the whole step",
    );
  }

  console.log("");
  console.log("  THE OWNER STILL HAS TO CONFIRM (completeness — no response can show it):");
  for (const item of record.owner_must_confirm) {
    for (const q of item.questions) console.log(`    ${item.id}: ${q}`);
  }

  console.log("");
  console.log("  --------------------------------------------------------------");
  if (SIMULATED) {
    console.log("  UNPROVEN — this run talked to a stand-in, so it measured the");
    console.log("  harness and not the world. Law 3 is about the LIVE system, and a");
    console.log("  gate that could go green against a fixture would be that law");
    console.log("  defeated by its own instrument. Unset COMPOSIO_BASE_URL and");
    console.log("  TWO_HANDS_OPENROUTER_URL and run it against the real thing.");
    if (unmeasured.length > 0) for (const r of unmeasured) console.log(`    ${r.id}: ${r.note}`);
  } else if (verdictWord === "UNPROVEN") {
    console.log(`  UNPROVEN — ${unmeasured.length} of ${GATE_OF} task(s) produced no evidence:`);
    for (const r of unmeasured) console.log(`    ${r.id}: ${r.note}`);
    console.log("  A run with a hole in it is not a 9-of-10. Fix the hole and re-run.");
  } else if (verdictWord === "CLEAN") {
    console.log("  CLEAN — ten calls happened against live accounts and the gate is met.");
    console.log("  This is a Law-3 result: it measured the live system, not the repo.");
  } else {
    console.log("  BROKEN — the run happened and the gate was not met. The numbers");
    console.log("  above are real; that is what makes them worth acting on.");
  }
  console.log(`  written: ${outFile}`);
  console.log("");
  return exitCode;
}

// Run the gate only when this file IS the command, never when it is imported.
// `test/run_ten.test.ts` drives the half that is answerable with no key — the
// task loader, the substitution and the placeholder blocker — and without this
// guard importing it would fire a live run and call process.exit() out from
// under the test runner.
const INVOKED_AS_A_COMMAND =
  typeof process.argv[1] === "string" && resolve(process.argv[1]) === fileURLToPath(import.meta.url);

if (INVOKED_AS_A_COMMAND) {
  main().then(
    (code) => process.exit(code),
    (err) => {
      // An unexpected throw is not a failing gate — it is a gate that did not
      // run. Exit 2, loudly, rather than 1: reporting a crash as "the API hand
      // was wrong" is the same class of lie as printing a table of zeros.
      console.error("");
      console.error(`  UNPROVEN — the harness itself threw: ${err?.stack ?? err}`);
      console.error("  No measurement was produced. This is not a gate failure.");
      process.exit(UNPROVEN);
    },
  );
}
