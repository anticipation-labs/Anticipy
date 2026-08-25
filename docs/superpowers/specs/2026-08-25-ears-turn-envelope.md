# EARS — the turn envelope

**Date:** 2026-08-25
**Branch:** `jose_anticipy_system` (strict superset of `harness/tejas-fixes`:
`git rev-list --left-right --count harness/tejas-fixes...jose_anticipy_system` → `0 104`)
**Card:** EARS — "capture speech with real timestamps, on-device where possible.
Decision quality is capped by ear quality forever."
**Binding rules:** `HARNESS-LAWS.md` (LAW 1–6), `design/LOCAL-FIRST.md`
**Predecessors:** `docs/superpowers/specs/2026-08-24-voice-capture-design.md` §7 (this
supersedes its `seq`/`boot_id` reasoning — see §7), `CAPTURE-ARCHITECTURE.md` STEP 2
**Measured evidence:** `research/evals/call-2026-08-23-tejas/call_transcripts.json`
(137 production rows), `research/2026-08-25-the-ears-stopped.md`

**You do not need to have read `CAPTURE-ARCHITECTURE.md` to implement this.** Everything
that document contributes is restated here in §2 and §8.

---

## 1. The card, and what is actually true today

The Brief's §9 says *"Capture is the floor. ~67% word loss measured on a real call; no
VAD; dictation-grade recognizer used for ambient audio. The designed fix (segments,
capture-time keying, SpeechAnalyzer migration) exists on paper in `CAPTURE-ARCHITECTURE.md`
— Steps 2–5 are unbuilt."* It also states that all 260 events of the Tejas day had empty
capture timestamps.

Both sentences are stale. Verified against the source and against the 137 stored
production rows, not assumed:

| Claim | Verified state | Evidence |
|---|---|---|
| "Steps 2–5 unbuilt" — Step 1 | **built AND live** | `brain/segmenter.py` (470 lines), wired at `brain/worker.py:3780`; all 137 production rows carry a non-empty `segment`, across exactly 4 segment ids (96/23/13/5) |
| "Steps 2–5 unbuilt" — Step 3 | **substantially built, flag-gated** | `brain/sorter.py` (added `8ee59035`, 2026-08-25 02:21 -0700): `MODE_OFF/SHADOW/ON` off `ANTICIPY_SEGMENT_TRIAGE`, `render_payload`, `judge_segment`, `parse_verdict`; `worker.py:2459 sweep_closed_segments`. `MODE_ON` self-demotes to shadow (`worker.py:2518-2528`) |
| "Steps 2–5 unbuilt" — Steps 4, 5 | **genuinely absent** | zero repo hits for `ANTICIPY_GATE_MODEL` / `LLM.for_job` / `ingest_segment`; no `Audio/VoiceActivity.swift`, no `Audio/TurnEndpointer.swift`, zero hits for `silero` / `smart-turn` / `useNeuralEndpointing` anywhere under `app/` |
| "empty capture timestamps" | **FALSE, and the truth is worse** | `capture_started_at` is non-empty on **137/137** rows. It is stamped at POST time: `created − capture_started_at` is min 0.047 s, **p50 0.053 s**, p90 0.057 s, max 0.065 s |
| `capture_ended_at` | empty on 137/137 | same dump |
| `spoken_at` | empty on 137/137 | same dump — this is the column `FINDINGS.md` actually reported, and the Brief generalised it |
| `seq` | `0` on 137/137 (int, not empty) | PocketBase number-field default |
| `boot_id` | empty on 137/137 | — |

**This is the finding that reframes the card.** The defect is not a missing column. It
is a column that is present, populated, and worthless: `capture_started_at` is
informationally identical to `created`, to within 18 ms across 137 rows. **A monitor
that checks "is `capture_started_at` present?" reports GREEN today.** Anything this spec
produces must be unable to pass on that.

**The ears are dead as of this writing.** Zero transcript rows in ~31 hours. The last
delivering build was b75 (last row 2026-08-24 03:34:24Z); b76–b80 delivered none; b82
(`app/ios/project.yml:186`, `CURRENT_PROJECT_VERSION: "82"`) is compiled and verified but
not installed on a phone. **Nothing in this spec can be verified live today.** §11 says
exactly which claims wait on a working build.

---

## 2. The one sentence

**Ordering is a comparison; boundaries are a subtraction. A constant offset preserves the
first and destroys the second — so the phone must stop sending one instant three times
and start sending the two instants it already computes.**

That is the whole of this spec. Everything below is which two, where, and how anyone
proves it.

---

## 3. Ordering is already fixed in the repo and has never run in the world

**Do not rebuild this.** Commit `55c89a71` ("Stamp when it was said, say why the flush
fired, and keep a journal", 2026-08-24 14:30:59 -0700) already stopped `pushEvent`
calling `Date()` and made the instant a caller-supplied parameter carried through the
offline queue:

- `app/ios/Anticipy/Backend/AnticipyBackend.swift:525-529` — `if let capturedAt { … }`
  writes `capture_started_at`, `spoken_at`, `capture_ended_at` from the parameter.
- `app/ios/Anticipy/AnticipyApp.swift:199` — `BufferedLine.capturedAt: Date?`, so the
  `@AppStorage("unsentLines")` disk queue carries the instant across a relaunch.
- `app/ios/Anticipy/AnticipyApp.swift:325-329` — `heard(_:speaker:explicit:from:at:continuesPrevious:)`
  takes `at capturedAt: Date = Date()`.
- Consumer already live: `brain/worker.py:2789 capture_key` reads `capture_started_at`
  first, `spoken_at` as an alternate, falls back to `created`.

**Be precise about what that fixed.** On the *live* path, the pre-`55c89a71` push-time
stamp already ordered correctly — 18 ms of jitter across 137 rows cannot reorder turns
whose true gaps are seconds. What it broke was the *buffered* path: the offline retry
queue re-stamped every buffered line at the moment signal returned, so a whole buffered
conversation collapsed into one second and arrived shuffled. That is Omi's shipped bug
#6551 in Anticipy's own code, and it is the failure mode the pendant makes routine rather
than rare.

**So the smallest change that makes ordering correct is: ship a build.** No code. b82 or
its successor, installed on a phone, delivering rows. Every line of new work in this spec
is about *boundaries*, not ordering.

---

## 4. What is broken: the flush knows both ends and throws one away

`PhoneListener.deliver` already receives both instants and lets only one escape.

```
app/ios/Anticipy/Audio/PhoneListener.swift:966
  private func deliver(_ line: String, reason: TranscriptFlushPolicy.Reason?,
                       wordsAppearedAt: Date, at now: Date = Date())
```

- `wordsAppearedAt` — when this line's words **first went unsent**. Set at
  `PhoneListener.swift:1033-1034` (`let since = pendingSince ?? Date()`) on the first
  partial after words go pending, read at `:932` in `flushTail`.
- `now` — the instant the flush produced the line.

`wordsAppearedAt` is used for the echo check and the cut-continuation mark, then dropped
(`:1017`, `:1019`: `onSpeaker(line, tag, now, …)` / `onLine?(line, now, …)`). Only `now`
reaches the backend, where `AnticipyBackend.swift:525-529` writes it to all three columns.

**Two consequences, both live:**

1. **`capture_span` collapses.** `brain/segmenter.py:105-110`:
   `end = parse_ts(capture_ended_at) or start`, and `parse_ts("")` returns `None`
   (`:65-68`). With `capture_ended_at` empty, end **is** start.
2. **Every gap is flush-to-flush.** `brain/sorter.py:265-266` computes
   `gap_s = start − prev_end`. With `prev_end == prev_start`, the "silence" between two
   turns includes the entire speaking duration of the later turn plus the 2.6 s debounce
   (`TranscriptFlushPolicy.swift:24`, `utteranceGap = 2.6`) — up to 8 s for a ceiling
   flush (`maxHold = 8`).

**The error is one-directional and always pushes toward splitting a conversation that did
not end.** Measured on the real call: of six inter-turn gaps ≥ 30 s
(34.6, 38.0, 39.6, 66.6, 90.5, 309.7 s), the 38.0 s gap was followed by a 37-word turn —
roughly 14.8 s of speech at 150 wpm — so true silence was about 23.2 s. A 15 s error
against `CONTINUE_S = 45` (`brain/segmenter.py:28`), which is the threshold that decides
whether the next turn joins the open conversation or opens a new one. Three of the call's
gaps sit in the 30–60 s band, straddling it. None flipped on this call, and a 27.4-minute
single call still produced 4 segments.

---

## 5. What the iOS side writes, exactly, and where

**Three values. No new columns. No new files. No migration.**

### 5.1 `capture_started_at` — change the VALUE, not the column

Set it to `wordsAppearedAt`, not to `now` and never to `Date()` at push time.
`capture_started_at` is the canonical column (`worker.py:2805-2808`); keep writing
`spoken_at` to the same instant so the rollout alias stays meaningful rather than
decorative. `AnticipyBackend.swift:525-529` already writes both from one parameter — it
needs no change beyond §5.2.

**Residual error, stated honestly.** `pendingSince` is set on the first *partial* after
words go unsent, so it lags true speech onset by tens to low hundreds of milliseconds.
That is 30–100× better than the 2.6–10.6 s error it replaces, and it is noise against
`CONTINUE_S = 45`. It is not sample-accurate and this spec does not claim it is; §8 names
what would be.

### 5.2 `capture_ended_at` — a genuinely distinct instant

Set it to `now`, the flush instant. Today `AnticipyBackend.swift:527-529` aliases one
value onto all three columns; that aliasing is what collapses `capture_span`. `pushEvent`
gains a second optional `Date` parameter and writes `capture_ended_at` from it.

**The invariant the wire must satisfy:** `capture_started_at < capture_ended_at ≤ created`.
Strictly less on the first comparison — equality means an implementation still aliased.

### 5.3 The thread from the flush to the queue

Four edits, all mechanical, all in files that already exist:

1. `PhoneListener.swift:117` — `onLine` widens from
   `(String, Date, Bool) -> Void` to `(String, Date, Date, Bool) -> Void`
   (`line, startedAt, endedAt, continuesPrevious`).
2. `PhoneListener.swift:121` — `onSpeaker` widens the same way.
3. `PhoneListener.swift:1017,1019` — pass `wordsAppearedAt` **and** `now`.
   `PhoneListener.swift:1157` is a **fourth delivery site that bypasses `deliver`
   entirely**: the parting tail at session stop calls `onLine?(tail, Date(), …)`
   directly, so it stamps teardown time and skips the speaker tagger. It must carry the
   same two instants. Do not leave it behind — it is the last line of every session.
4. `AnticipyApp.swift:325-329` — `heard` gains `endedAt: Date`;
   `AnticipyApp.swift:194-199` — `BufferedLine` gains `var endedAt: Date? = nil`,
   **optional so a queue written by the previous build still decodes** (the same rule the
   existing `capturedAt`, `source` and `account` fields follow).
   `AnticipyApp.swift:206` `@AppStorage("unsentLines")` then carries it across relaunch
   with no further work.

### 5.4 The pendant path passes no capture time at all

`AnticipyApp.swift:264`:

```swift
pendantTranscriber.onTranscript = { [weak self] line in
    Task { await self?.heard(line, from: .pendant) }
}
```

`heard` defaults `at capturedAt: Date = Date()`, so **pendant lines are stamped at
processing time even after `55c89a71`.** The two phone-mic closures (`:252`, `:260`) both
pass `at: at`; this one does not, because `TranscriberClient.onTranscript` is
`((String) -> Void)?` (`app/ios/Anticipy/Audio/TranscriberClient.swift:16`) and carries no
instant to pass.

**Scope ruling:** widening `TranscriberClient.onTranscript` to carry two instants is
**in** this spec, because the same envelope must mean the same thing from both mouths or
`source` becomes uncomparable. Deriving those instants from the pendant's own boot counter
via BLE time-sync is **out** — that is Step 7, it needs firmware, and it is named in §12.
Until then the pendant's instants come from the phone clock at decode, which is honest for
Mode 1 (in range, live) and wrong for Mode 2 (backlog). **The pendant must not be trusted
for boundaries until Step 7.**

---

## 6. What the server must accept: nothing

**There is no server-side work in this spec.** Verified, not assumed:

- `backend/pb_migrations/1700000004_segments.js:45-53` adds all eight envelope fields to
  `events`: `capture_started_at`, `capture_ended_at`, `gap_before_ms`, `seq`, `boot_id`,
  `source`, `backfill`, `segment` — all `required: false`.
- **That migration is deployed.** Every one of those eight fields appears on the
  production rows in the Tejas dump. Independently corroborated by
  `research/2026-08-25-the-ears-stopped.md:69-70`, which fingerprinted the live backend
  four ways and enumerated the live `events` schema.
- `backend/pb_hooks/guard.pb.js` imposes no field whitelist on phone-authored transcript
  POSTs; its `events` branch (`:297-322`) governs only agent-written `read_line`/`read_fact`.

Two live server readers the implementer must know about, neither of which changes:

- `brain/worker.py:2789 capture_key` falls back to arrival when the stamp is more than
  `CLOCK_SKEW_MAX_S = 6h` (`:2770`) from `created`. Harmless for phone-live. **Silently
  fatal for pendant backlog older than 6 h** — Step 7 must revisit it.
- `brain/segmenter.py:109` stops collapsing `end` onto `start` the moment §5.2 lands. No
  code change; the fallback simply stops firing. That is the entire point of this spec.

---

## 7. What the iOS side does NOT write, and why each

Every one of these is a field the envelope design names and this spec deliberately leaves
alone. The reasons differ and the differences matter.

**`gap_before_ms` — derivable, and already derived.** `brain/sorter.py:265-266` computes
the gap from the two stamps. Writing it from the phone creates a second source of truth
that can disagree with the first, and the phone cannot see turns arriving from another
source. A field two parties compute independently is a bug waiting for its first
disagreement.

**`seq` — do not write it from the phone, and there is a live defect here.**
`docs/superpowers/specs/2026-08-24-voice-capture-design.md:216,326` says *"`gap_before_ms`,
`seq` and `boot_id` stay unwritten and out of scope; nothing consumes them."* The
"nothing consumes them" half became false 13 hours later: `brain/sorter.py:261-262` reads
it —

```python
seq = row.get("seq")
ordinal = int(seq) if isinstance(seq, int) else i + 1
```

PocketBase returns `"seq": 0` as an **int** for every unset number field, so
`isinstance(seq, int)` is `True`, `ordinal` is `0`, and the `i + 1` fallback never runs in
production. Executing `render_payload` against the real row shape returns
`ordinals == [0, 0, …]`, `new_ordinals == []`: every turn renders `#0`, no turn is ever
marked `[NEW]`, and the verdict has no ordinal to point at. `tests/test_sorter.py`'s
helper omits the key when `seq is None`, so the tests take the `i + 1` branch and
production takes the `int(0)` branch — **green tests over a row shape production never
emits**, the same defect class as §1's `capture_started_at`.

**The decision the old spec reached is still right, for a better reason.** The fix is not
"write `seq` from the phone" — that masks the zero-default bug instead of fixing it, and
`docs/superpowers/specs/2026-08-25-sorter-conversation-granularity.md:172-173` already
specifies the ordinal comes from `turn_count` at append, **server-side**.
`brain/segmenter.py:409` already increments `turn_count` on every append and
`store.stamp_event` already writes to the event row; the ordinal is one more argument
there. Writing `seq` from the phone *without* `boot_id` is strictly worse than not writing
it: `seq` is scoped per boot and per source, so a counter that restarts mid-conversation
makes every post-restart turn read as already-triaged, and a phone+pendant segment gets
colliding ordinals. **iOS writes no `seq`. The defect is handed back in §12.**

**`boot_id` — no reader, and it only earns its place beside a persisted `seq`**, as the
audit key that detects a counter reset. Writing it alone is a dead field.

**`backfill` — Step 7.** Nothing produces backlog yet.

**`eot` (which timer fired) — deferred, with the reason.** It is nearly free:
`reason?.rawValue` is already computed at `PhoneListener.swift:1010` and already journaled.
But it has **no column** — it is the one envelope field `1700000004_segments.js` does not
add — and the information is already on the wire in usable form: `parent_line` is written
exactly when the 8 s ceiling cut a sentence (`AnticipyBackend.swift:537`), so a line whose
successor carries `parent_line` was ceiling-cut. Adding a column to restate that is not
the smallest change. **`eot` earns its migration at Step 5 and not before**, because that
is when it gains values (`semantic`, `timeout`) that `parent_line` cannot express.

**`struct Turn` / `onTurn` — ergonomics, not correctness.** `CAPTURE-ARCHITECTURE.md`
Step 2 proposes a struct and an `onTurn` closure. A four-argument closure carries the same
two instants with a smaller diff and no shim to maintain. Take the struct when a fifth
field arrives.

**`Audio/TurnQueue.swift` — already solved.** Step 2 asks for a disk-backed queue to
replace an in-memory `unsent: [String]`. `@AppStorage("unsentLines")` with `BufferedLine`
(`AnticipyApp.swift:172-206`) is that queue, it already survives relaunch, and it already
carries `capturedAt`. Building a second one would be a rewrite of working code.

---

## 8. VAD and neural endpointing: later, and here is the trigger

**Not now.** Four reasons, in order of weight:

1. **LAW 5 order.** The fix order is senses → context → examples → model tier →
   structure, and *within* senses the order is recording before detecting. The current
   defect is not that the phone detects boundaries badly — it is that the phone **already
   knows both instants and the wire cannot carry them**. A better endpointer feeding the
   same one-instant wire changes nothing measurable. Building it first would be tape by
   definition.
2. **Nothing can be measured today.** Zero transcript rows in 31 hours. Tuning
   `vad_threshold_on = 0.50` / `min_speech_ms = 250` against no data is guessing with
   extra steps.
3. **The gate for opening it is already fixed and numeric**, in
   `docs/superpowers/specs/2026-08-24-voice-capture-design.md` §8: after real timestamps
   and boundaries ship and one manual session is recorded — shard rate below 25%,
   `speaker` populated on the large majority of owner lines, and word capture still under
   60%. Deciding that bar *after* seeing the result is how a bake-off gets talked into the
   wrong conclusion.
4. **Cost.** Silero VAD CoreML (1.2 MB) plus Smart Turn v3 (8 MB int8 ONNX) is 9 MB of
   model, an ONNX runtime on iOS with no ANE execution provider, and — for
   `SpeechAnalyzer`, the other half of the same migration — an iOS 26 floor against
   `app/ios/project.yml` targeting 16.0, plus the loss of
   `SFSpeechRecognitionRequest.contextualStrings`, which `AnticipyVocabulary` rides at
   `PhoneListener.swift:805` and `LocalTranscriber.swift:23`.

**The higher-fidelity option that needs no new model and no iOS floor**, recorded here so
it is not rediscovered: `SFTranscriptionSegment` already exposes `timestamp`
("the start time of the segment in the processed audio stream") and `duration` ("the
number of seconds it took for the user to speak the utterance") — Apple's documentation
data API, https://developer.apple.com/tutorials/data/documentation/speech/sftranscriptionsegment.json
(only `voiceAnalytics` is deprecated on that type, not the timing). `PhoneListener` reads
only `result.bestTranscription.formattedString` (`:866`) and never `.segments`. The
wall-clock origin exists as `requestBornAt` (`:196`, set `:817`).

**Why it is not the smallest change** — a caveat verified in the code rather than from a
source: orphan buffers are replayed into the new request **after** `requestBornAt` is set
(`:840-847`), so `wall = requestBornAt + segment.timestamp` is wrong by the replayed
duration for the first segments after a recognizer swap. The replayed duration is
computable from the held buffers' `frameLength`, but that is a second correctness argument
to get right, and §5 needs none.

---

## 9. LAW 1 — why this is legal, and the four pieces it does not cover

**Law 1:** no regex, word list, or threshold may decide what words MEAN. Pattern-matching
is legal in senses (audio plumbing), the seatbelt, and deterministic gates/evals.

**Everything in §5 is senses, and it is the easy case.** Clocks, a timer identity, and a
counter. `capture_started_at` and `capture_ended_at` are wall-clock instants — they carry
no opinion about the words at all. The flush reason says *which timer fired*, which is
mechanism the phone knows for certain. `CONTINUE_S = 45` is a threshold over a clock, not
over a vocabulary. `capture_key`'s `CLOCK_SKEW_MAX_S = 6h` is a plausibility window on a
number. None of these can be wrong about meaning because none of them can see meaning.

**The gate in §10 is the other permitted category** — a deterministic gate — and it is
built so it *cannot* read words: it never requests the `text` column, the same discipline
`overnight/are_the_ears_live.py` states for itself.

**Four pieces in this neighbourhood are NOT covered by that exemption. Name them so
nobody cites this spec as cover for building one.**

1. **`decide_link`'s band-3 prefilter — exists today, live, and is meaning-adjacent.**
   `brain/segmenter.py:113-156` decides whether two turns are *about the same thing* using
   proper-noun overlap, a ≥2 content-word overlap, an `<8`-word length threshold, and an
   explicit opener word list: `_ANAPHORIC` at `:44-46`
   (`so|anyway|anyways|okay|ok|right|back to|where were we|and|but|also|it|that|they|he|she|those|these|which`).
   "Is this the same conversation" is a judgement about what the words mean. **This spec
   does not touch it and does not defend it.** It is pre-existing, it is on the wrong side
   of the line, and it belongs in the next Law 1 audit
   (`research/2026-08-24-law1-audit.md` is the last one).
2. **Trigger A, "direct address" — unbuilt, and must not be built as a regex.**
   `CAPTURE-ARCHITECTURE.md` proposes a free regex on the turn (`remind me`, `can you`,
   `look up`, `what time is`, `add to my`) to route a turn into a fast lane. Deciding a
   sentence is *addressed to her* is meaning, full stop. Zero call sites today. It stays
   at zero until a model decides it.
3. **The gate's `<6 content words and no direct address → auto-fail` short-circuit —
   unbuilt.** A word-count threshold concluding a segment contains no actionable intent is
   a threshold deciding meaning. The `>120 words → auto-pass` twin is safer (it opens a
   door rather than closing one) but the auto-fail is a hard stop where every line reaches
   triage today.
4. **The `<2 words = fragment` guard** (`brain/anticipy_core.py:1452-1455`:
   `if len(line.split()) < 2: … decision="ignore", reason="fragment, no intent"`) is cited
   by the architecture as free Tier 0. It is a word-count threshold that discards an
   utterance unheard. In scope
   for the audit, out of scope here.

---

## 10. The gate leg

`overnight/turn_envelope_gate.py`. Read-only, against **LIVE production** — the only place
the answer exists. Same house rules as `tejas_gate.py` and `are_the_ears_live.py`: a leg
that cannot be tested **fails**; report the first failure but run every leg; exit code is
the verdict.

```
0   the envelope is proven true against live rows
1   FAILED — a leg's invariant is violated
2   UNPROVEN — too few qualifying rows, or the backend could not be read
```

**Design rule, stated first because it is the whole point: no leg may check that a field
is non-empty.** Presence is exactly the check that reads green today on a worthless
column (§1). Every leg asserts a **relationship between two instants** that only an
honest stamp can satisfy.

**Scope filter.** Only `kind="transcript"` rows whose `device_id` build number is at or
above the build carrying the fix (`device_id` is `iphone-b75`-shaped; parsing an integer
out of it is plumbing). Below `MIN_ROWS = 20` qualifying rows the gate exits **2**, never
0 — an empty table is not a passing grade.

**Leg 1 — the stamp is not the postmark.** Over the qualifying rows,
`median(created − capture_started_at) ≥ 2.0 s`, and at least one row `≥ 2.6 s`.
*Why it cannot be faked:* today's push-time stamping produces p50 0.053 s and a maximum of
0.065 s. An honest `wordsAppearedAt` is at minimum `utteranceGap = 2.6 s` behind the POST
for a gap flush and up to `maxHold = 8 s` for a ceiling flush. A mock that writes `now`
lands in the 0.05 s band and fails by two orders of magnitude. **The floor is above every
value the broken implementation can physically produce.**

**Leg 2 — start and end are two different instants.**
`capture_ended_at > capture_started_at` **strictly**, on ≥ 90% of qualifying rows, with
`median(end − start) ≥ 0.5 s`.
*Why it cannot be faked:* an aliasing implementation — today's, and the most likely wrong
fix — writes them equal, scoring 0%. An empty `capture_ended_at` also scores 0%, so the
presence check comes free without being the check.

**Leg 3 — the phone cannot finish speaking after it posts.**
`capture_ended_at ≤ created` on **100%** of qualifying rows. Catches a timezone bug, a
format bug, and a wrong-clock device, and it is the invariant `capture_key`'s
`CLOCK_SKEW_MAX_S` fallback exists to survive.

**Leg 4 — the offline queue preserves the stamp.** At least one qualifying row with
`created − capture_started_at > 60 s`.
*Why it cannot be faked:* only a line that was buffered and flushed later, carrying its
original instant, can produce that. This is the `55c89a71` claim, and it is the one leg
that requires a deliberate act: airplane mode on, speak two sentences, wait a minute,
airplane mode off. **If no such row exists in the window the leg reports UNPROVEN (exit 2),
not pass** — the procedure was not run, and an unrun procedure is not evidence.

**Leg 5 — a flush burst did not collapse.** Among qualifying rows, find any group of ≥ 3
whose `created` values fall within 2 s of each other (a queue flush). Their
`capture_started_at` values must span **> 30 s**.
*Why it cannot be faked:* this is Omi #6551 stated as an assertion. If the queue
re-stamped at flush, the span is under 2 s and the leg goes red. If no such group exists,
this leg reports UNPROVEN, not pass.

**Leg 6 — the ears are alive at all.** Reuse `overnight/are_the_ears_live.py`'s asymmetry
test (`kind="transcript"` count versus `kind="anticipy_says"` count over the window) as a
**precondition**. Zero transcripts while the machine is provably writing means the gate is
UNPROVEN. Without this leg, a deaf phone produces a gate that finds no violations and
prints a clean bill of health — which is exactly the failure `are_the_ears_live.py` was
written for.

**Law 1 posture of the gate itself.** It never requests the `text` column
(`fields=` on every query names only `id,created,device_id,source,capture_started_at,capture_ended_at`),
so it cannot measure meaning with a threshold even by accident. It creates nothing,
patches nothing, touches no job.

---

## 11. What can be proven now, and what waits on a working build

**LAW 3: repo-green is a claim.** Stated per item so nobody reports this done off a test
run.

**Provable now, with no phone:**

- Leg 1's arithmetic against the 137 stored production rows — it must go **red**, and if
  it goes green on today's data the leg is written wrong.
- A replay of the 137 rows through `segment_all` / `render_payload` with corrected
  synthetic stamps, showing how many of the four segments survive an honest `end`.
- Pure-Foundation unit tests for §5.3 in `app/ios/Tests/`, alongside the existing
  `TranscriptFlushPolicyTests.swift` / `TranscriptCursorTests.swift`: that
  `deliver` emits `wordsAppearedAt` as start and `now` as end, that they are never equal,
  and that a `BufferedLine` encoded by the previous build still decodes with
  `endedAt == nil`.
- The `seq` zero-default defect (§7) — reproducible by executing `render_payload` against
  a row dict containing `"seq": 0`.

**Waits on a build installed on a phone that delivers rows:**

- That `capture_started_at ≠ created` at all — Leg 1.
- That start and end are distinct — Leg 2.
- That the offline queue preserves stamps across a flush — Legs 4 and 5.
- Whether `pendingSince` tracks speech onset closely enough in the field (§5.1's residual
  error is reasoned, not measured).
- The `CAPTURE-ARCHITECTURE.md` Step 2 stopwatch check: a deliberate 30 s pause, and the
  logged gap matching it.

**Blocked before any of that:** the ears are dead. b82 is compiled and verified and not
installed. **Whoever owns the phone unblocks this spec, and nothing in it is testable
until they do.**

---

## 12. LOCAL-FIRST posture

Required by `design/LOCAL-FIRST.md` rule 5. **This spec moves metadata only. Zero new
audio, and zero new audio-derived data, leaves the phone.** Two timestamps and an existing
`source` string. No embedding, no voiceprint, no frame, no sample. `design/LOCAL-FIRST.md`
rule 3 — "what travels is the smallest conclusion that works" — is satisfied trivially: an
instant is not a conclusion about anybody.

The one place this spec touches the standing violation is §5.4: the pendant path currently
routes through `TranscriberClient`, and the Brief's §9 records that as *"Local-first is
violated today where pendant audio streams to a cloud transcriber; the local path exists
with zero call sites."* Widening the callback signature neither worsens nor fixes that.
It is named here so the envelope work is not mistaken for having addressed it.

---

## 13. Law compliance

- **LAW 1.** §9 in full. Everything added is clocks and counters; the four uncovered
  pieces are named rather than absorbed, and none of them is touched.
- **LAW 2.** No tape. Nothing here is a string patch, so no `TAPE:` comment would be
  honest and none is added. If an implementer finds themselves special-casing a device or
  a build with a string test, that is tape and it needs its red gate leg.
- **LAW 3.** §11 splits every claim into provable-now and waits-on-a-build, and the gate
  in §10 runs against LIVE, not against a fixture.
- **LAW 4.** This file is the record. The `seq` reversal, the `eot` deferral, the pendant
  scope ruling and the VAD trigger are written down rather than left in a thread.
- **LAW 5.** Strict order: this is senses, and within senses it is *recording* before
  *detecting*. §8 refuses the endpointer until the wire can carry what the phone already
  knows.
- **LAW 6.** Self-reviewed in §14. An adversarial pass against these laws, the tests and
  the recorded failures happens before any of it is called done.

---

## 14. Spec self-review

- **Placeholders:** none. No TBD, no "handle edge cases", no unnamed mechanism. Every file
  is named with a line number and every number is either measured here or cited to its
  declaration.
- **Corrections folded in, rather than quietly dropped:** the Brief's "empty capture
  timestamps" is refuted with the dump (§1); the Brief's "Steps 2–5 unbuilt" is corrected
  in both directions (§1); the predecessor spec's "nothing consumes `seq`" is corrected
  while its *decision* is upheld for a stronger reason (§7).
- **Internal consistency:** §2 says the smallest change, §3 concedes ordering needs no
  code, §5 spends its whole budget on boundaries. §6 claims zero server work and §7 keeps
  it true by refusing the one field (`eot`) that would need a migration.
- **The obvious wrong fix is called out by name** in two places: aliasing one instant onto
  both columns (§5.2, Leg 2), and writing `seq` from the phone to paper over a server
  default (§7).
- **Scope:** one surface (iOS), four mechanical edits plus one callback widening, one new
  gate file. No brain change, no migration, no new subsystem.

---

## 15. Handed back

Every open question, and who answers it. Nothing here is rhetorical.

1. **When does a build reach a phone?** — *Owner.* b82 is compiled, verified, and not
   installed; b76–b80 delivered zero rows. Every live leg in §10 is blocked on this and
   nothing else. This is the only genuine blocker in the document.

2. **The `seq` zero-default defect — who fixes it, and where?** — *Whoever owns
   `brain/sorter.py` and `brain/segmenter.py`.* Not this spec, and **not the phone**. Two
   changes, both server-side: `sorter.py:261-262` must treat `0` as absent (PocketBase's
   default is not an ordinal), and `segmenter.py`'s `store.append` /`stamp_event` should
   write the ordinal from `turn_count` (`segmenter.py:409`), per
   `2026-08-25-sorter-conversation-granularity.md:172-173`. Currently latent — `MODE_ON`
   self-demotes to shadow at `worker.py:2518-2528`, so `write_verdict` is unreachable —
   but it means the Step 3 shadow evaluation is today measuring a payload where every turn
   renders `#0` and nothing is ever `[NEW]`.

3. **Does `pendingSince` track speech onset closely enough?** — *Measurement, after a
   build ships.* §5.1 reasons it is tens-to-low-hundreds of ms and therefore noise against
   `CONTINUE_S = 45`. That is an argument, not a number. If it turns out to be seconds,
   §8's `SFTranscriptionSegment` route becomes the answer and the replay-offset caveat at
   `PhoneListener.swift:840-847` has to be solved.

4. **`decide_link`'s `_ANAPHORIC` word list (`segmenter.py:44-46`) is live and on the
   wrong side of Law 1.** — *Owner, plus the next Law 1 audit.* It ships today, it decides
   whether two turns are about the same thing using an opener list and a word-overlap
   count, and this spec does not touch it. It is not registered as tape. Either it gets a
   `TAPE:` comment with a red gate leg (LAW 2), or the meaning call moves to a model. It
   cannot stay unmarked.

5. **`capture_key`'s `CLOCK_SKEW_MAX_S = 6h` versus the pendant's `LATE_MAX_S = 6h`.** —
   *Whoever builds Step 7.* Backlog older than 6 h silently falls back to arrival time at
   `worker.py:2811-2812`, which is the exact reordering the envelope exists to prevent.
   Harmless today because nothing produces backlog. It becomes a correctness bug the day
   the pendant does.

6. **Does the pendant get its own clock domain, or keep borrowing the phone's?** —
   *Whoever builds Step 7, and it needs firmware.* §5.4 gives the pendant the phone's
   decode-time instant, which is honest in range and wrong for backlog. The BLE time-sync
   design — record `(phone_wall_clock, pendant_boot_counter)` at connect, never trust the
   MCU's absolute clock — is specified in `CAPTURE-ARCHITECTURE.md` and unbuilt.

7. **Who runs Leg 4's airplane-mode procedure, and how often?** — *Owner or whoever holds
   the phone.* The leg cannot manufacture a buffered row; it can only detect one. Without
   a standing procedure, Leg 4 sits at UNPROVEN forever, which is honest but is not proof.

8. **Does `eot` get its column at Step 5, or earlier?** — *Whoever builds Step 5.* §7
   defers it on the grounds that `parent_line` already carries the only distinction the
   current flush policy can make. If someone wants the flush reason on the wire before
   neural endpointing exists, that is one additive nullable field and one line in
   `pushEvent` — but it is a server change, and this spec's claim to need none dies with
   it.
