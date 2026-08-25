# Why manual voice tests don't complete

Root-cause pass, 2026-08-24. Branch `jose_anticipy_system`.
Read-only investigation: no file in `app/ios/**` or `brain/**` was modified.

> **Reading the line numbers.** This report is about the code **on the phone**,
> which is not the code in your working tree. Unless a citation says "HEAD" or
> names a file that does not exist in build 76, every `file:line` below is
> against **commit `6e277694`** — recover it with
> `git show 6e277694:app/ios/Anticipy/Audio/PhoneListener.swift`. HEAD's line
> numbers for the same code are hundreds of lines further down (`PhoneListener`
> grew 544 lines between the two). Citations to `ListenWatchdogPolicy.swift`,
> `ListenResumePolicy.swift`, `ListenTally.swift`, `ListenJournal.swift`,
> `ListeningDiagnosticsView.swift` and `ListenControlPolicy.swift` are against
> the working tree, because those files exist **only** there.

---

## The one-line answer

**This is already diagnosed and the fix is a deploy plus a device build** — and
the live measurement below narrows it further than that.

The phone is on build 76. Build 76 is commit `6e277694` (2026-08-23 20:48).
Every one of the five capture fixes landed on 2026-08-24, *after* that commit,
and **the build number was never bumped past 76** — six subsequent commits
touched `project.pbxproj` and left `CURRENT_PROJECT_VERSION = 76` in place.

The rest of this document exists because three things are *not* covered by that
answer:

- **Production has received ZERO transcript lines in the last 24 hours** (measured, below). Whatever the manual tests did today, the audio never reached the server. **That rules out every server-side mechanism as the cause of today's failures** and puts the fault on the phone, at or before delivery.
- **Mechanism 2 below (echo suppression) is live in build 76 AND in HEAD.** It is not fixed, it is not on anyone's board, and it produces exactly the words the owner used: *"transcription is inconsistent."* A tester who repeats a test phrase gets one line for two utterances, silently.
- **A tester on build 76 cannot tell "she didn't hear me" from "she heard me and said nothing"** for the capture half. See "The unfalsifiability problem".

---

## The live measurement — start here, it reorders everything

Run read-only against production at 2026-08-25 04:22 UTC
(`set -a; . ./.env.local; set +a` then `python3 proof/capture_day.py --hours N`):

| window | transcript lines that arrived |
|---|---|
| last 6h | **0** |
| last 12h | **0** |
| last 24h | **0** |
| last 26h | 3 |
| last 30h | 140 |

`capture_day.py`'s own verdict on the 6-hour window, unedited:

```
NOTHING ARRIVED. That is a finding, not an empty report:
it is what a suspended app and a deaf recognizer both look
like from here. Read the phone's own journal next.
```

**Delivery stopped roughly 25 hours ago.** The newest transcript row anywhere in
production is `2026-08-24 03:34:24Z`. There was a burst of ~137 lines in the
26–30h window, three trailing lines, and then **nothing for a full day.**

Three facts make this conclusive rather than suggestive:

1. **The server is alive.** Jobs and `anticipy_says` rows continued through `2026-08-24 16:10Z` — twelve hours *after* the last transcript arrived. This is not an outage; it is one half of the pipeline going quiet.
2. **The last line arrived 14 minutes before build 76 was committed** (`6e277694`, 2026-08-24 03:48:35Z). The correlation is not proof of causation — the phone could equally have been off — but it is consistent with build 76 going onto the phone at that moment and **never successfully delivering a single line since.**
3. **The 48-hour blended report shows `longest gap between lines 50071s`** — 13.9 hours *inside* the measured window, on top of the 24-hour silence after it. Dead stretches of half a day are already the normal shape of this data.

**Consequence for the ranking:** the elaborate server-side silence machinery
(quiet hours, the uninvited cap, echo suppression, the meeting latch, the
self-talk gate) is real, is documented below, and **is not what happened today.**
Those mechanisms can only swallow a line that arrived. None arrived.

*Caveat, stated honestly:* zero lines is also what a phone that was switched off
all day looks like. The one thing that separates "nobody tested" from "testing
happened and nothing was captured" is the tester's own account — and the owner
reports that manual testing is underway. If that is right, this is the finding.

---

## The bet, and the one observation that settles it

**I would bet on mechanism 1: the recognizer went deaf and nothing rotated it.**

Why that one over the others:

- It is the only mechanism that needs **no trigger at all** — no phone call, no network failure, no sign-out, no memory pressure. It arrives on its own, on any session that outlives one Apple task-duration limit, which is every session anyone would call a real test.
- It is the only one where **the app cannot recover itself**. Verified exhaustively: the 4-second watchdog is inert on this state, `resumeListeningIfWanted()` is a no-op, and there is no other `Timer`, `asyncAfter`, or caller of `listener.start()` in build 76. Only a finger on the toggle fixes it — which matches a 24-hour flatline far better than any mechanism that self-heals in seconds.
- It **matches the measured shape**: a burst of ~137 lines, three trailing lines, then nothing for a day. That is a session that worked, went deaf mid-flight, and was never restarted — not a network problem (which would queue and drain) and not a sign-out (which would 403 and queue).
- It is **invisible in build 76 by construction**, which explains why this has been reported as "the test didn't complete" rather than as a specific bug, twice.

Mechanism 3 (the phone call) is the close second and would look nearly identical
from the server; the two are separated only on the phone. Mechanism 2 (echo
suppression) is what I would bet on for the *"transcription is inconsistent"*
half of the complaint, which is a different sentence in the same report and has
a different, unfixed cause.

**The single observation that would confirm it:** pick up the test phone while
it still claims to be listening, **say one fresh sentence, and watch the row
list under the waveform for fifteen seconds.**

- **No new row, waveform still animating, and no "waiting for a signal" count** → the recognizer is deaf with the microphone alive and the network fine. That is mechanism 1, and nothing else produces that exact combination.
- Then **toggle Listen off and on and say it again.** If the row appears immediately, the diagnosis is complete: capture is dead until a human intervenes, which is precisely the defect `ListenWatchdogPolicy` fixes and which is not on the phone.

That observation costs thirty seconds, requires no build, no deploy and no
credentials, and it is the only evidence build 76 can still produce — the
journal that would have answered it after the fact does not exist in that build.

---

## Which build is on the phone — the evidence

`app/ios/Anticipy.xcodeproj/project.pbxproj:415` and `:494` — `CURRENT_PROJECT_VERSION = 76`.

Introduced by:

```
6e277694  2026-08-23 20:48:35 -0700  harness fixes 1-5 of 6: exemplars, compute, mouth guard, shard tape, iOS ears
```

Commits after `6e277694` that touched `project.pbxproj` **without** bumping the
version (each still reports 76):

| commit | date | subject |
|---|---|---|
| `9fcdf5ae` | 08-24 | Nine audit findings: seven fixed, two proved already fixed or misdiagnosed |
| `aa753be7` | 08-24 | The app target can see the journal, and the journal cannot leak speech |
| `447da8f5` | 08-24 | A day of listening, folded out of the journal it already wrote |
| `6c496f02` | 08-24 | Three comments stop lying: the journal really is exportable from Settings |
| `2c4e9ec8` | 08-24 | The watchdog stops deciding from words it can no longer read |
| `a21bda71` | 08-24 | A call no longer ends the day, and she stops saying she is listening |

Plus `fb37ce4a` and `074281d8` on the same day.

**What build 76 does not contain.** `git ls-tree -r 6e277694` over
`app/ios/Anticipy/Audio` and `Views` returns **none** of:

```
ListenJournal.swift      ListenTally.swift          ListeningDiagnosticsView.swift
ListenWatchdogPolicy.swift   ListenResumePolicy.swift   ListenControlPolicy.swift
```

`git diff --stat 6e277694 HEAD` over the capture tree: **1777 insertions, 63
deletions across 10 files.** The entire diagnostic instrument — the thing built
yesterday specifically to answer "why didn't the test complete" — post-dates the
build that is on the phone.

**Corollary that matters for the ranking:** of the five known defects, only
**#1, #2 and #3 can bite a build-76 tester.** Defects #4 (journal eviction) and
#5 (58 minutes of silence misreported) are defects *in the instrument*, and the
instrument does not exist in build 76. They cannot be what happened. They become
live the moment you deploy, which is why they were worth fixing first.

**Build 76 is also not a unique identifier.** Seven distinct source trees call
themselves build 76. If the phone was loaded over the cable rather than through
TestFlight (TestFlight rejects a duplicate build number for one marketing
version, so a TestFlight 76 is necessarily the 08-23 one), nobody can say from
the number alone which of the seven is installed. The newest archive committed
under `app/ios/build/` is `Anticipy.xcarchive` at `CFBundleVersion 64`, created
2026-08-18 — there is no build-76 artifact in the repo to check against.

---

## Ranked mechanisms

### 1. The recognizer goes deaf mid-session and nothing rotates it — MOST LIKELY

**Evidence.** In build 76, `app/ios/Anticipy/Audio/PhoneListener.swift`:

- `:278` the rotation leg: `if self.pendingTail.isEmpty, self.partial.isEmpty, now.timeIntervalSince(self.requestBornAt) > 120`
- `:340` `self.partial = result.bestTranscription.formattedString` — assigned on **every** recognizer result
- `:310` and `:497` — the **only** two clears, at the start of a recognition task and in `stop()`. In build 76 `flushTail()` (`:375-386`) does **not** clear it.

So after the first utterance of a task, `partial` is never empty again for the
life of that task, and the leg at `:278` can never fire. This is confirmed
independently by the fix's own header, `ListenWatchdogPolicy.swift:5-14`.

Every other watchdog leg passes while the recognizer is deaf:

- `:267` `!engine.isRunning` — engine is fine
- `:268` `task == nil` — the task object still exists, it just stopped emitting
- `:270` `lastBufferAt > 6` — the tap at `:180-206` is wired to the **engine**, not the recognizer, so buffers keep arriving and keep the beacon fresh (`:203-205`)
- `:273` the mid-utterance leg requires `!pendingTail.isEmpty` — the rarer state; after a flush, pending is empty

And `:283` `suspended = !engine.isRunning` → **false**, so `ContentView.swift:977`
keeps drawing `WaveBars()` and `:984` never shows the interrupted banner.

**Why the task goes deaf at all.** `:304-306` sets
`requiresOnDeviceRecognition = true`. The 120-second rotation at `:279` exists
precisely to retire a task before Apple's task-duration limit lands. With the
rotation dead, the task runs indefinitely and hits that limit. Three outcomes:
it finalises (`:353` → recovers), it errors (`:364` → recovers), or **it goes
quiet with no `isFinal` and no error — and nothing in build 76 can see that.**

**Nothing in build 76 recovers from this except a human.** Exhaustively, the
only three things that can restart capture are:

- the 4-second watchdog `Timer` (`PhoneListener.swift:265`) — every leg passes, so it does nothing;
- `resumeListeningIfWanted()` (`AnticipyApp.swift:1081`) — a no-op while `isListening` is true, so **even closing and reopening the app does not fix it**;
- the toggle at `ContentView.swift:942-944` — a finger.

There is no other `Timer`, no other `asyncAfter`, and no other caller of
`listener.start()` in the build. Once the recognizer goes deaf, the phone stays
deaf until somebody reaches over and taps the switch twice.

**Scenario.** Tester taps Listen. Says "testing one two three." Line appears.
Keeps testing for a few minutes. Somewhere past the task-duration limit the
recognizer stops emitting. The waveform keeps animating, the button still says
listening, the briefing still says "I'm listening." Every sentence from that
moment is gone. The tester keeps talking to a phone that stopped hearing,
backgrounds the app and reopens it to check (which does nothing), then reports
that the test didn't complete.

**How to confirm.** On build 76: speak a fresh, distinct sentence and watch the
session list under the waveform (`ContentView.swift:1005-1010`). If no new row
appears within ~10 seconds while the waveform is animating, the recognizer is
deaf. Restarting listening by hand will fix it — which is itself the tell.
On a deployed build: `ListeningDiagnosticsView` → "Longest stretch hearing
nothing", and the `swapsByCause` rows under "Why it stopped or restarted".

**Fixed but undeployed?** YES. `ListenWatchdogPolicy.swift` replaces the leg
with a pure-time decision and `run_watchdog_policy_tests.sh` fails the build if
`PhoneListener` reads the transcript string again. Not on the phone.

---

### 2. The tester repeats the test phrase and the second one is silently dropped — NOT FIXED, LIVE IN HEAD

**Evidence.** `PhoneListener.swift` (build 76 `:400-406`, HEAD equivalent) calls
`TranscriptFlushPolicy.isEchoOfPrevious` and **returns without delivering**:

`app/ios/Anticipy/Audio/TranscriptFlushPolicy.swift`:
- `:45` `let echoWindow: TimeInterval = 12`
- `:64` `if apart > window { return false }`
- `:71` `if new.count < 4 || old.count < 4 { return false }`
- `:77` `if novel > 2 { return false }`
- `:78` `return Double(shared) / Double(new.count) >= 0.7`

Four or more words, at least 70% word overlap with the previous line, at most
two novel words, within 12 seconds → **dropped, with no UI trace whatsoever**.
No row, no dotted circle, no counter. The line never reaches `onLine`.

**Scenario — this is the manual-testing scenario.** A tester does not say
different things. A tester says *"Testing, can you hear me now"*, waits, says it
again, waits, says it again. Utterance 1 delivers. Utterance 2, six seconds
later: 100% shared words, 0 novel → dropped. The tester sees one line for two
identical utterances and reports **"transcription is inconsistent."** That is
the owner's exact phrasing.

The guard was written for a real defect (a ceiling flush and a banked window
handing over one sentence twice in slightly different words, observed live
2026-08-17). Its comment at `:58-60` says it is "deliberately conservative"
because "real repetition is short and identical" — that reasoning holds for
conversational speech and fails completely for deliberate repeated testing,
which is the only kind of speech a manual test contains.

**How to confirm.** Say a ≥4-word phrase. Wait 3 seconds. Say it verbatim again.
Wait 15 seconds. Say it verbatim a third time. **Two lines appear, not three**,
and the missing one is the middle one. That is a complete, unambiguous
confirmation and it takes 30 seconds.

**Fixed but undeployed?** NO — **this one is not fixed anywhere.** It is in
build 76 and it is in HEAD. It is not on the board.

> **LAW 1 flag.** `isEchoOfPrevious` is a word-overlap ratio (0.7), a word-count
> floor (4), a novelty threshold (2) and a time window (12s) deciding that two
> utterances *mean the same thing*. Deciding "he said that already" is a meaning
> judgement, not audio plumbing. The senses carve-out covers transport,
> timestamps and format; it does not obviously cover semantic identity. This is
> at minimum a boundary case with a now-measurable harm, and it carries no
> `TAPE:` comment and no gate leg (LAW 2). Flagging rather than fixing, per the
> instruction to flag over complete. The narrow, law-abiding alternative if you
> want it today: dedup on the *cursor's* record of which characters were already
> emitted from a given recognition hypothesis — a structural fact — rather than
> on how similar two finished sentences look.

---

### 3. A phone call ends the session permanently, after minting a task every 4 seconds

**Evidence.** Build 76 `PhoneListener.swift`:

- `:221-230` the interruption observer sets `suspended = true` on `.began`. It does **not** touch `isListening`.
- `:479` is the only assignment of `isListening = false` in the file, inside `stop()`.
- `AnticipyApp.swift:1080-1082` — `resumeListeningIfWanted() { if keepListening, !listener.isListening { listener.start() } }`. `isListening` is still `true` throughout the call, so the guard is false in the one state the function exists for. **Total no-op.**
- Called from `ContentView.swift:721-724` (`onAppear`) and `:725-733` (`scenePhase == .active`) — both no-ops.

Compounding, for the whole length of the call: `:267` sees `!engine.isRunning` →
`recoverAudio()` (`:251-260`) → `configureAndStartEngine()` → `:183-186` the
input format is 0 Hz while the call owns the session, so it sets `suspended` and
returns → `:259` `swapRecognition(flushPending: true)` → `:458` `startRecognition()`
mints a fresh `SFSpeechAudioBufferRecognitionRequest` and task. Every 4 seconds,
none of which can hear anything. A ten-minute call mints ~150 recognition tasks.

`ListenResumePolicy.swift:9-14` adds the part that makes it permanent: iOS
suspends the app once audio stops flowing — `UIBackgroundModes: audio`
(`app/ios/project.yml:179-181`) buys execution only *while* audio is flowing —
so the process is not running to receive the `.ended` notification, and on
return the only route back to listening was the owner toggling the switch by
hand, with the briefing on the same screen still saying "I'm listening."

**Scenario.** Tester is mid-test, takes a call, comes back, keeps talking.
Nothing from that point on is captured. The home screen says listening.

**How to confirm.** The banner at `ContentView.swift:984` ("Mic interrupted,
taking it back…") stuck on, or — more likely — listening simply producing
nothing after a call while the UI looks healthy. On a deployed build the
diagnostics screen answers it directly: "Listening right now" is the first row
on the screen (`ListeningDiagnosticsView.swift:36`) precisely because "you
turned it off" and "a call took the microphone and nothing brought it back"
produce identical silence.

**Fixed but undeployed?** YES — `ListenResumePolicy.swift` splits the two facts
(`isListening` = the owner wants it; `suspended` = the mic is not ours) and
answers `.retakeMicrophone` to the state the old guard answered "nothing" to.

> **Deploy hazard.** Do not ship the interruption fix without the *uncommitted*
> `app/ios/Anticipy/Audio/ListenControlPolicy.swift` beside it. Its header
> documents a regression the interruption fix itself opened: the label became
> honest ("Waiting for the microphone") while the tap action stayed keyed on
> `isListening`, so an owner who opens the app during a call and taps the big
> control **turns listening off until they toggle it back by hand** — the exact
> ending the interruption work set out to close, through a door the same commit
> installed. Both files are in the working tree and being edited by another
> agent right now.

---

### 4. A line is captured, shown on screen, and never sent — and never even queued

**Evidence.** `AnticipyApp.swift` build 76, in `heard(...)`:

- `:294` `sessionLines.append(...)` — the row the tester watches
- `:299-300` `transcript.append(TranscriptLine(id: "local-\(UUID())", ...))` — the feed row
- `:305` `guard !accountID.isEmpty else { return }` — **returns before the push and before the queue**
- `:306-318` push, and on throw, queue to disk

If `accountID` is empty (a forced sign-out — an expired token 401s and calls
`signOut`), the line is rendered twice on screen and then dropped on the floor.
It is **not** added to `unsentLines`, so `pendingCount` stays 0 and the
"N things you said are waiting for a signal" banner
(`ContentView.swift:991-1001`) never appears. The row keeps its dotted circle
(`ContentView.swift:1655`) forever, which reads as "still sending."

Separately, `flushUnsent()` at `:332`: `guard line.account == accountID else { continue }`
— a queued line belonging to a different account is discarded silently with
`continue`, not requeued and not counted.

**Scenario.** Tester's session token expires mid-test. The app keeps
transcribing beautifully. Every line appears on screen. Nothing reaches the
server. Nothing says so.

**How to confirm.** The dotted circle vs. filled checkmark on the session rows
(`ContentView.swift:1655-1659`) — `line.received` flips only when the server
echoes the line back. A row that stays dotted for more than ~5 seconds was not
received. Cross-check against the server with `proof/capture_day.py`.

**Fixed but undeployed?** Not addressed by any of the five. The delivery *failure*
path is well built; this is the *no-owner* path, which returns early. Worth a
follow-up, but it needs a signed-out tester to fire, so it is not my bet.

---

### 5. The app is jetsammed while backgrounded and nothing restarts it

**Evidence.** `keepListening` is `@AppStorage` (`AnticipyApp.swift:152`) so the
*intent* survives, but nothing relaunches the process. `SessionLine`
(`AnticipyApp.swift:1697-1702`) has no persistence — the moment the app
relaunches, every row the tester was using as evidence is gone. On reopen,
`ContentView.swift:721-724` → `resumeListeningIfWanted()` → `isListening` is
false on a fresh process → `.start` → the app looks perfectly healthy **the
instant the tester looks at it**, with no trace that it was dead for an hour.

**Fixed but undeployed?** The cause is iOS; the *visibility* is fixed and
undeployed. `ListenTally` gives "Times listening started" and "Longest stretch
hearing nothing" (`ListeningDiagnosticsView.swift:47-51`), which is the only
thing that makes a jetsam gap legible after the fact.

---

### 6. A pause outlives the app

**Evidence.** `SettingsView.swift` build 76 `:19` `@AppStorage("listeningPauseUntil")`,
set at `:609`, cleared at `:616`/`:628`/`:643`. The clearing at `:642-643` is a
`Task` — if the app is killed during the pause it never runs, and this is
**deliberate**: the copy at `:85` says "If iPhone closes the app before
\(clock(ends)), I'll stay off until you start me again."

**Scenario.** Someone paused for an hour yesterday, the app was killed, and the
phone has been silently not-listening since. The home screen shows only "Listen
with phone" — correct, but easy to walk past.

**Not a defect** — it is honest and it is surfaced in Settings. Listed because
it is a real "the test didn't complete" cause a tester can hit, and the checklist
should rule it out in five seconds.

---

### 7. Server-side: delivered, processed, and deliberately silent

**Not the cause of today's failures — no line arrived to be silenced.** Recorded
because it is what a tester will hit *the moment delivery is restored*, and
because several of these fire hardest on exactly the input a manual test
produces.

**Measured in production, last 48h: 264 of 282 delivered lines (93.6%) ended as
`decision="ignore"` with an empty goal — they produced nothing visible at all.**
10 more produced only "Looking into it". 8 produced an action. The app renders
an `ignore` with an empty goal as `EmptyView()`
(`app/ios/Anticipy/Views/ConversationCard.swift:121-122`) — a blank card face.
**The overall "a delivered line produced something visible" rate is 6.4%.**

*(Line numbers in `brain/anticipy_core.py` are shifting — another agent is
editing it right now. Function names are the durable anchor.)*

**Fires on essentially every short manual test:**

- **The self-talk gate** — `anticipy_core.py:2331-2333`: `if decision.addressee == "self" and not explicit: handled = None`. A `print` and nothing else. **128 of 282 production lines (45%) carry `addressee="self"`.** A tester alone in a quiet room is, by definition, talking to themselves.
- **`shard_too_thin`** (def `anticipy_core.py:636`, called `:1680`) — ≤4 words with an inventive goal → dropped. **42% of real production lines are ≤4 words.** Its escape hatch (`decision.continues >= 1`) **can never fire in production** — see below.
- The fragment gate (`:1405-1408`, <2 words), the ambient catch-all (`:2024-2026`), and the "second key" owes-nobody gate (`:1592-1606`).

**Fires when a tester repeats a phrase — the manual-test signature:**

- **`already_raised` / `already_said`** (`worker.py:1846-1893`, `:1902-1937`, reached at `:2311`) — a 24-hour window with 0.6 goal-token overlap, read from the durable `anticipy_says` record so a redeploy does not reset it. **Say the test phrase a second time within 24 hours and she is silent.** This is the server-side twin of mechanism 2 and, together with it, the most likely reason a *second* test attempt looks broken.
- **`is_echo_of_her`** (`worker.py:1653-1690`) — reading her own SMS or feed text back out loud, a documented testing habit, is discarded before triage.

**Fires at an odd hour, or on a brisk test:**

- **Quiet hours 22:00–08:00** (`worker.py:53`, applied `:568-571`, `:2143-2148`, `:2267-2273`). **This is correctly timezone-aware** — `CLOCK_TZ` comes from the owner's profile (`worker.py:3078-3082`, refreshed `:3193-3199`), *not* UTC. **The memory note about `is_the_brain_live`'s quiet-hours leg false-alarming 10h/day is stale — that is fixed too** (`is_the_brain_live.py:180-190` converts to the owner zone before comparing).
- **The parked-ask gauntlet** (`worker.py:2116-2180`): a question is only asked after `ASK_QUIET_S = 120` seconds of *total silence*, in daylight, under the 3/day uninvited cap, and it expires 600 seconds after parking. **A tester who speaks every 90 seconds never satisfies it, and the question dies unasked.** The harder you test, the more certain her silence.
- **The meeting latch** (`worker.py:2054-2055`): **10 lines within 180 seconds arms it.** While armed every card is held for a digest instead of texted, and any parked question is **cancelled outright** (`anticipy_core.py:1449-1453`). Disarming needs 6–10 minutes of quiet. **A tester firing ten short test lines in three minutes trips this squarely.**

**Silent by construction:**

- **No live LLM** → every line becomes `ignore` (`worker.py:3081-3089`; `anticipy_core.py:2389`). An expired `OPENROUTER_API_KEY` in the Railway env produces total, silent, undifferentiated silence. The only signal is `llm=heuristic` in the startup log at `worker.py:3121`.
- **No owner phone number** → `notify_owner` returns `None` → no text, no `anticipy_says` row (`anticipy_core.py:2672-2676`). Recorded live 2026-08-16 as *"he didn't text me once during our testing."*

**What the three `capture_day` metrics actually prove.** `shard_rate` is the
share of stitched *thoughts* of 1–4 words; `thoughts == lines` means **not one
row in the window resolved a `parent_line`**. Direct query of production:
**`parent_line` has never been written, not once, in 1858 all-time transcript
rows.** Both writers are inactive — the server's `record_link()`
(`worker.py:2492-2500`) is gated on `LINKS_ON`, which defaults **off**
(`worker.py:2445-2448`, and see FOLLOWUPS item 11); the phone's `parentLine:`
landed in `55c89a71` on 2026-08-24 and **has never been in a shipped build.**

Three consequences:

1. **`capture_day.py`'s stitching is a no-op against production.** `shard_rate == raw_shard_rate` exactly (0.415 == 0.415). **The headline "41% shard rate" is a pre-fix number** — anyone reading it as evidence about the cut-marking work is reading data the work never touched.
2. This does **not** indict the server build — `LINKS_ON` off is the current tree's own default. It indicts the *config*: the cut-marking pipeline is disabled at both ends simultaneously.
3. **`shard_too_thin`'s escape hatch is unreachable.** `decision.continues` is always `None`, so the deliberate exemption for "a terse confirmation the model itself linked to an established thread" can never fire, and every ≤4-word line is dropped with no way to spare a legitimate continuation. That is 42% of real lines.

**`speaker_coverage: 0%`** despite the tagger shipping 2026-08-04: no voiceprint
is enrolled on the account under test, so `SpeakerTagger` returns nil and no
speaker evidence reaches triage at all (`anticipy_core.py:1414-1447`).

**The gate that cannot see any of this.** `overnight/is_the_brain_live.py` reads
**only `kind="anticipy_says"` rows** (`:245`), and every leg is an
*over*-speaking check — too many asks, quiet-hours breaches, repeats. **It is
structurally incapable of catching "a line arrived and produced nothing."** With
zero says rows it prints *"no messages in the window, so no rule could be
broken — not a pass"* (`:252`) and **still exits 0**. A totally deaf day passes
the liveness gate. `is_it_live.py` checks only the extension and setup page;
`done_gate.py`'s legs are all offline fixtures; `tejas_gate.py` leg 2 asserts
`shard_too_thin` behaves on four fixtures but never checks that continuation
marks exist in production — the exact condition that makes the floor over-fire.

**Nothing in the repo gates on "what share of delivered lines produced a visible
outcome."** It is computable from rows `capture_day.py` already reads. Today it
is 6.4%. That is the missing scoreboard.

**The ingest path itself is sound** and is not a suspect: the phone POSTs to
PocketBase directly (`app/ios/Anticipy/Backend/AnticipyBackend.swift:545`),
`backend/pb_hooks/guard.pb.js:399` admits exactly the owner's own POST, and a
bad or expired session gets a **403, not a silent 200** (`guard.pb.js:520`+,
`:422`). The phone handles that 403 correctly — it journals it and persists the
line to the on-disk queue (`AnticipyApp.swift:352-364` in HEAD).

> **LAW 1 flags on the server side, unprompted per `CLAUDE.md`.** `shard_too_thin`
> (`anticipy_core.py:636`) is **legal** — it carries a `TAPE:` comment and
> `tejas_gate.py` leg 2 tracks its removal. These do not: `looks_like_dictation`
> (`:342`), `explicitly_non_action_content` (`:356`) and `explicitly_for_memory`
> (`:361`) are regexes routing a line to silence before triage;
> `in_conversation` (`:297`) is a backchannel share threshold; `is_echo_of_her`
> (`worker.py:1653`) is a 6-word-run / 0.6-fraction rule; `already_said`
> (`worker.py:1902`) lets a 0.6 content-word overlap decide *"she already said
> this"*; `MEETING_DENSITY_N = 10` (`worker.py:2054`) lets a line count decide
> *"he is in a meeting."* Each can silently swallow a manual test line, and all
> of them lack the expiry marking LAW 2 requires. Add FOLLOWUPS item 9
> (`_GO_AHEAD_RE`), already recorded.

> **A latent bug found in passing, worth handing to whoever owns `_may_say`:**
> `SPEAK_ONCE` returns the string `"defer"` during a live conversation
> (`worker.py:2263-2265`), but at the `"ask"` call site (`anticipy_core.py:2333`)
> and the `"act"` site (`:2241`) that string is **truthy** and is used as a bare
> `elif`, so the message sends anyway. Only the `ambient_act` path (`:1917-1930`)
> honours it. Not causing silence — causing the opposite — but it means two of
> the three deferral paths do not defer.

---

## The unfalsifiability problem — the most important finding after the build

**Can a tester on build 76 tell "she didn't hear me" from "she heard me and said
nothing"?**

**Partly — and precisely the wrong half.**

**What build 76 *does* give them.** The delivery half is genuinely instrumented:

- `ContentView.swift:1655-1659` — every session row carries `circle.dotted` until the server echoes it, then `checkmark.circle.fill`. That distinguishes *captured but not delivered* from *delivered*.
- `ContentView.swift:1665-1672` — a `bolt.fill` when `decision == "act"`. That distinguishes *delivered and acted on* from *delivered and silent*.
- `ContentView.swift:991-1001` — "N things you said are waiting for a signal" when the offline queue is non-empty.
- `ContentView.swift:984` — "Mic interrupted, taking it back…" while `suspended`.

So: **once a line exists, the tester can follow it.** That is real and it is more
than nothing.

**What build 76 does not give them — the capture half.** If **no row appears at
all**, these are all indistinguishable:

1. the recognizer went deaf (mechanism 1) — waveform still animating
2. the flush simply hasn't fired yet — up to 8s (`TranscriptFlushPolicy.swift:24` `maxHold: 8`, `utteranceGap: 2.6`)
3. the echo guard dropped it (mechanism 2) — no trace of any kind
4. the app was jetsammed and has just silently restarted (mechanism 5)
5. the tester wasn't loud enough

Four of those five are bugs, one is normal, and **the UI is byte-identical in
all five**. `suspended` is the only capture-side signal, and it is false in
mechanisms 1, 2 and 5.

It gets worse in three specific ways:

- `ContentView.swift:1005` gates the session list on `session.listener.isListening`. In the deaf case that is still true, so the list stays visible showing **stale** rows — an animated waveform above a list that stopped growing looks like "you haven't said anything yet."
- `:1007` `sessionLines.suffix(4)` — only the last four rows. A tester who spoke ten times cannot scroll back to see where it stopped.
- The rows carry **no timestamps**. Nothing on screen says the last line landed forty minutes ago.

**So the honest answer: no.** For the failure that is most likely to be what
happened, a build-76 tester has no way to tell a bug from normal operation, and
after a relaunch there is nothing to read at all. That is why every previous
report of this ends at "some testing attempts did not complete" — the instrument
that would finish the sentence shipped a day too late.

**What to tell a tester today, on build 76, concretely:**

> Watch the small list of your sentences under the waveform, not the waveform.
> The waveform means the microphone is open; it does not mean anything is being
> understood. A sentence you just said should appear as a new row within about
> 8 seconds. A dot beside it means it is still going to the server; a filled
> check means the server has it. **If the waveform is moving and no new row
> appears within 15 seconds, she has gone deaf — turn Listen off and on again,
> and write down the wall-clock time.** Never say the same sentence twice in a
> row while testing; say a different one each time, with a number in it.

That last sentence works around mechanism 2 and is worth saying out loud even
before anything is deployed.

---

## What to do before the next manual test

Ordered. Steps 1–3 take about a minute and settle the root question; do not skip
to engineering before doing them.

**0. Discriminate the two halves, on the phone, right now. (30 seconds, and it is the observation this whole report turns on.)**

Production has had zero lines for 24 hours. Two things produce that, and the
phone can tell them apart today, on build 76, with no new software:

- Pick up the test phone. Does the home screen show **"N things you said are waiting for a signal"** (`ContentView.swift:991-1001`)?
  - **Yes, N > 0** → speech *was* captured and could not be delivered. The fault is the wire or the account, not the microphone. Go to step 2 and check sign-in.
  - **No, and it claims to be listening** → speech was **never captured**. That is mechanism 1, 3 or 5, and it has been running for a day.
- Then, with the app open and the waveform animating, **say one fresh sentence and count to fifteen.** If no new row appears under the waveform (`ContentView.swift:1005-1010`), **the recognizer is deaf right now** — and toggling Listen off and on will bring it back, which is itself the confirmation.

Write down which of those you saw before touching anything else. It is the one
piece of evidence that build 76 can still produce and that nothing else can
reconstruct after the fact.

**1. Settle which build is on the phone. (5 seconds, decisive.)**
Open the app → Settings → the "Listening" section at the top.
- **If there is no row reading "Find out what listening actually did"** → the phone is on build 76 or earlier. Mechanisms 1, 2 and 3 are all live, the failure is already diagnosed, and **no new engineering is warranted** — go to step 4.
- If the row is there, the phone has the fixes; go to step 2 and read it.

*(That row is `SettingsView.swift:67-71` in HEAD. Build 76's `SettingsView` contains no diagnostics or journal row at all — verified by grep against `6e277694`.)*

**2. Rule out the boring causes, in this order.**
- Settings → Listening: does it say she is paused? (mechanism 6)
- Settings → Listening: does it say iPhone has microphone access switched off? (`SettingsView.swift:76-79`)
- Is the account signed in? (mechanism 4 — an expired token makes every line render and none send)
- Is `pendingCount` showing "N things you said are waiting for a signal" on the home screen? If yes the network is the story, not the microphone.

**3. Run the 30-second echo test — before anything is deployed.**
Say a phrase of 4+ words. Wait 3 seconds. Say it **verbatim** again. Wait 15
seconds. Say it verbatim a third time.
- Three rows → mechanism 2 is not firing.
- **Two rows, missing the middle one → mechanism 2 confirmed**, and a large part of "transcription is inconsistent" is explained by a bug that is in HEAD too and that a deploy will *not* fix.

**4. Deploy, in this order. Nothing below is new engineering.**

a. **Push the branch.** 48 commits were unpushed at the time of writing; re-check, other agents are still committing.

b. **Deploy the server** — `railway up`. Production predates the cut-marking
work (`thoughts == lines`, zero continuation marks). Then verify it actually
moved: `railway up` reports success while failing, so run the
`overnight/is_it_live.py`-style check and believe only that. **Repo-green is not
done (LAW 3).**

c. **Bump `CURRENT_PROJECT_VERSION` to 77 before archiving.** This is the single
cheapest process fix in this document. Seven different source trees currently
call themselves build 76; the board says "Build 76 is on the phone" and that
sentence cannot be checked. Bump it, and never reuse a number again.

> **The gate gap behind this whole investigation.** `overnight/is_it_live.py`
> exists for exactly this failure — its docstring says "'fixed' has repeatedly
> meant 'fixed on my screen'" — but it compares the **server and the extension**
> against the source tree. **It has no leg for the iOS build.** The one surface
> that failed here is the one surface no gate watches, which is why the answer
> to "which build is on the phone" had to be reconstructed from
> `project.pbxproj` archaeology instead of read off a scoreboard. A leg that
> fetches the running app's `CFBundleVersion` (or, failing that, one that simply
> fails when `CURRENT_PROJECT_VERSION` has not changed since the last commit
> that touched `app/ios/Anticipy/`) would have made today a five-second
> question. Worth a card.

d. **Resolve the two in-flight files first.** `ListenControlPolicy.swift` and
`ListenInterruptionContract` tests are uncommitted and another agent is editing
`PhoneListener.swift`, `ListenResumePolicy.swift`, `ContentView.swift` and
`SettingsView.swift` right now. Shipping the interruption fix *without*
`ListenControlPolicy` installs a new way to end the day with one tap (see
mechanism 3's deploy hazard). Wait for that agent, then archive.

e. **Run the iOS logic gate** — `sh app/ios/Tests/run_all.sh`. It compiles the
real pure-Foundation sources with `swiftc`, no simulator or signing needed, and
covers `run_watchdog_policy_tests.sh`, `run_resume_policy_tests.sh`,
`run_control_policy_tests.sh`, `run_interruption_contract_tests.sh`,
`run_journal_tests.sh` and `run_tally_tests.sh` — the tests for all five fixes.

f. **Build to the device.** Use the committed xcodebuild recipe.
**Do not run `app/ios/build_on_mac.sh`** — it overwrites the committed project.

g. **Verify the new build is really on the phone** before testing anything:
Settings → the "Find out what listening actually did" row must exist. If it
does not, the install did not take, and you are about to repeat today.

**5. Make the next test produce a readable result whatever happens.**

- **Write down the wall-clock start time** before tapping Listen. Every number on the diagnostics screen is a duration; without a start time they cannot be anchored.
- **Say a different sentence each time, each containing a number** ("test line one", "test line two"). This defeats mechanism 2, and the numbers make gaps visible in the delivered data.
- **Say something every 2–3 minutes for at least 10 minutes.** Mechanism 1 needs a task to outlive Apple's duration limit; a 90-second test will pass while the bug is fully present. A short test is what makes this bug look intermittent.
- **Deliberately reproduce the interruption**: have someone call the phone mid-test, hang up, then keep talking for two more minutes. This is the single highest-value scenario, it is currently un-reproducible in the test suite by design (no device has to receive a real call), and it is the one the owner already hit.
- **At the end, before doing anything else, open Settings → "Find out what listening actually did"** and screenshot it. Read, in order: "Listening right now", "Nothing heard for", "Longest stretch hearing nothing", "Lines that did not reach the server", and the "Why it stopped or restarted" section. Then export the log from that screen.
- **Cross-check the server half**: `set -a; . ./.env.local; set +a` then `python3 proof/capture_day.py --hours 6` and compare the line count and timestamps against what the phone says it sent. A disagreement localises the failure to the wire in one step. **Use `--owner <ref>`** — the blended report mixes two owners, and the script says so itself: *"One owner talking fills another's silence, so the blended longest gap CANNOT show a dead day."*

**6. Do not conclude "she heard me and said nothing is a bug" until these are ruled out.**

Once delivery is restored, the *default* outcome for a manual test line is
silence — 93.6% of real delivered lines produce nothing visible, mostly by
design. Before filing that as a defect:

- **Never repeat a test phrase.** A 24-hour, 0.6-overlap guard (`worker.py:1846-1937`) means attempt #2 of the same sentence is silent *by design*, on top of the phone-side echo drop (mechanism 2). Between them, repetition is the single most misleading thing a tester can do.
- **Do not fire ten lines in three minutes.** That arms the meeting latch (`worker.py:2054-2055`), which holds every card and **cancels any parked question outright**, then needs 6–10 minutes of silence to disarm.
- **Pause for two full minutes after the line you expect a question about.** The parked-ask valve requires `ASK_QUIET_S = 120` seconds of total silence and expires 600 seconds after parking (`worker.py:2116-2180`). A tester who keeps talking guarantees the question dies unasked.
- **Test in daylight, local time.** Quiet hours are 22:00–08:00 in the owner's zone (`worker.py:53`). A card will be created; no text will ever come.
- **Confirm the account has a phone number saved.** Without one `notify_owner` returns `None` and there is no text and no `anticipy_says` row (`anticipy_core.py:2672-2676`) — recorded live on 2026-08-16 as *"he didn't text me once during our testing."*
- **Confirm the worker has a live model.** Its startup line (`worker.py:3121`) prints `llm=heuristic` when the key is missing or expired; in that state **every** line is silently `ignore`.
- **Enroll a voiceprint** if speaker tags matter to the test. Coverage is currently 0% because no profile exists on the account under test, so no speaker evidence reaches triage at all.
- **Expect no continuation marks.** `parent_line` has never been written in production and `ANTICIPY_LINKS` is off, so `capture_day.py`'s stitching does nothing and every ≤4-word line is dropped with its escape hatch unreachable. Judge shard numbers accordingly — they are pre-fix numbers.

---

## Smaller findings, recorded so they are not rediscovered

- **`everEmittedThisTask` is write-only.** `PhoneListener.swift:105`, `:312`, `:408` in build 76; `:216`, `:740`, `:877` in HEAD. It is assigned in two places and **read nowhere**, in both trees. Its declaration comment says "see the final handler, where it decides a polish from a whole unsent monologue" — the final handler does not consult it; it calls `flushTail()` unconditionally. A comment that claims a guard exists where none does, in a file where comments are treated as load-bearing.
- **The tester's evidence is capped at four rows and carries no timestamps** (`ContentView.swift:1005-1010`). Even on a deployed build, the live screen is a poor instrument; the diagnostics screen is the instrument. Tell testers that explicitly.
- **`app/ios/Tests/run_interruption_contract_tests.sh` and `run_control_policy_tests.sh` are untracked.** They are the tests for the two highest-value fixes and they are not committed yet.
