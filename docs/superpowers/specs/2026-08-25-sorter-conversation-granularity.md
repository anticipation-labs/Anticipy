# SORTER — judge closed conversations, not lines

**Spec, 2026-08-25.** Board card §11 (SORTER), part 2 of 5. Option A, built in
option C's shape. Nothing here is a task list and nothing here is code.

Retiring `shard_too_thin` is the stated expiry of one of the five pieces of tape
`overnight/tape_gate.py` holds red by name (`[tape:shard_too_thin]`,
`tape_gate.py:480-493`, audit item 20). This spec is what that retirement costs.

---

## 1. The card's diagnosis is half right, and the half that is wrong changes the design

The card says she is **context-blind**. She is not. She is **line-scoped**, and the
context she gets is deliberately inert. Verified:

| Claim | Verdict | Where |
|---|---|---|
| One model call per line | **True** | `worker.py:3308` calls `anticipy.hear(line, …)` once per event; `Brain.triage` (`orchestrator.py:434`) takes a single `transcript_line` |
| The conversation reaches the model | **True — as a pipe-joined string in a parenthesis** | `anticipy_core.py:2574-2576`: `earlier = " \| ".join(c for c in convo[-16:] …)` → `(Earlier in this conversation: …)` |
| Which lines it contains is decided by an 8-word count and a 45-second timer | **True** | `recent_turns(segment_id, limit=8)` (`segmenter.py:299`) over the open segment; the segment is chosen by `decide_link`'s `len(text.split()) < 8` (`:149`), `len(overlap) >= 2` (`:142`), `_ANAPHORIC` (`:44`) and `CONTINUE_S = 45` (`:28`) |

So the payload is not empty. Four things are wrong with it, and only the fourth is
what the card describes:

1. **It is capped at 8 turns and carries no structure.** No timestamps, no gap
   markers, no turn boundaries, no voice verdicts — one flat string. The model
   cannot tell a 2-second gap from a 4-minute one, or three speakers from one.
2. **It is ordered by arrival, not by capture.** `recent_turns` sorts
   `"-created"` (`segmenter.py:309`). `segmenter.py`'s own module docstring calls
   capture-keying "THE RULE THAT MUST NEVER BE BROKEN" and names Omi #6551 as the
   bug it prevents. The one function that feeds the model breaks it. Our pendant is
   store-and-forward, so backlog reaches the prompt out of order.
3. **The context can belong to a conversation that is already over.**
   `open_segment()` runs at `worker.py:3282`, `place_turn` at `:3363` — *after*
   `hear()`. `should_close` is evaluated only inside `place_turn`
   (`segmenter.py:375`). So the first line of a new conversation is judged with the
   previous conversation's last eight lines in its prompt. That is over-context, and
   it is the exact failure `inherited_errand` (`orchestrator.py:563`) exists to veto
   after the fact.
4. **The context is untrusted by construction.** `SECOND_LOOK`
   (`orchestrator.py:417-431`) says it in capitals: *"THAT CONTEXT IS NOT HIM
   COMMITTING … Judge ONLY the current line's own words."* `TRIAGE_SYSTEM` says the
   same. And the return schema has one verdict, for one line.

**The real diagnosis: the unit of judgment is a line, the conversation is evidence
she is told not to act on, and no verdict can be attached to any turn but the
current one.** "Give her the conversation" does not fix that — she has eight lines
of it. Making the conversation the judged unit does.

One more schema fact the card's own wording exposes: the model can return
**ignore / ask / act only**. `answer` is minted by routers in `hear()`
(`:1394` briefing, `:1414` recall) that never call the model at all, and
`TRIAGE_SYSTEM` folds a spoken factual question into "act with a research goal"
(`overnight/triage_eval.py` header states this as the scoring rule). The four-way
verdict the card names does not exist in the model's schema. §5 adds it.

---

## 2. Segment-close events already exist as a rule, and do not exist as an event

**They do not need EARS.** The card's stated dependency is not real.

What exists today:

- The **rule**, pure and tested: `should_close` (`segmenter.py:159`), `segment_all`
  (`:191`), `tests/test_segment_all.py`, `proof/test_segmenter.py`.
- The **transition**: `SegmentStore.close` (`segmenter.py:349`) PATCHes
  `status="closed"` and `ended_at`.
- The **storage**: the `segments` collection with `triaged_through_seq`, `dirty`,
  `summary`, `entities`, `parent_segment`, `supersedes`
  (`backend/pb_migrations/1700000004_segments.js`), and `events.segment`, `seq`,
  `capture_started_at`, `capture_ended_at`.
- The **capture timestamps** the boundary rule needs — shipped from the phone:
  `AnticipyBackend.swift:499-520` writes `capture_started_at` / `capture_ended_at` /
  `parent_line`; the worker reads them in `capture_key`.

What does not exist:

- **Any wall-clock evaluation of closure.** `should_close` is called from exactly one
  place, `place_turn` (`segmenter.py:375`), which runs only when the *next* turn
  arrives. A conversation that ends and is followed by silence **never closes**. Its
  row stays `status="open"` forever.
- **Any emission.** `close()` PATCHes a row. Nothing polls it, nothing subscribes, no
  backend hook reads `segments` (grepped `backend/pb_hooks/` — only account-deletion
  and ownership-claim code touches the table).
- **Any reader.** `worker.py:3357` says it in its own words: *"NOTHING reads it
  yet."*
- **`is_late` (`segmenter.py:172`) has no callers anywhere in the shipped tree.**
  `tests/test_continues.py:14` records this. The late-thought rule is written and
  unwired.

**So the missing piece is one wall-clock sweep inside the worker's existing poll
loop.** The precedent is already there and already fires on quiet:
`maybe_ask_parked` (`worker.py:2126`, `ASK_QUIET_S = 120`) and
`deliver_pending_digest` (`:2073`). This is server-side. **It unblocks the card
tonight.**

What EARS still owes SORTER is not an event — it is capture *quality*. On the one
real paired conversation, 33% of words were captured and `speaker` was empty on all
137 rows. Better payloads do not fix a transcript that lost two words in three. That
is EARS' card, and this one does not wait for it.

---

## 3. What closes a conversation

A conversation closes when **capture-time quiet ≥ `CONTINUE_S` (45 s)** *and*
**arrival-time quiet ≥ `SETTLE_S`** since the last row landed for that segment.

Both keys, because they answer different questions. Capture-time quiet asks *did the
person stop talking* — the only question that has ever been allowed to move a
boundary. Arrival-time quiet asks *has the transport finished delivering what they
said* — a fact about BLE and the offline queue, not about words. Closing on capture
time alone means a 3-minute pendant backlog lands into a conversation we already
judged; closing on arrival time alone is Omi #6551 reproduced in our own code.
`SETTLE_S` is a transport parameter and is derived from the offline queue's own flush
behaviour, not picked.

Also closing, unchanged from today's rules:

- **`MAX_SEGMENT_S` (1800 s) force-close**, which **relinks**: the successor carries
  `parent_segment` and inherits the parent's summary, entities and any unanswered
  ask. A forty-minute call is one conversation to a human and the segment row is only
  a storage bound. `segment_all` deliberately does not apply it (`:191` docstring)
  and that stays true.
- **Session end** as reported by the phone, when the app says listening stopped, is
  evidence of quiet arriving early — never evidence a conversation continues.

**A closed segment is never reopened.** Closing is final; linking is additive. The
alternative — reopen, re-judge the merged whole, retract dispatched work — means
cancelling jobs that may already be running in his browser. That is the wrong trade
and CAPTURE-ARCHITECTURE.md already decided it.

### What happens to a thought that arrives after close

This is where "can't miss" breaks, so it is enumerated, by **capture time**, with no
default branch:

| Case | What happens |
|---|---|
| Capture time falls inside or adjacent to a **closed** segment, and is younger than `LATE_MAX_S` (6 h) | Inserted into that segment; the row is marked `dirty`. The segment is re-judged **once**, after `BACKFILL_SETTLE_S` of no further inserts, writing `supersedes`. **Only items still `awaiting_confirm` may be revised.** Anything released, running, done or already texted about is never retracted. |
| Capture time is **older than `LATE_MAX_S`** | Memory only. Ingested, never judged, stamped so — this is what gives `is_late` (`segmenter.py:172`) its first caller. Acting on six-hour-old intent is worse than missing it. |
| Capture time is **after** the close and continues the topic | A new segment with `parent_segment` set. The parent's summary and entities ride forward as thread context. The parent is **not** re-judged. |
| Capture time is unreadable | The turn is not placed and not judged, and **that is recorded as an outcome**, not a silence. `parse_ts` already refuses implausible stamps (`segmenter.py:52-88`) rather than guessing. |

**The named killer, and the rule that answers it.** The previous draft of this design
advanced `triaged_through_seq` *before* the model call, on the claim-first precedent
from the 2026-07-30 six-jobs-from-one-line incident. That precedent is
claim-first **paired with** `release_stranded_claims` (`worker.py:2664`) — *"Hand back
anything a previous life claimed and never finished."* Advancing a cursor has no
such arm: one transient timeout strands every word behind it, permanently, and a
sweep that then stamps those never-judged turns "ignore (judged with its
conversation)" is a **false delivery claim** — the same shape as findings marked
delivered and never sent.

So: **the cursor advances only on a parsed verdict.** Turns enter a segment claimed
with the existing `mark_processed(ev, "processing")` (`worker.py:2567`), the exact
stamp `release_stranded_claims` already sweeps, so a dead worker's segment members
come back on their own. Idempotency against double-acting is carried by three belts
that already exist: the claim, the `[NEW]`-only instruction in the prompt, and
`_queue_job`'s merge/dedupe. Never by a cursor with no recovery arm.

---

## 4. What the one strong call sees

The whole closed segment, rendered as **turns**, not as a joined string. Per turn:

- a stable **ordinal** (from `turn_count` at append — the total order the verdict
  points into),
- `[hh:mm:ss]` **capture** time and `[gap: Ns]` since the previous turn,
- the phone's **voice verdict**: `owner`, a named other, or `no verdict` — carried
  as evidence, never inferred from wording. `memory._speaker_verdict` (`memory.py:2133`)
  explicitly refuses to infer speaker from words and the audit calls that the right
  instinct; it stays right here.
- **capture source** (`phone_mic` / `pendant` / `typed`), which decides nothing and
  exists to be compared,
- `[NEW]` on turns past `triaged_through_seq`.

Around the turns:

- **Participants** as evidence: the roster's own vocabulary, plus which voices
  actually appear in this segment. Never a claim about who is present.
- **The parent thread** when `parent_segment` is set: its one-line summary, its
  entities, and any question of ours that is still unanswered.
- **Recalled memory**, through the same `memory_notes` sanitizer the browser agent's
  memory block uses (`anticipy_core.py:2645`), so a fact unsafe to replay is unsafe
  in both places by construction.
- **The posture**, read at *judge* time and not at attach time: `MEETING_ARMED` is
  fresher when the segment closes than when its first turn landed.
- **What is currently held or awaiting his answer.** "Okay let's do it" is judgeable
  only against the card it lands on. Today a regex releases that card
  (`anticipy_core.py:1485`) precisely because the model was never shown it.

### What it returns

For the segment: a one-line **`summary`** and an **`entities`** list, written back to
the row. Not a spare output — `decide_link` reads both as its prefilter
(`segmenter.py:132-143`) and the next segment reads the summary as thread context, so
this call is never wasted.

Plus **`splits_after`**: ordinals after which the model read a *new* conversation
starting. Items are scoped to their side of a recorded split. See §11 — this is how
the model's reading of the boundary starts governing what is judged together, even
while the clock still picks the database row.

Plus **`items`**: 0..4 objects, each a verdict about a finished thought:

```
{ decision: ignore | ask | act | answer,
  goal, missing, assumption, touches, addressee, owes,
  owner_committed: true|false,
  evidence: [ordinals] }
```

`answer` is new (§1) — a spoken question to her, answerable from what she knows, is a
verdict and not a routing accident.

Two output rules are structural, not stylistic:

1. **Every item names its evidence turns by ordinal, and every ordinal must be a
   turn in this payload.** An out-of-range ordinal is discarded, the same
   discipline the numbered link question already uses (`anticipy_core.py:2660-2668`):
   a hallucinated answer lands out of range and is therefore droppable rather than
   followable. This is what replaces the shard floor (§7).
2. **Every `[NEW]` turn is accounted for.** A turn named by no item is stamped
   `ignore` explicitly, with a reason. Nothing is left in "Thinking…" forever and
   nothing is silently unjudged. Per-turn stamps go on through `mark_processed`
   exactly as today, so the app's feed and the act haptic see what they see now and
   **iOS does not change**.

Items route through the *same* funnel per-line verdicts route through now — the
owner-is-a-party question, the consequential hold, quiet research, the held card and
its one go-ahead text, the meeting hold, the ask valve. The funnel is extracted, not
reimplemented. A second copy of that logic is how the organs get lost.

---

## 5. The direct lane does not change

Explicit events — typed into the app, arrived by SMS — keep today's immediate
per-line `hear()`, verbatim. A direct channel is structural evidence that he is
talking to her and it must answer in seconds, not at the next quiet. Everything in
this spec is about the **ambient** lane (`AMBIENT_ADDRESSEES = ("person",
"dictation", "self")`, `orchestrator.py:314`), which is where the pendant lives and
where every recorded failure happened.

That carve-out is also why several per-line fences survive: they still have a lane
(§8).

---

## 6. The two-stage shape, and what the cheap stage may do

The card recommends option C — a cheap per-line filter for obvious noise, full
judgment at close — and calls it "the sane implementation of A".

**The shape is accepted. The filter is refused.**

HARNESS-LAW 1 forbids a pattern deciding what words mean, and *"obvious noise"* is a
judgement about meaning. That alone rules out a word list. But a cheap **model** gate
would not be a Law-1 violation, and it still fails here, for a reason specific to
this system: the failure is **asymmetric and traceless**. A gate that answers "no
actionable intent" on the one segment containing the one real errand produces a miss
with nothing in the record saying so — and misses are already the measured weakness
(19.4% at the current tier, `TESTING-PASS-2026-08-21-ROUND2.md`). Three commits have
already shipped a cheap filter in front of a model call that excluded the exact case
the feature existed for. A fourth is not a coincidence, it is a pattern.

**So: no cheap stage may answer the judging question, and stage A is priced alone
(§9).**

What a first stage is legitimately allowed to do, in three tiers:

**Tier 0 — deterministic, no model, decides nothing about meaning.** Capture-time
arithmetic; gap measurement; `should_close`; turn ordering; the `[NEW]` cursor; the
claim and the stamps; rendering the payload; the word/`SETTLE_S` counters that decide
*when* to call. None of these read a word for its sense. This is the entire legal
content of "stage A".

**Tier 1 — cheap model, exactly one job, and it cannot suppress anything.** The
closed segment's one-line summary and entity list. It is a *product* of the judging
call, not a gate in front of it — nothing it returns can prevent the strong call.

**A fast lane that may only ACCELERATE.** A direct-address trigger fires the
segment-so-far judge early, capped at one per segment. Its trigger may be: the wake
name (addressing, not meaning — already stripped by name at
`anticipy_core.py:1411-1413`) or the channel being explicit (a transport fact). It
may **not** be `_RECALL_RE`, `remind me`, `can you`, `look up` or any sibling: those
are word lists deciding meaning, and CAPTURE-ARCHITECTURE.md's Trigger A proposed
exactly them. A fast-lane *miss* costs latency. A fast-lane *false negative on a
filter* costs the errand. Only one of those is recoverable, and the trigger is
therefore allowed to be wrong in only that direction.

**Explicitly forbidden to any stage before the model:** deciding a segment has no
actionable intent; deciding a line is noise; deciding a line is too short; deciding a
sentence means consent. Those are the four the code does today, and three of the four
are measured wrong.

---

## 7. How the shard floor retires

`shard_too_thin` (`anticipy_core.py:651`, called at `:1840`) is **not** a brevity
rule, and reading it as one is why it looks harder to remove than it is. Its own
docstring: *"A thin line may act on its own words; it may not act on words the model
added."* The predicate is

```
novel = goal_tokens(decision.goal) − goal_tokens(line + context_shown)
return len(novel) > 2
```

gated behind `len(tokens(line)) <= 4`. So it is a **provenance check on the goal**,
fenced by a word count. The provenance half is the protection. The word count is the
tape.

Two facts about it that matter for the replacement:

- It runs **after** the model, after the strong second opinion, after
  `inherited_errand`, after the second look — and **only in the ambient lane**
  (`:1836`). It does not stop a line reaching the model. It drops the *verdict*: the
  line is still ingested into memory at `:1422`, and the event is stamped `ignore`
  with an empty goal. So what is downstream of a drop is: no card, no job, no text,
  no question — and a memory.
- **Its escape hatch cannot fire in production.** `(decision.continues or 0) >= 1`
  requires `link_candidates`, which requires `LINKS_ON`, which is
  `ANTICIPY_LINKS` and **defaults off** (`worker.py:2446`, gate at `:3293`). So
  `continues` is always `None`, and every ≤4-word ambient act/ask with three or more
  novel tokens is dropped with no way to spare a legitimate continuation. On the one
  real conversation on file that is a rule standing over **74 of 137 lines (54%)**;
  the wider production sample measures 42%.

**The replacement: keep the provenance check, delete the word count, and re-scope
"the evidence" to the item's own evidence turns.**

```
novel = goal_tokens(item.goal) − goal_tokens(text of the turns in item.evidence)
```

This is strictly stronger than what it replaces, in three ways:

1. **It applies at every length.** Today a five-word line inventing six tokens is
   checked by nothing at all. The floor's own recorded lesson — invention, not
   brevity, is the tell — is finally applied to the whole population it was always
   about.
2. **It is scoped to the item's evidence, not to the segment.** This is the load-
   bearing distinction and it is where the earlier draft of this design was attacked
   and lost. "The whole conversation as allowed vocabulary" resurrects the recorded
   invented-number failure: `At 5:15` spoken by the other party becomes a legal digit
   in a text about a different dinner. Evidence-scoped, it does not. The digit guard
   and `unsupported_names` / `unsupported_counts` (`orchestrator.py:638-671`) keep
   their present scope and their present standing as declared seatbelts.
3. **The spare cases become real instead of theoretical.** "seven works" is spared
   because its evidence turns contain the dinner, not because of a `continues` flag
   that never fires. "book us Earls tomorrow" is spared because its goal says only
   what its own evidence says. "At 5:15" is still blocked, at three words, because
   *schedule / meeting / Monday / Evans* are still novel against its own evidence.

The four cases `tejas_gate` leg 2 pins today all still hold under the replacement,
which is what makes the two gates reconcilable rather than opposed.

### Getting `tape_gate` leg 2 green for this entry — and the trap in the way

Mechanically, leg 2 asks one question per entry: does `Tape.state()` return `GONE`?
For this entry `find = "def shard_too_thin("` and `GONE` means that literal text
appears **nowhere in the shipped organs** — `brain, extension, app, backend, proof,
firmware` (`tape_gate.py:153`). Today it is at `brain/anticipy_core.py:651`, with the
call at `:1840`. `tests/test_tape_gate.py:117` and `overnight/tejas_gate.py` mention
the name but are **not shipped organs**, so they do not block `GONE`.

Deleting the function therefore turns leg 2 green **for this entry** — leg 2 as a
whole stays red while the other four pieces live, which is the steady state the gate
documents as `exit 1 TAPE OUTSTANDING`.

But deleting it immediately turns **leg 1 red**: *"the registry names tape that is no
longer in the tree."* Its instruction is to drop the `Tape(...)` entry from
`KNOWN_TAPE`, drop the `[tape:shard_too_thin]` bullet from HARNESS-LAWS.md, and
*"lower `AUDIT_UNDECLARED_COUNT`"*.

**That last instruction cannot be followed, and this is a finding, not a
formality.** Leg 4 requires `AUDIT_UNDECLARED` (the tuple) to equal the registry's
audit items, requires `len(AUDIT_UNDECLARED) == AUDIT_UNDECLARED_COUNT`, and pins
that count against the audit document's own row —
`| **TAPE, UNDECLARED** … | **5** |` at `research/2026-08-24-law1-audit.md:73`.
Every path is red:

- drop the entry, leave the count at 5 → tuple has 4, count says 5 → leg 4 red;
- drop the entry, lower the count to 4 → doc says 5 → leg 4 red;
- edit the doc to 4 → falsifies a dated measurement, erases the record that item 20
  ever existed, and leg 4's own message forbids it: *"The audit is the dated record —
  … if it shrank, say which piece was closed and how."*

**The gate as written has no green path for retiring one of the audited five.** It
can record tape and it can record tape that never existed; it cannot record tape that
was *closed*. The change that fixes it is small and belongs in the same diff as the
deletion, not in a follow-up:

- A **`CLOSED_TAPE`** list. Each retired entry keeps its `tid`, `audit_item`,
  `ledger_needle`, the commit that closed it, and **the leg that proves the
  replacement**.
- **Leg 1**'s stale branch passes when the entry has moved to `CLOSED_TAPE` *and*
  the replacement leg it names exists.
- **Leg 2** reads `KNOWN_TAPE` only — green for the entry the moment it moves.
- **Leg 3** reads `KNOWN_TAPE + CLOSED_TAPE`, so item 20 is known by name forever.
  The property that makes leg 3 unsatisfiable by silence is preserved exactly.
- **Leg 4** counts `KNOWN_TAPE + CLOSED_TAPE` against the doc's 5. The census cannot
  shrink and the audit document is never edited.
- **Leg 5** requires the ledger bullet to *move*, from "Known standing tape" to a
  "Retired tape" section naming the closing commit. The human book records the
  closure instead of forgetting it.

Three books still have to agree; hiding a piece of tape still costs three coordinated
edits; the census still cannot be shortened quietly. The gate gains one state it was
missing: **closed**.

### `tejas_gate` leg 2 flips in the same commit, and it flips first

`tejas_gate.py:147-190` is a **regression pin with the opposite polarity**: it fails
when `shard_too_thin` is *absent*. Its own comment says both legs are correct —
*"this one says do not remove it yet, that one says do not keep it"* — and it is
right. Its four behavioural assertions are the lesson, and they must survive as
**behaviour**, not as a function name:

| Case | Must still |
|---|---|
| `"At 5:15"` → a meeting with Dr. Evans on Monday | be **blocked** |
| `"seven works"` with the dinner in its evidence | be **spared** |
| `"At 5:15"` typed by the owner (`explicit`) | be **spared** |
| `"book us Earls tomorrow"` → book Earls tomorrow | be **spared** |
| **new:** a 9-word line whose goal invents six tokens against its evidence | be **blocked** |

The leg is rewritten to drive the evidence-scoped provenance check against those five
cases, deterministically and offline, exactly as it drives `shard_too_thin` today.
**Order: the rewritten leg is green before the function is deleted, in one commit.**
Green replacement first, deletion second. A deletion that lands ahead of its proof
deletes the lesson, which is the third attack this design has already survived.

`len(line.split()) < 2` (`anticipy_core.py:1434`, audit item 8) **dies in the same
diff**, for the same reason and with the same replacement. Its stated justification is
verbatim that *"related memories injected as context can make triage hallucinate"* an
intent for a fragment — a hazard that exists only because the fragment is judged
alone. It is also the single largest silencer in the real data: **43 of 137 lines
(31%) never reach a model at all.** Leaving it while removing the shard floor would
keep a word count deciding what a third of speech means.

---

## 8. The twenty fences: which survive, which stop making sense

Option A moves the *unit* of judgment. It does not by itself remove a single fence.
But a fence that vetoes a line judged **in context** is a different object from one
that vetoes a line judged **alone**, and three of the twenty become incoherent.

**Stop making sense — must not run on segment-judged items:**

| # | Fence | Why it dies here |
|---|---|---|
| 20 | `shard_too_thin` (`anticipy_core.py:651`) | Replaced by evidence-scoped provenance (§7). |
| 23 | `inherited_errand` (`orchestrator.py:563`, the largest word-list machine in the repo) | Its entire job is *"the errand came from the context, not this line."* That sentence is meaningful only while the context is inert decoration. When the segment is the unit, an errand from three turns back **is in scope by construction** and the verdict names its evidence. Running it on a segment item vetoes precisely the capability this change buys. **Survives on the per-line lanes (§5).** |
| 9 | Progressive / exact-message stitching (`anticipy_core.py:1518-1519`), which *replaces* the Decision with a regex-composed act | It exists because a recognizer finalizes at punctuation and the model classifies both halves as nothing. Both halves are now in one payload with their gap markers, and joining them is a reading the model can do. **Survives on the per-line lanes**, where dictation still arrives split. |

**Change standing but survive:**

| # | Fence | New standing |
|---|---|---|
| 1 | `_GO_AHEAD_RE` release (`:1485`) | The model can now see the held card and the yes in one payload, so it should decide which plan a yes lands on. But a release that waits for close waits up to 45 s + poll, and this is the one path where latency *is* the product. It survives as the **fast lane's** first customer (§6) — accelerating a real judgment, never being one. |
| 8 | `len(line.split()) < 2` (`:1434`) | Deleted with the shard floor (§7). |
| — | The **strong second opinion** (`orchestrator.py:489-506`) | It re-asks the *same* `TRIAGE_SYSTEM` about the *same* decorated line at a better tier, and replaces the cheap verdict in either direction. Under segment granularity the segment judge **is** the strong call, so asking twice pays twice for one verdict: it is **replaced, not stacked**, on the segment lane. **It stays on the per-line lanes.** Law 5's ordering is the argument — context is fixed before tier, and this is the tier fix being superseded by the context fix. |

**Survive unchanged, because their input is a goal or a card and not a line in a
conversation:** `_IRREVERSIBLE_RE` / `_VERBS` (#24 — a fail-closed seatbelt, legal,
and it should outrank a segment verdict exactly as it outranks a line one);
`unsupported_names` / `unsupported_counts` (#25); the digit guard (#29);
`_same_pending` / `_same_plan` / `_refines_pending` / `_merge_into` (#17);
`_withdrawn_in_conversation` (#16); `_references` in both its forms (#31);
`_DONE_RE` and the memory fact-identity thresholds (#41, #42, #44); `asking.py`'s
question limit and third-person drop (#49, #50 — the latter is separately registered
tape); `_EXPLICIT_CORRECTION_RE`, `_LOSSLESS_REPLACEMENT_RE`, `_EXPLICIT_NEW_TASK_RE`,
`_RETRACT_RE` (#12–#15); `_BROWSER_TARGET_RE` (#18). The pre-model routers #3
(quotation), #4 (dictation), #5 (briefing), #6 (recall) and #7 (memory-fact) also
survive this card — they are Law-1 violations the audit already recorded, and
retiring them is a different card. §4's addition of `answer` to the item schema is
what eventually makes #5 and #6 removable; it does not remove them here.

**Two get worse, and this spec names them without fixing them.** Under a design whose
premise is *meaning comes from the conversation*, `_withdrawn_in_conversation`
(#16, whose docstring says it *"OUTRANKS the model"*) and
`answerThatEndsTheErrand` on the phone (#55, which writes a job `cancelled`, quotes
the owner's sentence back as proof, and never sends it to the brain) become the only
places in the system where a sentence cancels real work with no conversation
consulted at all. That is a sharper problem after this change than before it.

---

## 9. What it costs

The card claims ~50 cheap calls become ~3 strong ones, *"cheaper AND smarter"*, and
points at CAPTURE-ARCHITECTURE.md. **The call-count direction is right, the magnitude
is understated, and the dollar claim does not follow from the call claim — the doc
does not check it.**

CAPTURE-ARCHITECTURE.md:104 reads: *"a 4-minute conversation ≈ 25 lines ≈ 25 triage
calls + 25 extraction calls = 50 cheap calls."* Both halves verify —
`memory.ingest` (`memory.py:555`) calls `_extract` (`:2051`), one LLM call per line;
triage is one call per line. `llm.py:27` puts it at *"4-6 model calls"* per ambient
utterance.

**But the one real paired conversation on file is not 25 lines.** Measured directly
from `research/evals/call-2026-08-23-tejas/call_transcripts.json`:

| | measured |
|---|---|
| lines / span | **137 / 27.4 min** |
| words | **1,271** (median 3/line, mean 9.3) |
| lines ≤ 4 words | **74 (54%)** |
| lines < 2 words (die at the fragment floor before any model) | **43 (31%)** |
| segments the live path recorded | **4** (3 capture gaps ≥ 45 s) |
| segments `segment_all` produces over the same rows | **1** |
| decisions | 131 ignore, **6 act**, 0 ask |

So today, for this conversation: **137 extraction calls + at most 94 triage calls ≈
231 cheap calls**, plus a second opinion per act/ask and a second look per
ignore-with-goal. At the measured **$0.000682 per voice decision**
(`TESTING-PASS-2026-08-21-ROUND2.md:19`) that is **≈ $0.093 for one 27-minute
conversation**.

**Why that number is low, and why it is fragile.** It is low because **97% of the
triage prompt is served from cache** — 3,076 of 3,173 input tokens, after moving the
clock sentence off the front of the system prompt. The static prompt is identical on
every line, so 94 calls share one cached prefix. `TRIAGE_SYSTEM` has since grown to
**18,337 chars ≈ 4.6k tokens**, and the entire transcript of this conversation is
**1,271 words ≈ 1.7k tokens**.

**The segment payload is smaller than the prompt that carries it.** That single fact
determines the design: the cost of a judging call is dominated by the system prompt,
exactly as it is today, so **the saving is the number of calls — and the number of
calls is the number of flushes, not the number of segments.**

| regime | strong calls, this conversation | strong input tokens |
|---|---|---|
| close-only (4 segments) | **4** | ~25k |
| close + `FLUSH_WORDS = 400` | **7** | ~44k |
| close + CAPTURE-ARCHITECTURE's `FLUSH_SECONDS = 90` | **22** | ~144k |

Today's ~94 triage calls carry ~460k input tokens (97% cached). Against that:

- **Call count falls ~29× at close-only** (231 → 8, counting one cheap
  summary/extraction per segment in place of 137 per-line extractions). That win is
  certain.
- **The dollar win is not certain.** Strong input tokens are ~18× fewer than today's
  cheap input tokens, so the change is cheaper **iff the strong tier costs less than
  ~18× the cheap tier per input token** — before accounting for the fact that today's
  tokens are 97% cached and the segment payload's transcript half is not cacheable at
  all. That ratio is not a number to assume. `ANTICIPY_LLM_LEDGER` (`llm.py:163-196`)
  already records `prompt_tokens`, `cached_tokens` and `cost` per call, by caller.
  **It is measured on the replay before the flip, and the flip does not happen if the
  budget in §10 fails.**
- **The 90-second flush is the cliff and is rejected as priced.** 22 strong calls
  re-sending a growing transcript is 5.8× the close-only cost and only ~3× below
  today's total, for a design whose entire justification is being cheaper. The
  mid-segment trigger is therefore counted in **words, not seconds** —
  `FLUSH_WORDS = 400`, ≈ 3 minutes of continuous speech at 130 WPM, which produces 3
  flushes on this conversation instead of 18. Worst-case latency for an ambient
  thought becomes **45 s of quiet or 400 words, whichever is first** — which is what
  the EARS card already asks for in its own words: *"never judge while sound is
  arriving — judge when a thought CLOSES."*

**And one thing gets cheaper that the card does not claim.** Memory extraction is
36% of spend and runs 137 times on this conversation. Per-segment extraction makes it
4, with richer entities. That is a larger saving than the triage half.

---

## 10. Pre-registered criteria

Written before anyone is invested, and honest about the instrument first.

### The labeled set cannot carry this

`research/evals/call-2026-08-23-tejas/labeled_set.json` is **25 rows**. The card's
**68% → 80%** is **17 → 20 rows — a three-row move**, and one row is 4 points. Of the
25: **4 are `act`**, 15 are `ignore`, and only **6 have a `record_id` that exists in
the real transcript** — the other 10 are held-out synthetic exemplars with hand-
written `around` context. A criterion of "beat 80%" is a criterion on three rows of a
set that mostly cannot express conversations. It stays as a **no-regression tripwire**
and is not the success measure.

### Primary: the one real paired conversation

Ground truth is `FINDINGS.md` — 6 acts, of which **exactly one was defensible** (the
Tuesday call). Replayed through the segment judge:

- **SUCCESS**: the Tuesday call still acts, **and at most one** of the other five
  returns as an act.
- **FAILURE**: the Tuesday call is lost, **or** three or more of the five return.

Per-defect, because four of the five are context failures and are exactly what this
change exists for — if they do not go away, the change did not work:

| act | must now |
|---|---|
| "anticipate.com" domain purchase from a garbled proper noun | not act |
| "confirm who 'him' refers to" — the referent was named seconds earlier | resolve, or not act |
| Tuesday call | **still act** |
| CST→PST conversion held behind a confirmation gate | answer, not hold |
| "what was your email again" — asked of Tejas, answered with Omar's | not act |
| "At 5:15" → a meeting with Dr. Evans | not act |

### Recall — the "can't miss" half

The set is balanced so silence cannot max the score, and the whole-call replay is the
real recall test.

- **Per-label**: `act`, `ask` and `answer` accuracy on the labeled set must not fall.
  Aggregate accuracy alone is never reported — 15 of 25 rows are `ignore`.
- **No spam**: 131 ignores must not become 30 acts. **≤ 2 items per closed segment
  and ≤ 6 items across the whole conversation.**

### The shard population directly

74 of 137 lines are ≤4 words — the exact population the retired floor stood over.
After the change, of those 74:

- **≥ 1 and ≤ 3 produce a card**, and
- **every one that does names evidence turns whose text contains its goal's content
  words.**

Zero would mean the replacement is the floor again wearing a different shape. More
than three would mean the floor was load-bearing after all and the tape comes back
on, declared.

### Cost, measured and not assumed

Replay both ways with `ANTICIPY_LLM_LEDGER` on.

- **SUCCESS**: total cost per conversation **≤ 1.25×** today's measured $0.093;
  **≤ 10 strong calls** per conversation; **≤ 150k strong input tokens per
  conversation-hour**. (This conversation measures 7 calls, ~96k/h.)
- **FAILURE**: > 2× today's cost, **or** the cached-token share on the segment prompt
  below 80% — which would mean the payload broke prompt caching and the design is
  structurally expensive rather than badly tuned.

### Withdrawal rule

**One production miss of a direct spoken instruction, attributable to waiting for a
segment close, demotes the close-only lane back to per-line for act/ask —
automatically.** Written down now because afterwards everyone will have a persuasive
reason it was a one-off.

### Abandonment rule

If after two weeks in shadow the shard population still produces zero cards **and**
the act count on real conversations has not moved, this bought latency and cost and
no judgment. Revert it rather than tune it into justifying itself.

### Shadow, and what shadow means

`ANTICIPY_SEGMENT_TRIAGE = off | shadow | on`, defaulting off, then shadow for 2–3
days, diffs written to `research/evals/segment-shadow/` (Law 4).

**In shadow the judge writes nothing else — in particular not the `summary` back onto
the segment row.** The live per-line path reads that row as thread context
(`decide_link`, `segmenter.py:132`), so a shadow that edits it is not a shadow. This
is a named attack on the earlier draft and it was correct.

### Law 3

None of this is done until a gate leg is green **against LIVE**, verified with an
`overnight/is_it_live.py`-style fingerprint after the deploy. Prod has served stale
code twice and `railway up` reports success while failing.

---

## 11. The boundary is still chosen by a word count, and this spec does not fix it

Said plainly, because the alternative is that it goes unsaid.

`decide_link` (`segmenter.py:113-156`) decides what belongs to one conversation using
`len(text.split()) < 8`, `len(overlap) >= 2`, `_ANAPHORIC`, and three clock
constants. Audit item **#48, severity H**: *"conversation boundaries — entirely by
pattern and clock; no model is ever consulted."* It returns `"escalate"`, documented
as *"worth one cheap model call"*, and **nothing anywhere calls a model on it**;
`segment_all` treats it as `new`. That is a Law-1 violation this card **inherits and
does not remove.**

What this spec does about it, short of the fix:

- **`splits_after` (§4) is used, not just recorded.** Items are scoped to their side
  of a split the model read. So the model's reading governs *what is judged
  together* — the thing that actually affects a verdict — even while the clock still
  picks which database row the turns are stored under.
- The two real defects found in §1 are corrected as part of building this: **capture
  ordering in `recent_turns`** (`segmenter.py:309`), and **judging a turn against a
  segment that is already over** (`worker.py:3282` reading before
  `place_turn` at `:3363`).
- The measured disagreement is now visible: this conversation is **1 segment to
  `segment_all` and 4 to the live path**. That gap has never been reported anywhere
  and it is now a number the shadow diffs carry.

Retiring #48 properly — a model judging its own boundary — is a separate card and it
should be written.

---

## 12. Law compliance

- **Law 1.** Meaning moves decisively to the model: the judged unit becomes the
  conversation, and two word counts die (`shard_too_thin`'s ≤4, and the <2-word
  fragment floor that silences 31% of lines). The cheap gate that would have been the
  Law-1 violation is refused outright (§6). Inherited and named, not fixed: #48
  (§11), and the pre-model routers #3–#7.
- **Law 2.** No new tape. If any part of this ships taped it needs a `TAPE:` marker,
  a `KNOWN_TAPE` entry and a ledger bullet in one diff. `shard_too_thin` retires
  through the mechanism in §7, which requires `tape_gate` to gain the `CLOSED_TAPE`
  state it currently lacks.
- **Law 3.** Repo-green is not done. Shadow, then flip, then a live fingerprint.
- **Law 4.** This spec is in `docs/` the day it exists; shadow diffs go to
  `research/evals/segment-shadow/`.
- **Law 5.** Fix order senses → context → examples → tier → structure. Senses shipped
  (capture timestamps). **This card is the context step**, and it comes *before*
  tier — which is the argument for replacing the strong second opinion rather than
  stacking on it (§8).
- **Law 6.** §13 is the adversarial pass. It is not the last one required.

---

## 13. What would kill this

- **The cursor.** Advance `triaged_through_seq` before a verdict and one timeout
  strands 400 words permanently, then a sweep marks them delivered. §3 answers it:
  cursor advances on a parsed verdict only; membership is claimed with the existing
  lease that `release_stranded_claims` already sweeps.
- **Guard dilution.** Allow the whole segment as goal vocabulary and the recorded
  invented-number failure comes straight back. §7 answers it: evidence-scoped, never
  segment-scoped.
- **Latency on the go-ahead.** A spoken yes that waits 45 s for a close is a
  regression on the one path where speed is the product. §6/§8 answer it with a fast
  lane that may only accelerate, capped at one per segment — and §10 pre-registers the
  withdrawal rule if it is not enough.
- **Missing organs.** The go-ahead release, the spoken answer to parked work, and
  progressive stitching all live in `hear()` **between** triage and the funnel. A
  segment lane that routes items *around* that funnel loses them silently. §4
  requires extraction, not reimplementation.
- **Shadow that is not a shadow.** §10.
- **Deleting the lesson.** `tejas_gate` leg 2's five cases must be green against the
  replacement **before** the function goes, in one commit. §7.
- **The gate with no green path.** `tape_gate` cannot currently record a closed piece
  of tape. If that is discovered during the flip instead of now, the pressure will be
  to edit the audit document. §7 answers it before anyone is under that pressure.
- **The instrument.** The success measure is a 25-row set where three rows are 12
  points. §10 moves the primary criterion onto the 137-line conversation and the
  74-line shard population, and says out loud that the labeled set is a tripwire and
  not a scoreboard.

## 14. Decisions made without the owner

- **EARS is not a prerequisite** and this card starts now (§2).
- **No cheap pre-filter over meaning**, in any tier, including a cheap model (§6).
  This is a refusal of the card's own option C in substance while keeping its shape.
- **The mid-segment trigger is words, not seconds** — `FLUSH_WORDS = 400`, not
  `FLUSH_SECONDS = 90` — because the 90-second cadence is 22 strong calls on the one
  conversation we have measured (§9).
- **The strong second opinion is replaced on the segment lane, not stacked** (§8).
- **`tape_gate` gains a `CLOSED_TAPE` state** in the retirement diff (§7).
- **The <2-word fragment floor dies with the shard floor** (§7), which is a second
  audited construct removed by a card that was scoped to one.
