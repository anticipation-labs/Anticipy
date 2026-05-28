// Node 22 native TS support: run with
//   node --experimental-strip-types --test __tests__/dedup.test.mts

import { test } from "node:test";
import assert from "node:assert/strict";

import {
  filterValidIntents,
  isDuplicateOfExisting,
  jaccardSimilarity,
  tokenize,
  IGNORED_ACTION_TYPES,
  CONFIDENCE_THRESHOLD,
  type RawIntent,
  type ExistingIntent,
  type IntentCandidate,
} from "../src/lib/dedup.ts";
import { buildIntentPrompt } from "../src/lib/intent-prompt.ts";

// ─── tokenize ────────────────────────────────────────────────────────────────

test("tokenize: lowercases, drops short tokens, dedupes", () => {
  assert.deepEqual(
    tokenize("Book a flight to Paris next Tuesday and book a flight"),
    ["book", "flight", "paris", "next", "tuesday", "and"]
  );
});

test("tokenize: handles null/undefined/empty", () => {
  assert.deepEqual(tokenize(null), []);
  assert.deepEqual(tokenize(undefined), []);
  assert.deepEqual(tokenize(""), []);
  assert.deepEqual(tokenize("   "), []);
});

test("tokenize: filters words 2 chars or shorter (to/be/in/no fall out)", () => {
  // tokenize() keeps words with length > 2
  assert.deepEqual(tokenize("To go to be in"), []);
  // "yes" "but" "and" are >2 chars; "no" is filtered
  assert.deepEqual(tokenize("yes no but and"), ["yes", "but", "and"]);
});

// ─── jaccardSimilarity ───────────────────────────────────────────────────────

test("jaccard: identical strings = 1", () => {
  assert.equal(jaccardSimilarity("book flight paris", "book flight paris"), 1);
});

test("jaccard: completely disjoint = 0", () => {
  assert.equal(
    jaccardSimilarity("book flight paris", "send email mom"),
    0
  );
});

test("jaccard: one empty = 0", () => {
  assert.equal(jaccardSimilarity("book flight paris", ""), 0);
  assert.equal(jaccardSimilarity("", "book flight paris"), 0);
});

test("jaccard: word reorder produces the same score", () => {
  const s1 = jaccardSimilarity(
    "book flight paris next tuesday",
    "next tuesday book flight paris"
  );
  assert.equal(s1, 1);
});

test("jaccard: short stop-words don't move the needle", () => {
  // tokenize() drops <=2-char words. After filtering:
  //   "book a flight to"          → [book, flight]
  //   "I want to book a flight"   → [want, book, flight]
  // Intersection = 2, union = 3, similarity = 2/3
  const sim = jaccardSimilarity("book a flight to", "I want to book a flight");
  assert.equal(sim > 0.6, true);
  assert.equal(sim < 0.7, true);
});

// ─── isDuplicateOfExisting ───────────────────────────────────────────────────

const existingFlight: ExistingIntent = {
  action_type: "book_flight",
  summary_for_user: "Book a flight to Paris next Tuesday",
  evidence_quote: "I really need to book that flight to Paris",
};

test("dedup: 80%+ summary similarity flags duplicate regardless of action_type", () => {
  const candidate = {
    action_type: "purchase_ticket",
    summary_for_user: "Book a flight to Paris next Tuesday morning",
    evidence_quote: "different quote entirely",
  };
  assert.equal(isDuplicateOfExisting(candidate, [existingFlight]), true);
});

test("dedup: same action_type + 60%+ evidence overlap flags duplicate", () => {
  const candidate = {
    action_type: "book_flight",
    summary_for_user: "Reserve flights to France",
    evidence_quote: "I really need to book that flight to Paris airport",
  };
  assert.equal(isDuplicateOfExisting(candidate, [existingFlight]), true);
});

test("dedup: same action_type + 50% summary overlap flags duplicate (transcript drift)", () => {
  // LLM re-emits same intent with slightly expanded wording two cycles later
  const candidate = {
    action_type: "book_flight",
    summary_for_user: "Book flight Paris Tuesday morning",
    evidence_quote: "different quote",
  };
  assert.equal(isDuplicateOfExisting(candidate, [existingFlight]), true);
});

test("dedup: different intent with shared topic word is NOT a duplicate", () => {
  const candidate = {
    action_type: "buy_gift",
    summary_for_user: "Buy souvenir for friend visiting Paris",
    evidence_quote: "Gotta pick up something for Sara",
  };
  assert.equal(isDuplicateOfExisting(candidate, [existingFlight]), false);
});

test("dedup: against empty existing list returns false", () => {
  const candidate = {
    action_type: "book_flight",
    summary_for_user: "Book a flight",
    evidence_quote: "I need to book a flight",
  };
  assert.equal(isDuplicateOfExisting(candidate, []), false);
});

test("dedup: handles null fields in existing intents without crashing", () => {
  const broken: ExistingIntent = {
    action_type: null,
    summary_for_user: null,
    evidence_quote: null,
  };
  const candidate = {
    action_type: "book_flight",
    summary_for_user: "Book a flight to Paris",
    evidence_quote: "I need to book a flight",
  };
  assert.equal(isDuplicateOfExisting(candidate, [broken]), false);
});

test("dedup: realistic 30s-cycle drift — first emit then second emit", () => {
  // First analyze cycle: "I really need to book that flight to Paris"
  const firstEmit: ExistingIntent = {
    action_type: "book_flight",
    summary_for_user: "Book flight to Paris next Tuesday",
    evidence_quote: "I really need to book that flight to Paris next Tuesday",
  };
  // Second analyze cycle, transcript grew: same flight task surfaces again
  const secondCandidate = {
    action_type: "book_flight",
    summary_for_user: "Book flight to Paris on Tuesday",
    evidence_quote: "yeah I really need to book that flight to Paris next Tuesday for sure",
  };
  assert.equal(isDuplicateOfExisting(secondCandidate, [firstEmit]), true);
});

// ─── filterValidIntents ──────────────────────────────────────────────────────

test("filterValidIntents: drops intents below confidence threshold", () => {
  const intents: RawIntent[] = [
    {
      action_type: "book_flight",
      confidence: 0.5,
      summary_for_user: "Book flight",
      evidence_quote: "...",
    },
    {
      action_type: "book_flight",
      confidence: 0.65,
      summary_for_user: "Book flight at threshold",
      evidence_quote: "...",
    },
    {
      action_type: "book_flight",
      confidence: 0.9,
      summary_for_user: "Book flight high conf",
      evidence_quote: "...",
    },
  ];
  const filtered = filterValidIntents(intents);
  assert.equal(filtered.length, 2);
  assert.equal(filtered[0].summary_for_user, "Book flight at threshold");
});

test("filterValidIntents: drops every IGNORED_ACTION_TYPE", () => {
  const intents: RawIntent[] = Array.from(IGNORED_ACTION_TYPES).map((t) => ({
    action_type: t,
    confidence: 0.9,
    summary_for_user: `Ignored: ${t}`,
    evidence_quote: "...",
  }));
  assert.equal(filterValidIntents(intents).length, 0);
});

test("filterValidIntents: drops entries with empty summary or missing action_type", () => {
  const intents: RawIntent[] = [
    {
      action_type: "book_flight",
      confidence: 0.9,
      summary_for_user: "  ",
      evidence_quote: "...",
    },
    {
      action_type: "",
      confidence: 0.9,
      summary_for_user: "Has summary but no action_type",
      evidence_quote: "...",
    },
    {
      action_type: "book_flight",
      confidence: 0.9,
      summary_for_user: "Valid one",
      evidence_quote: "evidence",
    },
  ];
  const filtered = filterValidIntents(intents);
  assert.equal(filtered.length, 1);
  assert.equal(filtered[0].summary_for_user, "Valid one");
});

test("filterValidIntents: handles non-numeric confidence safely", () => {
  const intents: RawIntent[] = [
    {
      action_type: "book_flight",
      confidence: "0.9", // string
      summary_for_user: "Book flight",
      evidence_quote: "...",
    },
    {
      action_type: "book_flight",
      confidence: undefined,
      summary_for_user: "Book flight",
      evidence_quote: "...",
    },
    {
      action_type: "book_flight",
      confidence: NaN,
      summary_for_user: "Book flight",
      evidence_quote: "...",
    },
  ];
  // typeof NaN === "number" but NaN < CONFIDENCE_THRESHOLD is false… NaN compared with < always false.
  // Our filter requires confidence >= threshold; NaN >= 0.65 is false, so it's filtered out.
  assert.equal(filterValidIntents(intents).length, 0);
  assert.equal(CONFIDENCE_THRESHOLD, 0.65);
});

test("filterValidIntents: lowercases action_type for consistent dedup downstream", () => {
  const intents: RawIntent[] = [
    {
      action_type: "Book_Flight",
      confidence: 0.9,
      summary_for_user: "Book a flight",
      evidence_quote: "...",
    },
  ];
  const filtered = filterValidIntents(intents);
  assert.equal(filtered[0].action_type, "book_flight");
});

// ─── End-to-end: messy real-world transcripts ────────────────────────────────

test("buildIntentPrompt: produces stable system+user pair for each transcript", () => {
  const teenagerRamble = `
[Speaker 0]: oh my god so today was insane
[Speaker 1]: wait what happened in math
[Speaker 0]: like literally Mr. Howard gave us a pop quiz I bombed it I'm gonna fail
[Speaker 1]: no you're not stop being dramatic
[Speaker 0]: also I told my mom I'd book that flight to LA for spring break by Friday
[Speaker 1]: ugh spring break is so far away though
[Speaker 0]: I knowwww but if I don't book it the prices triple
[Speaker 1]: did you see what Madison wore today
[Speaker 0]: that crop top? yeah no thoughts honestly
`.trim();

  const { system, user } = buildIntentPrompt(
    teenagerRamble,
    "Wed, Apr 29, 2026, 5:45 PM",
    "America/Los_Angeles",
    [],
    []
  );
  assert.match(system, /CRITICAL FILTER/);
  assert.match(system, /Default to FILTERING borderline conversational items/);
  assert.match(user, /Skip conversational back-and-forth/);
  assert.match(user, /book that flight to LA/);
  assert.match(user, /America\/Los_Angeles/);
});

test("buildIntentPrompt: includes recent actions block when provided", () => {
  const { user } = buildIntentPrompt(
    "test",
    "now",
    "UTC",
    ["Book flight to Paris", "Email Sara about the proposal"],
    []
  );
  assert.match(user, /Book flight to Paris/);
  assert.match(user, /Email Sara about the proposal/);
  assert.match(user, /DO NOT re-emit/);
});

test("buildIntentPrompt: includes cross-session context when provided", () => {
  const { user } = buildIntentPrompt(
    "test",
    "now",
    "UTC",
    [],
    ["[book_flight] Book flight to Tokyo", "[reminder_add] Pick up dry cleaning"]
  );
  assert.match(user, /earlier conversations today/);
  assert.match(user, /Book flight to Tokyo/);
});

// Pipeline test: simulate what the LLM might emit for messy transcripts and
// verify the filter+dedup pipeline produces the expected output.

test("pipeline: pure-gossip transcript with synthetic LLM emit returns 0 actionable intents", () => {
  // Simulate an LLM hallucinating low-confidence "intents" for a gossip-only transcript
  const llmEmits: RawIntent[] = [
    {
      action_type: "answer_question",
      confidence: 0.7,
      summary_for_user: "Tell Madison her crop top looked fine",
      evidence_quote: "no thoughts honestly",
    },
    {
      action_type: "small_talk",
      confidence: 0.95,
      summary_for_user: "Catch up about the math quiz",
      evidence_quote: "wait what happened in math",
    },
    {
      action_type: "acknowledge",
      confidence: 0.9,
      summary_for_user: "Acknowledge friend's drama",
      evidence_quote: "oh my god so today was insane",
    },
  ];
  // All three are conversational types — should all be dropped
  assert.equal(filterValidIntents(llmEmits).length, 0);
});

test("pipeline: meeting-overlap transcript surfaces 2 distinct tasks but not chit-chat", () => {
  // Multi-speaker meeting, LLM might emit 5 candidates — only 2 should survive
  const llmEmits: RawIntent[] = [
    {
      action_type: "send_proposal",
      confidence: 0.92,
      summary_for_user: "Send the Q2 proposal to Maya by EOD Thursday",
      evidence_quote: "I'll have the proposal in your inbox by Thursday",
    },
    {
      action_type: "schedule_call",
      confidence: 0.88,
      summary_for_user: "Schedule a call with engineering team about the migration",
      evidence_quote: "let's get eng on a call about the migration soon",
    },
    {
      action_type: "confirm_status",
      confidence: 0.95, // high conf but ignored type
      summary_for_user: "Confirm Maya is still on the proposal",
      evidence_quote: "you're still on it right?",
    },
    {
      action_type: "answer_question",
      confidence: 0.91,
      summary_for_user: "Answer Pat's question about the deadline",
      evidence_quote: "when's that due again?",
    },
    {
      action_type: "send_proposal",
      confidence: 0.5, // below threshold
      summary_for_user: "Maybe also send to Pat",
      evidence_quote: "should we loop in Pat",
    },
  ];
  const filtered = filterValidIntents(llmEmits);
  assert.equal(filtered.length, 2);
  assert.equal(filtered[0].action_type, "send_proposal");
  assert.equal(filtered[1].action_type, "schedule_call");
});

test("pipeline: 30s growing-transcript drift is fully deduplicated end-to-end", () => {
  // First analysis tick — only 30s in
  const cycle1: RawIntent[] = [
    {
      action_type: "book_flight",
      confidence: 0.9,
      summary_for_user: "Book a flight to LA before Friday",
      evidence_quote: "I told my mom I'd book that flight to LA",
    },
  ];
  const filtered1 = filterValidIntents(cycle1);
  const stored1: ExistingIntent[] = filtered1.map((i) => ({
    action_type: i.action_type,
    summary_for_user: i.summary_for_user,
    evidence_quote: i.evidence_quote,
  }));

  // Second tick — same intent re-emerges with slightly different wording
  const cycle2: RawIntent[] = [
    {
      action_type: "book_flight",
      confidence: 0.91,
      summary_for_user: "Book the LA flight by Friday",
      evidence_quote: "I told my mom I'd book that flight to LA for spring break by Friday",
    },
    // A genuinely new intent shows up too
    {
      action_type: "send_text",
      confidence: 0.85,
      summary_for_user: "Text Madison about the project",
      evidence_quote: "I gotta text Madison about the bio project",
    },
  ];
  const filtered2 = filterValidIntents(cycle2);
  const newOnes = filtered2.filter(
    (c) => !isDuplicateOfExisting(c, stored1)
  );
  // The flight book is a duplicate; only the Madison text should survive
  assert.equal(newOnes.length, 1);
  assert.equal(newOnes[0].action_type, "send_text");
});

test("pipeline: mostly-um-transcript with one clear task captures only the real task", () => {
  // Synthesize what an LLM might infer
  const llmEmits: RawIntent[] = [
    {
      action_type: "schedule_meeting_reminder",
      confidence: 0.82,
      summary_for_user: "Remind yourself to call the doctor tomorrow at 9 AM",
      evidence_quote: "uh I gotta call the doctor tomorrow at 9",
    },
    // hallucinated low-conf intent on um/uh noise
    {
      action_type: "clarify_status",
      confidence: 0.55,
      summary_for_user: "Clarify what user meant by 'um'",
      evidence_quote: "um uh um",
    },
  ];
  const filtered = filterValidIntents(llmEmits);
  assert.equal(filtered.length, 1);
  assert.equal(filtered[0].action_type, "schedule_meeting_reminder");
});

test("pipeline: mixed-language transcript — non-English content shouldn't crash filtering", () => {
  // Synthesize a plausible LLM emit (LLMs can usually still extract the English task)
  const llmEmits: RawIntent[] = [
    {
      action_type: "buy_item",
      confidence: 0.78,
      summary_for_user: "Buy 2kg de manzanas — apples for Sunday's pie",
      evidence_quote: "compra dos kilos de manzanas para el pie del domingo",
    },
  ];
  const filtered = filterValidIntents(llmEmits);
  assert.equal(filtered.length, 1);
  // tokenize should not crash on accented chars
  const sim = jaccardSimilarity(
    "Buy 2kg de manzanas — apples for Sunday's pie",
    "compra dos kilos de manzanas para el pie del domingo"
  );
  assert.equal(typeof sim, "number");
  assert.equal(sim >= 0 && sim <= 1, true);
});

// ─── Edge case: malformed LLM JSON ───────────────────────────────────────────

test("filterValidIntents: handles array containing non-object entries", () => {
  const intents = [null, undefined, "string", 123, { not: "an intent" }] as RawIntent[];
  const filtered = filterValidIntents(intents);
  assert.equal(filtered.length, 0);
});

// ─── Investor-demo scenarios ────────────────────────────────────────────────
// Each test simulates the LLM output for a realistic transcript and checks
// that the filter+dedup pipeline produces exactly the expected count.

test("scenario: one buried task in chit-chat returns exactly 1 intent (not 3)", () => {
  // Buried-task transcript:
  //   "Hey did you see Madison's post / yeah / so anyway I gotta book that
  //    flight to LA before Friday or my mom kills me / lol / what'd you eat"
  // The LLM tends to over-emit on conversational filler. Filter should
  // collapse to exactly 1.
  const llmEmits: RawIntent[] = [
    {
      action_type: "book_flight",
      confidence: 0.92,
      summary_for_user: "Book a flight to LA before Friday",
      evidence_quote: "I gotta book that flight to LA before Friday",
    },
    {
      action_type: "answer_question",
      confidence: 0.88,
      summary_for_user: "Tell friend whether you saw Madison's post",
      evidence_quote: "did you see Madison's post",
    },
    {
      action_type: "small_talk",
      confidence: 0.94,
      summary_for_user: "Continue chatting about food",
      evidence_quote: "what'd you eat",
    },
  ];
  const filtered = filterValidIntents(llmEmits);
  assert.equal(filtered.length, 1);
  assert.equal(filtered[0].action_type, "book_flight");
});

test("scenario: 5-task rapid-fire meeting yields exactly 5 intents, no duplicates", () => {
  // Five distinct task assignments across speakers in a single tick.
  const llmEmits: RawIntent[] = [
    {
      action_type: "send_proposal",
      confidence: 0.93,
      summary_for_user: "Send the Q2 proposal to Maya by Thursday EOD",
      evidence_quote: "Maya, you've got the Q2 proposal by Thursday",
    },
    {
      action_type: "schedule_call",
      confidence: 0.9,
      summary_for_user: "Schedule kickoff call with engineering Friday morning",
      evidence_quote: "let's get eng kickoff on the calendar Friday AM",
    },
    {
      action_type: "follow_up_with",
      confidence: 0.86,
      summary_for_user: "Follow up with the design team about new mocks",
      evidence_quote: "ping design about the updated mocks",
    },
    {
      action_type: "create_report",
      confidence: 0.88,
      summary_for_user: "Pull the revenue numbers for the board deck",
      evidence_quote: "I need the revenue numbers for the board deck",
    },
    {
      action_type: "book_meeting",
      confidence: 0.91,
      summary_for_user: "Book the all-hands room for next Wednesday at 2 PM",
      evidence_quote: "grab the big room for all-hands Wednesday at 2",
    },
  ];
  const filtered = filterValidIntents(llmEmits);
  assert.equal(filtered.length, 5);

  // Every one should be unique against the others — no internal collapse
  const stored: ExistingIntent[] = [];
  let kept = 0;
  for (const c of filtered) {
    if (!isDuplicateOfExisting(c, stored)) {
      kept += 1;
      stored.push({
        action_type: c.action_type,
        summary_for_user: c.summary_for_user,
        evidence_quote: c.evidence_quote,
      });
    }
  }
  assert.equal(kept, 5);
});

test("scenario: 5-task meeting re-emits over 3 cycles → still 5 stored intents", () => {
  // Realistic drift: in practice the LLM keeps the same key nouns across
  // re-emits — the topic ("Q2 proposal to Maya", "eng kickoff call") is
  // what stays stable, while filler verbs/connectors shift. The Jaccard
  // dedup is calibrated for exactly this pattern.
  const cycle1: RawIntent[] = [
    {
      action_type: "send_proposal",
      confidence: 0.93,
      summary_for_user: "Send Q2 proposal to Maya by Thursday EOD",
      evidence_quote: "Maya you've got the Q2 proposal by Thursday",
    },
    {
      action_type: "schedule_call",
      confidence: 0.9,
      summary_for_user: "Schedule eng kickoff call for Friday morning",
      evidence_quote: "let's get eng kickoff scheduled Friday morning",
    },
  ];
  // Cycle 2: 1+2 re-emit (drift, but nouns preserved), 3 newly surfaces
  const cycle2: RawIntent[] = [
    {
      action_type: "send_proposal",
      confidence: 0.94,
      summary_for_user: "Send Q2 proposal to Maya by Thursday end of day",
      evidence_quote: "Maya you've got the Q2 proposal by Thursday EOD",
    },
    {
      action_type: "schedule_call",
      confidence: 0.91,
      summary_for_user: "Schedule eng kickoff call Friday morning",
      evidence_quote: "let's get eng kickoff scheduled Friday morning for sure",
    },
    {
      action_type: "follow_up_with",
      confidence: 0.86,
      summary_for_user: "Follow up with design team about updated mocks",
      evidence_quote: "ping the design team about the updated mocks",
    },
  ];
  // Cycle 3: 1-3 all re-drift, 4+5 newly surface
  const cycle3: RawIntent[] = [
    {
      action_type: "send_proposal",
      confidence: 0.92,
      summary_for_user: "Send Q2 proposal Maya Thursday EOD",
      evidence_quote: "the Q2 proposal needs to be with Maya by Thursday",
    },
    {
      action_type: "schedule_call",
      confidence: 0.9,
      summary_for_user: "Schedule the eng kickoff call Friday morning",
      evidence_quote: "let's get eng kickoff scheduled Friday morning",
    },
    {
      action_type: "follow_up_with",
      confidence: 0.85,
      summary_for_user: "Follow up with design team about the updated mocks",
      evidence_quote: "ping design team about updated mocks",
    },
    {
      action_type: "create_report",
      confidence: 0.88,
      summary_for_user: "Pull revenue numbers for the board deck",
      evidence_quote: "I need the revenue numbers for the board deck",
    },
    {
      action_type: "book_meeting",
      confidence: 0.91,
      summary_for_user: "Book the big room for all-hands Wednesday 2 PM",
      evidence_quote: "grab the big room for all-hands Wednesday at 2",
    },
  ];

  const stored: ExistingIntent[] = [];
  for (const cycle of [cycle1, cycle2, cycle3]) {
    const filtered = filterValidIntents(cycle);
    for (const c of filtered) {
      if (!isDuplicateOfExisting(c, stored)) {
        stored.push({
          action_type: c.action_type,
          summary_for_user: c.summary_for_user,
          evidence_quote: c.evidence_quote,
        });
      }
    }
  }
  assert.equal(stored.length, 5);
  // All 5 expected types are present
  const types = stored.map((s) => s.action_type).sort();
  assert.deepEqual(types, [
    "book_meeting",
    "create_report",
    "follow_up_with",
    "schedule_call",
    "send_proposal",
  ]);
});

test("scenario: noisy 'um uh yeah so um' transcript with one buried task → 1 intent", () => {
  // The LLM tends to be confidence-poor on transcripts with heavy speech
  // disfluency. Filter must keep the one real intent and discard the
  // fillers / clarifications.
  const llmEmits: RawIntent[] = [
    {
      action_type: "reminder_add",
      confidence: 0.82,
      summary_for_user: "Pick up the prescription at the pharmacy after work",
      evidence_quote: "I gotta pick up that prescription after work",
    },
    {
      action_type: "acknowledge",
      confidence: 0.96,
      summary_for_user: "Acknowledge speaker's filler words",
      evidence_quote: "um uh yeah so um",
    },
    {
      action_type: "clarify_status",
      confidence: 0.7,
      summary_for_user: "Clarify what the speaker meant",
      evidence_quote: "so like, what was I saying",
    },
  ];
  const filtered = filterValidIntents(llmEmits);
  assert.equal(filtered.length, 1);
  assert.equal(filtered[0].action_type, "reminder_add");
});

test("scenario: pure gossip — even high-confidence chit-chat gets dropped", () => {
  // Gossip-only transcript: the LLM may emit high-confidence "intents" that
  // are conversational. Every one should be filtered.
  const llmEmits: RawIntent[] = [
    {
      action_type: "small_talk",
      confidence: 0.97,
      summary_for_user: "Continue gossiping about the new neighbour",
      evidence_quote: "did you see who moved in next door",
    },
    {
      action_type: "answer_question",
      confidence: 0.95,
      summary_for_user: "Tell friend whether you saw the neighbour",
      evidence_quote: "no I haven't seen them yet",
    },
    {
      action_type: "respond_to_message",
      confidence: 0.9,
      summary_for_user: "Respond about the new neighbour",
      evidence_quote: "they seem nice though",
    },
    {
      action_type: "acknowledge",
      confidence: 0.88,
      summary_for_user: "Acknowledge the topic switch",
      evidence_quote: "anyway",
    },
  ];
  const filtered = filterValidIntents(llmEmits);
  assert.equal(filtered.length, 0);
});

test("scenario: dedup catches near-duplicates with different word order", () => {
  // Same task, different word order, slightly different vocab — Jaccard
  // should treat as duplicate.
  const stored: ExistingIntent[] = [
    {
      action_type: "send_email",
      summary_for_user: "Email Sarah about the contract revisions",
      evidence_quote: "I need to email Sarah about the new contract terms",
    },
  ];
  const candidate: IntentCandidate = {
    action_type: "send_email",
    summary_for_user: "Email Sarah regarding contract revisions",
    evidence_quote: "got to email Sarah about the contract terms",
  };
  assert.equal(isDuplicateOfExisting(candidate, stored), true);
});
