# The call recorder — what iOS permits, what it refuses, and what to build instead

> Status: SPEC, carrying a **NO-GO on the card as written** and a GO on three
> quarters of what the card is for. Not a plan, no task list, no code.
> Card: *"Build Anticipy phone call and FaceTime recorder (iOS)"* — assigned
> Jose, created by Omar. Note: *"iOS app to detect phone calls and FaceTimes,
> start recording automatically, and sync notes/recordings with the pendant and
> central brain."* Step: *"Build widgets so that you press and tap and it starts
> recording."* It is **not** one of the twelve cards in
> `docs/BOARD-STATE-2026-08-24.md`.
> Laws that bind: `HARNESS-LAWS.md` 1, 3, 4, 5, 6 · `design/LOCAL-FIRST.md`
> rules 1, 3, 5.
> Adjacent and load-bearing: `docs/FOLLOWUPS.md` item 8,
> `research/2026-08-24-deepgram-leak.md`, `CAPTURE-ARCHITECTURE.md` Levels 0–3,
> `docs/FIFTY-MOMENTS-STATUS.md` moments 11, 13, 14, 16.
>
> **Sourcing rule used throughout.** Every external claim is either quoted from a
> URL fetched in this session, or explicitly marked as carried from the research
> lens / from my own knowledge and not independently re-verified. Every repo
> claim was read at the file this session. Where I could not determine something,
> §11 says so and names who settles it.

---

## 1. The answer first

**A third-party iOS app cannot record the audio of a phone call or a FaceTime
call. There is no public API for it in 2026, there is no entitlement to request,
and there is no configuration of AVAudioSession that changes it.** This is not
"hard", not "needs research", not "challenging". It is refused by the operating
system, and the refusal is already measured on this repo's own hardware.

Four independent confirmations, all fetched this session:

| Source | What it says |
|---|---|
| Apple DTS, [forums/thread/666607](https://developer.apple.com/forums/thread/666607) — a developer asking specifically about an App Store app that records incoming and outgoing telephone calls | *"There's no supported way to do this."* And, on the request for a written policy: *"As as I know Apple has never published an official document saying why that's the case."* |
| Apple DTS, [forums/thread/651540](https://developer.apple.com/forums/thread/651540) | `AVSpeechSynthesizer.mixToTelephonyUplink` can *insert* speech into an outgoing call — *"However this is the only functionality that we have (as far as I know) regarding modifying the call audio."* And: *"I also don't know of a way to 'read' the audio from the call, I am pretty sure that's not possible."* |
| [Handling audio interruptions](https://developer.apple.com/documentation/avfaudio/handling-audio-interruptions) | *"System alerts, such as receiving an incoming phone call, interrupt the active audio session."* |
| [RPRecordingErrorCode](https://developer.apple.com/documentation/replaykit/rprecordingerrorcode) | ReplayKit ships a dedicated error constant, `activePhoneCall` — *"Unable to record due to an active phone call."* ReplayKit does not merely omit call audio; it refuses to record **anything** while a call is active. |

The shape of the platform is a **one-way door**: an app may write into the call
uplink and may not read from it. That is the single sentence to remember.

**This repo has already measured the same fact, on a real device, and built
around it.** While a call owns the session, `AVAudioEngine`'s input node reports
0 Hz and 0 channels, and `installTap` with that format raises an `NSException`
that no `try?` can catch:

```swift
guard format.sampleRate > 0, format.channelCount > 0 else {
```
— `app/ios/Anticipy/Audio/PhoneListener.swift:439`

The watchdog ranks the interruption leg **first**, above the dead-engine leg,
and the comment above it explains why retrying is worse than standing still:
*"45 [recognition tasks] in three minutes, not one of which can hear anything."*
(`app/ios/Anticipy/Audio/ListenWatchdogPolicy.swift:88`). The audio layer was
deliberately designed to give up during a call. The card asks to undo a decision
that was made because the alternative was measured and failed.

**Three consequences the card's own wording has to absorb.**

1. **"Start recording automatically" is out.** Not the timing — the recording.
   Not even *half* of it: the app cannot record the owner's own side either,
   because the microphone is what iOS takes away. "Surely we can at least get
   our own voice" has the same answer as everything else: the input node is
   0 Hz.
2. **"FaceTimes" is out twice over.** The same audio-session block applies, and
   Apple's *own* recorder covers *"a phone call or FaceTime audio call"*
   ([support.apple.com/en-us/121583](https://support.apple.com/en-us/121583),
   fetched this session) — it does not name FaceTime **video**. Inference from
   that wording, not a cited exclusion: video FaceTime is recorded by nobody,
   including Apple.
3. **"Sync notes/recordings … with the central brain" is a LOCAL-FIRST
   violation as written**, independent of iOS. `design/LOCAL-FIRST.md` rule 1:
   *"RAW AUDIO NEVER LEAVES A DEVICE. Not to Deepgram, not to anyone."* Rule 3:
   *"What travels is the smallest conclusion that works."* Recordings syncing to
   the brain is the thing the law exists to forbid. Flagging this per LAW 6 even
   though nobody asked for a review: **if this card ships as literally worded, it
   ships a second Deepgram.** What may sync is text and conclusions, which is
   what already syncs today.

**What is NOT blocked, and is the reason this card should not simply be closed:**
detecting a call is fully supported and unprivileged; a one-tap Control Center
trigger is fully supported; and there is a route to *both sides of a call, on
device, lawfully* that this product is unusually well placed to take, because it
already has a second microphone in the design. §2, §3 and §4.

---

## 2. Two capabilities, one card: detecting is not recording

The card conflates them, and they have opposite verdicts. Detection is the
shippable core.

### 2.1 Detection is available to any app, with no entitlement

[`CXCallObserver`](https://developer.apple.com/documentation/callkit/cxcallobserver)
(fetched this session, iOS 10.0+, **not deprecated**):

> "VoIP apps typically interact with the [`CXCallObserver`] returned by the
> `callObserver` property of a `CXCallController`. However, **any app can create
> a new `CXCallObserver` object to be notified of any calls activity on the
> system.**"

And [`CXCall`](https://developer.apple.com/documentation/callkit/cxcall):

> "You don't instantiate `CXCall` objects directly. Instead, `CXCall` objects
> are **created by the telephony provider when an incoming call is received or
> an outgoing call is initiated.**"

So the widely-repeated forum claim that CallKit cannot see ordinary cellular
calls is wrong. The deprecated predecessor points the same way: `CTCallCenter`
carries *"Getting call information in Core Telephony is no longer supported. Use
[CXCallObserver] instead."* (carried from the lens; I did not re-fetch it.) **Do
not reach for CoreTelephony.**

### 2.2 What detection actually hands you — thin, and thin on purpose

`CXCall`'s entire property surface, verified this session: `uuid`, `isOutgoing`,
`hasConnected`, `hasEnded`, `isOnHold`. That is all.

- **No phone number. No name. No handle. No duration.** Anticipy can know *"an
  outgoing call started at 14:02 and ended at 14:19"* and nothing whatsoever
  about who was on it.
- That thinness is a feature for this product, not a limitation to work around.
  It is exactly `design/LOCAL-FIRST.md` rule 3's "smallest conclusion that
  works", and it means the call sense can never leak an identity it does not
  have.

### 2.3 The real limit on detection: a suspended app observes nothing

`CXCallObserver` delivers to a live process. This repo has already measured that
a call outlives the app's background runway:

> *"Held only across an interruption, and worth ROUGHLY THIRTY SECONDS … What
> thirty seconds actually covers: Siri, a notification tapped and dismissed, a
> fifteen-second call declined … A ten-minute call still suspends the app"*
> — `app/ios/Anticipy/Audio/PhoneListener.swift:137,149-151`

`Info.plist` declares `UIBackgroundModes = [bluetooth-central, audio]` and
nothing else — no `voip`, no `processing`, no `fetch`
(`app/ios/Anticipy/Info.plist`). `audio` buys execution only while audio is
actually flowing, and during a call none is.

So: **call *start* is reliably observed** (the app is usually awake, or the
interruption notification wakes the same code path), and **call *end* is not
reliable for exactly the long calls worth remembering**. Two mitigations, both
already in the tree or adjacent:

- `ListenResumePolicy` already covers the "app was suspended, owner reopens it"
  case, and its header records the exact incident this fixed
  (`app/ios/Anticipy/Audio/ListenResumePolicy.swift:1-40`). A call boundary
  recovered late is still a usable boundary — `CAPTURE-ARCHITECTURE.md`'s
  ordering rule is that every boundary decision keys off capture time, never
  arrival time, precisely so late facts still land in the right place.
- With a pendant connected, `bluetooth-central` keeps the process being woken
  for BLE notifications. Whether that is enough to keep an observer alive across
  a forty-minute call is **unverified** — §11, question 3.

### 2.4 What detection alone unlocks — this is the shippable core

None of these need call audio. All of them are blocked today only by the absence
of a call sense.

1. **She stops lying about the silence.** Today, during a call, the home card
   says *"Mic interrupted, taking it back…"* and the briefing says *"Something
   else has the microphone right now."*
   (`app/ios/Anticipy/Audio/ListenControlPolicy.swift:24-27`). Honest, but it
   describes a mechanism. With a call sense she can say the true thing: *"You're
   on a call — I can't hear it. I'm back when you hang up."* That is a MOUTH-grade
   upgrade for one `if`.
2. **A real conversation boundary, for free.** `CAPTURE-ARCHITECTURE.md` Level 3
   is built entirely on capture-time silence deciding segment boundaries. A call
   start and end are *ground truth* boundaries — better than any silence
   heuristic, and available at zero model cost. This is the SORTER card's
   dependency arriving early.
3. **The meeting posture stops guessing.** Today it arms on line density
   (`brain/worker.py:2185-2209`, `meeting_heard`, per
   `docs/FIFTY-MOMENTS-STATUS.md` moment 11). A call is a fact about the
   telephony stack, not a threshold over ambient audio. `docs/FOLLOWUPS.md`
   item 5 records the live failure mode density has — *"Steady >=3-lines/180s
   ambience (a TV) can sustain the meeting latch"*. A call sense does not fix
   the TV, but it removes calls from the set of things density has to infer.
4. **The post-call moment becomes addressable.** "Call ended, and it was long"
   is the only trigger under which route C (§3.3) makes sense. Without a call
   sense there is no such moment and route C degrades into a timer, which
   `design/NO-MORE-TIMERS.md` exists to refuse.
5. **The pendant lane can arm itself** when a call connects (§3.1), so the owner
   is not asked to think about it at the moment they are least able to.

**LAW 1 check, stated before anyone objects.** A `CXCall` callback is a fact
delivered by the OS about the telephony stack. It is not a pattern over the
owner's words and it decides nothing about what anything MEANS. It is squarely
in LAW 1's permitted "senses — audio plumbing, timestamps, transport" category.
The line that must not be crossed: **"a call is happening" may be handed to the
model as context; it may never itself flip a triage rule.** A call fact becoming
`if on_call: suppress` is a threshold deciding meaning, and would be a violation
wearing a sense's clothes.

---

## 3. The adjacent thing that satisfies the intent

The underlying want is not "a recorder". It is **"remember what was said on a
call"** — the same want behind fifty-moments 11, 13, 14 and 16, which are
scored today as if a call were audible and are not:

| Moment | Text | Status today |
|---|---|---|
| 11 | 40-min work call → zero texts during, then ONE message after | partial |
| 13 | *Mid-call* someone asks "what's 4pm eastern for you?" → instant answer | **GAP** |
| 14 | A colleague *on the call* asks the OTHER person to review a doc → nothing lands for you | partial |
| 16 | "I'll bring the drill Sunday" *on Tuesday's call* surfaces Saturday | **GAP** |

Read `docs/FIFTY-MOMENTS-STATUS.md:28-33`. Moments 13 and 14 require hearing
**the other person**, mid-call. On the phone's own microphone that is
structurally impossible, forever, for the reasons in §1 — no amount of brain
work reaches them. **This card is the only route to those two moments, and only
via §3.1.** That is the honest reason not to close the card outright.

Five routes, ranked. For each: what it gives, what it costs, whether it is
permitted.

### 3.1 RECOMMENDED — the pendant hears the room, on speakerphone

**What it gives.** Both sides of the call, as audio in a room: the owner
directly, the far end out of the phone's speaker. It is the only route in this
document that reaches moments 13 and 14. It is real-time. It works for FaceTime
video, FaceTime audio, cellular, WhatsApp, anything that makes sound.

**Why it is permitted.** The pendant is a separate microphone on a separate
device. It is not subject to the phone's audio session at all, so the 0 Hz guard
never applies to it. Nothing here is a private API, an entitlement, or a
workaround of an Apple restriction — it is a microphone in a room, which is what
Anticipy already is.

**Why it fits this product specifically.** `CAPTURE-ARCHITECTURE.md` Levels 0–2
already say the pendant is a microphone and *the phone does all processing*.
`design/LOCAL-FIRST.md`'s scoreboard already calls the pendant path *"law-abiding
by design"*. This route asks for no new architecture — it asks for the
architecture that is already written down to actually be true.

**What it costs, stated rather than hidden:**

1. **Speakerphone.** The far end must be in the room. iOS can make this the
   default: Settings → Accessibility → Touch → Call Audio Routing → Speaker
   (carried from the lens; not re-verified this session). It is a real behaviour
   change for the owner and it is not always socially available.
2. **A flashed pendant.** `research/2026-08-24-deepgram-leak.md` establishes a
   physical pendant exists and pairs in two taps — and also that the repo's
   comfortable belief that the pendant path is "latent" is wrong.
3. **The Deepgram lane must be closed first, and it is not.** `docs/FOLLOWUPS.md`
   item 8 and §6 below. Shipping this route on today's wiring means every word of
   every call the pendant hears goes to `wss://api.deepgram.com`
   (`app/ios/Anticipy/Audio/TranscriberClient.swift:27`). That is not a footnote;
   it is a blocking dependency.
4. **Two unverified platform assumptions**, which is why this is a recommendation
   and not a plan. §11 questions 2 and 3.
5. **Consent.** Everybody in the room, and the person on the other end, is being
   recorded by a device that does not announce itself. §5.

**Honest statement of the risk.** That BLE reception and on-device speech
recognition both keep working while telephony owns the phone's microphone is an
**inference from the API contracts, not an Apple statement, and not measured on
this hardware**. The reasoning: BLE is a data transport, not audio;
`LocalTranscriber` feeds `SFSpeechAudioBufferRecognitionRequest` with buffers it
is handed rather than opening a capture route
(`app/ios/Anticipy/Audio/LocalTranscriber.swift:35-37`). Plausible, standard, and
**not proven**. One device test with a flashed pendant and a live call settles it
in ten minutes. Nothing about this route should be promised to Omar until it has.

### 3.2 Apple's own Call Recording, imported by hand

**What it gives.** The real call, both sides, at full quality, with Apple's
on-device transcript already attached — and with the consent problem solved by
Apple rather than by us.

**What is verified.** [support.apple.com/en-us/121583](https://support.apple.com/en-us/121583),
fetched this session: *"Learn how to record a phone call or FaceTime audio call
on your iPhone starting in iOS 18, or in the Phone app starting in iPadOS 26 or
macOS Tahoe."*

**What is carried from the research lens and NOT re-verified by me** — the iPhone
User Guide page ([record and transcribe a call](https://support.apple.com/guide/iphone/record-and-transcribe-a-call-iph57c6590e9/ios))
is a JavaScript shell; three fetch attempts this session returned only the
guide's navigation, so I could not re-read the article text. Per the lens:

- Both parties hear an audible notice; recordings land in a **Call Recordings**
  folder in Notes with an on-device transcript.
- The only exports are user-driven UI actions: *"Tap […], tap Save Audio Files"*
  / *"tap Share Audio"*; transcript export is *"Add Transcript to Note or Copy
  Transcript"*.
- It is **unavailable** in a named list of regions including the entire European
  Union, and can be switched off in Settings → Apps → Phone → Call Recording.
  US and Canada are supported.

Treat that region list as directional until someone re-reads the page in a
browser. It does not change the ranking either way.

**What it costs.**

1. **It is manual, per call, forever.** There is no programmatic read: iOS has no
   public Notes framework, and (per the lens, confidence "likely") every Notes
   Shortcuts action touching call recordings is navigation-only. There is also no
   Shortcuts personal-automation trigger for a call starting or ending. Both are
   **absence proofs**, not cited denials — nobody can prove an API does not exist
   by reading docs. But the absence is consistent across two independent
   searches and matches the shape of §1.
2. **Roughly four taps per call**, at the moment the owner is least likely to
   bother.
3. **It needs an ingestion path this app does not have** — a Share Extension, a
   second Xcode target, an App Group, and a file→text transcriber. §6.
4. **Not real-time.** Moments 13 and 14 stay dead.

**Permitted:** yes, entirely. It is Apple's own consented recording, shared by
the owner through the system share sheet. Zero App Review risk. It is the
*safest* route in this document and the *least likely to be used twice*.

### 3.3 The post-call voice note

**What it gives.** The owner's own account of what was decided, in the owner's
words, thirty seconds after hanging up. Not the call — the conclusion.

**What it costs.** Recall is lossy and self-serving; it never contains the thing
the *other* person said that the owner did not notice, which is most of what
moments 14 and 16 are about.

**Why it is nonetheless ranked third and not last.** It is the only route that is
**already almost entirely built**. It needs the call-end sense from §2 and the
one-tap trigger from §4, and then it composes out of machinery that ships today:
`PhoneListener` → `heard(_:from:)` → the brain. No new target, no entitlement, no
decoder, no law to amend. It is the cheapest thing on this list by an order of
magnitude and it should ship first for that reason alone.

**Permitted:** yes, trivially. It is the microphone the owner already granted,
recording the owner, at a moment the owner initiated.

### 3.4 Explicit-start recording of in-person meetings

Already the product. The widget (§4) makes it one tap instead of three, and it
is the honest target for the card's widget step. Listed here so the ranking is
complete, not because it is new work beyond §4.

### 3.5 REJECTED — carry the call yourself as the default calling app

This is the one route that would yield genuine raw call audio through a
sanctioned door, so it is recorded with its price rather than omitted.

**The mechanism, verified this session** at
[Preparing your app to be the default calling app](https://developer.apple.com/documentation/callkit/preparing-your-app-to-be-the-default-calling-app):
iOS/iPadOS **18.2+**; entitlement `com.apple.developer.calling-app` set true;
`UIBackgroundModes` must contain `voip`; the app links CallKit or
LiveCommunicationKit. *"A calling app handles `tel:` URLs the system sends to
it"* — it services them by placing a **VoIP** call, which the app itself carries,
so the app legitimately owns the media. There is no system call to be interrupted
by, because there is no system call.

**Why it is rejected for Anticipy — five reasons, any one sufficient:**

1. **It makes Anticipy a telephone company.** Every call the owner places routes
   through a PSTN gateway Anticipy operates and pays for, under a number
   Anticipy owns.
2. **LOCAL-FIRST rule 1.** The media transits a vendor **of Anticipy's
   choosing**. The "the carrier already carries it" argument is not good enough
   here: the carrier is a regulated common carrier the owner already chose; a
   SIP gateway is a third party Anticipy hands his life to. This repo has already
   killed exactly one vendor on exactly this law (Deepgram, `design/LOCAL-FIRST.md`
   scoreboard row 1: *"the earlier idea of moving phone STT to Deepgram is DEAD
   on this law"*). Doing it again without Omar amending the law in writing would
   be the same mistake with a better excuse.
3. **It covers a third of the card.** `tel:` URLs are **outgoing** calls placed
   from a contact card. Incoming cellular calls still ring in the Phone app and
   remain invisible. FaceTime is untouched entirely.
4. **The documented fallback erases the benefit.** *"When you let the
   conversation fall back to the system, it handles the conversation as a
   cellular network conversation."* Every fallback is a call captured by nobody,
   and the owner cannot tell which kind they just had.
5. **The iOS 26 default *dialer* variant does not help.**
   [`com.apple.developer.dialing-app`](https://developer.apple.com/documentation/livecommunicationkit/preparing-your-app-to-be-the-default-dialer-app)
   (verified this session) is the more powerful surface — it uniquely grants
   metadata: *"your app can access the device's conversation history, from the
   moment your app became the default dialer app"* — but it exposes **no audio**,
   and it is region-locked for development: *"To test your app's behavior as a
   default dialer app, your Apple Developer account needs to be registered in the
   European Union (EU), and the test device must be located within the EU."*
   Note the arithmetic: the EU is also where Apple's own Call Recording (§3.2) is
   unavailable, so the two never combine anywhere on Earth.

**If Omar overrules this**, the amendment he is signing is to `design/LOCAL-FIRST.md`
rule 1, in writing, naming the vendor — not a judgement call made inside a spec.

### 3.6 REFUSED — the conference-bridge recorder

Every shipping App Store call recorder works this way: the owner puts the party
on hold, dials the vendor's recording line, taps Merge Calls, and the vendor's
server records its own leg. TapeACall's own listing says it plainly —
*"TapeACall requires your carrier supports 3-way calling"* (carried from the
lens; not re-fetched).

It is App-Store-legal and it is the only mechanism that reliably yields raw
both-sides call audio without becoming a phone company. **It is refused here on
the law, not on feasibility**: it ships the owner's conversation to a third
party's servers, which is `design/LOCAL-FIRST.md` rule 1 head-on. Named
explicitly so that the next agent who rediscovers it finds this paragraph instead
of proposing it again.

### 3.7 Undetermined — ScreenCaptureKit on iOS 27

New this session, and worth flagging because it changes the ReplayKit story:
[`RPRecordingErrorCode`](https://developer.apple.com/documentation/replaykit/rprecordingerrorcode)
now carries *"deprecated as of iOS 27.0 … Apple recommends using
**ScreenCaptureKit** instead"*, and
[ScreenCaptureKit](https://developer.apple.com/documentation/screencapturekit)
is listed as **iOS 27.0 (beta)** — previously macOS-only. Its
`SCStreamConfiguration` exposes `capturesAudio`, `captureMicrophone`,
`microphoneCaptureDeviceID` and `excludesCurrentProcessAudio`, all marked
available on iOS.

**I could not determine whether ScreenCaptureKit on iOS is subject to the same
active-call refusal**, because Apple's iOS-specific ScreenCaptureKit
documentation does not discuss telephony, and this session's WebSearch budget was
exhausted (200/200) before I could look for a WWDC session or release note that
does. Two reasons not to bank anything on it: the restriction ReplayKit's error
constant *described* has never been documented as lifted — only the constant is
deprecated; and this app targets iOS 16.0 (`app/ios/project.yml:5`), so an iOS 27
beta API is three floors above the product. **Revisit when iOS 27 ships.** Do not
plan against it. → §11, question 8.

---

## 4. The widget step — buildable, and the only step of the card that is

> *"Build widgets so that you press and tap and it starts recording."*

**Verdict: GO.** This is real, current, and unblocked — and it is the part of
the card that most directly serves route 3.3 and 3.4.

**What Apple provides**, verified this session at
[Creating controls to perform actions across the system](https://developer.apple.com/documentation/widgetkit/creating-controls-to-perform-actions-across-the-system):

> "A control allows your app to execute an action, launch your app to a specific
> view, or launch a locked camera capture extension from **Control Center, the
> Lock Screen, or by using the Action button**."

> "Controls can be buttons or toggles: buttons perform an action, and toggles
> perform an action and switch between two states."

> "Use `AppIntent` or `OpenIntent` for control buttons and `SetValueIntent` for
> control toggles."

A **toggle** is the right shape: listening is a two-state fact the owner owns,
and `SetValueIntent` is what Apple names for it.

### 4.1 What it may legitimately record

The room, through the phone's microphone — the same capture `PhoneListener`
already performs, started without walking to the app. **Not a call.** Everything
in §1 still applies: pressing the control during a call starts a capture that
hears 0 Hz.

That last sentence is the entire design problem of this step, and this repo has
already written the law for it. `ListenControlPolicy.swift:17-18` closed a defect
on **2026-08-25** whose lesson transfers exactly:

> "THE RULE THIS FILE ENFORCES: **a control's label describes what tapping it
> does.** Not what is happening."

and the incident that produced it:

> "an owner who opens the app during a call, sees a pulsing dot beside a sentence
> and taps it to hurry things along has turned listening off until they toggle it
> back by hand."

**Therefore, binding on the implementer:** the Control Center control must be
driven by `ListenControlPolicy.face` and by nothing else. Not a second copy of
the logic living in a widget target — the same value, read across the App Group.
A control is exactly the surface where the label/action drift this file was
written about would reappear, and it would reappear on the Lock Screen where the
owner has the least context.

### 4.2 The one thing I could not determine, and the safe fallback

**Can a control's `AppIntent` start and sustain microphone capture without
launching the app?** I could not verify this. The intent's `perform()` runs in
the widget extension's process, and a short-lived extension holding a long-lived
recording `AVAudioSession` is not something Apple's control documentation
addresses either way. The doc confirms controls perform work — *"The app intent
requires a `perform()` function in which you carry out actions"* — but says
nothing about audio capture, and this is precisely the sort of thing that fails
on device rather than at compile time.

- **The safe shape, if it cannot:** `openAppWhenRun = true` (or an `OpenIntent`).
  Tap → Anticipy launches → listening starts. Still one tap. Still "press and tap
  and it starts recording". Slower and less magical, and honest.
- **The two-minute test that settles it:** iOS ships a first-party Voice Memos
  control. Add it to Control Center, tap it, and watch whether Voice Memos opens.
  Apple's own answer to the same problem is the best available precedent.
  → §11, question 5.

### 4.3 What it costs in this tree, which is more than it looks

`app/ios/project.yml` declares **exactly one target** — `Anticipy`, `type:
application` (`:219`). There is no extension target, no `.entitlements` file, and
no App Group anywhere in the project. A control widget therefore brings:

- a new Widget Extension target in `project.yml` (and `build_on_mac.sh` must not
  be run — `docs/` and this repo's memory both record that it overwrites the
  committed project);
- an App Group, so the extension and the app share listening state;
- an availability floor: controls are iOS 18+ (**my own knowledge, not verified
  this session** — the `ControlWidget` symbol page 404'd on two path guesses).
  The app targets iOS 16.0 (`project.yml:5`), so the widget extension carries its
  own higher floor and the app's floor does not move. The compiler settles this
  the moment someone writes it.

**Consent note:** starting a recording from a control still lands under App Store
guideline 2.5.14 (§5). The system's orange microphone indicator is a real
system-provided visual indication, and the mic permission is the explicit
consent — but the control must not be able to start a *silent* capture the owner
cannot see from the Lock Screen.

---

## 5. Consent and notice, and the recommended default

**App Review.** There is **no App Store guideline named "call recording"** — I
read the current guidelines text this session and searched it; the phrase does
not appear, and the only guideline mentioning phone calls at all is 2.5.12, which
is about *blocking* spam numbers. The block in §1 is technical, not a written
policy ban. What does bind, verbatim from
[the guidelines](https://developer.apple.com/app-store/review/guidelines/):

> **2.5.14** Apps must request explicit user consent and provide a clear visual
> and/or audible indication when recording, logging, or otherwise making a record
> of user activity. This includes any use of the device camera, microphone,
> screen recordings, or other user inputs.

> **2.5.1** Apps may only use public APIs and must run on the currently shipping
> OS. … Apps should use APIs and frameworks for their intended purposes …

2.5.14 alone makes *"start recording automatically"* — the card's own phrase — a
rejection risk even for room audio, independent of everything in §1.

**Law.** Carried from the lens and **not legal advice**: US federal law is
one-party consent (18 U.S.C. § 2511); roughly eleven-to-twelve states require
all-party consent — California, Delaware, Florida, Illinois, Maryland,
Massachusetts, Montana, Nevada, New Hampshire, Pennsylvania, Washington; Canada
is one-party under Criminal Code s.184(2)(a). Secondary source:
[RCFP's recording guide](https://www.rcfp.org/introduction-to-reporters-recording-guide/).
Apple's own recorder resolves this by announcing itself **audibly to both
parties**. A silent recorder does not, and route 3.1 — a pendant listening to a
speakerphone call — is exactly a silent all-party recording of someone who never
consented.

**Recommended default, and it is the conservative one:**

1. **Nothing auto-records.** The card's "automatically" is dropped on three
   independent grounds: it is impossible for calls (§1), it is a 2.5.14 risk for
   rooms, and it is the wrong product. Anticipy's whole interruption culture is
   that she earns each action with evidence.
2. **Route 3.1 arms, it does not record.** When a call connects, the pendant lane
   may become *available* with the owner told so in one sentence; the owner
   starts it. This is the same shape as the enrollment ask in
   `docs/superpowers/specs/2026-08-24-voice-capture-design.md` §5 — asked once,
   on evidence, declinable permanently.
3. **The other party is Omar's call, not this spec's.** Anticipy cannot inject
   audio into a call to announce itself — the one API that could
   (`mixToTelephonyUplink`) exists, and using it to announce a recording the far
   end did not agree to would be a strange first use. My recommendation: route
   3.1 ships only with an explicit in-product statement that the owner is
   responsible for telling the other party, and that in all-party-consent states
   they must. **Get counsel before shipping any recording feature.**
4. **What travels stays text.** Per LOCAL-FIRST rule 3 and §1 consequence 3: the
   brain receives lines and conclusions. No audio, no recordings, ever, on any
   route in this document.

---

## 6. What it depends on: **the ingestion path is dead**

Every route in §3 except 3.3 and 3.4 lands on the same missing plumbing. This is
the finding that should reorder the work, and all four legs were read at the file
this session.

**1. There is no path from an audio *file* to text anywhere in the app.** A grep
across `app/ios/Anticipy/` for `SFSpeechURLRecognitionRequest` and `AVAudioFile`
returns **zero hits**. Every transcript this product has ever produced came from
a live buffer stream. Route 3.2 hands the app an `.m4a` and there is nothing in
the binary that can read one.

**2. The only wired non-microphone transcriber is Deepgram, and it is a live
violation.** `TranscriberClient` opens
`wss://api.deepgram.com/v1/listen?encoding=opus…`
(`app/ios/Anticipy/Audio/TranscriberClient.swift:27`), is instantiated
unconditionally at `app/ios/Anticipy/AnticipyApp.swift:166`, and is fed raw
frames at `:1052` (`pendant.onOpusFrame = { frame in transcriber.send(opusFrame: frame) }`).
`docs/FOLLOWUPS.md:38-47` (item 8) records this as a shipped `LOCAL-FIRST` rule 1
violation, and `research/2026-08-24-deepgram-leak.md` establishes that the repo's
comfort — *"latent only because the firmware is BUILT_AND_VERIFIED_NOT_FLASHED"* —
**is wrong**: the path is reachable in two taps on hardware that exists, the
backend route that mints Deepgram credentials answers `401` (not `404`) on
production, and the app connects to *any* peripheral advertising the Omi service
UUID.

**3. The law-abiding replacement is never instantiated.**
`app/ios/Anticipy/Audio/LocalTranscriber.swift` sets
`requiresOnDeviceRecognition = true` and its header claims a Settings toggle. It
has **no call sites in app source** — its only appearances outside its own file
are in the dSYMs of archived builds.

**4. And it could not be plugged in as-is, because a decoder is missing.**
`PendantManager` emits **Opus** frames (`app/ios/Anticipy/BLE/PendantManager.swift:7`);
`LocalTranscriber.append(pcmBuffer:)` takes *"decoded 16 kHz mono PCM buffers"*
(`LocalTranscriber.swift:35`). A grep for any Opus decoder across
`app/ios/Anticipy/` finds none, and `project.yml` links no packages. **There is a
codec-shaped hole between the two halves of the local pendant path**, and the
Deepgram lane exists partly because that hole was never filled — Deepgram accepts
raw Opus, so nobody had to decode anything.

**Two smaller dependencies, for completeness:**

- **The event `source` vocabulary is a closed three-value set**, documented in
  three places: `phone_mic | pendant | typed`
  (`app/ios/Anticipy/AnticipyApp.swift:249-266`, `app/ios/README.md:12-15`,
  `brain/anticipy_core.py:1042-1043` and `:1268-1269`, `brain/worker.py:3584`).
  Any new capture source — an imported call recording, a widget-started
  session — is a fourth value that must be added deliberately at every one of
  those sites, and `anticipy_core.py:1269` is emphatic that it *"names WHICH
  MICROPHONE heard this line … It is not channel and must never be read as one."*
- **One Xcode target, no App Group** (§4.3). Both the Share Extension of route
  3.2 and the control of §4 are new targets.

**Consequence for sequencing.** Nobody should build a call recorder on top of a
dead ingestion path. The decoder plus `LocalTranscriber` plus a file→text entry
point is upstream of routes 3.1 and 3.2 both, and closing the Deepgram lane is
owed *before the pendant goes live* regardless of this card
(`docs/FOLLOWUPS.md` item 8). **That work is this card's real first step, and it
is currently owned by nobody.**

---

## 7. Go / no-go, with the cut line

**NO-GO on the card as written.** "Detect phone calls and FaceTimes, start
recording automatically, and sync notes/recordings with the pendant and central
brain" cannot be built: the recording half is refused by iOS (§1), and the
syncing-recordings half is refused by `design/LOCAL-FIRST.md` (§1.3).

**GO on a card that keeps the intent and drops the mechanism.** In order:

### Build now

1. **Close the ingestion hole** — Opus decoder, `LocalTranscriber` wired, the
   Deepgram lane off. Not glamorous, owed anyway (`FOLLOWUPS` 8), and everything
   good in this card is downstream of it. **If only one thing gets built, build
   this.**
2. **The call sense** — `CXCallObserver`, no entitlement, LAW 1-clean, and it
   immediately buys the honest "I can't hear a call" statement (§2.4.1), a real
   conversation boundary for the SORTER (§2.4.2), and the post-call moment
   (§2.4.4). Small, and it is the shippable core of the card.
3. **The control** (§4) — Control Center / Lock Screen / Action button toggle,
   driven by `ListenControlPolicy`, recording the room. This is the card's own
   widget step, delivered literally.
4. **The post-call voice note** (§3.3) — composes from 2 and 3, no new
   machinery.

### Build after a device test says yes

5. **The pendant on speakerphone** (§3.1) — the only route to moments 13 and 14,
   gated on §11 questions 2 and 3 and on step 1 being done.
6. **Share-extension import of Apple's Call Recordings** (§3.2) — gated on a
   file→text path existing, and worth doing only if the owner will actually use
   it twice.

### Drop

- **"Start recording automatically"** for calls — impossible (§1), and for rooms
  it is a 2.5.14 risk and the wrong product (§5).
- **FaceTime video capture** — nobody records it, including Apple.
- **Syncing recordings to the brain** — LOCAL-FIRST rule 1 and 3. Text and
  conclusions travel; audio does not.
- **The conference bridge** (§3.6) — refused on the law, named so it is not
  re-proposed.

### Revisit if any of these change

- Apple publishes an API or entitlement exposing call audio, or lifts the
  `activePhoneCall` refusal in ScreenCaptureKit's iOS form (§3.7).
- Shortcuts gains a personal-automation trigger for a call starting or ending —
  that alone would make route 3.2 nearly automatic.
- Apple exposes Call Recordings to App Intents or a framework.
- Omar amends `design/LOCAL-FIRST.md` in writing, which reopens §3.5.

**The one-sentence version for the board:** *the recorder cannot be built, the
detector can, the widget can, and the way Anticipy actually remembers a call is
the pendant listening to a speakerphone — which needs the Deepgram lane closed
first.*

---

## 8. Law compliance

- **LAW 1.** The call sense is a fact from the OS about the telephony stack —
  "senses", explicitly permitted. No regex, word list or threshold appears
  anywhere in this design. The named trap: a call fact may enter a prompt as
  context; it may never be wired as `if on_call: <behaviour>`, which would be a
  threshold deciding meaning with a sense's alibi (§2.4).
- **LAW 2.** No tape proposed. Nothing here is a string patch, so no `TAPE:`
  comment would be honest. If an implementer reaches for one — a substring test
  on a transcript to guess "this was a call" instead of asking CallKit — it needs
  a `tape_gate.py` leg and it is the wrong fix twice over.
- **LAW 3.** Almost nothing in this document can be proven in the repo. The 0 Hz
  guard, the watchdog and the thirty-second assertion are already-measured device
  facts. Everything proposed — the call sense firing, FaceTime being observed,
  BLE surviving a call, the control starting capture — is **device behaviour and
  is unproven until a device says so**. §11 names each test. No leg of this card
  may be called done from a green compile.
- **LAW 4.** This file is the record. The no-go, the rejected routes with their
  reasons, and the two absence-proofs are written down here rather than left in a
  conversation, so the next session does not re-derive them wrongly.
- **LAW 5.** Strict order, and §7 follows it: senses (the decoder, the local
  transcriber, the call sense) before anything structural. Writing a rule about
  how Anticipy behaves on calls while she is deaf during them would be tape by
  definition.
- **LAW 6.** Self-review in §10, adversarial by construction: the strongest
  argument against this recommendation is stated in §3.5 rather than omitted, and
  the recommendation's own riskiest assumption is flagged in §3.1 rather than
  buried.
- **LOCAL-FIRST rule 1.** Honoured by construction on every recommended route:
  the pendant's audio never leaves the phone once step 1 is done, the control
  records to the same on-device recognizer, and the imported call recording is
  transcribed on device. Two routes were **refused on this rule specifically**
  (§3.5, §3.6), and one currently-shipping violation is named as this card's
  blocking dependency (§6.2).
- **LOCAL-FIRST rule 3.** The call sense carries `uuid / isOutgoing /
  hasConnected / hasEnded` and no identity, because that is all iOS has. The
  smallest conclusion that works, for free.
- **LOCAL-FIRST rule 5.** This section is that statement. The "later" being named
  (per rule 5's own requirement) is: on-device transcription of pendant and
  imported audio, which is §7 step 1 and not a promise for a future quarter.

---

## 9. Decisions made without the owner

Recorded per LAW 4 so Omar can overrule them knowingly rather than discover them.

1. **The card is answered with a no-go rather than a partial build.** The
   alternative was to build detection, ship it as "the call recorder", and let
   the recording half stay quietly unfinished. That is how a card becomes
   permanently 80% done and how the board came to say zero progress against 44
   commits (`docs/BOARD-STATE-2026-08-24.md:8-9`).
2. **The pendant-on-speakerphone route is ranked above Apple's own Call
   Recording**, despite Apple's being safer and higher fidelity. Reason: it is
   the only route that reaches moments 13 and 14, and route 3.2's four-taps-per-
   call will be used twice and then never. Omar may reasonably disagree — if he
   values fidelity and consent over real-time, 3.2 becomes first.
3. **The default calling app (§3.5) is rejected rather than proposed with
   caveats.** It is the only sanctioned door to raw call audio, and rejecting it
   is a real cost. It is rejected because taking it requires amending
   `design/LOCAL-FIRST.md`, and a spec must not amend a law it is judged by.
4. **"Automatically" is dropped rather than reinterpreted.** It would have been
   easy to redefine it as "the pendant lane arms automatically" and claim the
   step. §5.2 arms; the owner still starts. Said plainly rather than finessed.
5. **The Deepgram lane is treated as this card's blocking dependency**, not as
   somebody else's problem to be worked around. Building route 3.1 on today's
   wiring would ship the exact violation the law was written for, at higher
   volume than the current one.

---

## 10. What would kill this

The adversarial pass, per LAW 6. Each of these would invalidate part of the
recommendation, and each is checkable.

1. **BLE or on-device speech does not survive an active call.** Route 3.1 dies
   entirely and the card collapses to detection plus the widget. This is the
   single largest risk in the document and it is unmeasured (§3.1, §11 q2).
2. **`CXCallObserver` does not report FaceTime.** Half the card's subject
   disappears from the sense. `CXCall`'s doc says objects are created "by the
   telephony provider", which may or may not include FaceTime's provider.
   Unverified (§11 q1).
3. **The app is suspended for the whole of a long call and observes neither end
   nor resume.** Detection degrades to "a call happened, discovered late", which
   is still usable under `CAPTURE-ARCHITECTURE.md`'s capture-time ordering but
   kills the real-time post-call prompt (§2.3).
4. **A control cannot start capture without launching the app**, and the owner
   experiences a full app launch on every tap. Survivable (§4.2), less magical
   than the card imagines.
5. **The owner will not use speakerphone.** Route 3.1 is socially unavailable in
   an office, a café, or any call with anything private in it. If the honest
   answer is "he will never do this", the ranking in §3 inverts and route 3.2
   becomes the recommendation.
6. **Apple's Call Recording is off or unavailable in the owner's region**, which
   removes route 3.2 as a fallback and leaves 3.1 alone.
7. **A future iOS removes `CXCallObserver`'s any-app access.** It has been stable
   since iOS 10 and is not deprecated, but the whole shippable core rests on one
   sentence in one doc page.

---

## 11. Handed back

Every open question, and who answers it.

1. **Does `CXCallObserver` report FaceTime calls — audio and video — or only
   cellular telephony?** The card names FaceTime; nothing in this document proves
   the sense sees it. `CXCall`'s "created by the telephony provider" is
   suggestive and not conclusive. A ten-minute device test: observer running,
   place a FaceTime call to a second device, see whether a `CXCall` arrives.
   **→ whoever holds `app/ios/` , on a device.**

2. **Does BLE reception + `SFSpeechAudioBufferRecognitionRequest` keep working
   while a call owns the phone's audio session?** The single assumption route 3.1
   rests on, and it is my inference from API contracts, not an Apple statement.
   One flashed pendant, one live call. Nothing about 3.1 may be promised until
   this is answered. **→ whoever has the pendant.**

3. **Does `bluetooth-central` keep the process alive across a forty-minute call,
   continuously enough to observe the call ending?** Distinct from question 2 —
   that one is about capability, this one is about runway. **→ same device
   session as q2.**

4. **Will the owner actually put calls on speakerphone?** This is a product
   question, not a technical one, and it decides whether §3.1 or §3.2 is the
   recommendation. Nobody in this repo can answer it. **→ Omar.**

5. **Can a Control Center control's `AppIntent` start and sustain microphone
   capture without launching the app?** Undetermined from the documentation
   (§4.2). Fastest answer available: add Apple's own Voice Memos control to
   Control Center, tap it, and watch whether Voice Memos opens. **→ whoever
   builds the widget, before designing around it.**

6. **What iOS version do WidgetKit controls require?** I state iOS 18 from my own
   knowledge; the `ControlWidget` symbol page 404'd on two path guesses this
   session and I did not verify it. The compiler settles it at build time and it
   changes only the widget extension's floor, not the app's. **→ whoever builds
   the widget.**

7. **Is the regional unavailability list for Apple's Call Recording accurate, and
   is the feature on for this owner?** The user-guide page is a JavaScript shell
   and did not yield its text to three fetch attempts; the list (including the
   whole EU) is carried from the research lens. Settle it by opening the page in
   a browser and by checking Settings → Apps → Phone → Call Recording on the
   owner's handset. **→ whoever owns the device; five minutes.**

8. **Does ScreenCaptureKit on iOS 27 lift the active-call refusal that ReplayKit
   named?** Undetermined (§3.7); this session's WebSearch budget was exhausted
   before I could look for a WWDC session or release note. Not urgent — the app
   floors at iOS 16 — but it is the one place Apple's position could have moved.
   **→ revisit when iOS 27 ships.**

9. **Is there genuinely no Shortcuts automation trigger and no App Intent for
   call recordings?** Both are absence proofs carried from the lens, not cited
   denials, and an absence proof from documentation is the weakest evidence in
   this document. If one exists, route 3.2 becomes near-automatic and jumps the
   ranking. **→ worth one pass through the Shortcuts app on a real device.**

10. **Who closes the Deepgram lane, and when?** `docs/FOLLOWUPS.md` item 8 says
    the decision is owed *before the pendant goes live* and names both options —
    build the phone-side Opus decoder, or amend the law and say so. It is
    currently owned by nobody, it is a live violation today
    (`research/2026-08-24-deepgram-leak.md`), and §7 step 1 of this card cannot
    start without the answer. **→ Omar decides the law; whoever holds
    `app/ios/Audio/` builds the decoder.**

11. **Does Omar accept the no-go, or does he want §3.5 — Anticipy as the default
    calling app — with `design/LOCAL-FIRST.md` rule 1 amended in writing to name
    the vendor?** That is the only trade in this document that buys real call
    audio, and it is his to make, not this spec's. **→ Omar.**

12. **Is legal counsel engaged before any recording feature ships?** §5's legal
    findings are secondary-source reporting, and route 3.1 is a silent all-party
    recording of people who never consented. **→ Omar.**

13. **Is any of it true of a real device and a real production brain?** LAW 3.
    Nothing in §7 is done until a device session and an `is_it_live`-style check
    say so. **→ every deploy.**
