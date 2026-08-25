# The cold stranger's path, walked through the code

**Date:** 2026-08-24 · **Tree:** `/Users/josegaelcruzlopez/Desktop/anticipy-omize`
· **Branch:** `jose_anticipy_system` · **Method:** read-only source walk plus
unauthenticated GETs against the live backend. No product code touched.

**Why this exists.** `overnight/done_gate.py` passes legs 1–5 and fails leg 6:
*no cold stranger has ever onboarded on their own accounts and been carried
through a real day.* A human has to live that week. What had not been done is
walk the stranger's path through the code first, so the week is not spent
discovering what a reading would have caught. That is this document.

**Churn caveat.** Three agents were editing `app/ios/**`, `brain/**` and
`extension/**` while this was written; `git status` showed 35 uncommitted
files. Everything below is pinned by **symbol name first, line number second**.
`app/ios/project.yml` and `Anticipy.xcodeproj/project.pbxproj` both changed
under me mid-walk (build 76 → 77); that is recorded in Step 0 rather than
hidden.

**Verdict counts:** 9 dead ends. 6 steps that work. 4 things that cannot be
settled without a device and a person.

---

## Step 0 — Getting the app onto the phone

**Verdict: cannot tell without a device. Two facts are certain and one is
newly in motion.**

The App Store is not the door and neither is TestFlight. `docs/BRIEF.html:504`:

> *TestFlight rejects builds with the speaker frameworks silently during
> processing (missing privacy manifests suspected). Build 76 installs by cable;
> distribution needs this solved.*

So step one for a stranger is: hand your iPhone to someone with a Mac, Xcode,
and membership in team `49T86P9XGW` (`app/ios/ExportOptions.plist`), who builds
and runs it onto your device over a cable. The floor is iOS 16.0
(`app/ios/project.yml`, `options.deploymentTarget.iOS`).

**Which build a stranger would install.** You asked what
`CURRENT_PROJECT_VERSION` reads now, because it had been stuck at 76.
It is **77 in the working tree, uncommitted**, and **76 at HEAD**:

- working tree: `app/ios/project.yml:144` → `CURRENT_PROJECT_VERSION: "77"`,
  and `Anticipy.xcodeproj/project.pbxproj:419,498` → `77`
- `git show HEAD:app/ios/project.yml:120` → `"76"`

It was **not** stuck across nineteen commits. Walking every commit that touched
`project.yml`, the number moves nearly every time — `…50, 51, 52, 53, 54, 55,
56, 57, 58, 59, 60, 61, 62, 64, 75, 76`. The gap is real but different: **76 has
been the committed value since `6e277694`**, and 77 is another agent's
in-flight fix landing as I read. Nothing here is a stranger-facing defect; I
report it because you asked and because the answer differs from the premise.

One rough edge for whoever does the cable install: `app/ios/README.md` still
documents *"Product → Archive → Distribute App → App Store Connect → Upload"*
followed by *"TestFlight → add yourself as internal tester"* — a route
`docs/BRIEF.html:504` says does not work. The README also opens with
`./build_on_mac.sh`, which regenerates `Anticipy.xcodeproj` from `project.yml`
and overwrites the committed project file.

---

## Step 1 — First launch: the door is sign-up, not hello

**Verdict: works, with two ways to be silently wrong.**

Routing is a three-way branch in `AnticipyApp` (`app/ios/Anticipy/AnticipyApp.swift:24-47`):
`!session.isSignedIn → AuthView`, else `hasOnboarded → HomeView`, else
`OnboardingView`. On a fresh install `authToken` and `accountID` are both `""`,
so `isSignedIn` (`AnticipyApp.swift:1054`) is false and **the very first screen
is `AuthView` in `.signUp` mode** (`Views/AuthView.swift:15`). There is no
guest mode, no skip, no offline path.

Sign-up is real PocketBase, not a stub: `POST api/collections/owners/records`
(`Backend/AnticipyBackend.swift`, `createAccount`). `/api/health` on the live
host returns 200, so the backend is up.

**Dead end 1 — a non-North-American stranger's number is silently corrupted.**
`AuthView.canGo` (`Views/AuthView.swift:305-325`) requires a phone that
`looksReachable` (`:299-303`) — 10 to 15 digits, not all identical. That string
is then normalised by `AnticipySession.e164` (`AnticipyApp.swift:577-584`),
which **prepends `+1` to any bare 10-digit number**. A stranger in London or
Bangalore who types their local 10-digit number gets a US number written to
their account. Nothing validates it, nothing tests deliverability, and SMS is
the only out-of-app channel (`Notifier.swift` header). *Scenario: a stranger who
is not in the US or Canada completes sign-up successfully and never receives a
single text for the rest of the week, with no error anywhere.*

**Dead end 2 — `hasOnboarded` is device-global, not account-scoped.**
`@AppStorage("hasOnboarded")` is declared at `AnticipyApp.swift:9` with no
account key. If the stranger is handed a phone that anyone has onboarded before
— which is exactly how a cable install happens — they sign up and land
**straight on `HomeView`**. They never see the mic primer, so listening is
never started, and `AuthView.swift:82-85` pre-fills the *previous* person's
email and opens in sign-in mode. *Scenario: the stranger's phone was set up on
someone else's Mac, the installer opened the app once to check it, and now the
stranger's first screen is a feed with a dead microphone and no way to discover
the four-step tour except "Replay the welcome tour" buried in Settings.*

Also true, lower severity: `AnticipySession.init` starts a 3-second poll before
sign-in (`AnticipyApp.swift`, `startPolling`), so an unauthenticated poll runs
against production the whole time the sign-up screen is open. It fails
invisibly and harms nothing.

---

## Step 2 — Onboarding: four beats

**Verdict: works. This is the most solid part of the path.**

`OnboardingView.Step` (`Views/OnboardingView.swift:61-67`) is four pages:
welcome, howItWorks, mic, phone. Named for the reader as
`["Hello", "How I work", "May I listen?", "Where to reach you"]` (`:101`).

**Permissions are correct and complete.** Speech recognition then microphone,
both from `PhoneListener.start()` (`Audio/PhoneListener.swift:267` then `:278`,
nested so the order is guaranteed), reached from `advance()` at
`OnboardingView.swift:235-241`. The in-app copy at `:514` matches what actually
happens: *"iOS asks twice, once for speech, once for the microphone."*

Every runtime permission has its Info.plist key, generated from
`project.yml` (`targets.Anticipy.info.properties`):
`NSSpeechRecognitionUsageDescription`, `NSMicrophoneUsageDescription`,
`NSBluetoothAlwaysUsageDescription`, `NSContactsUsageDescription`, and **both**
calendar keys — the legacy `NSCalendarsUsageDescription` ships deliberately
because the deployment floor is 16.0 and an app linked on 16 without it
crashes. **I found no runtime permission request without a matching key.** No
location, camera, photos, health, or biometrics anywhere.

Notifications are not asked here. `Notifier.askIfNeeded()`
(`Notifier.swift:50-65`) fires only the first time a job is actually waiting,
so a day-zero stranger never sees that prompt. Correct by design.

**The one rough edge.** The final "Where to reach you" step blocks on a network
write: `advance()` (`OnboardingView.swift:245-269`) refuses to finish unless
`saveOwnerPhone` succeeds. Offline, the primary button — the one that says
"Start living your day" — becomes a no-op that repaints an "I couldn't save
that just now" card. The stranger is not trapped, but the escape is the *ghost*
button, "Skip for now" (`:177`, `:205-210`), which is the one that looks like
giving up. *Scenario: a stranger finishing onboarding on hotel wifi taps the
big button four times, sees the same error card each time, and the only way
forward is the small grey text that reads like abandoning the step.*

---

## Step 3 — Voice enrollment: never offered, so speaker coverage stays 0%

**Verdict: broken, in the specific sense you asked about.**

You asked whether the enrollment page exists, is reachable, and whether a
stranger is ever asked. Answers: **it exists, it is reachable only if you go
hunting, and no stranger is ever asked.**

`Views/VoiceEnrollView.swift` is complete — a 12-second scripted read, an
`enrolling` flag that suppresses transcription during it, done/failed/unavailable
states. The model ships: `Anticipy/Resources/speaker-embedding.onnx` (26 MB) is
a real file and is in the Resources build phase
(`Anticipy.xcodeproj/project.pbxproj:305`).

But it has **exactly one presentation site in the entire app**:
`Views/SettingsView.swift:583-585`, a `.sheet` opened by the button at
`SettingsView.swift:204-208` inside `Section("Your voice")` (`:196`). Grep of
`app/ios` for `VoiceEnrollView` returns the definition, that one sheet, one
comment in `project.yml`, and four Xcode bookkeeping lines. Nothing. Else.

It is not in `OnboardingView`, not in `ContentView`/`HomeView`, not in
`OnboardingFinale`, not in `InterviewView`. To reach it a stranger must, with
nobody suggesting it, tap the slider glyph in the Home toolbar, scroll past
Listening / Pendant / You, and find "Teach me your voice."

The consequence is mechanical, not speculative. With no owner profile,
`VoiceRoster.identify` cannot produce a verdict, `SpeakerTagger` returns nil,
and the `speaker` field on every event is empty. `research/2026-08-24-engine-options.md:254`
records it as measured: `speaker` 0%, cause **"enrollment unreachable"**,
confidence **"Certain. One call site, measured 0/221."**
`docs/superpowers/plans/2026-08-24-voice-capture.md:238` names the downstream
cost: *"which is why it was empty on all 137 lines of the Tejas call, and why
four of that call's six bad acts happened."*

The fix is planned and unbuilt — `EnrollmentInvite.swift` plus an onboarding
page, Task 4 of that plan, and
`docs/superpowers/plans/2026-08-25-phone-as-pendant.md:317` still carries
`[ ] Land the enrollment invite + onboarding page (plan Task 4, still unlanded)`.

*Scenario: the stranger wears this for a week in an office. Every line anyone
says near them is attributed to nobody, and a colleague saying "I'll send that
tonight" is indistinguishable from the stranger saying it. Four of six bad acts
on the one call that was ever scored came from exactly this.*

---

## Step 4 — The first text

**Verdict: works on paper; three ways to fail silently.**

The path is real and single: `VoiceArm.text()` (`brain/voice_arm.py:411`) POSTs
to Twilio `Messages.json`. Above it, `TwilioTransport.send`
(`brain/conversation.py:232`) → `Conversation.reach_out` (`:332`) →
`Anticipy.notify_owner` (`brain/anticipy_core.py:2727`). Selected once at
worker start: `worker.py:3095-3099` picks `TwilioTransport` when
`has_credentials()` is true and `MockTransport` otherwise.

The stranger's very first text is `maybe_welcome_new_owner`
(`brain/worker.py:226-279`), called from the 60-second profile beat at
`worker.py:3177`. It requires the `owner_profile` row to be under 3600 seconds
old and stamps one welcome per number, durably.

For it to arrive, all of this must hold at once: the stranger was **signed in**
when they saved the number (otherwise `owner_ref` is absent and
`backend/pb_hooks/owner_profile_owner.pb.js:53-60` rejects the row); they did
not take "Skip for now"; `brain/supervisor.py` discovered their account via
`GET /worker/owners` — **that route is live, I probed it: 403 without a token,
404 on POST, so it is deployed and GET-only**; and Twilio accepted the send.

**Dead end 3 — the welcome text has no quiet-hours guard.**
`CLOCK_QUIET_START, CLOCK_QUIET_END = 22, 8` (`worker.py:53`) is consulted at
`worker.py:125` (the night digest) and `worker.py:569` (the clock lane).
`maybe_welcome_new_owner` is called from the profile poll at `worker.py:3177`
and consults neither. *Scenario: a stranger finishes onboarding at 1am — which
is when people set up new toys — and the product's first ever words to them
arrive as a phone buzz at 1am.*

**Dead end 4 — there is no consent artifact of any kind.** No opt-in record, no
`STOP` keyword handling, no A2P 10DLC registration, no verification code sent
to the number. Greps for `STOP|opt.?in|consent|10DLC|A2P|unsubscribe` across
`brain/`, `backend/`, `app/`, `extension/` return nothing implementing any of
it. The number typed in onboarding is trusted verbatim after `e164()` reshapes
it. *Scenario: a stranger types a digit wrong, and an uninvolved person starts
receiving an AI's texts about someone else's day with no way to make them
stop.*

**Dead end 5 — a missing-credentials worker records texts as delivered.**
`MockTransport.send` (`brain/conversation.py:196-199`) returns a **truthy**
dict, and `anticipy_core.py` states plainly that *"the caller treats any truthy
return as delivered."* The only signal is `sms=mock` in a startup log line
(`worker.py:3128`). `.env.local` today has `TWILIO_ACCOUNT_SID`,
`TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER` populated and `TWILIO_MOCK=false`, so
the muzzle is off — but both `TWILIO_API_KEY_SID` and `TWILIO_API_KEY_SECRET`
are commented-out placeholders, so outbound runs on full-account auth. *Scenario:
a credential rotates mid-week, the worker restarts into mock, and the feed keeps
showing "I texted you about that" for days while the stranger's phone is silent.*

**Unresolvable from source: trial vs paid.** Twilio trial accounts can only text
*verified* numbers. Nothing in the repo branches on it; `voice_arm.py:389`
merely notes that Twilio's error body is the only thing distinguishing
"unverified number" from "account suspended", and the resulting `SendFailed`
reaches a `print()` on worker stdout and nowhere else.

Inbound is genuinely wired: `POST /sms/inbound`
(`backend/pb_hooks/sms.pb.js:24`) with real Twilio signature validation
(`:88-101`), sender→account resolution by phone (`:163-179`), and a `sms_reply`
event the worker consumes (`worker.py:2580-2625`). A sender matching zero or
more than one account is **dropped behind a 200 with a console line**
(`sms.pb.js:204-210`).

---

## Step 5 — The hands: nothing tells the stranger, and what they'd install is wrong

This is where the week ends. Three separate dead ends stack.

**Dead end 6 — nothing asks for the browser until an errand is already stuck.**
The browser was deliberately removed from first run
(`Views/OnboardingView.swift:14-20`). The only first-run mention is descriptive
(`:406-407`, *"I set things up in Chrome on your computer"*) and never says
install anything. The ask lives on Home behind `browserOffer`
(`Views/ContentView.swift:221-223`):

```swift
verified && !session.agentPaired && !browserOfferDeferred && !handling.isEmpty
```

`!handling.isEmpty` means **the card cannot appear until work is already parked
with no hands**. The single link to the install guide in the whole product is
`SettingsView.swift:263-269`, rendered only when unpaired. *Scenario: day one,
the stranger says "book me a table Thursday", the brain mints an errand, the
errand sits in "Waiting for your browser", and the product's only response is a
card that appears after the failure rather than before it.*

**Dead end 7 — the extension the stranger would download is three minor
versions behind the app, and the app tells them to fix it in a way that cannot
work.** This is the one the repo's own tooling already knows about. I ran
`python3 overnight/is_it_live.py` against production:

```
[PASS] the backend is answering
[PASS] the setup page only names the folder the download produces
[FAIL] the served extension's version matches source     served 0.8.4, source 0.11.0
[FAIL] the served extension IS the source, byte for byte  differs: served 251359 chars, source 338485
[FAIL] no uncommitted changes masquerading as shipped     35 file(s) uncommitted
```

I confirmed it by hand. `GET https://backend-production-61e0a.up.railway.app/anticipy-claude-version-extension.zip`
returns 122,423 bytes; its `manifest.json` reads `"name": "Anticipy Claude
Version", "version": "0.8.4"`. The app pins
`AnticipySession.expectedExtensionVersion = "0.11.0"`
(`AnticipyApp.swift:114`) and `staleExtension()` (`:120-136`) fires whenever
Chrome is behind. The banner it fires is `ContentView.swift:629-631`:

> *"Chrome is running the old extension (0.8.4). Open chrome://extensions and
> press Reload to get 0.11.0. Until then it's working from old instructions."*

**Pressing Reload cannot change anything.** The folder on disk is 0.8.4, and
0.11.0 is not downloadable from anywhere — the only download URL serves 0.8.4.
The stranger is told to perform an action that is guaranteed not to fix the
problem, with no next step. *Scenario: the stranger does the whole five-minute
Chrome ceremony correctly, pairs successfully, and is immediately shown a
warning banner that will never go away no matter how many times they follow its
instruction.*

**And the staleness is two layers deep.** Even the zip committed in the repo is
not the current source. Diffing `backend/pb_public/anticipy-extension.zip`
against `extension/`:

| file | in zip | in source |
|---|---|---|
| `agent_loop.js` | 320,430 | 339,229 |
| `config.js` | 4,843 | 7,634 |
| `side_trip.js` | 20,388 | 25,132 |
| `supervised_read.js` | 33,957 | 34,389 |
| `manifest.json` | **identical** | **identical** |

Because `manifest.json` is byte-identical, both report `0.11.0`. `extension/build-zip.sh`
has not been re-run since 2026-08-22. So a deploy of the current repo would ship
a zip that reports a version it does not contain, and `staleExtension()` — which
only speaks when Chrome is *behind* a literal — cannot detect it.

**Dead end 8 — the supervised mail read can never run on the extension in
production.** The live 0.8.4 zip contains 12 files. It is missing `config.js`,
`learn.js`, `login_wall.js`, `recipes.js`, `side_trip.js`, `supervised_read.js`
and `theme.js`. Grep of the live `background.js` for
`supervised_read|supervisedRead|watching_until` returns **zero hits**.

Two independent reasons it fails. First, the code is absent. Second, the claim
filter: live `background.js:359` requires
`status="queued" && owner_ref="…" && workflow_id!="" && lane!="research"`, and
`AnticipyBackend.queueJob` (`:571-593`) — the function `startSupervisedRead`
calls — **never sets `workflow_id`**. So the row is invisible to that filter
even if the code existed.

The failure the stranger sees is the honest-but-terminal one at
`Views/SupervisedReadView.swift` (the 10-silent-poll branch, ~30s):
*"Nothing's come back from your Chrome…"* — forever. *Scenario: the stranger
taps "Open my mail while I watch", grants the most invasive consent the product
asks for anywhere, watches a spinner for thirty seconds, and is told nothing
came back. It never will.*

**Dead end 9 — the install guide points at two things that no longer exist.**
`backend/pb_public/setup.html` Step 5 tells the stranger:

> *"Still setting the app up? You're already on the right screen — the one
> headed **'Your hands on the computer.'**"*

That screen was deleted when the browser left first run
(`OnboardingView.swift:14-20`); onboarding is four beats and none is it. The
same dead pointer is repeated in `extension/onboarding.html:638-640`. The guide
then says to find **"Browser agent"** in Settings; the actual header is
`Section("Your computer")` (`SettingsView.swift:251`). *Scenario: a stranger
mid-onboarding reads "you're already on the right screen", looks at a screen
asking for their phone number, and concludes they have done something wrong.*

Two smaller notes on this step. The live `setup.html` is itself the older
"Anticipy Claude Version" page — the repo's rewritten, theme-aware version
(which links `/site.css` and `/theme.js`) is not deployed. And
`extension/sync-to-chrome.sh:15-18` records that an unpacked extension's ID is
derived from its folder path, so *"a new folder means a new ID, which means the
pairing with the phone breaks and has to be redone"* — a stranger who tidies
their Documents folder mid-week silently loses the hands.

**What does work here:** the pairing mechanism itself. The extension mints an
agent record and a 6-digit code (`backend/pb_hooks/agent_auth.pb.js:45-67`,
`POST /agent/register` — live, returns 400 on an empty body, so it is
deployed); the phone claims it with read-back verification
(`AnticipyBackend.pairAgent`, `:379-410`); the code auto-submits at six
characters (`SettingsView.swift`, `.onChange(of: pairCode)`); and the two
failure sentences are correctly distinguished — *"That code didn't match"* vs
*"I can't reach Anticipy right now. That's my end, not your code."*
`login_wall.js` blocks nothing at install time; it is a runtime page classifier
with, by explicit design, no site list at all.

---

## Step 6 — The first approval: approve / cancel / undo / receipts

WIRE IT ALL step 1. Traced control by control.

**No button in this app is wired to a nonexistent endpoint.** There is no
FastAPI or Flask service — `brain/` is a polling worker — and every path the
app constructs resolves either to a PocketBase record route on a collection
that exists in migrations, or to one of 14 `routerAdd` hooks in
`backend/pb_hooks/`. I probed six of them live: `/agent/register` 400,
`/transcription/token` 401, `/auth/claim` 401, `/me/delete` 401, `/sms/inbound`
415, `/worker/owners` 403 on GET. All deployed.

**APPROVE — works.** `ConfirmJobCard`'s primary
(`ContentView.swift:1580`, label `:1594`) → `AnticipySession.confirm`
(`AnticipyApp.swift:1573`) → `AnswerRoutePolicy.route` → `approvalFields`
(`:1288`) → `PATCH api/collections/jobs/records/{id}`. The digest the app
computes matches the five keys `backend/pb_hooks/workflow_guard.pb.js:167-178`
demands, and the transition `awaiting_confirm → queued` is legal at `:123-125`.
Failure has real UI: `write(id:expected:)` (`AnticipyApp.swift:1697-1731`)
records `failedWrites`, the card reads it (`ContentView.swift:1528`) and shows
*"That didn't go through… Nothing was sent."* (`:1570-1574`).

**CANCEL, "Not now" — works.** `ContentView.swift:1602` →
`AnticipySession.decline` (`AnticipyApp.swift:1679`) → `cancellationFields`
(`:1540`) → PATCH. Legal at `workflow_guard.pb.js:123-124`. Same error UI.

**CANCEL, "Stop" on a running job — rendered, wired, and its failure is
invisible and permanent.** `HandlingCard` declares `@State private var stopping
= false` (`ContentView.swift:1742`). The button sets `stopping = true`
(`:1802`), discards the result (`_ = await session.stopRunning(job)`, `:1803`),
and is `.disabled(stopping)` (`:1808`) with label
`Text(stopping ? "Stopping…" : "Stop")` (`:1805`). **`stopping` is never set
back to `false` on any path**, and unlike `ConfirmJobCard` and `DoneCard`,
`HandlingCard` never reads `session.failedWrites`. *Scenario: the stranger
watches an errand go somewhere wrong, taps Stop, the PATCH is refused, and the
card reads "Stopping…" — greyed out, no error, no retry — while the browser
keeps clicking. This is the one control whose entire justification is that they
have no other way to stop a run away from the desk.*

**UNDO — does not exist.** Case-insensitive grep for `undo` across all 45 Swift
files returns comments and two body strings that *deny* undo
(`SettingsView.swift:436` *"It can't be undone"*). There is no `session.undo`,
no undo control, no route. And there is nothing to build against yet:
`workflow_guard.pb.js:127-129` makes `done`, `failed` and `cancelled`
**terminal**, so any undo is a new job by construction. The nearest neighbours
are "FORGET" on a supervised-read fact (a `read_veto` event, fired with `try?`
so a failed send looks identical to a successful one —
`AnticipyApp.swift:932`) and "Start a fresh attempt", which explicitly refuses
to be an undo. **Step 1 of WIRE IT ALL cannot be marked wired.**

**RECEIPTS — rendered from the wrong field.** `workflow_guard.pb.js:203-210`
refuses any `done` transition unless the job carries a `receipt` with
`verified === true`, a matching `effect_key`, and a non-empty `evidence` array.
The migration adds the column (`pb_migrations/1700000025_job_workflows.js:21`).
But **`AgentJob` has no `receipt` field** — `Backend/AnticipyBackend.swift:5-31`
declares `id, goal, params, status, result, created, workflow_id,
workflow_version, workflow_state, consequence, approval, scope_digest,
effect_key, effect_uncertain, reconciliation, lane` and stops. The app *writes*
`"receipt": ""` on approve and cancel and never reads it back. `DoneCard`
therefore feeds `job.result` — free text the extension happened to write — into
`JobReceiptPolicy.doneCard`. *Scenario: the structured, server-enforced
evidence exists in the database and the stranger never sees a byte of it; what
they see is whatever sentence the browser wrote.*

**"Start a fresh attempt" always reports success.**
`AnticipySession.requestFreshRetry` (`AnticipyApp.swift:1643-1648`) is the one
write path that bypasses `write(id:)`; it calls `heard(...)`, which is
non-throwing and buffers to the on-disk unsent queue on failure — and returns
early with no signal at all if `accountID` is empty (`:338`). The error line at
`ContentView.swift:1913` can only ever appear as a false positive inherited
from an earlier failed write on the same job id.

**Other silent-failure controls found:** "Save details" / "Save" (phone) in
Settings — `upsertOwner` swallows errors and the UI only ever adds a success
sentence; "Release this browser" — `try?`, non-throwing, no error UI; and
`approvalFields` throwing a *local* `WorkflowWriteError` surfaces as *"I
couldn't reach Anticipy"*, which names the wrong cause and can never succeed on
retry. Three empty button closures exist and all three are correct SwiftUI
`.cancel` idiom, not dead buttons.

---

## Step 7 — The rest of WIRE IT ALL

**The verify loop (act → evidence → done-text with photo): the photo does not
exist.** `grep -rn "MediaUrl"` across every `.py`, `.js` and `.swift` in the
repo returns **zero results**. There is no MMS path, no screenshot attachment,
no image in any outbound text. `VoiceArm.text` posts only `From`, `To`, `Body`
(`brain/voice_arm.py:411`). Evidence exists browser-side and server-side as
URLs in `receipt.evidence`; it reaches neither the text nor the app (see
receipts above).

**The clean-day counter: does not exist.** Grep for
`clean_day|cleanDay|"clean day"|cleanDays` across the repo returns three
matches, all of them prose in comments and test docstrings. No counter, no
state, no surface.

---

## Truth-telling check: what the app says vs what it does

Verified, because you flagged it: **"Stop listening" and "Pause for 15 minutes"
do not pause the pendant, and the screen says she is not listening while pendant
audio streams to Deepgram.**

- `SettingsView.pause(minutes:)` (`:628-633`) and `stopNow()` (`:623-626`) both
  call `session.stopListening()`.
- `AnticipySession.stopListening` (`AnticipyApp.swift:1167-1170`) sets
  `keepListening = false` and calls `listener.stop()`. It touches nothing else.
- Pendant transcription is keyed **only** on
  `session.isSignedIn && pendant.state == .connected`
  (`AnticipyApp.swift:69-76`). Neither `keepListening` nor
  `listeningPauseUntil` appears anywhere in that `.task(id:)`.
- `SettingsView.listeningState` (`:597-612`) reads only `session.listener.*` and
  returns **"I'm not listening."**

So with a pendant connected, both controls leave BLE Opus flowing to
`wss://api.deepgram.com` while the one screen a person opens to make it stop
reports silence. `research/2026-08-24-deepgram-leak.md` already documents the
full ten-step path and confirms `/transcription/token` is live in production
(401, not 404).

**Honest scoping:** this only bites a stranger who has a pendant, and onboarding
says twice that they do not need one (`OnboardingView.swift:410`,
`ContentView.swift:879-881`). If the stranger week is run phone-only, this is
not a week-ender. If a pendant is handed over, it is the most serious
truth-telling defect in the product.

---

# What will break the stranger week

Ranked by how early it bites.

**1. Sign-up hour — the phone number is silently wrong for anyone outside
NANP.** `AnticipyApp.swift:577-584`. Texts are the product; a stranger with a
mangled number gets zero of them and no error. Bites at minute two, discovered
on day three when they wonder why she never texts.

**2. Sign-up hour — a reused phone skips onboarding entirely.**
`AnticipyApp.swift:9` (`hasOnboarded` is device-global). The mic is never
started, so she hears nothing all week. Highly likely, because a cable install
means the phone passed through someone else's hands first.

**3. Hour one — the extension a stranger installs is 0.8.4 against an app
expecting 0.11.0, and the app's own fix instruction cannot work.**
`overnight/is_it_live.py` already reports this: *served 0.8.4, source 0.11.0*.
The banner (`ContentView.swift:629-631`) tells them to press Reload; Reload
changes nothing and there is nothing newer to download. Permanent warning, no
exit.

**4. Hour one — nothing tells them to install the extension until an errand has
already failed to run.** `ContentView.swift:221-223` requires
`!handling.isEmpty`. The hands are the only executor, and the product's first
day is designed to discover that fact by failing.

**5. Day one — the install guide names a screen that was deleted and a Settings
section that was renamed.** `setup.html` Step 5 vs `OnboardingView.swift:14-20`
and `SettingsView.swift:251`. A stranger following instructions correctly
concludes they broke something.

**6. Day one, 1am — the welcome text has no quiet-hours guard.**
`worker.py:3177` vs `worker.py:53`. The product's first words can arrive in the
middle of the night, which is precisely the "makes them say what?" failure the
definition of done forbids.

**7. First time an errand goes wrong — Stop is a one-way trip to "Stopping…".**
`ContentView.swift:1742`, `:1802-1808`. The control that exists so they can
stop a runaway run away from their desk is the one control with no failure
surface.

**8. First time they try the mail read — it can never complete.** The live
0.8.4 extension has no supervised-read code, and `queueJob` never sets
`workflow_id`, so the row is unclaimable twice over. Costs the most invasive
consent in the product for a guaranteed nothing.

**9. All week — every line is unattributed, because enrollment is never
offered.** `SettingsView.swift:583-585` is the only route.
`research/2026-08-24-engine-options.md:254` calls the 0% certain. This does not
stop the week; it makes the week's data much harder to read, and it is the
named cause of four of six bad acts on the only call ever scored.

**10. All week — no consent artifact, no STOP handler, no 10DLC.** Not a
technical break; a real exposure the moment a stranger mistypes a digit.

**11. Whenever it happens — approvals, receipts and undo are not what WIRE IT
ALL step 1 describes.** Undo does not exist; receipts render `result` instead
of the server-verified `receipt`; the done-text has no photo because no MMS
path exists; the clean-day counter does not exist. Three of the card's five
steps have no implementation to test.

---

# What I could not determine without a device

1. **Whether the cable install actually succeeds on a stranger's phone.**
   Signing, the team-`49T86P9XGW` provisioning profile, whether the stranger's
   UDID is registered, and how long the profile lasts before the app refuses to
   launch mid-week. If a free/personal profile is used, it expires in 7 days —
   exactly the length of the stranger week. Someone with the Mac must confirm
   which profile type is used.

2. **Whether the Twilio account is trial or paid.** Nothing in the repo
   branches on it and nothing surfaces it. On a trial account, a cold
   stranger's unverified number silently fails every send with the failure
   visible only on worker stdout. One glance at the Twilio console settles it,
   and it decides whether the week produces any texts at all.

3. **Whether production's brain is running this brain.** `is_it_live.py`
   byte-verifies the extension; `is_the_brain_live.py` exists precisely because
   the worker has no served artifact, and its header documents the 2026-08-18
   case where a correct guard had been committed seventeen hours before the
   failure and simply was not running. I confirmed the backend hooks are
   deployed by probing routes. I could not confirm the worker's code, and I did
   not run `is_the_brain_live.py` because it reads live owner rows.

4. **Whether the speaker engine works on a real phone even once enrolled.**
   `SpeakerTagger.available` is `embedder != nil`, and the embedder only exists
   behind `#if canImport(SherpaOnnx)` (`Audio/SpeakerTagger.swift`,
   `VoiceEmbedderFactory.make`). The package is pinned by git revision
   `00ad9a19a6…` (`project.yml`) and the 26 MB model is in the Resources build
   phase, so it *should* link — but `docs/BRIEF.html` §9 says live-phone quality
   is unmeasured, bench numbers only, and TestFlight rejects builds carrying
   these frameworks. Whether it links, loads and judges correctly on the
   stranger's actual device is a device question.

---

## One thing worth saying plainly

Six of the nine dead ends above are not logic bugs. They are **drift between
what is deployed and what is in the tree**, and between what the documentation
says and what the screens are called. The live extension is three minor versions
old; the committed zip is four files stale against its own source; the live
setup page is the pre-rename copy; the guide points at a screen deleted in a
refactor; the app's version pin was found rotted three versions shut on
2026-08-24. `overnight/is_it_live.py` already goes red on the biggest one.

Per HARNESS-LAWS Law 3 — nothing is fixed until its gate leg is green against
LIVE — the cheapest work before the stranger week is not new code. It is
rebuilding the zip, redeploying `pb_public`, and getting `is_it_live.py` to
three greens.
