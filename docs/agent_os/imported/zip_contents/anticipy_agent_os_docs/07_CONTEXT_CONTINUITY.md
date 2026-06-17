# 07 — Context Continuity

## The problem

Models forget. Context compacts. New agents do not inherit instincts. A future agent can accidentally undo weeks of product law unless the law lives outside the model.

## The solution: durable genome

Create these files and load them in order every session:

1. `CLAUDE.md` or agent router.
2. `logs/factory/CONSTITUTION.md`.
3. `logs/factory/CURRENT_TRUTH.md`.
4. `logs/factory/RECEIPTS.md`.
5. `logs/factory/DECISIONS.md`.
6. `logs/factory/FAILURES.md`.
7. `logs/factory/NEXT_GATE.md`.
8. `logs/factory/RESEARCH_NOTES.md`.
9. `logs/factory/AGENT_PROTOCOL.md`.

## Constitution contents

Must include:

- full done definition,
- prepare-and-park rule,
- no self-attestation,
- no vent action,
- money hard stop,
- receipts only,
- skeptic law,
- no silent scope shrink,
- big details before micro details.

## Current truth contents

Must include:

- date/time,
- branch/commit,
- what is proven,
- what is partial,
- what is absent,
- what is blocked,
- next gate,
- exact commands to resume,
- latest model route verification,
- active services/ports,
- dirty worktree status.

## Receipts contents

Append-only. Each receipt:

- gate,
- date,
- commit SHA,
- artifact proof,
- skeptic verdict,
- commands run,
- known limitations.

## Decisions contents

All user product decisions with dates:

- prepare generously, park safely, ask only press-go,
- no acting on vents,
- money/payment hard stop,
- browser-use open-source arm under our model,
- big things before micro details,
- no fake percentages.

## Failures contents

Every failure with tripwire:

- OpenRouter misrouting,
- stale worktree patches,
- self-attesting proof,
- sarcasm false-action,
- money payment-send hole,
- browser bridge misleading readiness,
- laptop sleep killing loops,
- research taper.

## Startup ritual

Every fresh session:

```bash
git status --short
git branch --show-current
git log --oneline -5
cat logs/factory/CONSTITUTION.md
cat logs/factory/CURRENT_TRUTH.md
cat logs/factory/RECEIPTS.md
cat logs/factory/DECISIONS.md
cat logs/factory/FAILURES.md
cat logs/factory/NEXT_GATE.md
python scripts/verify_model_route.py
bash scripts/run_suite.sh
```

If any file is missing, create it before building.

## Agent injection

Every spawned agent receives:

- Constitution summary,
- current gate,
- allowed files,
- forbidden files,
- receipt requirement,
- skeptic criteria,
- failure tripwires.

## Compaction rule

Before any long run, update `CURRENT_TRUTH.md`. After any completed gate, update `RECEIPTS.md`. After any failure, update `FAILURES.md`. This makes shutdowns survivable.

## Archive rule

Never delete stale docs blindly. Move them to:

```text
logs/factory/archive/YYYY-MM-DD/<filename>
```

Then write a short archive note: why archived, replacement doc, date.
