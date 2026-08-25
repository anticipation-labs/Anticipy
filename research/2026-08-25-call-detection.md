# Call detection — what CXCallObserver gives, whether FaceTime is in it, and what the card becomes

**Date:** 2026-08-25 · **Tree:** `/Users/josegaelcruzlopez/Desktop/anticipy-omize`
· **Branch:** `jose_anticipy_system` · **Card:** *"Build Anticipy phone call and
FaceTime recorder (iOS)"* (Omar).

**Spec this executes against:**
`docs/superpowers/specs/2026-08-25-ios-call-recorder.md`. Its **NO-GO on the card
as written stands and is not re-litigated here** — no third-party iOS app can
record the audio of a phone call or a FaceTime. This document is the GO half:
step 2 of that spec's build order, the call sense.

**One-line verdict:** detection is real, unprivileged and now has a tested
decision in the tree; **whether it sees FaceTime is UNKNOWN and no document can
settle it** — only a device can; and the card has to be re-scoped from *recorder*
to *sense*.

---

## 1. What `CXCallObserver` actually gives

### 1.1 Any app may observe, with no entitlement

From Apple's documentation for
[`CXCallObserver`](https://developer.apple.com/documentation/callkit/cxcallobserver),
read this session through the documentation JSON endpoint because the HTML page
is a JavaScript shell that yields only its `<title>`:

> "VoIP apps typically interact with the CXCallObserver object returned by the
> callObserver property of a CXCallController instance. However, **any app can
> create a new CXCallObserver object to be notified of any calls activity on the
> system.**"

Availability, from the same source and confirmed against the shipped header:
**iOS 10.0+, iPadOS 10.0+, Mac Catalyst 13.0+, visionOS 1.0+, watchOS 9.0+**, and
**not deprecated**. `API_UNAVAILABLE(macos, tvos)` — so this is an iOS-side sense
only, which matters if anyone later wants the same thing on `app/macos/`.

The widely repeated forum claim that CallKit cannot see ordinary cellular calls
is therefore wrong, and `CTCallCenter` is the wrong door — its own page carries
*"Getting call information in Core Telephony is no longer supported. Use
CXCallObserver instead."* (carried from the spec; not re-fetched). **Do not reach
for CoreTelephony.**

### 1.2 The whole surface, read from the SDK rather than remembered

`CXCall.h`, iPhoneOS 26.2 SDK
(`/Applications/Xcode.app/.../iPhoneOS26.2.sdk/System/Library/Frameworks/CallKit.framework/Headers/CXCall.h`),
in full:

| Property | Type |
|---|---|
| `UUID` | `NSUUID *` |
| `outgoing` | `BOOL` (`isOutgoing`) |
| `onHold` | `BOOL` (`isOnHold`) |
| `hasConnected` | `BOOL` |
| `hasEnded` | `BOOL` |

That is the entire surface. **No phone number, no name, no handle, no start
date, no duration.** `init` is `NS_UNAVAILABLE`.

This is not a limitation to work around; it is `design/LOCAL-FIRST.md` rule 3 —
"the smallest conclusion that works" — arriving for free. The sense can know *an
outgoing call was connected and is now over* and can know **nothing whatsoever**
about who was on it, so it cannot leak an identity it does not have.

### 1.3 The shape of the API decides the shape of the policy

`CXCallObserver.h` is fourteen lines of interface, and two facts in it are
load-bearing:

```objc
@protocol CXCallObserverDelegate <NSObject>
- (void)callObserver:(CXCallObserver *)callObserver callChanged:(CXCall *)call;
@end
```

1. **There is exactly one delegate method.** No `callStarted`, no `callEnded`.
   Every transition this product wants — connected, ended, promoted by call
   waiting — has to be *derived*.
2. **`calls` is authoritative**: *"Retrieve the current call list, blocking on
   initial state retrieval if necessary."*

So a sense that folds one `callChanged` at a time turns a missed or coalesced
callback into a state it never leaves. Folding the whole `calls` list instead is
total, and the same code path that handles a callback answers *"what happened
while we were suspended"* — which is the case a call sense exists for.

### 1.4 The real limit: a suspended app observes nothing

Already measured in this tree and not re-derived here. `Info.plist` declares
`UIBackgroundModes = [bluetooth-central, audio]` only; `audio` buys execution
while audio is *flowing*, and during a call none is. `PhoneListener.swift:137,
149-151` records the background assertion as worth *"ROUGHLY THIRTY SECONDS —
not a phone call … A ten-minute call still suspends the app."*

**Consequence, and it is designed for rather than hidden:** call *start* is
usually observed, call *end* is not reliable for exactly the long calls worth
remembering. Every instant the policy emits is therefore a **bound it can
defend**, never a measurement it cannot — see §3.2.

---

## 2. Is FaceTime in the stream? **UNKNOWN, and no document settles it**

The card names FaceTime explicitly, so this is the question that most needed an
answer, and the honest answer is that I could not get one.

**What I checked, and what it returned:**

| Source | Result |
|---|---|
| `CXCallObserver` documentation JSON | FaceTime **not mentioned** |
| `CXCall` documentation JSON | FaceTime **not mentioned**; calls are *"created by the telephony provider"* |
| CallKit framework overview JSON | FaceTime **not mentioned**; the overview is about integrating *your* VoIP service |
| `grep -rni facetime` over **every header** in `CallKit.framework`, iPhoneOS 26.2 SDK | **zero hits** |
| `grep -rli facetime` over **every framework header in the whole iPhoneOS 26.2 SDK** | **zero hits** |

So FaceTime is not named anywhere in the public iOS SDK, in any framework, at
all. There is **no source that says FaceTime calls appear in this stream and no
source that says they do not.**

**I could not search the web for community reports.** This session's WebSearch
budget was already exhausted (200/200) before I reached the question — the same
wall the spec hit at its §11 q8 — and direct fetches of Stack Overflow,
DuckDuckGo, Mojeek and a SearxNG instance returned a block, three CAPTCHAs and a
403 respectively.

**This must not be implied to work.** `CXCall`'s *"created by the telephony
provider"* is suggestive and it is not conclusive: it is equally readable as "the
cellular telephony provider only". Everything built here therefore says `call`,
meaning *whatever the telephony provider told us about*, and
`run_call_presence_tests.sh` **fails the build** if the policy starts naming
FaceTime or naming telephony. A device promotes the claim; nothing else may.

**The ten-minute test that settles it** (spec §11 q1, unchanged): observer
running on a device, place a FaceTime **audio** call and then a FaceTime **video**
call to a second device, and watch whether a `CXCall` arrives for either. Owner
of `app/ios/`, on a device. Until then the card's FaceTime half is unproven, not
delivered.

---

## 3. What was built

### `app/ios/Anticipy/Audio/CallPresencePolicy.swift`

A pure-Foundation decision, in the tradition of `TranscriptFlushPolicy`,
`ListenJournal`, `ListenTally`, `ListenResumePolicy`, `ListenWatchdogPolicy` and
`ListenControlPolicy`: it can be shown to fail with `swiftc` alone — **no
simulator, no signing, no network, and no device that has to receive a real phone
call.** That last clause is the whole reason it is a file and not four lines
inside a delegate method.

`decide(was:sees:now:)` folds the call list and the clock into one `Verdict`
carrying three things decided from the same facts at the same instant. One value
rather than three functions, which is the lesson `ListenControlPolicy` paid for:
what to remember, what the listener does, and what the day records will drift if
a caller can ask for one without the others.

**1. `Action` — what the listener should do**

- `.standDownForCall` while any call is live, **ringing included**. An incoming
  call takes the audio session with the *ringtone*, before anyone answers and
  whether or not anyone ever does. Fires on every observation, which is safe
  precisely because the instruction is to do nothing.
- `.retakeMicrophone` on the **edge** where the last call leaves. Edge-only
  because it costs a capture rebuild — the same defect shape as the background
  assertion taken on every write of `suspended`, which renewed a thirty-second
  grant a hundred and fifty times across a ten-minute call.
- `.nothing` otherwise.

It deliberately does **not** ask whether the owner wants listening at all.
`ListenResumePolicy` owns that; asking it twice is how two right answers to
different questions end up rendered on one control.

**2. `Boundary` — ground-truth conversation edges**

`CAPTURE-ARCHITECTURE.md` Level 3 decides segment boundaries from capture-time
silence, a heuristic over ambience. A call connecting and ending are not
heuristics: they cost no model call and they are right in a noisy room and a
quiet one alike. This is the SORTER's dependency arriving early.

- `.callOpened(at:outgoing:sawItConnect:)`
- `.callClosed(at:outgoing:heldForAtLeast:sawItConnect:)`
- **A call that never connected produces no boundary at all.** A declined ring
  took the microphone and gave it back — the listener hears about that through
  `Action` — but nothing was said, so there is no conversation to bound.

**3. `State` — everything remembered between observations, and no more.**

### 3.2 The epistemics are in the type, which is the part worth arguing about

The phone can be suspended across the moment a call connects. So:

- **`heldForAtLeast` is a FLOOR and never a duration.** Measured from the first
  instant this device was *certain* the call was connected. A forty-minute call
  the phone only noticed at minute thirty-nine reports "at least one minute" —
  true, and honestly useless. **That is the correct failure**, and it is the
  opposite of the available alternative, which is a confident wrong number.
- **`sawItConnect` is how a consumer tells the two apart.** True means the call
  was in view before it connected, so the instant is close. False means it was
  already up the first time this device looked.
- Floored at zero, so a clock that moves backwards between observations — a
  timezone crossing, an NTP correction — cannot report a call that lasted a
  negative number of seconds.

**Two defects found and fixed, recorded because the fixes are the interesting
part.** The first was found by the tests, the second by the adversarial pass that
`HARNESS-LAWS.md` law 6 asks for; neither would have been caught by reading.

1. **The leading-call-only state could not vouch for a call it watched.** The
   first version remembered only the call in front, so during call waiting a
   second call that rang through the first conversation lost the fact that it had
   been watched arriving, and its opening claimed `sawItConnect: false` about a
   call seen from its first ring. The floor stayed correct — it was the epistemic
   flag itself lying, in the safe direction, which is still the one field that
   exists to say how much to trust the floor being wrong. `State.seenLive` is now
   simply the calls that were live at the previous observation, which is both
   wider and simpler, and it also covers a call displaced by call waiting and
   later resumed — a case the first fix still got wrong.

2. **A displaced call closes while still being live, and nothing said so.** Call
   waiting: the owner puts the first call on hold and speaks on the second, so
   the first stretch of conversation is over even though that call has not ended.
   Emitting the close is right — pretending the first call ran continuously
   through the second would be the lie — but a consumer reading the close alone
   would fire a post-call prompt at somebody in the middle of the call they just
   switched to. **The `Action` in the same `Verdict` already distinguished them**
   — `.retakeMicrophone` beside a close means the phone is free, `.standDownForCall`
   beside a close means the owner simply moved on — and nothing had ever said so.
   It is now on the case, pinned by two named checks and by a sweep leg asserting
   that a close carries `.retakeMicrophone` if and only if nothing is left live.
   This is the concrete payoff of the three answers riding in one value instead
   of being three functions a caller can ask separately.

### 3.3 Tests

`app/ios/Tests/CallPresencePolicyTests.swift` and
`app/ios/Tests/run_call_presence_tests.sh`, registered in `run_all.sh`.

**44 checks, exit 0.** Stories — a declined ring, a watched call, a call
discovered in progress, hold, call waiting, the swap that ends one call and
connects another in a single callback, a call displaced and later resumed, an
ended call lingering in the list, a clock that moved backwards, the retake edge,
a floor that only grows — and then the part that makes them a contract rather
than a pile of anecdotes: a **sweep of 1,638 combinations** (6 prior states × 273
call lists, being every flag combination of up to two calls) asserting nine
invariants, including that the same list observed again records nothing and
changes nothing. Without that one, a sense polled once a second writes a
conversation boundary once a second.

### 3.4 The four law legs in the runner

Source rules, checked with comments stripped so the file's own explanation of a
rule cannot trip it:

1. **LAW 1 — no duration threshold.** Fails the build on a stored `TimeInterval`,
   on any `…Seconds`/`…Minutes` constant, or on any comparison against one. *"A
   call longer than N minutes deserves a message"* is a threshold deciding
   meaning wearing a sense's clothes, and it is the single most likely way this
   file stops being a sense. It reports how long a call was held and stops.
2. **LOCAL-FIRST rule 3 — no identity.** Fails on `handle`, `phoneNumber`,
   `callerName`, `remoteParty`, `contactID`. `CXCall` carries none, so such a
   field is either dead weight or a value that arrived from somewhere it should
   not have.
3. **No claim about FaceTime, and none about telephony.** §2.
4. **It stays pure Foundation.** The moment it imports CallKit there is no macOS
   binary that can run any of this, and the one decision in the app about phone
   calls goes back to being a decision nothing can prove wrong without a device
   that receives a real call.

Plus a fifth: nothing outside the policy may read a call's `hasConnected`, so
there is never a second answer to *where a conversation begins*.

---

## 4. What is NOT done, said plainly

**The policy has no call site.** The `CXCallObserver` adapter that would feed it
is not built, so **nothing in the running app knows a call is happening yet.**
The runner prints this after every green run, and it points here.

This is the spec's own §9.1 risk — *"build detection, ship it as 'the call
recorder', and let the rest stay quietly unfinished"* — so it is named rather
than implied to be finished. `LocalTranscriber.swift` is the cautionary case in
this same directory: 43 lines, law-abiding, and **zero call sites** for months
while the violating path it was meant to replace kept running.

**LAW 3.** None of this is verified live and none of it can be. Build 87 is on no
phone, the ears have been dead for 41 hours, and the simulator does not model
phone calls. What *is* verified: `sh app/ios/Tests/run_all.sh` exits **0** (335
checks), and `xcodebuild … -destination 'platform=iOS Simulator,name=iPhone 17 Pro'`
**BUILD SUCCEEDED** with `CFBundleVersion 87` in the built bundle.

### The next three steps, in order

1. **`CallSense`** — a thin `CXCallObserverDelegate` that maps `CXCall` →
   `CallPresencePolicy.Call`, folds on every `callChanged` **and** on foreground
   return, and publishes the verdict. Small; it is the missing call site.
2. **The honest sentence** (spec §2.4.1). Today the home card says *"Mic
   interrupted, taking it back…"* and the briefing *"Something else has the
   microphone right now."* — honest, but describing a mechanism. With the sense
   she can say the true thing: *"You're on a call — I can't hear it. I'm back
   when you hang up."* A MOUTH-grade upgrade for one `if`, and it must be driven
   through `ListenControlPolicy` rather than a second copy of the logic.
3. **The post-call voice note** (spec §3.3) — composes from 1 and 2 with no new
   machinery. `.callClosed` is the only trigger under which it is not a timer,
   which is what `design/NO-MORE-TIMERS.md` exists to refuse.

**The LAW 1 trap on the far side of all three, stated now:** a call fact may be
handed to the model as context. It may **never** be wired as `if on_call:
<behaviour>` or `if heldForAtLeast > N: <speak>`. That is a threshold deciding
meaning with a sense's alibi, and it is the exact thing leg 1 of the runner
exists to catch on the day somebody reaches for it.

---

## 5. What the card must be re-scoped to

**Re-scope from a recorder to a sense.** *"Detect phone calls and FaceTimes,
start recording automatically, and sync notes/recordings with the pendant and
central brain"* cannot ship: the recording half is refused by iOS on every route
(spec §1, four independent Apple sources plus this repo's own 0 Hz measurement at
`PhoneListener.swift:439`), and *"sync recordings with the central brain"* is
`design/LOCAL-FIRST.md` rule 1 head-on — the exact pattern whose last instance,
the pendant's Deepgram lane, was deleted last night and is now enforced against
by `overnight/no_vendor_ears.py`. **Recordings do not travel; conclusions do.**

**What the card keeps:** call detection (this document), the widget step
delivered literally as a Control Center / Lock Screen / Action-button control
that records *the room* through `ListenControlPolicy` (spec §4 — GO, with §11 q5
still open on whether a control's `AppIntent` can sustain capture without
launching the app), and the post-call voice note. **What it drops:** "start
recording automatically" — impossible for calls, and for rooms a guideline 2.5.14
rejection risk; FaceTime *video* capture, which nobody records including Apple;
and recordings syncing anywhere.

**What stays unproven rather than dropped:** FaceTime detection. §2.

### Two sentences for the board

> The recorder cannot be built and the detector can: `CallPresencePolicy` now
> decides, from CallKit's call list and the clock alone, when a call has the
> microphone, when it is back, and where the conversation boundaries were — 39
> tests, no device needed — but it has no call site yet and the `CXCallObserver`
> adapter that feeds it is the next step.
>
> Whether `CXCallObserver` reports FaceTime at all is **unknown** — Apple's
> documentation never names FaceTime and neither does any header in the entire
> iOS 26.2 SDK — so the card's FaceTime half is unproven until somebody places
> one on a real device with the observer running.
