# Voice Capture Quality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the phone hear the owner well enough to trust manual voice testing, and make a failed test explain itself.

**Architecture:** Five changes on the existing `SFSpeechRecognizer` path, in LAW 5 order. New pure-Foundation policy objects (journal, flush reason) land first with their own device-free tests; the integration into `PhoneListener` and `AnticipyBackend` happens once, afterwards, consuming those interfaces. No speech engine is replaced.

**Tech Stack:** Swift 6.2 (`/usr/bin/swift`, target iOS 16.0), Foundation-only for policy code, `swiftc` shell runners under `app/ios/Tests/` for tests, Python 3 for the gate leg.

**Spec:** `docs/superpowers/specs/2026-08-24-voice-capture-design.md` — read it. It is the binding authority; this plan argues from it.

## Global Constraints

- `HARNESS-LAWS.md` binds every task. LAW 1: no pattern-match may decide meaning. LAW 2: no tape without an expiry and a red gate leg. LAW 3: repo-green is not done; say what is offline-only. LAW 4: decisions go in repo files. LAW 5: senses → context → examples → model tier → structure. LAW 6: self-review adversarially before declaring done.
- `design/LOCAL-FIRST.md`: raw audio never leaves the device; voiceprints never sync; only conclusions travel.
- **`minNewWords` MUST NOT appear in `PhoneListener.swift`.** `app/ios/Tests/run_flush_policy_tests.sh` fails the build if it does, because a flush floor once marked words as sent without sending them. See spec §6 Change 2 (struck).
- **Do not change `VoiceRoster.match = 0.78` or `margin = 0.05`** (`VoiceRoster.swift:27,29`). `tests/test_roster_parity.py` pins Swift to `proof/voice_roster.py`.
- Policy code is **Foundation-only** so it tests without a simulator, signing or network. Follow the precedent in `TranscriptFlushPolicy.swift:10-12`.
- Comments explain the **incident** a guard prevents, in plain prose. Never write a comment claiming a mechanism that does not exist.
- **No em dash in any iOS string a person reads.** Comments may use them.
- Regression floor, unchanged at every task: `PYTHONPATH=. python3 -m pytest tests -q --ignore=tests/test_day_zero_oracle.py` = 1054 passing; `python3 overnight/tejas_gate.py` = 8/8; `node extension/tests/run_all.mjs` = 55 suites. `tests/test_day_zero_oracle.py` is deselected because it imports `playwright`, absent on this machine.
- Another editor is active in this working tree. **Re-read any file immediately before editing it.** Do not revert changes you did not make. Do not run formatters or linters. Do not `git add -A`; stage only the paths you touched.
- Never commit secrets. `.env.local` is never read or echoed.

---

### Task 1: The listening journal

**Files:**
- Create: `app/ios/Anticipy/Audio/ListenJournal.swift`
- Create: `app/ios/Tests/ListenJournalTests.swift`
- Create: `app/ios/Tests/run_journal_tests.sh`

**Interfaces:**
- Consumes: nothing.
- Produces — Task 3 calls exactly this, so the names are fixed:

```swift
enum ListenEvent: Equatable {
    case sessionStarted
    case sessionStopped(cause: StopCause)
    case recognizerSwapped(cause: SwapCause)
    case flushed(reason: String, words: Int)
    case posted(ok: Bool, detail: String)

    enum StopCause: String, Equatable {
        case owner, interruption, routeChange, authorizationLost, unrecoveredFailure
    }
    enum SwapCause: String, Equatable {
        case error, taskLimit, routeChange, silenceRotation
    }
}

final class ListenJournal {
    static let shared: ListenJournal
    init(limit: Int = 400)
    func record(_ event: ListenEvent, at: Date = Date())
    var entries: [String] { get }        // oldest first, human-readable
    func clear()
}
```

**Why it exists:** a manual voice test currently leaves no evidence at all — no `print`, `NSLog`, `os_log` or `Logger` anywhere in `PhoneListener.swift` or `AnticipyApp.swift` — so "the test didn't complete" cannot be diagnosed. Spec §9.

- [ ] **Step 1: Write the failing tests**

`app/ios/Tests/ListenJournalTests.swift`, in the style of `TranscriptFlushPolicyTests.swift` (plain `main`-level checks, a `check(_:_:)` helper, non-zero exit on failure — read that file first and match it). Cases:

1. `record` then `entries` returns one line containing the event name.
2. Entries come back oldest-first.
3. A `sessionStopped(cause: .routeChange)` line contains `routeChange` — the cause must be readable, since the cause is the whole point.
4. **Bounded:** with `limit: 3`, recording 10 events keeps 3 and keeps the NEWEST 3. `backend/start.sh` exists because a disposable log filled a volume and took production down; an unbounded journal on a phone is the same mistake.
5. `clear()` empties it.
6. A `flushed(reason: "ceiling", words: 12)` line contains both `ceiling` and `12`.
7. Recording from two queues concurrently does not crash and yields 200 entries with `limit: 400` (serialize with a private `DispatchQueue`, the pattern `VoiceRoster.swift:54` already uses).

- [ ] **Step 2: Write the runner and prove the tests fail**

`app/ios/Tests/run_journal_tests.sh`, modelled on `run_flush_policy_tests.sh`: `set -e`, `mktemp -d`, `trap` cleanup, `swiftc -O` the source plus the test file, run the binary. Do NOT add wiring assertions yet — Task 3 adds the call sites, so a wiring check here would be red for a reason that is not a defect.

Run: `sh app/ios/Tests/run_journal_tests.sh`
Expected: compile failure — `ListenJournal` does not exist.

- [ ] **Step 3: Implement `ListenJournal.swift`**

Foundation only. A private `DispatchQueue` for serialization, a ring bounded by `limit` evicting oldest-first, and a `record` that formats one readable line per event including an ISO-8601 timestamp. No audio, and no transcript text beyond the word COUNT that `flushed` carries — the events collection already holds the words, and the journal must not become a second copy of the owner's speech.

- [ ] **Step 4: Prove the tests pass**

Run: `sh app/ios/Tests/run_journal_tests.sh`
Expected: every check passes, exit 0. Paste the output.

- [ ] **Step 5: Commit**

```bash
git add app/ios/Anticipy/Audio/ListenJournal.swift app/ios/Tests/ListenJournalTests.swift app/ios/Tests/run_journal_tests.sh
git commit -m "A listening session that fails can now say why"
```

---

### Task 2: The flush knows why it fired

**Files:**
- Modify: `app/ios/Anticipy/Audio/TranscriptFlushPolicy.swift`
- Modify: `app/ios/Tests/TranscriptFlushPolicyTests.swift`

**Interfaces:**
- Consumes: nothing.
- Produces — Task 3 consumes this:

```swift
extension TranscriptFlushPolicy {
    enum Reason: String, Equatable {
        case gap        // a pause ended the utterance: a complete thought
        case ceiling    // maxHold expired mid-speech: a cut, not an ending
        case final      // the recognizer finalized
    }
    /// Why must these words go out now, or nil if they need not.
    func flushReason(pendingSince: Date?, lastPartialAt: Date?, now: Date) -> Reason?
}
```

`mustFlushNow` stays, unchanged and still used, so nothing that calls it today breaks. `flushReason` is additive.

**Why it exists:** the 8s `maxHold` ceiling correctly stopped silent data loss (`TranscriptFlushPolicy.swift:14-17`, ~250 words arriving as 71 characters), but a ceiling flush currently *ends a line*, so continuous speech is cut every 8 seconds regardless of sentence boundary. That is where the 54% shard rate comes from. Telling the caller WHY the flush fired lets a cut be marked as a continuation instead of published as a complete thought. Spec §6.

- [ ] **Step 1: Write the failing tests**

Append to `app/ios/Tests/TranscriptFlushPolicyTests.swift`, matching its existing style. Cases:

1. `pendingSince == nil` → `flushReason` is `nil`.
2. Pending 9s with a partial 0.1s ago → `.ceiling` (still speaking, ceiling expired).
3. Pending 3s with the last partial 2.7s ago → `.gap` (a pause longer than `utteranceGap` 2.6 ended it).
4. Pending 3s with the last partial 0.5s ago → `nil` (still mid-utterance, ceiling not reached).
5. **Precedence:** pending 9s AND last partial 2.7s ago → `.gap`. A completed thought is not a cut; if both conditions hold the gap wins, because marking a finished sentence as a continuation would chain unrelated lines together.
6. `mustFlushNow` still returns true at exactly `maxHold` and false below it — the existing contract is untouched.

- [ ] **Step 2: Prove they fail**

Run: `sh app/ios/Tests/run_flush_policy_tests.sh`
Expected: compile failure — no `flushReason`.

- [ ] **Step 3: Implement `flushReason`**

Pure function on the existing `utteranceGap` / `maxHold`. Order the checks so `.gap` is tested before `.ceiling` (test 5). Comment the precedence with the reason, not just the rule.

- [ ] **Step 4: Prove they pass**

Run: `sh app/ios/Tests/run_flush_policy_tests.sh`
Expected: all pass, exit 0, including the pre-existing wiring assertions. Paste the output.

- [ ] **Step 5: Commit**

```bash
git add app/ios/Anticipy/Audio/TranscriptFlushPolicy.swift app/ios/Tests/TranscriptFlushPolicyTests.swift
git commit -m "A cut mid-sentence is not the same event as a finished thought"
```

---

### Task 3: Wire the phone up

**Files:**
- Modify: `app/ios/Anticipy/Audio/PhoneListener.swift`
- Modify: `app/ios/Anticipy/Backend/AnticipyBackend.swift`
- Modify: `app/ios/Anticipy/AnticipyApp.swift` (only the `heard(...)` call path, if a continuation flag must ride through it)

**Interfaces:**
- Consumes: `ListenJournal.shared.record(_:)` and `ListenEvent` from Task 1; `TranscriptFlushPolicy.Reason` and `flushReason(...)` from Task 2.
- Produces: `events.parent_line`, `events.spoken_at`, `events.capture_ended_at` now populated by the phone.

**This is the integration task.** Re-read all three files immediately before editing; another editor is active in this tree.

- [ ] **Step 1: Journal the call sites**

Record `sessionStarted`; `sessionStopped` with a real cause at every exit; `recognizerSwapped` at each `swapRecognition` call site with the cause that drove it — the watchdog distinguishes them already (`PhoneListener.swift:267-282`: dead engine, stale buffer, silent recognizer, and the 120s silence rotation), and the recognition callback's `error != nil` branch (`:364`) is `.error`; `flushed` with `reason.rawValue` and the word count; `posted` with the outcome.

- [ ] **Step 2: Set the two unset flags**

In `startRecognition` (`PhoneListener.swift:298`), alongside the existing `contextualStrings` and `requiresOnDeviceRecognition`:

```swift
req.taskHint = .dictation
req.addsPunctuation = true
```

`addsPunctuation` needs `if #available(iOS 16.0, *)` only if the deployment target were lower; it is 16.0, so no guard is required. Neither is set anywhere in `app/ios/` today.

- [ ] **Step 3: Mark a ceiling flush as a continuation**

Replace the flush trigger's use of `mustFlushNow` with `flushReason`, and when the reason is `.ceiling`, mark the emitted line as continuing the previously emitted one, carrying the previous line's id as `parent_line`. A `.gap` or `.final` flush carries no parent. Keep `cursor.takePending` all-or-nothing — do not introduce a word floor, and do not let the identifier `minNewWords` appear in this file (`run_flush_policy_tests.sh` fails the build on it).

- [ ] **Step 4: Stamp capture time where capture happens**

`capture_started_at` is the canonical column (`brain/worker.py:2387-2390` reads it first, accepting `spoken_at` as an alternate). Today `pushEvent` sets it to `Date()` at network-push time (`AnticipyBackend.swift:487`), so the offline retry queue re-stamps buffered lines at flush — the exact reordering bug the comment above it claims to fix. Set `capture_started_at` and `spoken_at` to the instant the flush produced the line, set `capture_ended_at` at the same point, carry all three unchanged through the offline queue, and stop `pushEvent` calling `Date()`. Leave `gap_before_ms`, `seq` and `boot_id` alone: nothing consumes them.

- [ ] **Step 5: Prove it builds and the existing checks hold**

```bash
sh app/ios/Tests/run_flush_policy_tests.sh
sh app/ios/Tests/run_cursor_tests.sh
sh app/ios/Tests/run_journal_tests.sh
sh app/ios/Tests/run_all.sh
```
Expected: all exit 0. Paste each tail. Then confirm the Swift compiles as the app sees it — `xcodebuild` is available at `/usr/bin/xcodebuild`; if a full build needs signing you cannot satisfy, say so explicitly rather than claiming a build you did not run, and fall back to `swiftc -parse` over the three modified files.

- [ ] **Step 6: Commit**

```bash
git add app/ios/Anticipy/Audio/PhoneListener.swift app/ios/Anticipy/Backend/AnticipyBackend.swift app/ios/Anticipy/AnticipyApp.swift
git commit -m "Stamp when it was said, say why the flush fired, and keep a journal"
```

---

### Task 4: Enrollment stops hiding in Settings

**Files:**
- Modify: `app/ios/Anticipy/Views/OnboardingView.swift`
- Create: `app/ios/Anticipy/Audio/EnrollmentInvite.swift`
- Create: `app/ios/Tests/EnrollmentInviteTests.swift`
- Create: `app/ios/Tests/run_enrollment_invite_tests.sh`

**Interfaces:**
- Consumes: `VoiceEnrollView` (exists), `SpeakerTagger.hasOwnerProfile` (`:47`), `VoiceRoster.unnamedPeople` (`:58`).
- Produces:

```swift
struct EnrollmentInvite {
    static let voicesBeforeAsking = 3
    /// Should she ask him to teach her his voice, right now?
    static func shouldAsk(hasOwnerProfile: Bool, unnamedVoices: Int, alreadyAsked: Bool) -> Bool
}
```

**Why it exists:** `VoiceEnrollView.swift` shipped in build 43 and is complete, but is presented ONLY from `SettingsView.swift:571-573` behind a button the owner must go find. It is absent from onboarding, though brief 09's definition of done requires "onboarding + Settings (re-enroll)". With no owner profile every verdict is forced ambiguous (`VoiceRoster.swift:175-176`), `SpeakerTagger` returns nil (`:113`), and `speaker` is never written — which is why it was empty on all 137 lines of the Tejas call, and why four of that call's six bad acts happened. Spec §5.

- [ ] **Step 1: Write the failing invite tests**

`app/ios/Tests/EnrollmentInviteTests.swift` plus its runner, both modelled on the flush-policy pair. Cases:

1. Owner profile already exists → false, whatever the voice count. Never ask for something already done.
2. No profile, 3 unnamed voices, not asked → true.
3. No profile, 2 unnamed voices → false. Fewer than three is not yet evidence.
4. No profile, 5 voices, already asked → false. Once, ever. This product's whole character is that she earns each interruption (`UNINVITED_TEXTS_PER_DAY = 3`, `SPEAK_ONCE`), so a declined ask is not re-raised.
5. No profile, 0 voices, not asked → false.

Run the runner. Expected: compile failure, `EnrollmentInvite` undefined.

- [ ] **Step 2: Implement `EnrollmentInvite.swift`**

Foundation only, no UI, no storage — a pure decision so it is testable without a device. Persisting `alreadyAsked` belongs to the caller.

- [ ] **Step 3: Prove the tests pass**

Run: `sh app/ios/Tests/run_enrollment_invite_tests.sh`. Paste the output.

- [ ] **Step 4: Add the onboarding page**

Read `OnboardingView.swift` fully first and match its existing page structure, animation and voice. Add a page presenting `VoiceEnrollView`, skippable without friction, that does not block finishing onboarding. Reuse the copy already approved in Settings — *"Teach me your voice and I'll stop mixing up your plans with other people's."* Do not invent new voice, do not show percentages or scores, no developer language, no em dash in anything a person reads. If `SpeakerTagger.available` is false the page must not appear at all — the Settings screen already handles that case with "Learning voices needs a piece I don't have on this phone yet."

- [ ] **Step 5: Prove the app still compiles**

Run the same checks as Task 3 Step 5, plus `sh app/ios/Tests/run_interview_tests.sh` since onboarding is adjacent to the interview flow. Paste the tails. State plainly which checks are compile-level and which would need a device.

- [ ] **Step 6: Commit**

```bash
git add app/ios/Anticipy/Views/OnboardingView.swift app/ios/Anticipy/Audio/EnrollmentInvite.swift app/ios/Tests/EnrollmentInviteTests.swift app/ios/Tests/run_enrollment_invite_tests.sh
git commit -m "She asks for your voice on day one, instead of waiting in Settings"
```

---

### Task 5: A shard rate that cannot regress quietly

**Files:**
- Modify: `overnight/tejas_gate.py`
- Modify: `proof/score_links.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: a ninth gate leg.

- [ ] **Step 1: Add the leg**

Read `overnight/tejas_gate.py` fully first; match `leg_2_shard_floor`'s structure exactly (raise `LegFailed` with a sentence naming what breaks for a person, return a one-line success string, register in `LEGS`). The new leg asserts the phone-side machinery that keeps a mid-sentence cut from becoming its own line exists and is wired: `flushReason` present in `TranscriptFlushPolicy.swift`, and `PhoneListener.swift` both calling it and setting a parent on a `.ceiling` flush. Follow the precedent recorded at `leg_4_compute_lane`: test the real organ end to end, never a word list — an earlier version of that leg checked a regex for verb membership and was itself a LAW 1 violation.

Baseline is `54%` shards on the recorded call and the target is under 25% (spec §8). State in the leg's own comment that it asserts the MECHANISM, and that the RATE is only measurable on a live session — LAW 3.

- [ ] **Step 2: Note the interaction in `score_links.py`**

`parent_line` is now written by the phone as well as by the brain's dark link path. `proof/score_links.py` scores the timer arm against the link arm; phone-authored edges are real continuations and improve ground truth, but the harness must say so before anyone scores a verdict, or the comparison moves under them. Add that note where the arms are built. Do not change the scoring.

- [ ] **Step 3: Prove both**

```bash
python3 overnight/tejas_gate.py
PYTHONPATH=. python3 -m pytest tests -q --ignore=tests/test_day_zero_oracle.py
```
Expected: 9/9 legs, 1054+ passing. Paste both tails.

- [ ] **Step 4: Commit**

```bash
git add overnight/tejas_gate.py proof/score_links.py
git commit -m "The shard fix gets a leg, so it cannot rot back"
```

---

## Self-Review

**Spec coverage:** §5 → Task 4. §6 Change 1 → Tasks 2 and 3; §6 Change 2 struck by ruling, and Task 3 Step 3 plus the Global Constraints carry the prohibition. §7 → Task 3 Step 4. §8 free flags → Task 3 Step 2; §8 engine deferral needs no task by design. §9 → Tasks 1 and 3 Step 1. §10 testing → every task's own steps, plus Task 5.

**Placeholders:** none. Every interface is named with its exact signature and every test case states its expected value.

**Type consistency:** `ListenEvent` / `ListenJournal.record` in Task 1 match Task 3 Step 1. `TranscriptFlushPolicy.Reason` and `flushReason` in Task 2 match Task 3 Step 3. `EnrollmentInvite.shouldAsk` is self-contained in Task 4.

**Cross-task file overlap:** `PhoneListener.swift` is touched by Task 3 only. `TranscriptFlushPolicy.swift` by Task 2 only. `TranscriptFlushPolicyTests.swift` by Task 2 only, and Task 3 runs but does not edit it. No two tasks modify the same file.

**Known conflict, already ruled:** the flush-policy runner forbids `minNewWords` in `PhoneListener.swift`. Spec §6 Change 2 is struck for that reason and the constraint is repeated in Task 3 Step 3.
