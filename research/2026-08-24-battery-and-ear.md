# Battery sanity, which ear heard what, and the build number nobody bumped

**Date:** 2026-08-24 · **Tree:** `/Users/josegaelcruzlopez/Desktop/anticipy-omize`
· **Branch:** `jose_anticipy_system` · **Scope:** `app/ios/` only.

---

## 1. What "battery sanity" turned out to mean

**Not "is it low".** The phone already answers that better than this app can,
and answering it again would be a second, worse battery indicator. The question
worth an instrument is: **what did LISTENING cost, over what window, and what
was the phone doing while it spent that** — so the number is *explainable*, and
so a change in it can be noticed.

Three things follow from that framing, and each of them is a decision that could
have gone the other way:

**It is a fold over the journal, not a counter.** `ListenTally` already exists
for exactly this shape of question and was built over five tasks with a stated
rule: the tally DERIVES, and has no call sites of its own, because a counter
next to a `record()` call is a second source of truth that drifts the first time
somebody adds an event and forgets it. `run_tally_tests.sh` fails the build if
`PhoneListener` ever names `ListenTally`. So the battery arrives as a journal
event and is folded, like everything else on that screen.

**It is a typed event, not a `.noted` sentence.** The journal already records
`.noted("… · low power mode on")`, and `.noted` was the tempting place to put
this. It is the wrong one: `ListenTally` keeps notes *verbatim* precisely
because they are prose written for a person, and parsing our own sentences twice
is how the writing and the reading drift apart. A drain has to be **subtracted
from the reading before it**, which means it must arrive as two values the
compiler can keep honest. `ListenEvent.batteryRead(percent: Int, onPower: Bool)`
also has a privacy property nothing else in the journal has: **its type is its
argument.** An Int and a Bool cannot carry a word the owner said.

**It reports and does not judge.** No threshold anywhere — not in the policy,
not in the fold, not on the screen. There is not one recorded drain figure in
this repo to draw a comparison from, so any "high"/"normal" would be a rule
written while the sense is unmeasured, which is what Law 5 calls tape by
definition. The screen says `4% over 2 hr 10 min` and stops. A gate leg now
keeps it that way (below).

### The three honesty problems, and what each cost to solve

| Problem | If ignored | What was done |
|---|---|---|
| **The charger** | A day spent plugged in reports a triumphantly small drain; a day that charged in the middle reports a *negative* one | Intervals that begin on power are excluded from the measurement and reported separately — `On the charger · 1 hr 5 min, not counted above` — so the exclusion is visible instead of silent |
| **Not listening** | Overnight drain with the microphone off gets charged to listening, making the product look expensive in the one direction that matters | An interval counts only if one **unbroken** listening session covered every instant of it. A stop, a start, or a stop-and-restart between two readings breaks the span |
| **Jitter** | Clamping each delta at zero counts every fall in full and every rise as nothing, inventing a point or two an hour | Signed deltas are summed, so a bounce nets itself out; the **total** is floored at zero, because a report claiming the phone gained battery by listening is a report nobody will believe about anything else either |

### Why this number can show the two costs the card already removed

The card asked for a measure that can show that a call minting an
`SFSpeechRecognitionTask` every four seconds, and the journal writing fifteen
identical lines a minute, were expensive. It can, because the measurement is
**attributed to a window rather than to a day**:

- points and seconds come from the *same pair of readings*, so a 40-minute call
  that spends the battery at four times the ambient rate is not diluted by the
  seven quiet hours around it;
- the counts that explain it are on the same screen, in the section directly
  below: `Restarted at Apple's time limit`, `Restarted after an error`,
  `Restarted when you came back`. On a pre-fix day that section reads in the
  hundreds. A person reads the drain and the swap count together.

A single "battery at start of day vs now" figure could not have done either.

### The sentinel

`UIDevice.current.batteryLevel` is **-1.0** until battery monitoring is switched
on, and it is off by default in every app. The obvious call-site cast,
`Int(level * 100)`, is -100; clamp it with `max(0,)` and it is 0 — **a phone
reported flat all day**. `BatteryReadingPolicy.reading` returns `nil` for it, the
same answer `CaptureSourcePolicy` gives for an ear it cannot name and for the
same reason: silence is recoverable, a confident wrong number is not. There is a
gate leg for the one line that turns monitoring on, because without it the entire
instrument is green end to end and measuring nothing.

### The churn

The thing that reads the battery is the **4-second watchdog**. An unguarded
write there is fifteen lines a minute — measured on this codebase three commits
ago as fully evicting the 400-line ring in twenty-seven minutes and both 256 KB
files in about five hours, which deletes the one
`sessionStopped cause: interruption` line that explains the whole day. A reading
is written when it **changes** and at no other time. Two legs hold that: the
policy's own check, and a source-shape leg in `run_journal_tests.sh` requiring
`shouldRecord` to appear before the first `.batteryRead` write inside
`startWatchdog`, anchored so that renaming the method fails loudly rather than
matching nothing.

---

## 2. Does provenance survive to the device?

**Yes — and, contrary to the card, the in-app feed already shows it.** I checked
before building anything, and found the work already committed (in `54157bba`):

| Hop | Where | State |
|---|---|---|
| Stamped on the wire | `AnticipyApp.swift:346, 359` — every `pushEvent(kind: "transcript", …)` in the app carries `source: source.wireName`; both of them, the live push and the offline-queue flush | done |
| All four `heard()` call sites name an ear | `.phoneMic` ×2, `.pendant`, `.typed` (default, from the compose line) | done |
| Decoded from the server | `AnticipyBackend.swift:104` — `let source: String?` on `BrainEvent` | done |
| Carried onto the feed model | `AnticipyApp.swift:517` — `source: ($0.source?.isEmpty == false) ? $0.source : nil`; PocketBase's `""` normalises to *no verdict*, never to a fourth kind of ear | done |
| Drawn on the raw row | `ContentView.swift:2004` — `CaptureSourcePolicy.badge(for: line.source)`, glyph + label, with a VoiceOver label | done |
| Drawn on the card front | `ConversationCard.swift` — `CaptureSourcePolicy.badge(for: front.ear)` | done |
| A mixed conversation claims no ear | `HeardGroup.ear` returns nil when sources disagree | done, and well checked |

**The `unknown` 46% is handled correctly and is not ours to fix.**
`CaptureSourcePolicy.badge(for:)` returns nil for nil, `""`, whitespace, `typed`
and any unrecognised value, so those rows draw **nothing** — no badge, no
placeholder, no "Unknown" chip that would read as a defect. The 130 unknown rows
in tonight's live run cannot have come from this app: both of its transcript
pushes stamp a source unconditionally. They predate the field or came from
another producer (server-side or the extension), and neither is in `app/ios/`.

### What I did find, and fixed

**A real hole in the gate, not in the app.** `run_capture_source_tests.sh`
protected the badge on `TranscriptRow` — the raw line, which for a grouped
conversation is **one tap behind the card**. Nothing anywhere asserted that
`ConversationCard` drew `front.ear` at all. Mutation-tested: replacing the card's
badge with `if false` left `run_all.sh` **completely green** while the front of
the feed lost provenance entirely — the same write-only life `events.source`
already had once. Two legs added, both mutation-tested red.

**Pendant lane:** I read `research/2026-08-24-deepgram-leak.md`. Nothing built
here encourages pendant use. The pendant badge is a truthful label on a line that
already exists; no affordance, no prompt, no pairing path was added or made more
prominent.

---

## 3. The build number

**76 → 77**, with a comment in `project.yml` in the house register saying what
changed. Regenerated with `xcodegen generate`; `git diff --stat` confirms
`Info.plist` is untouched, and the built Release app reports `CFBundleVersion 77`.

### Making it impossible to forget: `Tests/run_build_number_tests.sh`

Three legs, each anchored on something that **moves**:

1. **The number is a number.** App Store Connect compares build numbers
   numerically and every other leg reads this one; a value the script cannot
   parse is a check reporting on nothing.
2. **`project.yml` and the generated `.xcodeproj` agree.** `xcodebuild` reads the
   pbxproj, so a bump nobody ran `xcodegen` after ships the *old* number under a
   repo that swears otherwise. Same shape as the 2026-08-15 failure where a
   literal in `Info.plist` overwrote the setting and build 54 shipped twice.
   (Plus a leg keeping `Info.plist` on `$(CURRENT_PROJECT_VERSION)`.)
3. **The iOS source has not moved since the number did.** The commit where
   `CURRENT_PROJECT_VERSION` last changed is found with `git log -1 -G`, and the
   **working tree** is diffed against it. If the source has moved and the number
   has not, red — with the file list attached.

**Why this rule and not "bump on every commit":** leg 3 is green from the moment
you bump until the next source edit, which is exactly the rule a human would
state. It is red *while you are writing the change*, which is when the reminder
is useful, and green by the time the commit lands. It is not a rate limit and it
cannot be satisfied by bumping twice.

**Failure modes are loud, not silent.** No git, no repo, or no commit in history
that ever changed the setting → **exit 2 with a sentence**, never a skip. An
empty search is not a pass; that is the class of failure that produced three
gate rules passing by matching nothing this week.

`run_all.sh` runs it last, because a red leg there means "bump it before you
commit", not "the code is wrong".

---

## 4. What was built

| File | What |
|---|---|
| `app/ios/Anticipy/Audio/BatteryReadingPolicy.swift` | **new.** Pure Foundation. The sentinel, the rounding, the churn rule. No UIKit, no threshold |
| `app/ios/Anticipy/Audio/ListenJournal.swift` | `ListenEvent.batteryRead(percent:onPower:)`, its `describe`, and a parser that reads the **fields** (not a substring — the lesson `posted` paid for) |
| `app/ios/Anticipy/Audio/ListenTally.swift` | Four folded values: `batterySpentPoints`, `batteryMeasuredSeconds`, `batteryOnPowerSeconds`, `batteryReadings`. Plus the tie-break slot for a reading inside one instant |
| `app/ios/Anticipy/Audio/PhoneListener.swift` | Turns battery monitoring on at `begin()`; reads the battery on the watchdog tick that is already running (no second timer to measure the first one); guards the write with `shouldRecord` |
| `app/ios/Anticipy/Views/ListeningDiagnosticsView.swift` | Two rows in the existing voice: `Battery used while listening · 4% over 2 hr 10 min`, and `On the charger · 1 hr 5 min, not counted above` |
| `app/ios/project.yml` | 76 → 77 |
| `app/ios/Tests/BatteryReadingPolicyTests.swift`, `run_battery_tests.sh` | **new**, 16 checks + 2 wiring legs |
| `app/ios/Tests/run_build_number_tests.sh` | **new**, 3 legs |
| `app/ios/Tests/ListenTallyTests.swift` | +10 checks (32 total) |
| `app/ios/Tests/ListenJournalTests.swift` | `.batteryRead` added to `Kind`/`samples` — the compiler forced the parser and the fold to deal with it |
| `app/ios/Tests/run_journal_tests.sh`, `run_tally_tests.sh`, `run_capture_source_tests.sh`, `run_all.sh` | New legs |

### Three rows a person reads

```
Battery used while listening       4% over 2 hr 10 min
On the charger                     1 hr 5 min, not counted above
```

Three answers, because the two kinds of nothing are different questions:
**"Not recorded"** — the phone never told us (the simulator, a journal from
before this shipped, monitoring off). **"Nothing to compare yet"** — readings
exist, but no pair of them brackets an unplugged listening stretch. Neither is
*"it spent nothing"*, which is a much more reassuring claim and would be a lie in
both cases. That distinction is copied from how the same screen already reports
`Listening right now · Not recorded` rather than guessing "yes".

---

## 5. Checks and mutations

`sh app/ios/Tests/run_all.sh` → **all suites pass**, including
`ListenTally 32/32`, `ListenJournal 19/19`, `BatteryReadingPolicyTests` (16),
`build 77, bumped from 76 and not yet committed`.

Release build: **BUILD SUCCEEDED**; `CFBundleVersion` in the built app is **77**;
`BatteryReadingPolicy.swift` appears **4×** in `project.pbxproj` (in the target,
not merely on disk).

**Every new behaviour was broken on purpose and the check that went red was
named.** 22 mutations, all caught:

| # | Mutation | Went red |
|---|---|---|
| 1 | Drop the `level >= 0` guard | `the -1 sentinel is not a reading` |
| 2 | `shouldRecord` always true | `an unchanged reading is not written again` |
| 3 | Truncate instead of round | `a level rounds to the nearest point` |
| 4 | Count drain while listening was off | `a drain while listening was off is not charged to listening` |
| 5 | Count charger time as drain | `time on the charger is not counted as drain` |
| 6 | Clamp each delta instead of the total | `a battery that ticks up while unplugged does not net out as negative drain` |
| 7 | A reading resets the silence clock | `a battery reading is not evidence that anybody spoke` |
| 8 | Battery sorts after the stop in one instant | `a reading stamped with the stop still belongs to the session it ended` |
| 9 | `isBatteryMonitoringEnabled` removed | `Nothing switches battery monitoring on.` |
| 10 | Raw level cast at the call site | `PhoneListener no longer asks BatteryReadingPolicy…` |
| 11 | Churn guard removed from the watchdog | `The watchdog records a battery reading without first asking…` |
| 12 | Nothing records the battery | `Listening no longer records what it costs.` |
| 13 | `startWatchdog` renamed | `This gate can no longer find startWatchdog's body.` |
| 14 | `batteryWording` renamed | `This gate can no longer find the screen's battery wording.` |
| 15 | Window dropped, bare `4%` | `The battery number is shown without the window…` |
| 16 | A verdict word (`"Battery use is normal"`) | `The Listening screen judges the battery instead of reporting it` |
| 17 | Spent points not shown | `The Listening screen no longer shows what the battery spent.` |
| 18 | Bump reverted, source moved | `The iOS source has changed since build 76 was set…` |
| 19 | `xcodegen` never run after a bump | `project.yml says build 77 and the generated Xcode project says: 76` |
| 20 | `Info.plist` restates the number | `Info.plist no longer references $(CURRENT_PROJECT_VERSION).` |
| 21 | Version is `"77b"` | `…is not a plain integer` |
| 22 | `.noted(self.partial)` in the new code | privacy scan named the file and the expression |

### One mutation that survived, and what it taught

**#15 passed the first time.** The window leg grepped the whole `batteryWording`
function for `batteryMeasuredSeconds`, and the *guard* three lines above the
sentence — `if tally.batteryMeasuredSeconds == 0` — satisfied it. Dropping the
window from the returned sentence left the leg green. That is the fourth
instance of exactly the failure I was told not to add. Both legs now read only
the `return` lines, and require **one** return line to name both values. Re-run:
red. This is the single most useful thing mutation testing did today, and it
would not have been found by reading the leg.

### Existing legs I re-verified rather than trusted

- `run_capture_source_tests.sh` catches deletion of the `TranscriptRow` badge —
  confirmed red.
- It did **not** catch deletion of the `ConversationCard` badge — confirmed
  green under mutation, now fixed and confirmed red.
- `run_journal_tests.sh` still catches speech reaching the journal through the
  new code path — confirmed red on `.noted(self.partial)` inserted beside my own
  battery write.

---

## 6. What I could not prove without hardware (Law 3)

Everything above is **repo-green, not device-green**, and the battery half of it
is the part where that gap is real rather than formal.

- **The simulator has no battery.** `batteryLevel` is -1.0 and `batteryState` is
  `.unknown` there, forever. The policy is written so that this produces *no
  readings* and the screen says `Not recorded` — which is the correct behaviour
  and is checked — but it means **the simulator can never exercise the
  measuring path at all.** Nothing in the numbers below "Not recorded" has been
  observed on real hardware.
- **The simulator models no calls**, so the interaction that matters most —
  what a phone call's interruption does to the reading cadence, and whether the
  span-breaking logic behaves as designed across a real `.interruption` stop —
  is unproven.
- **The reading cadence is unobserved.** The change-only rule should produce a
  handful of lines an hour on a phone spending a point every ten minutes. On a
  device whose reported level oscillates more than expected it could be
  noisier. The rule is correct in shape; its *rate* wants one real day of
  wearing to confirm.
- **Whether the numbers are useful** is the open question, not whether they are
  correct. The fold is proven. Whether `4% over 2 hr 10 min` next to
  `Restarted at Apple's time limit · 31` actually lets somebody say "that day
  was expensive and here is why" needs a day of real wearing on build 77 and a
  second day to compare it against. That comparison is the whole point, and it
  cannot exist until two days have been recorded.

**Not verified against production**, and deliberately not: nothing here touches
the brain, the backend, or any deployed surface. The only live claim in this
report is the read-only one about `events.source`, which I checked against the
shipped code path rather than against the server.
