/**
 * Claude routing benchmark — compare Gemini Flash (today's primary) against
 * Claude Sonnet 4.5 on the 5 hardest scenarios from
 * engine/data/proactive_e2e.jsonl.
 *
 * Selection criteria: one scenario from each of the highest-leakage
 * brutal pattern_ids identified from the dataset:
 *   - concealed_delegation_first_person_framed (expected = 0)
 *   - pronoun_chain_cross_turn (expected = 1)
 *   - retraction_by_rephrase (expected = 1)
 *   - sarcasm_irony_not_intent (expected = 0)
 *   - meaning_vs_deciding (expected = 0)
 *
 * For each scenario we run the SAME extraction prompt buildIntentPrompt()
 * uses in production, once with Gemini Flash and once with Claude Sonnet
 * 4.5, and judge the output against the dataset's expected_intents.
 *
 * Pass criteria: extracted intent count == expected count, AND when
 * expected > 0 a plain text-overlap heuristic says the extracted summary
 * mentions the expected one. We're measuring extraction quality, not
 * dedup or notification — same generic check the master_benchmark uses.
 */

/* eslint-disable no-console */
import * as fs from "fs";
import * as path from "path";

// Load .env.local BEFORE any module that reads process.env at import time.
// claude.ts caches ANTHROPIC_API_KEY at module top-level — if we don't load
// env first, it sees an empty string and claudeAvailable() returns false.
const ROOT = path.resolve(__dirname, "..");
const ENV_FILE = path.join(ROOT, ".env.local");
if (fs.existsSync(ENV_FILE)) {
  for (const line of fs.readFileSync(ENV_FILE, "utf-8").split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const eq = trimmed.indexOf("=");
    if (eq < 1) continue;
    const k = trimmed.slice(0, eq).trim();
    const v = trimmed.slice(eq + 1).trim();
    if (!process.env[k]) process.env[k] = v;
  }
}

import { buildIntentPrompt } from "../src/lib/intent-prompt";
import { callGemini } from "../src/lib/gemini";
import { callClaude, claudeAvailable } from "../src/lib/claude";

const DATASET = path.join(ROOT, "engine", "data", "proactive_e2e.jsonl");

interface Scenario {
  name: string;
  difficulty: string;
  transcript: string[];
  expected_intents: string[];
  noise_should_NOT_act_on?: string[];
  pattern_id?: string;
}

// 5 of the hardest brutal-tier scenarios in proactive_e2e.jsonl. Selection
// criteria: each pattern_id stresses a different leakage failure mode the
// extraction LLM must reason about (delegation, pronoun chains, retraction,
// sarcasm, meaning vs. deciding). One scenario per failure mode.
const TARGET_PATTERNS = [
  "compound_retraction_partial_scratch", // partial retract: keep surviving subset
  "pronoun_chain_cross_turn",            // resolve "do that" across turns
  "meaning_vs_deciding",                 // soft musing → no intent
  "multi_speaker_wearer_named_friend_says", // friend's idea, no wearer commit
  "quotes_inside_quotes_third_party_commitment", // recounted quote, not own intent
];

function loadScenarios(): Scenario[] {
  const lines = fs.readFileSync(DATASET, "utf-8").split("\n").filter(Boolean);
  const all = lines.map((l) => JSON.parse(l) as Scenario);
  const picked: Scenario[] = [];
  for (const pat of TARGET_PATTERNS) {
    const match = all.find((s) => s.pattern_id === pat);
    if (match) picked.push(match);
  }
  return picked;
}

interface ExtractedIntent {
  action_type?: string;
  summary_for_user?: string;
  confidence?: number;
}

function fuzzyMatch(extracted: string, expected: string): boolean {
  const stop = new Set([
    "a", "an", "the", "to", "for", "with", "and", "or", "of", "in", "on",
    "at", "by", "is", "are", "be", "i", "me", "my", "you", "your", "we",
    "our", "this", "that",
  ]);
  const tokens = (s: string) =>
    s
      .toLowerCase()
      .replace(/[^a-z0-9 ]+/g, " ")
      .split(/\s+/)
      .filter((t) => t.length > 2 && !stop.has(t));
  const exTok = tokens(extracted);
  const expTok = tokens(expected);
  if (expTok.length === 0) return false;
  const exSet = new Set(exTok);
  const overlap = expTok.filter((t) => exSet.has(t)).length;
  return overlap / expTok.length >= 0.5;
}

interface ScenarioResult {
  name: string;
  pattern: string;
  expectedCount: number;
  extracted: ExtractedIntent[];
  pass: boolean;
  reason: string;
}

function scoreOne(scenario: Scenario, intents: ExtractedIntent[]): {
  pass: boolean;
  reason: string;
} {
  const expected = scenario.expected_intents ?? [];
  const conf = (i: ExtractedIntent) =>
    typeof i.confidence === "number" ? i.confidence : 1;
  const filtered = intents.filter((i) => conf(i) >= 0.65);
  if (expected.length === 0) {
    if (filtered.length === 0) return { pass: true, reason: "no_intents" };
    return {
      pass: false,
      reason: `false_positive (extracted ${filtered.length} expected 0)`,
    };
  }
  if (filtered.length === 0) return { pass: false, reason: "missed_expected" };
  for (const exp of expected) {
    const matched = filtered.some((i) =>
      fuzzyMatch(i.summary_for_user ?? "", exp)
    );
    if (!matched) return { pass: false, reason: `expected not matched: "${exp}"` };
  }
  return { pass: true, reason: "matched" };
}

async function runWith(
  scenario: Scenario,
  caller: "gemini" | "claude"
): Promise<ScenarioResult> {
  const transcript = scenario.transcript.join("\n");
  // Use identical prompt builder both runs — only the LLM changes.
  const localTime = new Date().toLocaleString("en-US", {
    timeZone: "America/Vancouver",
  });
  const { system, user } = buildIntentPrompt(
    transcript,
    localTime,
    "America/Vancouver"
  );
  const messages = [
    { role: "system" as const, content: system },
    { role: "user" as const, content: user },
  ];
  let raw = "";
  try {
    if (caller === "gemini") {
      raw = await callGemini(messages, { temperature: 0.0, max_tokens: 8192 });
    } else {
      raw = await callClaude(messages, {
        model: "claude-sonnet-4-5",
        temperature: 0.0,
        max_tokens: 8192,
        jsonOnly: true,
      });
    }
  } catch (err) {
    return {
      name: scenario.name,
      pattern: scenario.pattern_id ?? "?",
      expectedCount: scenario.expected_intents.length,
      extracted: [],
      pass: false,
      reason: `${caller} call failed: ${err instanceof Error ? err.message : err}`,
    };
  }
  let parsed: { intents?: ExtractedIntent[] } = {};
  try {
    parsed = JSON.parse(raw);
  } catch {
    return {
      name: scenario.name,
      pattern: scenario.pattern_id ?? "?",
      expectedCount: scenario.expected_intents.length,
      extracted: [],
      pass: false,
      reason: `${caller} returned unparseable JSON`,
    };
  }
  const intents = parsed.intents ?? [];
  const verdict = scoreOne(scenario, intents);
  return {
    name: scenario.name,
    pattern: scenario.pattern_id ?? "?",
    expectedCount: scenario.expected_intents.length,
    extracted: intents,
    ...verdict,
  };
}

async function main() {
  if (!process.env.GOOGLE_API_KEY) {
    console.error("Missing GOOGLE_API_KEY in .env.local");
    process.exit(1);
  }
  if (!claudeAvailable()) {
    console.error("Missing ANTHROPIC_API_KEY in .env.local");
    process.exit(1);
  }
  const scenarios = loadScenarios();
  console.log(`\nRunning ${scenarios.length} scenarios on Gemini Flash + Claude Sonnet 4.5\n`);
  let geminiPass = 0;
  let claudePass = 0;
  const rows: Array<{
    name: string;
    pattern: string;
    expected: number;
    gemini: { pass: boolean; reason: string; extracted: number };
    claude: { pass: boolean; reason: string; extracted: number };
  }> = [];
  for (const sc of scenarios) {
    const g = await runWith(sc, "gemini");
    const c = await runWith(sc, "claude");
    if (g.pass) geminiPass += 1;
    if (c.pass) claudePass += 1;
    rows.push({
      name: sc.name,
      pattern: sc.pattern_id ?? "?",
      expected: sc.expected_intents.length,
      gemini: { pass: g.pass, reason: g.reason, extracted: g.extracted.length },
      claude: { pass: c.pass, reason: c.reason, extracted: c.extracted.length },
    });
  }
  console.log("\nResults:\n");
  console.log(
    "scenario".padEnd(48),
    "exp".padStart(4),
    "gFlash".padStart(8),
    "claude".padStart(8),
    "  pattern"
  );
  console.log("-".repeat(95));
  for (const r of rows) {
    console.log(
      r.name.padEnd(48),
      String(r.expected).padStart(4),
      ((r.gemini.pass ? "PASS" : "fail") + `(${r.gemini.extracted})`).padStart(8),
      ((r.claude.pass ? "PASS" : "fail") + `(${r.claude.extracted})`).padStart(8),
      "  " + r.pattern
    );
    if (!r.gemini.pass) console.log("    gemini fail:", r.gemini.reason);
    if (!r.claude.pass) console.log("    claude fail:", r.claude.reason);
  }
  console.log("\nTotals:");
  console.log(`  Gemini Flash: ${geminiPass}/${rows.length}`);
  console.log(`  Claude 4.5  : ${claudePass}/${rows.length}`);
  console.log(`  Delta       : ${claudePass - geminiPass} scenarios\n`);
}

main().catch((err) => {
  console.error("FATAL:", err);
  process.exit(1);
});
