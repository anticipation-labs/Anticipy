# Why voice tests don't complete — verified against the tree, 2026-08-25

Follow-up to `research/2026-08-24-why-voice-tests-dont-complete.md`. That report
was read in full and its claims were **checked rather than believed**. Four of
them are now wrong. One thing it did not look at is, on the evidence below, the
larger half of the problem.

Read-only investigation. Nothing under `app/ios/**`, `brain/**` or `extension/**`
was modified. Branch `jose_anticipy_system`.

---

## The one-line answer

**The pipeline is dead at the delivery hop — phone to server — and has been for
29 hours. Nothing downstream of it has been exercised today at all.**

Measured live at `2026-08-25 09:00:01Z` against
`https://backend-production-61e0a.up.railway.app`:

| what | newest row | age at time of reading |
|---|---|---|
| `kind="transcript"` (his half) | `2026-08-24 03:34:24.685Z` — *"Let's go"* | **29 hr 26 min** |
| `kind="anticipy_says"` (her half) | `2026-08-24 16:10:20.009Z` | 16 hr 50 min |

The two clocks are the finding. The backend accepted writes for **12 hours 36
minutes after the last line arrived.** The server, its auth, its collections and
its writes were all healthy long after the ears went quiet, so the silence is
one-directional and its cause is upstream of the server. This is not an outage.

`proof/outcome_rate.py --hours 24` returns `lines: 0, outcome_rate: null`.
`--hours 48` returns the same 263 lines and the same 16 outcomes as yesterday's
run, because **not one new line has entered the window since.**

Consequence for everything else in this file and the last one: the 6.1% outcome
rate, the 45% `addressee="self"`, the 42% short lines, the meeting latch, the
parked-ask gauntlet, quiet hours — all of it describes lines that arrived
**before** the silence began. None of it is what is happening today. A guard can
only swallow a line that reached it.

---

## What the previous report got wrong

I checked its claims because I was told several claims in this project have not
survived inspection. Four did not.

### 1. "The phone is on build 76 and the version was never bumped" — STALE

`app/ios/Anticipy.xcodeproj/project.pbxproj:423` and `:502` now read
`CURRENT_PROJECT_VERSION = 79`. It was bumped by `fa4eb84f` — *"The phone finally
says what listening costs, and build 76 stops meaning seven things"* — which is
the commit that acted on that very finding, and then by two more. The report's
central recommendation ("bump it to 77 before archiving") was carried out.

**What is still true, and is the part that matters:** nothing in the repo can
say which build is *installed*. `overnight/is_it_live.py` has legs for the
backend and the extension and **no leg for iOS**, confirmed by running it. The
report was right that this is the gap; it is still open.

### 2. "The echo guard is a Law 1 violation, live in build 76 AND in HEAD" — CLOSED

This was the report's mechanism 2 and its loudest Law 1 flag: a 0.7 word-overlap
ratio, a 4-word floor, a 2-novel-word threshold and a 12-second window deciding
that two utterances *mean the same thing*, dropping the second with no trace.

**It is gone from HEAD.** `app/ios/Anticipy/Audio/TranscriptFlushPolicy.swift:91`
now reads:

```swift
func isEchoOfPrevious(_ line: String, previous: String,
                      lineageBrokeAt: Date?, wordsAppearedAt: Date) -> Bool {
    guard let brokeAt = lineageBrokeAt else { return false }
    let age = wordsAppearedAt.timeIntervalSince(brokeAt)
    guard age >= 0, age < utteranceGap else { return false }
    return Self.addsNoWord(line, beyond: previous)
}
```

Not one number decides meaning. `lineageBrokeAt` is a structural fact the
machine holds — the cursor lost its record of what it had already emitted,
because a decode window was replaced or a recognition task was swapped and its
held audio replayed. `addsNoWord` asks a transport question ("did the recognizer
hand back only words it had already handed us?") rather than a similarity one.
The commit is `c2bdef7b`, and its own comment cites the previous report by name
as the evidence that twelve seconds ate the tester's second attempt.

**Action for whoever owns the audit:** `research/2026-08-24-law1-audit.md` item
**#54** — *"the most upstream in the system"*, severity H — is closed and its
Class cell should move to the "Fixed since this audit" table. It is currently
still counted in the 61.

**Consequence for testing:** the previous report's advice *"never say the same
sentence twice in a row while testing"* is no longer needed on the phone side.
A tester repeating themselves inside one recognition task now delivers every
time. The server-side twin (`already_said`, 24 h, 0.6 overlap) is untouched and
still applies to her *replies* — see the test script.

### 3. "`speaker` is 0% because enrollment is unreachable" — WRONG ABOUT THE CODE

Recorded as *"Certain"* in `research/2026-08-24-engine-options.md:254`. The
enrollment screen is reachable, and was reachable in build 76 too:

- `app/ios/Anticipy/Views/SettingsView.swift:195-207` — a **"Teach me your voice"** button under a `Section("Your voice")`.
- Gated on `session.speakerTagger.available`, which is `embedder != nil` (`SpeakerTagger.swift:46`).
- `VoiceEmbedderFactory.make()` (`:152`) needs `SherpaOnnx` **and** a bundled `speaker-embedding.onnx`. Both ship: `app/ios/project.yml:11-12` and `:205-206` wire the package, `project.pbxproj:52,121,258,289,560-574` carry it, and `app/ios/Anticipy/Resources/speaker-embedding.onnx` exists — including inside the committed archive at `app/ios/build/Anticipy.xcarchive/…/Anticipy.app/speaker-embedding.onnx`.
- `git show 6e277694:…/SettingsView.swift | grep -c showVoiceEnroll` → **3**. Present in build 76.

`research/2026-08-24-cold-stranger-walkthrough.md:170` has it right and the
engine-options file has it wrong: the screen is **undiscoverable**, not
unreachable. Nothing invites anyone to it — no onboarding step, no prompt, no
card. The 0% is the ordinary consequence of nobody having walked to a screen
nobody mentions.

That is a five-minute fix for a tester (the script below tells them exactly
where to tap) and it does not need `EnrollmentInvite.swift` to be built first.

### 4. "The meeting latch silences the line" — already corrected, repeated anyway

`research/2026-08-25-outcome-rate.md` had already established that the latch
stamps `decision="act"` and delays the **text**, not the card. The previous
report still lists it among the mechanisms that produce silence. Reconfirmed
here: `brain/anticipy_core.py`'s `if fresh and in_meeting` appends to
`_meeting_held` after the decision is stamped. A latched line is an **outcome**,
not a silence.

---

## What the previous report did not look at, and it is Law 3

**Production is serving a backend built before 2026-08-22.**

`overnight/is_it_live.py`, run today:

```
[FAIL] the served extension's version matches source     served 0.8.4, source 0.11.0
[FAIL] the served extension IS the source, byte for byte differs: served 251359, source 362988
```

That is not merely a stale extension. The zip is a **static file committed into
`backend/pb_public/`** and served by the deployed PocketBase, so its version
dates the deployment that carried it up. Walking the commits that touched
`backend/pb_public/anticipy-claude-version-extension.zip`:

| committed version | date | commit subject |
|---|---|---|
| **0.11.0** | 2026-08-22 | Commit the whole working tree: iOS build 75, extension 0.11.0, and the testing pass |
| 0.8.3 | 2026-08-17 | Sync the build stamp and the version assertions to 0.8.3 |
| 0.8.2 | 2026-08-17 | Extension 0.8.2 |

**`0.8.4` was never committed at any point.** It is not in the history of that
file. So the running backend was not built from any commit — it was built by a
`railway up` uploading a **local working tree** sitting at 0.8.4, some time
around 2026-08-17. (This matches the recorded deploy mechanism: a manual upload,
no git pipeline, so pushing deploys nothing.)

Eight commits have touched `backend/pb_hooks` or `backend/pb_migrations` since,
including two from the last two days (`0d2ee640`, `afd4380a`). **`guard.pb.js`
is the code that admits the phone's POST.** The ingest half of the pipeline —
the exact hop that is dead — is running code from a working tree nobody can
name, roughly eight days stale.

This does not on its own explain the 29-hour silence: the same backend was
accepting `transcript` rows from this same phone as recently as 2026-08-24
03:34Z, so it was admitting POSTs then. But it does mean that **whatever is
found on the phone and fixed, the line it produces will meet 08-17-era ingest
code**, and no repo-green measurement describes what production will do with it.
Law 3, on the one hop that is currently broken.

---

## Localising it further, without the phone

Zero rows at the server narrows the fault to the phone. Two shapes remain, and
they are distinguishable from the diagnostics screen alone — which is the whole
point of the script in `docs/MANUAL-VOICE-TEST.md`.

**Shape A — never captured.** Recognizer deaf, mic taken by a call, app
jetsammed, listening quietly off. Signature on `Settings → Listening → Find out
what listening actually did`: **`Words sent` is 0 or has stopped rising**, and
`Longest stretch hearing nothing` is enormous. `ListenTally.swift:242` increments
`wordsFlushed` from `.flushed` events, so this counter rises only when audio
actually became a sentence.

**Shape B — captured and never delivered.** Signature: **`Words sent` is large**
while the server holds nothing. Then two sub-cases, and the diagnostics screen
separates them:

- `Lines that did not reach the server` **present and rising** → posts are being attempted and refused. `ListenTally.swift:295` counts `.posted(ok: false)`. The line is on the disk queue and the home screen says *"N things you said are waiting for a signal."*
- `Lines that did not reach the server` **absent** (`postsFailed == 0`) while `Words sent` is large → posts are not being *attempted* at all. See the correction immediately below before concluding anything from this.

### Correction to the previous report's mechanism 4 — it is far narrower than claimed

The previous report described a signed-out phone that "keeps transcribing
beautifully" while every line is rendered twice and dropped, with no queue, no
banner and no journal trace. The early return is real —
`AnticipyApp.swift`, in `heard(...)`:

```swift
sessionLines.append(SessionLine(text: line))
transcript.append(TranscriptLine(id: "local-\(UUID().uuidString)", …))
guard !accountID.isEmpty else { return }   // before the push AND before the journal
```

It returns before both the `backend.pushEvent` call and the
`ListenJournal.shared.record(.posted(...))` on either branch, so a line lost
here genuinely leaves no trace of any kind. **But the state it guards against
cannot persist**, and the previous report did not check that:

- `signOut()` calls **`listener.stop()`** — and its own comment records that this was the fix for exactly the scenario the previous report describes: *"the AVAudioEngine tap stayed installed and the room kept being transcribed behind the sign-in door."*
- `git show 6e277694:app/ios/Anticipy/AnticipyApp.swift` — **build 76 already has it.** So the fix predates the build the previous report was written about.
- `isSignedIn` is `!accountID.isEmpty && !authToken.isEmpty` (`:1098`), and `AnticipyApp.swift:27` swaps the entire window to `AuthView` the instant it goes false. A signed-out tester is looking at the sign-in screen, not at a healthy home screen.

So `guard !accountID.isEmpty` is **belt-and-braces for a race** — a line already
in flight when the credentials clear — not a sustained failure mode. It can eat
one or two lines at the moment of a forced sign-out. It cannot eat a day.

**This is the fifth claim in that report that did not survive checking, and it
matters because it is the one a tester would most easily mistake for the
answer.** `postsFailed == 0` with `Words sent` high therefore points at
something else — most likely that the app was restarted and the tally is
reading a fresh journal — and the tester should be sent to `Times listening
started` and `Longest stretch hearing nothing` rather than to the sign-in
screen.

**What still separates the two delivery failures**, which is the useful half:
`Lines that did not reach the server` **present and rising** means posts are
being refused and the line is safe on the disk queue, with the home screen
saying *"N things you said are waiting for a signal."* Its absence means no
post was ever refused. Neither number can be read without `Words sent` beside
it, and that pair is legible in about four seconds from a screen that already
ships.

---

## Law 1: what is still deciding meaning on this exact path

The audit (`research/2026-08-24-law1-audit.md`, 61 violations, 30 severity H) is
the standing record and is not restated here. What follows is only the subset
that fires on a **manual voice test**, verified present in the tree today.

### On the phone

**`answerThatEndsTheErrand` — `app/ios/Anticipy/AnticipyApp.swift:1490`, site `:1638`. Audit #55, severity H. STILL A WORD LIST.**

```swift
let whole: Set<String> = ["no", "nope", "stop", "cancel", "skip", "skip it",
                          "never mind", "nevermind", "forget it", "drop it",
                          "leave it", "don't bother", …]
let declines = ["never mind", "forget it", "don't need", "not needed",
                "drop it", "skip it", "call it off", "cancel it", …]
let handled  = ["handled it", "i handled", "did it myself", "took care of it",
                "already did", "already done", "already sent", "sorted it", …]
```

Three phrase lists on the **phone** decide that the owner's spoken answer means
*"call this errand off"*. On a hit the app writes the job `cancelled` and
**quotes his own sentence back to him as proof he called it off**, and the brain
never sees the line.

This is the most test-relevant violation in the system, because it fires on
exactly the step a manual test must exercise: answering after a card has been
held. The code has clearly been fought over — the comment records four live
incidents where substring matching killed errands the owner still wanted
(*"leave it with the concierge"*, *"drop it off at reception after 5"*, *"stop
it from auto-renewing"*, and a negated *"it's not already booked yet, go
ahead"* filed as proof he had done it himself), and the fix was to anchor the
phrase at the front of a clause. **Anchoring a word list is still a word list.**
It carries no `TAPE:` comment and no gate leg tracks its removal — Law 2.

### On the server, and this is the part that inverts the test

The owner's brief for this work is that recognition is an LLM harness, not
keyword matching. On the negative cases — the ones a good test *must* include —
that is currently not true. Three regexes end the pipeline **before any model is
called**:

| audit # | construct | file | what it decides | sev |
|---|---|---|---|---|
| #3 | `_NON_ACTION_CONTENT_RE` | `brain/anticipy_core.py:240`, site `:1357` | *"he labelled this a hypothetical/quote/example"* → returns `ignore`, **never calls the model** | M |
| #4 | `looks_like_dictation` (`DICTATION_MIN_WORDS = 40` + `_DICTATION_FILLERS_RE:220` + `_DICTATION_INSTRUCT_RE:226`) | `:344`, site `:1358` | *who he was talking to* — **overrides the model's `addressee`** | **H** |
| #7 | `_MEMORY_ONLY_RE` / `explicitly_for_memory` | `:253`, `:363`, site `:1423` | *"a fact for later, not a task"* → `ignore` | M |

Plus `len(line.split()) < 2` at `:1436` (audit #8) and `shard_too_thin`
(`:651`, site `:1674`, audit #20 — has a `TAPE:` comment that names no leg, so
nothing tracks its removal).

**So: a tester who says "that's just a hypothetical, don't act on it" and gets
silence has not tested the harness. They have tested `_NON_ACTION_CONTENT_RE`.**
A tester who dictates forty words of instruction-prose at another machine and
gets silence has tested a two-hit regex count, not the model's judgement of
audience. The script below marks every such case explicitly, so a pass is not
read as evidence about something it never touched.

`looks_like_dictation` is the worst of the three because it does not merely
decline — it **overrides a live model's `addressee` verdict**. That is Law 1's
central prohibition, at severity H, on the intake router every voice line
crosses.

---

## Reconciled against three findings that landed the same night

Checked after this file's first draft, and recorded so nobody re-checks them.

1. **`AnticipyVocabulary` works** (`research/2026-08-25-claim-audit.md`, `501c1184`). The "SpeechTranscriber silently ignores `contextualStrings`" claim is a true fact about Apple's *newer* API and a wrong description of this codebase — nothing here touches `SpeechTranscriber`, `SpeechAnalyzer` or `AnalysisContext`, and both shipping sites use `SFSpeechAudioBufferRecognitionRequest`, where contextual strings do work. **Neither document here made a vocabulary claim in either direction**, so nothing needed correcting; noted so the next reader does not go looking.
2. **The word-error-rate rig exists and has never been run** (`research/2026-08-25-transcription-quality.md`, `c1cf82b2`). `proof/engine_or_audio.py` is 1,400 lines with a 370-word ground-truth script, a recording protocol, pre-registered thresholds and 57 tests; `proof/runs/` does not exist, because the ~40-line scratch recorder that writes the mic tap to a WAV was never written. Confirmed by inspection. The test script now points a tester at that gap in Part 2 instead of inviting them to judge accuracy by ear, and asks for the one thing that *is* useful without the rig: the exact sentence said next to the exact row returned.
3. **The extension version number is not evidence.** Production serves 0.8.4 against source 0.11.0 — the finding in the section above — and separately the *committed* zip has been found declaring 0.11.0 while the `agent_loop.js` inside it was older. So the Law 3 conclusion above stands on the served version being one that was **never committed at all**, which no manifest edit can explain, rather than on any single version string. The test script's Appendix C now says a version number does not settle it.

## Corrections owed to other files

1. `research/2026-08-24-law1-audit.md` — item **#54** is closed by `c2bdef7b`; move its Class cell and add a row to "Fixed since this audit". The counts table is pinned by `tape_gate.py` leg 4 and must not be edited; the running-correction section is the place.
2. `research/2026-08-24-engine-options.md:254` — *"enrollment unreachable"*, confidence *"Certain"*, is wrong about the code. The screen is reachable from `Settings → Your voice`. The correct cause is that nothing invites anyone to it.
3. `research/2026-08-24-why-voice-tests-dont-complete.md` — mechanism 2 is fixed; the build-76 framing is superseded by build 79; step 4c ("bump to 77") is done.
4. `overnight/is_it_live.py` — still has no iOS leg, and now demonstrably needed one: it is green on "your Chrome is running the current code" and cannot say anything at all about the phone, which is the only surface that failed.

## Still open, unchanged from yesterday

- `brain/` should persist `Decision.reason` onto the transcript row. One column splits six of the seven indistinguishable silences apart. It is the single highest-value change for making any future manual test readable.
- 23% of arriving lines (61 of 263 at 48 h) carry an **empty `addressee`** — triage returning no classification at all for nearly a quarter of everything heard.
- Production's deploy is stale on the backend service (above). Verify with an `is_it_live.py`-style check after any `railway up`; it reports success while failing.
