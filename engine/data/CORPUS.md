# Proactive Training Corpus

A pipeline that turns Anticipy's accumulated `(transcript -> intent -> user
verdict -> outcome)` signal into a fine-tuning-grade dataset for distillation
or few-shot calibration.

## What's in this directory

| File                          | Purpose                                                      | Committed? |
|-------------------------------|--------------------------------------------------------------|------------|
| `export_training_corpus.py`   | Pulls `proactive_training_corpus` view -> JSONL              | yes        |
| `build_few_shot_block.py`     | Picks N positive + M negative exemplars from JSONL           | yes        |
| `calibrate_few_shot.py`       | Before/after benchmark with the few-shot block               | yes        |
| `training_corpus.jsonl`       | The exported dataset (real user transcripts)                 | NO — gitignored |
| `few_shot_block.txt`          | The rendered prompt fragment derived from the corpus         | NO — gitignored |
| `proactive_e2e.jsonl`         | Synthetic benchmark (already committed elsewhere)            | yes        |

The SQL view itself lives in `supabase/migrations/20260508_proactive_training_corpus.sql`.

## What the corpus is

One row per intent that reached a TERMINAL state (`confirmed`, `rejected`,
`executed`, `failed`, `auto_proceeded`) at least 48 hours ago. Each row has:

- `transcript_window` — the conversation window that produced the intent
  (built from `anticipy_transcripts` when available, with `evidence_quote`
  as a fallback).
- `extracted_intent_json` — the intent the system actually emitted
  (`action_type`, `summary`, `evidence_quote`, `parameters`, `importance`,
  `confidence`).
- `gate_verdict` — the terminal status.
- `signal_kind` / `signal_reasoning` — the matching `anticipy_preferences`
  row (one-sentence LLM summary of WHY the wearer accepted/rejected).
- `executed_outcome` — whether `anticipy_actions` ran successfully.

Test users (`e2e-test-*`, `*@anticipy-test.local`) are filtered out at the
view level so synthetic benchmark data never poisons the corpus.

## How to refresh

The pipeline is OPERATOR-RUN ONLY. There is no cron, no hook, no automatic
trigger. An operator must:

```bash
cd /workspaces/Anticipy/engine

# 1. Pull the view to local JSONL (gitignored).
export $(grep -v '^#' ../.env.local | xargs)
python data/export_training_corpus.py
# -> writes engine/data/training_corpus.jsonl

# 2. Build a few-shot block (8 positive + 4 negative exemplars).
python data/build_few_shot_block.py
# -> writes engine/data/few_shot_block.txt

# 3. (Optional) Run the before/after calibration on 30 stratified scenarios.
python data/calibrate_few_shot.py 30
# -> prints baseline vs few-shot pass rate, precision, recall.

# 4. (Optional) Toggle the few-shot block in production.
# Set ANTICIPY_FEW_SHOT_BLOCK to the file contents in the Vercel env.
# Default behavior unchanged when env var is empty.
export ANTICIPY_FEW_SHOT_BLOCK="$(cat data/few_shot_block.txt)"
```

The export script supports `--limit N`, `--out path`, and `--dry-run`.

## Privacy + access

- The view is `security_invoker = true` and explicitly revokes `anon` /
  `authenticated`. Only the `service_role` key can read it.
- The export script reads from PostgREST with `SUPABASE_SERVICE_ROLE_KEY`.
  No anon path exists.
- `training_corpus.jsonl` and `few_shot_block.txt` are in `.gitignore` —
  CI / operators will not accidentally commit real transcripts.
- The export script applies a defense-in-depth redaction pass on
  transcripts: emails, phone numbers, and long digit runs are replaced
  with `[EMAIL]` / `[PHONE]` / `[NUMBER]` placeholders before they leave
  the database.
- Treat the local file like a database dump: never paste into chat/docs,
  encrypt at rest if shared, delete when no longer needed.
- The corpus filters intents older than 48 hours so in-flight items
  (where the wearer might still revoke consent) never appear.

## Few-shot calibration result

Initial calibration on 26 stratified scenarios (the proactive_e2e.jsonl
dataset has 26 distinct categories):

| Metric         | Baseline | + Few-shot block | Lift          |
|----------------|----------|------------------|---------------|
| pass rate      | 23.1 %   | 34.6 %           | +11.5 pts     |
| avg precision  | 0.321    | 0.462            | +0.141        |
| avg recall     | 0.372    | 0.513            | +0.141        |
| false positives| 18       | 13               | -5            |
| missed         | 5        | 5                | 0             |
| spurious       | 4        | 4                | 0             |

Even on a tiny corpus (16 rows of real signal -> 8 positive + 4 negative
exemplars), the few-shot block measurably reduces false positives while
preserving recall. The lift comes mostly from precision — exactly what
you'd expect from showing the LLM "the wearer rejected this kind of thing".

## Future fine-tuning plan

### When to fine-tune vs few-shot

- Few-shot (current): cheap, instant to refresh, no model training cost,
  no infra. Practical floor of ~5 examples; ceiling around ~50 before
  the system prompt gets too long. The right tool while corpus < 1k rows.
- Fine-tune: warranted when the corpus crosses ~1k rows AND the few-shot
  precision plateau leaves real money on the table (false-positive
  notification storms costing trust, missed real intents costing trust).
  Switch criteria: `pass_rate > 75%` on the synthetic benchmark with
  few-shot, but `precision < 0.85` on real production traffic.

### Target model class

- Tier 1 (default): Gemini 2.5 Flash — Google does not currently expose a
  public API for fine-tuning Flash. When that ships, this is the obvious
  target (cheap inference, exactly the model the production route uses).
- Tier 1 fallback: a small open-weight model (Llama 3.3 70B or Mistral
  Small) fine-tuned on the JSONL via LoRA. ~8h on a single H100 at this
  scale. Hosted on Together / Fireworks at $0.20-0.60 / M tokens.
- Tier 2 (escalation): Claude Sonnet 4.5 / Opus do not need fine-tuning at
  this scale; rely on the few-shot block plus the existing prompt rules.

### Expected cost

- Few-shot: zero training cost, ~10 % more tokens per inference call
  (the block is ~5.7 KB).
- LoRA fine-tune of Llama 3.3 70B at 1-5k examples: ~$50-150 in compute,
  ~5-10 % per-call inference savings vs Flash.
- Hosted Gemini Flash fine-tune (when public): per Google preview docs,
  ~$8 per 1M training tokens. At 5k examples averaging 2 KB each, ~$80.

### Pipeline maturity gates

1. Corpus has > 200 rows of `signal_kind != null` (real preference signal).
   Today: 0. Target: Q3 2026.
2. The few-shot calibration shows < 2 pts of lift on a fresh stratified
   benchmark — diminishing returns triggers the fine-tune decision.
3. Production false-positive rate (rejections / total intents) dips below
   8 %. Above that we keep iterating on the prompt + few-shot block.
4. Cost per analyze call exceeds $0.0005. Today ~$0.0001. Distillation to
   a smaller fine-tuned model becomes economically attractive there.
