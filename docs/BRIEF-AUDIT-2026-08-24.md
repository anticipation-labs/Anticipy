# Law-6 audit of docs/BRIEF.html — 2026-08-24

Adversarial pass over the Brief against the tree it claims to describe.
11 auditors, one per section, ~1,251 distinct claims checked; 38 raised.
The refute stage died on a session limit, so **every finding below was
re-verified by hand** before being written down. Findings the auditors raised
that are NOT re-verified here were dropped, not carried.

Method note, per LAW 3: everything below is a `grep`/`wc`/`git log` against the
working tree at `a71d7ca7`, not a model's recollection.

---

## The headline: the Brief is one commit stale on its own two worst problems

```
1be9c163  2026-08-23  The Anticipy Brief — the hand-to-an-agent engineering document
4888612d  2026-08-24  the ask valve and the honest meeting window — shipped on the third round
```

`4888612d` is the **very next** commit to touch `brain/`. It fixed §9 open
problems 3 and 5, and §6 entry 21 items (1) and (4). Seventeen more commits
have landed since. The Brief still describes all of it as unfixed.

This is not a criticism of the Brief — it is the exact failure mode LAW 4
exists for. A spec that is not re-grounded rots at the speed of the branch.

---

## CONFIRMED — the Brief says UNFIXED, the tree says SHIPPED

| # | Brief claims | Verified reality |
|---|---|---|
| 1 | "AMBIENT ASK VALVE IS WELDED" (§6.21) and "The ambient ask valve is welded" (§9) | Shipped. `brain/anticipy_core.py:1915` is a branch commented **"THE ASK VALVE"**, calling `question_line` (imported :30) and setting `_pending_ask` (:949, :1933). Drained by `brain/worker.py:2126 maybe_ask_parked`, with a meeting guard at :2131 and the uninvited cap at :2151. |
| 2 | "MEETING_SETTLE_S=90" (§6.14, §6.3, §6.21, §9) | **No such constant exists.** `grep -rn MEETING_SETTLE brain/` returns a stale prose comment at `worker.py:2031` plus `MEETING_SETTLE_FLOOR_S = 360.0` / `MEETING_SETTLE_CEIL_S = 600.0` (:2069-2070) and an adaptive `min(CEIL, max(FLOOR, 2*MEETING_MAX_GAP))` (:2178-2179). The 90s wall the Brief calls "miscalibrated" was deleted for that reason. |
| 3 | "CAPTURE TIMESTAMPS UNWRITTEN BY THE APP … NO capture_ended_at" (§6.21, §5-AUDIO) | The app writes all three. `AnticipyBackend.swift:510-512` sets `capture_started_at`, `spoken_at` and `capture_ended_at` on every push, with a rationale comment at :496-499. |
| 4 | BrainClient is "DEAD CODE … a rebuilder should treat this file as vestigial" (§4) | The file is **gone**. `app/ios/Anticipy/Brain/` does not exist; deleted in `9fcdf5ae`. |
| 5 | "App expects extension 0.8.3" / agent row reads `ext/0.8.2` (§5-BACKEND, §4) | `expectedExtensionVersion = "0.11.0"` (`AnticipyApp.swift:114`). Its own comment records 0.8.3 as the rot that was fixed on 2026-08-24. |
| 6 | "The 3/day ceiling binds only one outbound path" (§9) | Binds two now — `worth_interrupting_him` and the parked-ask path at `worker.py:2151`. |
| 7 | "tests/ — 1004 deterministic tests" (§8) | 1054 collected, 1054 passing. |

## CONFIRMED — factually wrong, independent of staleness

| # | Brief claims | Verified reality |
|---|---|---|
| 8 | "research/supervised lanes are unclaimable by browsers" (§5-SECURITY) | **Backwards for one of the two.** `research_lane.pb.js:32` header: *"LANE 2 — `supervised_read` reaches a browser ONLY while somebody is watching."* It is browser-claimable, gated on a live `watching_until` lease. Only `research` is never claimable. A rebuilder reading the Brief would build the wrong fence. |
| 9 | workflow columns "…iOS decodes all of these" (§5-BACKEND) | `AgentJob` decodes **9 of 14**. Absent: `lineage_key`, `receipt`, `lease_token`, `lease_until`, `source_event_ids`. |
| 10 | "`deliver()` is the single exit" (§5-AUDIO) | `PhoneListener.stop()` calls `onLine?` directly, bypassing `deliver()` — so the flushed tail gets no echo check and no enrollment guard. |
| 11 | Footer + `CLAUDE.md` + `HARNESS-LAWS.md` cite `research/HOW-AN-AGENT-EXISTS.md` as "the field map" | Does not exist in the tree, on any branch, or anywhere in history. Same for `overnight/fellowship_gate.py`, cited as a scoreboard by both law files. |

## CONFIRMED — line references have drifted wholesale

Not pedantry: the Brief's value is that a rebuilder can follow a citation.

- `brain/worker.py` refs run **~295-300 lines short** (file is 3444 lines).
  e.g. "NOTHING reads it yet" cited at 3060-3068, actually 3356-3366.
- `app/ios/Anticipy/Audio/PhoneListener.swift` refs run **40-190 short** (731 lines).
- `backend/pb_hooks/guard.pb.js` described as **335 lines**; it is **522**, so
  every reference hung off that number lands ~170 lines early.

## Smaller, verified

- `profile_facts.source` enum omits `supervised_professional` (`anticipy_core.py:413`).
- `edges.rel` lists 5 values; only 3 are ever written (`about`, `committed_to`, `involves`).
- `_UNTRUSTED_BUDGET_DIVISOR` is in `anticipy_core.py:418`, not `memory.py`.
- `"segmented"` is listed as a live `decision` value; it appears only in
  `CAPTURE-ARCHITECTURE.md:199` as a *designed* flow.
- `place_turn` is described as pure; it takes a `SegmentStore` and does I/O.
- tejas_gate is described as running "without imports"; legs 2 and 4 import
  `brain.anticipy_core` directly.

---

## Measured state at `a71d7ca7` (2026-08-24)

```
done_gate.py        5/6 PASS   — first failing leg: 6, A STRANGER
tejas_gate.py       8/8 PASS
pytest              1054 passed
extension/tests     56/56 suites
triage_eval --live  68 / 68 / 72 / 72 %   (Brief claims 80%)
is_the_brain_live   1 RULE BROKEN IN PRODUCTION
```

### replay_call.py — the 137 recorded Tejas lines through this brain

| | 2026-08-23, build 75 | today |
|---|---|---|
| decisions | 131 ignore / **6 act** / 0 ask | 136 ignore / **1 act** / 0 ask |
| mid-call texts | **4** | **1** |
| invented people | **1** (Dr. Evans) | **0** |
| after-call digest | none | one |

The surviving text is `"5 PM CST is 3 PM PST."` — recorded failure #4, which
that evening was a *held card* containing a converter-page summary. The
surviving act is the Tuesday 3 PM meeting, which `FINDINGS.md` calls the one
defensible act, and it is held for the digest rather than fired mid-call.
All five wrong acts are gone.

### The triage_eval gap, reconciled

Four live passes: 68/68/72/72. Seven rows fail in **all four** — settled, not
variance. Four of the seven are `tejas-*` rows, including `tejas-domain`
(buy the misspelled domain) and `tejas-him`.

That is not a contradiction of the green tejas_gate. `triage_eval` measures the
**raw prompt** — `in_two_way_call_kwarg_missing: true`, no posture, no owes
gate, no shard floor. The replay proves the guards below the model catch every
one of them. So: **the judgment is still wrong there; the seatbelt is what is
saving it.** Whether the Brief should say 70%, or the eval should measure the
composed system, is a decision for the owner.

### LAW 3 — production is not this brain

`overnight/is_the_brain_live.py`: 2 uninvited messages sent between 22:00 and
08:00 in the last 24h, a rule this tree enforces. This tree fingerprints
`af23239bc2bc`. Not compared against Railway — the worktree is not linked
(`railway link` needs a human).

---

## What this audit did NOT establish

- The refute stage failed on a session limit; `laws-never` (§3, §10, §1, §2)
  was never audited at all. Those sections are **unchecked**, not clean.
- §7's 105 worked examples were not audited — they are judgment, not fact,
  and have no source to check against.
- Nothing here was verified against LIVE except `is_the_brain_live`. Per LAW 3
  every "fixed" above is repo-green only.
