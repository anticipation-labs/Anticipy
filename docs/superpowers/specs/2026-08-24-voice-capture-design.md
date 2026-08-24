# Voice capture quality — design

**Date:** 2026-08-24
**Branch:** `harness/tejas-fixes`
**Status:** approved in chat, awaiting spec review
**Binding rules:** `HARNESS-LAWS.md` (LAW 1–6), `design/LOCAL-FIRST.md`
**Reference briefs:** `design/briefs/09-local-speaker-recognition.md` (SHIPPED, reference
only), `CAPTURE-ARCHITECTURE.md`, `research/evals/call-2026-08-23-tejas/FINDINGS.md`

---

## 1. Goal

Make the phone hear the owner well enough that manual voice testing produces
trustworthy results, and make a failed test say why it failed.

This is LAW 5 step 1 and step 2 — "is she deaf?" and "is she blind?" — and it is
upstream of everything else. `FINDINGS.md` states the diagnosis plainly:

> Capture quality is upstream of decision quality; no prompt fixes it.

At 33% word capture and 54% shards, no prompt, exemplar or model-tier change can
recover words the microphone never delivered. The owner has confirmed manual voice
testing matters more right now than automated agent testing, so observability of a
manual session is a first-class deliverable rather than a nicety.

## 2. Non-goals

Named explicitly so scope cannot drift:

- **No STT engine swap.** `SpeechAnalyzer` is the likely long-term answer and is
  designed for in §8 as an explicit sequel, gated on this spec's measured numbers.
- **No Deepgram work.** It serves the pendant path only, the pendant firmware is
  `BUILT_AND_VERIFIED_NOT_FLASHED`, and `design/LOCAL-FIRST.md` forbids it for the
  phone mic in terms. The standing decision is recorded as `docs/FOLLOWUPS.md` item 8
  and is owed **before** the pendant ships, not here.
- **No new enrollment UI.** `VoiceEnrollView.swift` already exists and already has the
  right feel. This spec only makes it reachable.
- **No change to `VoiceRoster` thresholds.** `match = 0.78` and `margin = 0.05`
  (`VoiceRoster.swift:27,29`) were set by measurement over six models and one unsafe
  earlier value; `tests/test_roster_parity.py` pins Swift to
  `proof/voice_roster.py`. Out of bounds.
- **No naming of recurring voices.** Brief 09's remaining item ("I keep hearing
  someone — who is that?") is adjacent and deliberately excluded; `unnamedPeople`
  already exists for whoever picks it up.
- **No triage or prompt changes.** The brain already consumes `speaker`; this spec
  only makes the field arrive populated.

## 3. The measured evidence

From the 2026-08-23 Tejas call, the product's first paired eval — both the owner's
verbatim ground truth and every event the system produced:

| Measure | Value |
|---|---|
| Words captured | ~1,271 of ~3,900 (**33%**) |
| Lines that are ≤4-word shards | **54%** of 137 |
| Lines carrying a `speaker` tag | **0 of 137** |
| Events of that day carrying `spoken_at` | **0 of 260** |
| Decisions | 131 ignore, 6 act, **0 ask** |

Four of the six bad acts share one cause: the system did not know the owner was in a
two-way conversation. The triage prompt already contains the rule ("questions aimed at
other people: ignore"), but with no speaker attribution and 54% shards the model cannot
apply it.

A second, older datum matters because it is the same knob as the shards.
`TranscriptFlushPolicy.swift:14-17` records the 2026-08-16 live failure in the owner's
words:

> "Every time I talk for a long period of time and then I talk too quickly, the
> transcript doesn't save. That audio goes away, and then a new one will appear."

~250 words spoken without pausing arrived as three fragments totalling 71 characters.

## 4. Root causes, and which ones this spec fixes

Five distinct defects. An engine swap addresses only the last.

1. **Enrollment is unreachable.** `VoiceEnrollView.swift` is built and premium, but is
   presented only from `SettingsView.swift:571-573` behind a button the owner must go
   find. It is absent from `OnboardingView.swift`, even though brief 09's definition of
   done requires "onboarding + Settings (re-enroll)". With no owner profile,
   `VoiceRoster.identify` forces every verdict ambiguous (`VoiceRoster.swift:175-176`)
   and `SpeakerTagger` returns nil (`:113`), so `speaker` is never written
   (`AnticipyBackend.swift:491` writes it only when non-empty). **Fixed here (§5).**
2. **The flush ceiling terminates sentences.** `TranscriptFlushPolicy` pairs a 2.6s
   debounce with an 8s hard ceiling (`:24`). The debounce is correct and the ceiling
   was the right fix for silent data loss, but a ceiling flush currently ends a line.
   Continuous speech is therefore cut every 8 seconds regardless of sentence boundary.
   Echo suppression also ignores anything under 4 words (`:71`), so short shards are
   neither merged nor deduped. **Fixed here (§6).**
3. **Capture time is unwritten.** `spoken_at`, `capture_ended_at`, `gap_before_ms` and
   `boot_id` have zero writers in `app/ios/`. `capture_started_at` is stamped
   `Date()` inside `pushEvent` (`AnticipyBackend.swift:487`) — network-push time, so
   the offline retry queue re-stamps buffered lines at flush, which is the exact
   reordering bug the comment above it claims to fix. **Fixed here (§7).**
4. **A manual session leaves no evidence.** There are no `print`, `NSLog`, `os_log` or
   `Logger` calls in `PhoneListener.swift` or `AnticipyApp.swift`. When a test "doesn't
   complete" there is nothing to read, so the mic, the recognizer, the flush, the
   network and the brain are indistinguishable as suspects. **Fixed here (§9), and
   built first.**
5. **`SFSpeechRecognizer` has a task-duration limit** and weaker distant-mic handling.
   Hitting the limit is what produced the collapsed final in cause 2.
   **Explicitly deferred to §8.**

## 5. Enrollment becomes reachable

**Architecture.** No new components. `VoiceEnrollView` is presented from a second
place, and one evidence-triggered invitation is added.

**Onboarding page.** `VoiceEnrollView` is presented as its own onboarding page, in her
voice, skippable without friction — matching brief 08's rule that everything is
skippable and "skips recorded as nothing". It must not block finishing onboarding.

**The evidence-triggered ask.** If enrollment was skipped, she asks exactly once, and
only when she has evidence she needs it: when `VoiceRoster` has accumulated **three or
more distinct unnamed voices** while `hasOwnerProfile` is false. That is the moment the
need is demonstrable rather than hypothetical.

Rationale, and why not a timer or a launch-count: this codebase's whole interruption
culture is that she earns each interruption with evidence (`worth_interrupting_him`,
`SPEAK_ONCE`, `UNINVITED_TEXTS_PER_DAY = 3`). "Three voices and I cannot tell which is
you" is evidence. "Three days since install" is nagging. The ask is once, ever, per
install, and declining is permanent until the owner goes to Settings.

**Copy.** Reuse the Settings sentence already written and approved in tone: *"Teach me
your voice and I'll stop mixing up your plans with other people's."* No new voice to
invent, no percentages, no developer language.

**Local-first posture (required by `design/LOCAL-FIRST.md` rule 5).** Unchanged and
already compliant: the embedding is computed on-device by `SpeakerTagger.enrollOwner`
(`:118-123`), written to app support by `VoiceRoster.save`, never synced. What leaves
the phone is one word — `owner`, `other:<id>`, `other:<name>` — and never anything
voice-shaped.

## 6. The line boundary

**The principle:** the ceiling must stop *losing* words without starting to *invent*
sentence boundaries. Today it does both jobs with one action.

**Change 1 — a ceiling flush emits a continuation, not a terminus.** When
`mustFlushNow` fires on `maxHold` rather than on `utteranceGap` or a final result, the
emitted line is marked as continuing the previous one. The words go out immediately, so
nothing is lost and the existing failure does not return, but the consumer is told this
was a mid-sentence cut rather than a completed thought.

**Change 2 — a minimum-new-words floor with merge-forward.** A fragment below the floor
is held and merged into the next emission instead of posted alone, bounded by the same
`maxHold` ceiling so held words can never be stranded. The floor restores the intent of
the removed `take(minNewWords:)` without reintroducing all-or-nothing behaviour: the
old version dropped, this one defers.

**Where the marker travels.** The `events` collection already carries `parent_line`
(migration `1700000020`), written today only by the brain's dark link path and read by
nothing. A phone-authored continuation is exactly the same relationship — "this line
continues that one" — and `brain/links.py` already computes conversations as connected
components over it, order-independently, with a documented honesty wall for unknown
ids. Reusing it adds no schema and no second concept.

**Interaction with the dark link graph, stated so it cannot surprise anyone.** Writing
`parent_line` from the phone does not switch on `LINKS_ON` (`brain/worker.py:2445`) and
does not change any brain behaviour: nothing reads the field yet. It does mean
`proof/score_links.py`, when finally run, sees phone-authored edges alongside
model-authored ones. That is an improvement in ground truth, but it must be noted in
that harness before the comparison is scored, or the timer-versus-link verdict would be
measured against a moving target. **Action: note it in `proof/score_links.py` as part
of this work.**

**Anti-goal.** No word-count or phrasing rule may decide what a line *means* — the
floor decides only whether enough new material exists to post yet. Per LAW 1 that is
plumbing, in the "senses" category, not meaning.

## 7. Capture time becomes true

- Stamp the moment words are heard, not the moment they are sent.
  `capture_started_at` is the CANONICAL column — `worker.capture_key` reads it first
  and accepts `spoken_at` only as an alternate name so either works during a rollout
  (`brain/worker.py:2387-2390`). So the defect is not that the canonical column is
  missing; it is that it holds the wrong instant. Set it when the flush produces the
  line, and set `spoken_at` to the same instant so the rollout tolerance stays
  meaningful rather than decorative. `pushEvent` stops calling `Date()`
  (`AnticipyBackend.swift:487`) and transmits what it is given.
- Write `capture_ended_at` at the same point.
- The offline queue must carry these stamps through unchanged, so a line buffered
  offline and flushed hours later still reports when it was spoken.

**Why this matters beyond tidiness.** The brain already sorts by capture time —
`worker.capture_key` prefers when it was *said* and falls back to arrival — and
`tests/test_capture_order.py` already defends spoken-order replay of a flushed backlog
plus refusal of implausible stamps. That machinery is live and currently receiving
nothing to work with. This change feeds an existing consumer rather than adding one.

`gap_before_ms`, `seq` and `boot_id` stay unwritten and out of scope; they belong to
`CAPTURE-ARCHITECTURE.md`'s larger unbuilt design and nothing consumes them.

## 8. The engine — deferred, with the decision criteria fixed now

`SpeechAnalyzer` / `SpeechTranscriber` is the probable endgame: no task-duration limit
(which removes §6's root cause rather than managing it), materially better distant-mic
and multi-speaker handling — exactly the Tejas conditions — fully on-device, and
therefore `LOCAL-FIRST`-compliant by construction.

Two hard costs:

1. **iOS 26 floor.** `app/ios/project.yml:5` targets 16.0.
2. **No custom-vocabulary API.** `AnticipyVocabulary` rides
   `SFSpeechRecognitionRequest.contextualStrings` at both request sites
   (`PhoneListener.swift:303`, `LocalTranscriber.swift:23`) and exists because she
   proposed buying a misspelling of her own product name. It is load-bearing enough to
   own gate leg 7. A migration that forfeits it silently is a regression.

**Therefore, when it happens, it is an additional arm and not a replacement:** a
transcriber behind `@available(iOS 26, *)`, chosen by a real routing policy — which
does not exist today, since `CaptureSourcePolicy.swift` is only an SF-Symbol badge
mapper — with the legacy path retained for the floor and for vocabulary.

**Free wins taken now, on the current API:** `taskHint` and `addsPunctuation` are set
nowhere in `app/ios/`. Both are set in this work.

**The gate for opening §8 (LAW 3).** After §5–§7 ship and one manual session is
recorded: shard rate below 25%, `speaker` populated on the large majority of owner
lines, and word capture still under 60%. If capture is still poor once attribution and
boundaries are fixed, the engine is the remaining cause and the migration is justified
on evidence. If capture recovers, it was never the engine.

## 9. Observability — built first

A per-session diagnostic journal, on device, viewable and exportable from Settings.
Records, per listening session:

- session start, and stop **with its cause** (owner stopped it, interruption, audio
  route change, authorization loss, unrecovered failure);
- every recognizer swap with its trigger: error, task limit, route change, or the 120s
  silence rotation (`PhoneListener.swift:278-280`);
- every flush with its trigger: `utteranceGap`, `maxHold` ceiling, or final result;
- every event POST with its outcome, including offline-queued and later flushed.

**Why first.** It is the instrument for §5–§7 and the answer to "some testing attempts
didn't complete". Without it every manual session is a guess, and this repo has
repeatedly found the *measurement* to be the defect — a `T`-versus-space timestamp
comparison that returned zero rows and manufactured a 50.9% miss rate; a Chrome process
leak that turned timeouts into fabricated engine failures. The stated rule is that a
harness able to report a failure the system did not commit is more dangerous than no
harness.

**Constraints.** Bounded size with oldest-first eviction — `backend/start.sh` exists
because a disposable log DB filled a volume and took production down, and that lesson
transfers. No transcript text in the journal beyond what the events already carry, and
no audio, ever. It must be readable by a person, not just an engineer.

## 10. Testing

- **Pure-Foundation unit tests** for §6 and §7. `TranscriptFlushPolicy` and
  `TranscriptCursor` are already pure Foundation precisely so they can be tested without
  a device (`TranscriptFlushPolicy.swift:10-12`), and `app/ios/Tests/` already holds
  `TranscriptFlushPolicyTests.swift`, `TranscriptCursorTests.swift` and a fuzz runner.
  New behaviour lands there, in that style.
- **Every test must be red before it is green.** Each defect in §4 has a live incident
  behind it; the test asserts the incident cannot recur, and its failure message names
  the incident. This matches the house convention where tests cite a dated live failure.
- **Regression floor:** `PYTHONPATH=. python3 -m pytest tests` (currently 1054 passing,
  with `tests/test_day_zero_oracle.py` deselected because it imports `playwright`, which
  is absent from this machine), `python3 overnight/tejas_gate.py` (8/8), and
  `node extension/tests/run_all.mjs` (55 suites) all stay green.
- **A new gate leg for the shard rate**, so a regression cannot return quietly. It is a
  deterministic measurement of an outcome, which LAW 1 permits explicitly under "gates
  and evals".
- **Replay** against the recorded 137-line call via `overnight/replay_call.py`, which is
  the only fixture in the repo holding both ground truth and what the system actually
  did.
- **Device checks** for §5 and §9, which cannot be simulated: enrollment completes and
  `hasOwnerProfile` flips; a subsequent session stamps `speaker`; the journal names a
  real stop cause.

## 11. Law compliance

- **LAW 1.** Nothing added decides meaning by pattern. The minimum-new-words floor
  gates *when to post*, not what words mean; the shard gate leg measures an outcome.
  Both are in the permitted categories (senses, gates).
- **LAW 2.** No tape. Nothing here is a string patch, so no expiry comment would be
  honest.
- **LAW 3.** Repo-green is not done. §5 and §9 require a real device session, and §8's
  gate is explicitly a live measurement. This spec states which claims are offline-only.
- **LAW 4.** This file is the record. The engine deferral, the §6 interaction with
  `score_links.py`, and the §8 opening criteria are written down rather than left in
  conversation.
- **LAW 5.** Strict order: senses (§5, §9), context (§6, §7), then and only then the
  engine (§8). No structural rule is introduced while 1–4 are unfixed.
- **LAW 6.** Self-reviewed below. An adversarial pass against these laws and the
  recorded failures happens before any of it is called done.

## 12. Decisions made without the owner, and why

Recorded per LAW 4 so they can be overruled knowingly rather than discovered later.

1. **Enrollment asks once, on evidence (three unnamed voices, no owner profile), not on
   a timer.** Consistent with the interruption budget. Alternative considered and
   rejected: prompting at launch until satisfied, which is nagging and against the
   product's whole character.
2. **A phone-authored continuation reuses `parent_line` rather than adding a field.**
   Same relationship, existing column, no migration. Cost: `proof/score_links.py` must
   be told, which §6 requires.
3. **`gap_before_ms` / `seq` / `boot_id` stay unwritten.** Nothing consumes them;
   writing dead fields is not a fix.
4. **The §8 opening criteria are numeric and fixed now**, before anyone is invested in
   the answer. Deciding the bar after seeing the result is how a bake-off gets talked
   into the wrong conclusion — this repo has a documented instance where an isolated
   model bake-off would have kept the worse option and called it rigour.

## 13. Spec self-review

- **Placeholders:** none. No TBD, no "handle edge cases", no unnamed mechanism.
- **Internal consistency:** §2 excludes the engine and §8 defers it with criteria — no
  contradiction. §6 writes `parent_line` while §2 forbids brain changes; reconciled
  explicitly in §6, since writing a column no consumer reads is not a behaviour change,
  and the one affected harness is named with an action.
- **Scope:** five root causes, four fixed, one deferred with a written gate. Single
  implementation plan, one surface (iOS) plus one harness note.
- **Ambiguity:** the open question from chat — how she asks for a voice sample without
  it feeling like a form — is now closed two ways: the existing `VoiceEnrollView`
  supplies the feel, and §5 fixes the timing to a specific, testable condition.
- **Correction folded in:** an earlier draft of this design assumed enrollment had to be
  built. It ships already (build 43, brief 09) and is merely unreachable. The premise
  was wrong and the scope is smaller for it.
