# Anticipy System V1 resource envelope

This is a declared, enforced envelope, not an aspiration. A phase gate
runs the suite under a 2 GB cap that is deliberately below Mac class so
that Mac class resource assumptions cannot be silently baked in. The
same engine is the local single user Mac form and the multi tenant
scaled form; the envelope is per engine instance, and a tenant at scale
is one instance.

## Memory

| item | value | how enforced |
|---|---|---|
| working set cap (per engine instance) | 2 GB | RLIMIT_AS best effort plus the binding check: measured peak ru_maxrss must stay under 2 GB, run by `tests/anticipy/gate_resource.py` |
| RLIMIT_AS hard enforcement on macOS | not reliably enforceable | stated honestly; CPython on macOS maps large shared regions, so the measured RSS check is the binding one. On a Linux home base RLIMIT_AS is enforceable and is set. |

## Model calls per decision (design budget; measured at P5, finalized at P10)

The proactive cascade is text only and small. Per conversational unit:

| stage | calls | note |
|---|---|---|
| demand detection (Stage 1) | 1 | ~80 output tokens |
| hedge filter (Stage 1.5) | 1 | ~400 output tokens |
| intent extraction (Stage 2) | 0 or 1 | only on COMMIT or actionable latent |
| addressee/authority + memory resolution | folded into the above prompts where possible | one extra call only when a reference must be resolved |

Design budget: 2 to 4 model calls per decision, well under 4k prompt
tokens and under 1.5k completion tokens total. The real per decision
cost is read from the adapter call ledger (`<data_dir>/model_calls.jsonl`)
and reported with no rounding in the P11 handoff. The frozen action
engine, by contrast, is vision heavy (~1.5 cents/task); the proactive
text path is far cheaper and that number is measured, not assumed.

## Disk per user day of logs

| item | value |
|---|---|
| trajectory record | one JSONL line per decision, order of 1 to 3 KB |
| design budget | a heavy ambient day is thousands of decisions, order of a few MB per user per day, JSONL, compressible, exportable |

The trajectory log is the flywheel substrate. It is portable JSONL under
the per user partition in the adapter data dir, identical local and at
scale.

## Model call budget per phase run

Generation plus decision plus the 10 percent adversarial second model
sample. The fixed corpus is about 530 engine core cases plus the whole
system categories. Cached corpora are reused across phases so generation
is paid once per category, not once per phase.

## Status

- P0: cap declared, gate harness runs empty within the cap. Per decision
  numbers are design budget until measured.
- P5: per decision model calls and tokens measured on the full proactive
  corpus and written here.
- P10: final measured numbers replace the design budget; the gate
  reruns the full suite under the 2 GB cap.
