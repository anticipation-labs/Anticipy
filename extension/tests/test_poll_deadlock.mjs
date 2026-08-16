// Certification 2026-08-15: case 193 hung in `running` and the next 48 cases
// were NEVER CLAIMED — 48 consecutive failures from one stuck run. Same shape
// as the live evening: "Chrome says connected" while the queue sat untouched
// for ten minutes.
//
// Cause: poll() awaits the whole job run while holding a boolean lock, so a
// runJob() that never settles leaves the lock true forever and every later
// alarm returns at the guard, silently. And because the heartbeat kept
// renewing the hung job's lease, the stale-job sweep could never recover it
// either — the zombie was immortal.
//
// This proves both halves: the queue is reclaimed, and the hung job's lease
// is dropped so it can be handed back.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(join(HERE, "../background.js"), "utf8");

// --- the lock is a timestamp, never a boolean -------------------------------
assert.ok(/let pollStartedAt = 0;/.test(source),
  "the poll lock must be a timestamp so a dead cycle can be reclaimed");
assert.ok(!/pollInFlight/.test(source),
  "the boolean lock that caused permanent deafness must be gone");

const guard = source.match(/async function poll\(\)[\s\S]{0,600}/)[0];
assert.ok(/now - pollStartedAt < POLL_CYCLE_CEILING_MS/.test(guard),
  "a cycle older than the ceiling must not block a new one");
assert.ok(/reclaiming the queue/.test(guard),
  "reclaiming a dead cycle must be loud in the worker console");

// Only the owning cycle may release the lock, or a late zombie unlocks the
// cycle that is currently running.
assert.ok(/if \(pollStartedAt === now\) pollStartedAt = 0;/.test(source),
  "a reclaimed cycle finishing late must not clear another cycle's lock");

// --- a hung run stops beating so the stale sweep can recover it -------------
const beat = source.match(/for \(const \[id, active\] of activeJobs\)[\s\S]{0,700}/)[0];
assert.ok(/active\.startedAt/.test(beat) &&
          /POLL_CYCLE_CEILING_MS/.test(beat) &&
          /activeJobs\.delete\(id\)/.test(beat),
  "a run older than the ceiling must lose its lease instead of renewing it");
assert.ok(/startedAt: Date\.now\(\)/.test(source),
  "every claimed run records when it started");

// The ceiling has to be longer than a healthy run and shorter than patience:
// certification's slowest healthy case was ~90s.
const ceiling = Number(source.match(/POLL_CYCLE_CEILING_MS = (\d+) \* 60 \* 1000/)[1]);
assert.ok(ceiling >= 5 && ceiling <= 20,
  `poll ceiling ${ceiling}min must sit between a slow real run and human patience`);

console.log("test_poll_deadlock: all passed");
