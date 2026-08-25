# PHONE-AS-PENDANT — always-listening reliability — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make always-listening on the phone solid enough to live with for a
whole real day — and make that day *readable*, so every later claim is measured
rather than argued.

**Architecture:** Stage 0 builds the instrument, because nothing below can be
judged until a day can be read. Stage 1 closes the two holes that end a day.
Stage 2 makes crash recovery exactly-once. Every new decision is expressed as a
**pure Foundation policy function** in its own file with a standalone `swiftc`
runner — the `TranscriptFlushPolicy` tradition — so the mechanism is testable
with no device and no simulator.

**Tech Stack:** SwiftUI / AVFoundation / Speech (iOS 16 floor), pure-Foundation
policy files + `swiftc` runners, Python for the server-side day report.

**Spec:** `docs/BRIEF.html` moments 2, 10, 17, 49 and §9 item 1;
`docs/superpowers/specs/2026-08-24-voice-capture-design.md`; `HARNESS-LAWS.md`.

## Global Constraints

- iOS deployment target **16.0** — no API above that floor without an
  `@available` fence.
- **The journal never contains speech.** `ListenJournal`'s existing rule
  (word counts and causes only, never text) extends to every new event.
- **Law 1**: everything here is senses and mechanism — which clock ran out,
  which cause fired. No new judgment about what words mean.
- Pure policy files carry no UIKit/AVFoundation imports, so their runners
  compile standalone.
- **Do not reintroduce `minNewWords`.** `run_flush_policy_tests.sh` fails the
  build if it reappears; the 2026-08-16 loss (≈250 spoken words arriving as 71
  characters) is why. Nothing in this plan touches `utteranceGap` (2.6s),
  `maxHold` (8s), the debounce, or `takePending`'s all-or-nothing contract.

---

## The two findings that justify this card

Stated plainly, because a stranger hits the first on day one:

1. **A phone call can end listening for the rest of the day.** On interruption
   `.began` we set `suspended = true` and do nothing else. `UIBackgroundModes:
   audio` buys background execution only while audio is *flowing*; once the
   engine stops, iOS suspends the app and the 4-second watchdog Timer stops with
   it. Nothing wakes it — there is no `processing` or `fetch` mode, and
   `bluetooth-central` only fires for a pendant that does not exist yet. And
   `resumeListeningIfWanted()` is a **no-op** on return, because it guards on
   `!listener.isListening` and `isListening` was never set false. The only thing
   that restarts listening is the owner opening the app.

2. **A recognizer that dies with nothing pending is invisible.** `partial` is
   assigned on every result and cleared in exactly two places — neither of them
   a flush. The only "recognizer is deaf" leg requires words to be *pending*,
   which is the rarer state. The UI says Listening and the day produces nothing.

3. **A live data-loss bug the judges found, which outranks both.**
   `flushUnsent` does `let queue = unsent; unsent = []` **before a single
   POST**, and only reinstates failures at the end. A battery death inside those
   sequential round-trips loses everything already dequeued. That is moment #49
   — *"nothing is lost"* — scoring the exact opposite today.

4. **One line, minutes to fix.** `stopAfterEnrollment()` clears `enrolling`
   before calling `stop()`, and `stop()` emits its tail through `onLine?` — so
   the tail of a **voice-enrollment recording** can leave as a transcript line.
   Fix it first; it is the cheapest correctness win in the card.

---

## Blocking corrections from the adversarial pass

Applied to the stages below. Recorded here because each replaces something the
first draft got wrong.

- **Use `events.external_event_id`, not a new column.** It already exists with a
  UNIQUE partial index (`1700000028_event_sources.js`). No new migration, no
  dedupe hook, no TOCTOU — the storage engine refuses the duplicate. Stage 2.1
  drops from about a day to a few hours.
- **`pushEvent` must treat a unique-constraint rejection as SUCCESS.** Without
  this, dedupe converts a duplicate into an *infinite requeue*. This is the
  single highest-risk line in the card. Precedent already exists in
  `AnticipyBackend.swift`.
- **The file sink never blocks the audio thread.** Write via `queue.async`,
  never `.sync`, and add no journal call inside the tap closure. Count
  orphan-buffer overflows into a plain integer on the audio thread and let the
  existing 4-second watchdog record the tally. Assert the rule on source shape,
  the way `run_flush_policy_tests.sh` already does.
- **Every queue removal is a read-modify-write of the live store**, filtered by
  `clientLineID`. No snapshot writes after an `await`, ever.
- **Mint `clientLineID` in `heard()`**, at capture — never at flush. The offline
  queue once re-stamped every buffered line when the signal returned and
  reintroduced the reordering the capture stamps exist to prevent.

---

## STAGE 0 — make the instrument real (≈2 days)

**After Stage 0 alone, a real day becomes diagnosable for the first time.** If
the stranger week starts before everything lands, Stages 0 and 1 are the ones
that must be in the build.

### Task 1: persist the journal, bounded and rotated

**Files:**
- Modify: `app/ios/Anticipy/Audio/ListenJournal.swift`
- Test: `app/ios/Tests/ListenJournalTests.swift` (exists — extend)

**Interfaces:**
- Produces: a file sink alongside the existing ring, writing on the **existing
  serial queue** so the ordering guarantee is unchanged.
  `Application Support/listen-journal.log`, rotating to `.1` at 256 KB, two
  files kept.

- [ ] **Step 1: Write the failing test**

```swift
// Bounded and rotated for the reason the file's own header already gives:
// a disposable log that filled a volume is why backend/start.sh exists.
check("a file over the cap rotates and the newest line is in the newest file")
check("reopening reads back oldest-first")
check("nothing written contains transcript text")
```

- [ ] **Step 2: Run to verify it fails** — `sh app/ios/Tests/run_journal_tests.sh`
- [ ] **Step 3: Implement the file sink + rotation**
- [ ] **Step 4: Run to verify it passes**
- [ ] **Step 5: Commit**

### Task 2: `ListenTally` — a pure fold over events

**Files:**
- Create: `app/ios/Anticipy/Audio/ListenTally.swift`
- Create: `app/ios/Tests/ListenTallyTests.swift` + `run_tally_tests.sh`

**Interfaces:**
- Produces: `ListenTally.of(_ events: [(Date, ListenEvent)]) -> Tally` with
  session count, total listening minutes, longest unbroken stretch, swaps by
  cause, flushes by reason, POST failures, interruptions, and recoveries.

A pure fold means it is testable with `swiftc` alone and needs **no call sites
in PhoneListener** — the journal already records everything it reads.

- [ ] **Step 1: Write the failing test** (a day with one 20-minute gap reports
      the gap; an empty day reports zeros, not nil)
- [ ] **Step 2: Run to verify it fails**
- [ ] **Step 3: Implement the fold**
- [ ] **Step 4: Run to verify it passes**
- [ ] **Step 5: Commit**

### Task 3: Settings → "Listening, find out what's wrong" — in RELEASE

**Files:**
- Create: `app/ios/Anticipy/Views/ListeningDiagnosticsView.swift`
- Modify: `app/ios/Anticipy/Views/SettingsView.swift` (Listening section)

Ships **outside `#if DEBUG`** — the stranger week is a release build installed
by cable. Follows the haptics diagnostic's voice: plain sentences, no
percentages presented as scores, and no em dashes in anything a person reads.

**This makes three lying comments true.** `ListenJournal.swift` and
`PhoneListener.swift` both claim the journal is "exportable from Settings"; no
such UI exists today.

- [ ] **Step 1:** Add the `NavigationLink` and the view (tally + last ~60 lines
      in monospace + `ShareLink` over the log file)
- [ ] **Step 2:** Build for the simulator; confirm it renders and shares
- [ ] **Step 3:** Delete the now-true claims' "(not yet built)" hedges
- [ ] **Step 4: Commit**

### Task 4: record the three facts that are invisible today

**Files:** Modify `ListenJournal.swift` (one new case), `PhoneListener.swift`.

Add `noted(String)` carrying **senses facts only**, never speech:

- After `configureAndStartEngine`, read `AVAudioSession.category` and `.mode`
  **back** and note them. Three `try?` calls currently swallow every failure, so
  the app can report "Listening" over a session it never configured. (Readback
  is already proven possible in `HapticEngine.swift`.)
- Note `isLowPowerModeEnabled` at session start.
- Note orphan-buffer overflow, coalesced to one line per swap so it cannot
  flood the ring.

- [ ] **Step 1: Write the failing test** (a noted line is readable back and
      contains no transcript text)
- [ ] **Step 2–5:** fail → implement → pass → commit

### Task 5: `proof/capture_day.py` — the server-side day report

**Files:** Create `proof/capture_day.py`.

Reads a day of `events` for one owner and reports: lines, words, ≤4-word shard
rate **counting a `parent_line`-stitched chain as ONE line**, speaker coverage,
and the longest silent gap. No app change, no device. A deterministic
measurement of an outcome — Law 1's gates-and-evals category.

- [ ] **Step 1: Write the failing test** with synthetic rows
- [ ] **Step 2–5:** fail → implement → pass → commit

**STAGE 0 EXIT:** a real day is readable, from the phone and from the server.

---

## STAGE 1 — stop losing the day (≈2 days)

### Task 6: `ListenWatchdogPolicy` — close the blind spot

**Files:**
- Create: `app/ios/Anticipy/Audio/ListenWatchdogPolicy.swift`
- Create: `app/ios/Tests/ListenWatchdogPolicyTests.swift` + runner
- Modify: `PhoneListener.swift` — the watchdog body becomes a thin call site.

**Interfaces:**
- Produces:
  `decide(engineRunning:hasTask:lastBufferAt:lastResultAt:lastPartialAt:requestBornAt:hasPending:now:) -> Action`
  where `Action` is `.rebuild | .startRecognition | .swap(SwapCause) | .rotate |
  .nothing`.

Two behaviour changes inside it:
- rotation is judged on `lastResultAt`/`lastPartialAt`, **not** on `partial`, so
  it survives the first utterance;
- a new leg: engine running, audio flowing, no result for longer than the
  rotation window — **whether or not words are pending** → swap.

Also clear `partial` when a flush empties the pending text, so the two ideas
stop disagreeing.

- [ ] **Step 1: Write the failing test**

```swift
check("a recognizer silent for 130s with NOTHING pending is swapped")   // the hole
check("a person mid-sentence (partial 0.4s ago) is never rotated")      // the guard
check("a dead engine outranks everything")
check("a stale lastBufferAt rebuilds")
```

- [ ] **Step 2: Run to verify it fails**
- [ ] **Step 3: Implement the pure policy, then thin the call site**
- [ ] **Step 4: Run to verify it passes**, then the whole iOS gate
- [ ] **Step 5: Commit**

### Task 7: the interruption cliff

**Files:** Modify `PhoneListener.swift`, `AnticipyApp.swift`.

- On `.began`, take a background task assertion so the watchdog survives long
  enough to see `.ended`, and set state so `resumeListeningIfWanted()` is **not**
  a no-op on return.
- Stop the recognition-task churn: while a call owns the mic, the 0 Hz guard
  returns without installing a tap, yet `recoverAudio` still swaps the task —
  creating a fresh `SFSpeechRecognitionTask` on every 4-second tick for the
  length of the call.
- Say the honest sentence in the UI when listening really has stopped, rather
  than showing "Listening" over a dead engine.

- [ ] **Step 1: Write the failing tests** (policy-level: an interruption that
      began 3 minutes ago and never ended must not have swapped 45 times)
- [ ] **Step 2–5:** fail → implement → pass → commit

**STAGE 1 EXIT:** a call, Siri, or another app no longer ends the day.

---

## STAGE 2 — exactly one of everything (moment #49) (≈2 days)

**Files:** `AnticipyBackend.swift`, `AnticipyApp.swift` (`BufferedLine`,
`flushUnsent`), a backend migration, `brain/worker.py`.

`clientLineID` minted in `heard()` at capture and sent as
**`events.external_event_id`** — the column and its UNIQUE partial index already
exist (`1700000028_event_sources.js`), so the database refuses the duplicate with
no hook and no race. Today a replayed POST after a crash has nothing to collide
with.

**And fix the dequeue window first:** the snapshot-then-clear in `flushUnsent`
is the live loss. Read-modify-write the live store per line, filtered by
`clientLineID`.

**The scar this must not re-open:** the offline retry queue once re-stamped
every buffered line at the moment the signal returned, reintroducing exactly the
reordering the capture stamps exist to prevent. The id is minted **at capture**,
never at flush.

- [ ] **Step 1: Write the failing tests**
      — the same id posted twice yields ONE row and the queue **drains to empty**
        (a duplicate must not become an infinite requeue);
      — `heard()` called *during* the flush's await: the appended line survives;
      — killed after every single await: exactly one row per line on the server;
      — a queued line keeps its capture stamp through a flush.
- [ ] **Step 2–5:** fail → implement → pass → commit
- [ ] **Step 6: The #49 drill, on a real device** — kill the app mid-session,
      relaunch, confirm exactly one of everything and no re-texts.

---

## STAGE 3 — the honest number (≈1.5 days)

- [ ] A read-aloud check: a known script read to the phone, scored by
      `proof/capture_day.py`, giving the first post-fix capture number.
- [ ] `tejas_gate` **leg 9**, behavioural (not a source grep): `flushReason` is
      wired and a `.ceiling` flush sets `parent_line`. The leg's comment must
      state that the RATE is only measurable live (Law 3).
- [ ] The `proof/score_links.py` phone-authored-edge note.

**Leg numbering, to avoid a merge-time collision:** cluster A's plan already
claims tejas leg 9; SHELF 2's fallback leg is its own gate file. Assign centrally
before any of them merge.

---

## STAGE 4 — moments 2 and 17 (≈1 day)

- [ ] Land the enrollment invite + onboarding page (plan Task 4, still unlanded)
      so a stranger's lines carry a speaker tag from day one. Expose it per the
      voice gate's verdict: if the tagger ships dark, the page self-hides via
      `SpeakerTagger.available`.
- [ ] Read the first day report and decide moment 2 (background media) on
      evidence rather than in advance.

---

## What needs a real device and cannot be proven in a simulator

- Any interruption behaviour (calls, Siri) — the simulator does not model them.
- Battery and low-power-mode effects.
- The #49 drill.
- The capture number itself.

Everything in Stage 0 Tasks 1, 2, 5 and every pure policy file is device-free
and testable with `swiftc` alone. **That is why the policies are pure files.**

---

## Self-review notes

- **Spec coverage:** #49 → Stage 2. #10 → depends on Stage 1 (the night is only
  quiet if listening is still alive). #2 and #17 → Stage 4, deliberately after
  measurement. §9 item 1 → Stage 3 produces the number; the engine migration
  stays gated on the spec's pre-registered §8 criteria and belongs to EARS.
- **Not in scope, and deliberately:** the SpeechAnalyzer migration (EARS owns
  it), VAD (recovers ~zero words; queued post-stranger), and the pendant lane's
  Deepgram local-first debt (no pendant is flashed, so no stranger can hit it).
