# Five agents "stalled". The disk was full.

**Date:** 2026-08-25
**Symptom:** `Agent stalled: no progress for 600s (stream watchdog did not recover)`
**Actual cause:** `cat: stdout: No space left on device`

## Why this is worth a file

The stall message and the real fault share no words. An agent that dies of a
full volume reports a *watchdog timeout*, so the obvious reading — the model
hung, re-dispatch it — is wrong, and re-dispatching into a full disk kills the
replacement the same way. That is how five agents were lost in one evening:
each death looked independent, and the shared cause was invisible from every
one of them.

The only reason it was caught: a background *bash* task failed in the same
window and printed the true error, because a shell reports ENOSPC and an agent
harness reports a timeout.

## What fills it

| Source | Size | Regenerable |
|---|---|---|
| `/private/tmp/anticipy-dd` (iOS DerivedData) | 1.6 GB | yes, every build |
| Scratchpad `mut_*` / `rev*` tree copies | grows unbounded | yes |
| CoreSimulator device data | 7.4 GB | mostly |
| `/private/tmp/w/1096` — **another project**, not ours | 2.2 GB | not ours to delete |

The scratchpad is **shared between agents, not session-isolated** — an earlier
agent flagged this. So concurrent mutation-testing agents multiply each other's
footprint and all die together.

## Recovery

    rm -rf /private/tmp/anticipy-dd
    find "$SCRATCHPAD" -maxdepth 2 -type d \( -name 'mut_*' -o -name 'rev*' \
        -o -name DerivedData -o -name '*-dd' \) -exec rm -rf {} +
    xcrun simctl delete unavailable

Freeing 1.5 GB took the volume from **96% used to 52% used** — APFS releases
purgeable space only once pressure drops, so a small deliberate reclaim can
return several times its own size.

## The rule

**When two or more agents stall together, run `df -h /` before re-dispatching
anything.** Simultaneity is the tell: independent model hangs do not
synchronise, shared-resource exhaustion does.
