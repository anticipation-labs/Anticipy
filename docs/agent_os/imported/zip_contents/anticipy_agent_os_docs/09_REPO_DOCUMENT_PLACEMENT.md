# 09 — Repo Document Placement and Cleanup

## Goal

Make the repo self-steering. A new agent should know what Anticipy is, what is done, what is blocked, and exactly what to do next without asking the user to re-explain.

## Directory layout

Recommended:

```text
logs/factory/
  CONSTITUTION.md
  CURRENT_TRUTH.md
  RECEIPTS.md
  DECISIONS.md
  FAILURES.md
  NEXT_GATE.md
  AGENT_PROTOCOL.md
  RESEARCH_NOTES.md
  TIMELINE.md
  archive/

docs/product/
  DONE.md
  ARCHITECTURE.md
  ACTION_MODEL.md
  ONBOARDING.md
  BROWSER_ARM.md
  API_ARM.md
  VOICE_AND_LISTENING.md

docs/evals/
  EVAL_HARNESS.md
  SYNTHETIC_LIFE_BANK.md
  HIDDEN_TRUTH_SCHEMA.md
  RECEIPT_SCHEMA.md

docs/runbooks/
  STARTUP.md
  LONG_RUNNING_LOOP.md
  RELEASE.md
  ACCOUNT_CONNECTION.md
  INCIDENT_RESPONSE.md
```

## What to put where

### `logs/factory/CONSTITUTION.md`

Short supreme law. Stable. Read first.

### `logs/factory/CURRENT_TRUTH.md`

Mutable. Updated every run.

### `logs/factory/RECEIPTS.md`

Append-only ledger of proven done.

### `logs/factory/DECISIONS.md`

User decisions and architecture calls.

### `logs/factory/FAILURES.md`

Failure modes and tripwires.

### `logs/factory/NEXT_GATE.md`

One next gate only. No vague backlog.

### `CLAUDE.md` / `AGENTS.md`

Router. It must say: read Constitution, Current Truth, Receipts, Decisions, Failures, Next Gate before acting.

## What to archive

Archive stale/duplicative docs that conflict with the current law:

- old handoffs that redefine done smaller,
- old target files that optimize saturated metrics,
- old “percentage done” claims,
- old mock-only success reports,
- old OpenRouter/funding diagnoses that were corrected,
- old browser readiness claims that did not check actual extension connection.

Do not delete. Move to archive.

## What not to touch without explicit task

- hidden holdout answer keys,
- production secrets,
- user tokens,
- scoring thresholds,
- receipt ledger history,
- failure ledger history,
- real account data,
- payment functions.

## Cleanup command pattern

```bash
mkdir -p logs/factory/archive/$(date +%F)
# move stale docs only after writing replacement
mv logs/factory/OLD_HANDOFF.md logs/factory/archive/$(date +%F)/OLD_HANDOFF.md
```

## Required commit style

Use commits that say what was proven, not just what changed:

- Good: `Slice 0: Calendar/Gmail write now requires independent read-back receipt`
- Bad: `update api_hand.py`

## End-of-run update

Every run ends by updating:

1. `CURRENT_TRUTH.md`
2. `RECEIPTS.md` if anything closed
3. `FAILURES.md` if anything broke
4. `NEXT_GATE.md`
5. Git commit or explicit reason not committed
