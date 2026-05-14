"""Generator prompt templates for the v-final-prototype Stage 1.5 hedge
filter training data.

Pure-Python module, no API calls at import time. The generator script
(engine/data/synth/generate.py, not yet built) imports these constants
and pipes them through DeepSeek V4 Flash on OpenRouter to produce the
three datasets:

- utterance_in_context.jsonl
- memory_resolution.jsonl
- negative.jsonl

The schema each example must validate against is in `validate.py` and
documented in `README.md`. The 32 gold-standard utterances live in
`gold_standard.jsonl` and are the non-negotiable evaluation gate.

Why these specific templates: each one targets a known failure mode of
generic intent extractors (sarcasm fooling COMMIT, third-party reports
firing as wearer requests, past-tense triggering retroactive action,
hedging never surfacing later). Oversampling the boundary cases is what
makes the trained adapter robust at production.
"""

# Schema text appended to every generator call so the output is parseable.
# Keep this in lockstep with engine/data/synth/README.md's schema block —
# if you change one, change both.
SHARED_SCHEMA_BLOCK = """\
Return ONE JSON object per line (JSONL). NO markdown fences. NO prose.

Each line MUST validate against this schema:

{
  "id": "<uuid-like string, unique per row>",
  "kind": "<the kind you were asked to generate>",
  "turn_history": [{"speaker": "wearer" | "other", "text": "..."}, ...],
  "utterance": "<the latest WEARER utterance>",
  "user_memory": [{"kind": "...", "key": "...", "value": "...", "evidence_quote": "..."}, ...],
  "expected_label": "COMMIT" | "STORE_AS_LATENT" | "REFUSE",
  "expected_reason": "<one-line why-tag>",
  "expected_intent": <object if COMMIT, else null>,
  "expected_memory_write": <object if utterance reveals durable preference/aversion/contact/habit, else null>,
  "boundary_tag": "sarcasm" | "hedging" | "abandonment" | "third_party" | "past_tense" | "conditional" | "joke" | "brainstorm" | "real_action" | "multi_turn"
}

CRITICAL RULES:
- expected_intent is non-null IFF expected_label == "COMMIT"
- expected_memory_write is non-null ONLY when the utterance reveals durable info
  (sarcasm-derived aversion is the canonical case: REFUSE the action AND store the aversion)
- evidence_quote MUST be a verbatim substring of the utterance
- turn_history is the conversation BEFORE the utterance (can be empty)
- user_memory is the simulated knowledge graph state at the moment of the utterance
"""

# ─────────────────────────────────────────────────────────────────────────
# Dataset 1: utterance_in_context
# ─────────────────────────────────────────────────────────────────────────
#
# Conversations around an utterance. About half labeled "no intent — do not
# fire". Oversample sarcasm, retraction, third-party reporting, past-tense.
#
# The generator should produce: ~25k examples balanced across boundary tags,
# with ~50% COMMIT, ~25% STORE_AS_LATENT, ~25% REFUSE. Tune ratio based on
# what the hedge filter struggles with after the first training round.

UTTERANCE_IN_CONTEXT_SYSTEM = """\
You are generating training data for an AI wearable's hedge / sarcasm /
abandonment classifier. The wearer says things continuously throughout
the day. Some of what they say is a clear request to act ("book Carbone
for 7pm"). MOST of it is not — they hedge, joke, recap what someone
else did, retract, daydream, complain sarcastically. The classifier's
job is to tell those apart.

For each row, invent:
1. A short conversation around an utterance (turn_history can be empty
   or a few exchanges between WEARER and OTHER speakers).
2. The latest WEARER utterance.
3. Some lightweight user_memory state (contacts, recurrences, habits).
4. The correct expected_label and (when COMMIT) expected_intent.
5. The correct expected_memory_write when sarcasm reveals aversion or
   the utterance reveals a durable preference.

DIVERSITY REQUIREMENTS:
- Vary the action category. Don't make every COMMIT a restaurant booking.
  Mix: book_reservation, send_email, schedule_event, reorder, post_message,
  draft_proposal, set_reminder, navigate_to, log_expense, queue_song, etc.
- Vary the wearer's mood and conversational register. Casual, formal,
  frustrated, half-distracted, multitasking.
- Vary slot completeness. Some utterances should have ALL slots, some
  need_memory, some need_inference.

OVERSAMPLE these boundary tags:
- sarcasm (REFUSE + aversion memory write)
- abandonment (REFUSE, no memory write)
- third_party (REFUSE — wearer is RELAYING someone else's action)
- past_tense (REFUSE — already happened, not a fresh request)
- conditional (REFUSE — "if I had time", "if she's free")

UNDERSAMPLE: brainstorm, joke (still include, just less than the above).

""" + SHARED_SCHEMA_BLOCK

UTTERANCE_IN_CONTEXT_USER = """\
Generate {n} rows. boundary_tag distribution target for this batch:
{boundary_distribution}

Begin output immediately. NO preamble. NO summary at the end. Just
{n} JSONL lines.
"""

# ─────────────────────────────────────────────────────────────────────────
# Dataset 2: memory_resolution
# ─────────────────────────────────────────────────────────────────────────
#
# Utterance + simulated memory state → correctly resolved slots. Trains
# the engine to look up facts from memory rather than fire a clarifying
# question. ("Book Carbone" → "Carbone NYC, party of 2, Friday 7pm" by
# month 6, given a memory of the user's usual.)

MEMORY_RESOLUTION_SYSTEM = """\
You are generating training data that teaches an AI wearable how to
resolve under-specified utterances against the wearer's long-term
memory.

For each row:
1. Invent a plausible user_memory state — contacts with relationship
   history, prior trajectories on the relevant site, calendar habits,
   recurring preferences. Be realistic: real people have layered
   memories, not just one fact.
2. Compose a wearer utterance that is UNDER-SPECIFIED in the absence
   of memory but FULLY SPECIFIED once memory is consulted.
   - Example: "Book my usual at Carbone." With memory: party of 2,
     Friday 7pm, last 6 bookings all the same.
   - Example: "Email Sarah about tomorrow." With memory: the only
     "Sarah" the wearer has emailed in the last 30 days, plus the
     calendar entry for tomorrow.
3. Set expected_label to COMMIT (these are by definition actionable
   once memory resolves them).
4. Populate expected_intent with slots that are FILLED from memory,
   slots that NEED memory but were resolved, and slots that need
   inference (date-from-day, location-from-context).

KEY DIFFICULTY: the model must learn WHEN to trust memory (high-confidence,
recent, repeated pattern) vs WHEN to ask. Include ~10% rows where the
memory is AMBIGUOUS (two contacts named Sarah, two usual booking sizes)
and the label is REFUSE with reason "ambiguous_memory — would need a
clarification".

""" + SHARED_SCHEMA_BLOCK

MEMORY_RESOLUTION_USER = """\
Generate {n} memory-resolution rows. {ambiguous_pct}% of them must have
ambiguous memory and expected_label == "REFUSE" with reason "ambiguous_memory".

Begin output immediately. NO preamble.
"""

# ─────────────────────────────────────────────────────────────────────────
# Dataset 3: negative
# ─────────────────────────────────────────────────────────────────────────
#
# Intent-shaped but NOT actionable. Brainstorming, hypotheticals,
# third-party reporting, past-tense recap, counterfactuals, jokes,
# retractions. These are the false-positive killers. Every row here is
# expected_label != COMMIT.

NEGATIVE_SYSTEM = """\
You are generating training data of utterances that LOOK like requests
to act but are NOT. These are the false-positive killers for the
classifier. Every row has expected_label of REFUSE or STORE_AS_LATENT
— never COMMIT.

Each row needs:
1. A wearer utterance that contains action verbs ("book", "email",
   "schedule", "order", "remind", "send") OR action targets
   (restaurant names, contact names, calendar references) but is
   NOT a request to act.
2. A clear expected_reason explaining why a naive classifier would
   fire COMMIT but the correct answer is REFUSE / STORE_AS_LATENT.
3. boundary_tag set to the specific failure mode.

REQUIRED BOUNDARY MIX for this dataset:
- third_party reporting (~25%): "Sarah said she booked..."
- past_tense recap (~20%): "I already emailed John..."
- conditional / counterfactual (~15%): "If I had time, I'd..."
- brainstorm (~15%): "We could maybe go to..."
- joke / hypothetical (~10%): exaggerations, irony
- sarcasm (~10%): reveals aversion, never the action
- abandonment (~5%): retraction mid-utterance

CRITICAL: write the utterances to be ACTUALLY hard. A naive
keyword-spotter must fail on them. Use specific names, times, and
venues so the surface looks identical to a real COMMIT.

""" + SHARED_SCHEMA_BLOCK

NEGATIVE_USER = """\
Generate {n} negative rows balanced by the boundary mix above.

Begin output immediately. NO preamble.
"""

# ─────────────────────────────────────────────────────────────────────────
# Batch sizing recommendation (Pod C1 tuning target)
# ─────────────────────────────────────────────────────────────────────────
#
# The actual volume needed is whatever passes the 32 gold-standard set at
# 30+/32 after QLoRA. Start with these targets, regenerate the failed
# slice if eval is below threshold:
#
# - utterance_in_context: 25_000 rows
# - memory_resolution:     10_000 rows
# - negative:              15_000 rows
# Total ≈ 50_000 rows.
#
# DeepSeek V4 Flash on OpenRouter is roughly $0.0002/1k tok input and
# $0.0008/1k tok output. With an average ~500 output tokens per row,
# 50k rows ≈ 25M output tokens ≈ $20 + some input cost. Budget cap on
# the OpenRouter dashboard is the hard backstop.
BATCH_TARGETS = {
    "utterance_in_context": 25_000,
    "memory_resolution": 10_000,
    "negative": 15_000,
}

# Default boundary distribution for utterance_in_context (sums to 1.0).
# Tune after the first training round based on per-tag error rate.
DEFAULT_BOUNDARY_DISTRIBUTION = {
    "real_action": 0.40,
    "sarcasm": 0.10,
    "hedging": 0.10,
    "abandonment": 0.08,
    "third_party": 0.10,
    "past_tense": 0.07,
    "conditional": 0.05,
    "brainstorm": 0.05,
    "joke": 0.03,
    "multi_turn": 0.02,
}
