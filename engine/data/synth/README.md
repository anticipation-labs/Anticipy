# engine/data/synth — v-final-prototype synthetic data

This directory is the Phase 1 foundation for the **Stage 1.5 hedge / sarcasm /
abandonment classifier** described in the v-final-prototype master prompt.
Stage 1.5 sits between Stage 1 (demand detection) and Stage 2 (typed intent
extraction). It decides — **before** any action fires — whether an utterance
that *sounds* actionable should actually be acted on, stored as latent
intent, or refused.

## The three datasets

Each row in each dataset is a JSON object on its own line (JSONL). The
**schema is the same across all three datasets** so a single training /
eval pipeline can consume them.

```
{
  "id":              "<uuid>",
  "kind":            "utterance_in_context" | "memory_resolution" | "negative",
  "turn_history":    [{"speaker": "wearer"|"other", "text": "..."}],
  "utterance":       "<the latest wearer utterance>",
  "user_memory":     [{"kind": "...", "key": "...", "value": "...", "evidence_quote": "..."}],
  "expected_label":  "COMMIT" | "STORE_AS_LATENT" | "REFUSE",
  "expected_reason": "<short why-tag, free-form>",
  "expected_intent": {
    "action_category": "book_reservation" | "send_email" | "schedule_event" | "reorder" | ...,
    "slots":           { "<slot>": "<value>" | null },
    "needs_memory":    ["<slot>", ...],
    "needs_inference": ["<slot>", ...]
  } | null,
  "expected_memory_write": {
    "kind":  "preference" | "aversion" | "contact" | "habit" | "recurrence" | "sentiment_fact",
    "key":   "<short identifier>",
    "value": "<value>",
    "evidence_quote": "<the exact utterance fragment>"
  } | null,
  "boundary_tag":    "sarcasm" | "hedging" | "abandonment" | "third_party" |
                     "past_tense" | "conditional" | "joke" | "brainstorm" |
                     "real_action" | "multi_turn"
}
```

`expected_intent` is non-null iff `expected_label == "COMMIT"`.
`expected_memory_write` is non-null iff the utterance reveals durable info
(sarcasm-derived aversion, stated preference, contact relationship, etc.).

## File contents

| File                          | Purpose                                                | How produced               |
|-------------------------------|--------------------------------------------------------|----------------------------|
| `gold_standard.jsonl`         | The non-negotiable evaluation set. 30+/32 to pass.     | hand-authored from prompt  |
| `utterance_in_context.jsonl`  | Conversations around an utterance with typed intent.   | DeepSeek V4 Flash batch    |
| `memory_resolution.jsonl`     | Utterance + memory state → correctly resolved slots.   | DeepSeek V4 Flash batch    |
| `negative.jsonl`              | Intent-shaped but not actionable.                      | DeepSeek V4 Flash batch    |

## Phase 1 pipeline

Generation, validation, and adapter training run **offline-batch**, not in
the hot path. Concretely:

```
[OpenRouter DeepSeek V4 Flash]       Generator. Cheap & long-ctx. Pod C1
   |
   v
[engine/data/synth/generate.py]      Generator script (TODO). Reads prompt
   |                                 templates from `prompts.py`. Writes
   |                                 raw output to .jsonl.
   v
[engine/data/synth/validate.py]      Schema check + Gemini 2.5 Pro grades a
   |                                 random ~5% sample. Below agreement
   |                                 threshold → iterate prompts, regen
   |                                 the failed slice.
   v
[engine/data/synth/<kind>.jsonl]     Final dataset.
   |
   v
[Kaggle T4 QLoRA over Qwen3-8B]      Trains the hedge-filter adapter.
   |                                 Output: ~/.anticipy/adapters/
   |                                 hedge_filter_v1/
   v
[Eval against gold_standard.jsonl]   Must pass 30/32 to graduate Phase 1.
```

The generator is **NOT** wired yet (no `generate.py`). What's in this dir
today: `gold_standard.jsonl`, `prompts.py` (templates), `validate.py`
(schema check + sample grader). The generator itself is the next thing to
build once OPENROUTER_API_KEY lands.

## Cost & safety guardrails (real money)

- `OPENROUTER_API_KEY` is currently **empty** in `.env.local`. Phase 1
  generation cannot run until Omar provides one.
- DeepSeek V4 Flash via OpenRouter at the volumes Phase 1 wants
  (~50k examples across three datasets, ~500 tokens each) costs roughly
  $5–10 total. Budget cap on the OpenRouter dashboard is the enforcement
  point — `engine/data/synth/generate.py` will respect a soft cap env
  var `OPENROUTER_SOFT_CAP_USD` so a runaway loop doesn't blow past it.
- Generator output is written incrementally so a crash mid-run doesn't
  lose work.

## How `gold_standard.jsonl` was authored

The exemplar utterances spelled out in the master prompt (sarcasm,
hedging, abandonment, past-tense, real actions, multi-turn) are encoded
verbatim. The remaining ~half of the 32 are boundary variants the
generator will produce; once generated and reviewed, they get added to
this file. **30/32 of the FINAL set must pass for Phase 1 to graduate.**

Until the generator runs, the smaller hand-authored exemplar set serves
as the smoke-test gate.
