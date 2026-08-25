# MAC — the Mac hears the far side of the call, and nobody installs a driver

> Status: SPEC. Not a plan, not a sequence, no code, no task list.
> Card: "Build Anticipy macOS app (meeting recorder)" — Jose, created by Omar.
> Note on the card: *"Mac OS app similar to Granola that records meetings, adds
> functionality to the Chrome extension, and automatically syncs notes with the
> pendant."*
> Laws that bind: `HARNESS-LAWS.md` 1, 3, 4, 5, 6. `design/LOCAL-FIRST.md`
> rules 1, 3 and 5 decide §5 and half of §3.
> Nothing in `app/`, `brain/`, `extension/` or `backend/` was modified writing
> this. Every external fact below is either a URL, a file on this machine
> quoted by path, or explicitly marked as my own knowledge.
>
> **Three findings change the shape of the card before anybody writes a line.**
>
> **(1) The hard part is already solved by the OS, and it is not solved the way
> people assume.** Since macOS 14.2 a plain, signed, un-sandboxed app can tap
> another process's audio with `AudioHardwareCreateProcessTap` — no kernel
> extension, no system extension, no HAL plug-in, no admin password, no reboot.
> Verified two ways on this machine: the SDK header carries
> `API_AVAILABLE(macos(14.2))`, and seven shipping apps in `/Applications`
> already declare the Info.plist key it requires while this Mac has **zero**
> system extensions installed. §4 is the whole answer to "can a cold stranger
> install it" — and the answer is yes, but the thing that stops them is a
> **certificate we do not own**, not a driver.
>
> **(2) The Mac gets speaker attribution for free, and the phone never will.**
> The far end arrives on the tap; the owner arrives on the microphone. Two
> physical channels, no voiceprint, no `SpeakerTagger`, no threshold. The
> product has spent months trying to answer "who said that" acoustically
> (`Audio/VoiceRoster.swift`, cosine 0.78) and on a Mac the question is
> answered by the wiring. §3.4.
>
> **(3) The clause "syncs notes with the pendant" cannot be built, and not for
> a reason in this card.** The pendant is a BLE microphone whose only host is
> the iPhone, and the iPhone has posted **nothing to production since
> 2026-08-24 03:34:24.685Z** — measured live this session, 37.6 hours ago, by
> `python3 overnight/are_the_ears_live.py`. Builds 76 through 80 have delivered
> zero rows of any kind, ever (`research/2026-08-25-the-ears-stopped.md`). §8
> is that dependency, stated rather than assumed, and it is the reason this
> spec ships the Mac as a **second independent ear** and not as an accessory to
> a dead one.

---

## 1. What the card asks, checked against the tree and against production

Every row measured this session. Nothing inherited from the Brief, which is
stale on two of them.

| The card says | What is actually there | Verdict |
|---|---|---|
| "Mac OS app" | `app/` contains exactly one directory: `ios`. `git grep` finds no `.xcodeproj`, no `Package.swift`, no AppKit or SwiftUI-for-Mac source anywhere. `app/ios/project.yml:4-5` sets `deploymentTarget: iOS: "16.0"` and nothing else. | **Greenfield.** Nothing to undo, nothing to reuse, no Mac target has ever existed. |
| "similar to Granola" | Granola's own homepage: *"Uses your computer audio, so doesn't invite a bot"* and *"Works with Zoom, Google Meet, Teams and every other meeting app."* ([granola.ai](https://www.granola.ai/)) | **The model is right and it names the mechanism.** "Computer audio" is a process tap or a screen-capture stream; see §3. I could **not** verify from a public source which of the two Granola uses — do not repeat a guess about it. |
| "records meetings" | Nothing in this product records anything. `app/ios/Anticipy/Audio/PhoneListener.swift` transcribes and discards; `TranscriptCursor` tracks emitted **words**, never audio. There is no audio file anywhere in the product, on any device, ever. | **True, and this card would introduce the first stored audio in Anticipy's history.** §5 treats that as the change it is. |
| "adds functionality to the Chrome extension" | `extension/manifest.json` is version 0.11.0 with `tabs`, `tabGroups`, `scripting`, `debugger`, `notifications`, `<all_urls>`. It has no `tabCapture`, no `nativeMessaging`, no `offscreen`, and no knowledge of any meeting site — one grep hit across the whole tree, `extension/private_places.js:129` listing `teams.microsoft.com` as a place to ask before touching. | **Undefined in the card, and it is the half with the most leverage.** §9 makes it three concrete things. |
| "automatically syncs notes with the pendant" | The pendant is a BLE peripheral bound to the iPhone (`app/ios/Anticipy/BLE/PendantManager.swift`, GATT `19B10000-…`). No Mac code can see it. And the iPhone→server channel is dead: measured live, see below. | **Not buildable in this card.** §8.4. |

### 1.1 The live measurement, run this session

```
$ python3 overnight/are_the_ears_live.py
  ARE THE EARS LIVE?   https://backend-production-61e0a.up.railway.app
  [....] backend answers /api/health             200
  [....] speech heard in the last 24h            0
  [....] rows the SERVER wrote in the last 24h   0 (the control half)
  [....] newest speech of all time               2026-08-24 03:34:24.685Z (37.6h ago) from iphone-b75
  [....] newest row the server wrote             2026-08-24 16:10:20.009Z (25.0h ago)
  UNPROVEN — a leg that cannot be tested does not pass
```

Read that carefully, because it says two different things. The **backend is
healthy** (`/api/health` 200) — so the door this card needs to walk through is
open. And **the entire system has been idle for a day** — so nothing
downstream of the door is currently proven to work either. §8 is built on
exactly that distinction.

---

## 2. Non-goals

- **No implementation.** This is written to be executed by somebody else.
- **No fix for the phone.** Reverting the sherpa-onnx linkage and getting a
  build installed is `research/2026-08-25-the-ears-stopped.md`'s card, not
  this one. This spec names it as a dependency (§8.4) and stops.
- **No pendant integration.** Blocked upstream, §8.4. Anything in this document
  that mentions the pendant is naming a blocker, not designing against it.
- **No cloud transcription, of any vendor, at any tier, for any reason.** §5.2
  is a refusal, and it is a refusal with a precedent attached.
- **No change to `brain/`'s triage.** One brain-side ingest function is named
  as a prerequisite (§8.3); designing it belongs to whoever owns SORTER.
- **No calendar reading on the Mac.** Meeting identity comes from the browser
  (§9.1), which needs no new consent from anybody.
- **No new tape.** Nothing here is a string patch over meaning, so nothing here
  needs a `TAPE:` comment or a `tape_gate` registry entry. §12 says what to do
  if an implementer finds themselves reaching for one.
- **Not a plan.** No tasks, no ordering. §11 gives an honest size, not a
  schedule.

---

## 3. (1) The capture mechanism, named, with its floor and its prompts

### 3.1 Two streams, one clock

**The mechanism, in one sentence: a Core Audio process tap
(`AudioHardwareCreateProcessTap`, macOS 14.2+) drained through a tap-bearing
aggregate device gives what the far end says, an ordinary `AVAudioEngine`
input tap gives what the owner says, both are transcribed on-device, and no
audio ever leaves the Mac.**

| Stream | API | What it physically is | Who is on it |
|---|---|---|---|
| FAR | `CATapDescription` → `AudioHardwareCreateProcessTap` → `AudioHardwareCreateAggregateDevice` with the tap in `kAudioAggregateDevicePropertyTapList` | the audio Zoom/Chrome/Teams is *playing out* | everyone who is not in this room |
| NEAR | `AVAudioEngine.inputNode` on the default input device | the microphone | the owner, and anyone sitting with him |

Apple's own article for this is *Capturing system audio with Core Audio taps*
([developer.apple.com](https://developer.apple.com/documentation/coreaudio/capturing-system-audio-with-core-audio-taps)),
and it states the permission behaviour in one sentence: *"The first time you
start recording from an aggregate device that contains a tap, the system
prompts you to grant the app system audio recording permission."*

### 3.2 The version floor is macOS 14.2, and it is a hard floor

Verified from the SDK on this machine, not from memory:

```
/Applications/Xcode.app/…/MacOSX.sdk/System/Library/Frameworks/
  CoreAudio.framework/Versions/A/Headers/AudioHardwareTapping.h:44

AudioHardwareCreateProcessTap(CATapDescription* inDescription,
                              AudioObjectID*  outTapID)
                              API_AVAILABLE(macos(14.2)) API_UNAVAILABLE(ios, watchos, tvos);
```

`NSAudioCaptureUsageDescription` carries the same floor —
[macOS 14.2+](https://developer.apple.com/documentation/bundleresources/information-property-list/nsaudiocaptureusagedescription).
`CATapDescription` itself is annotated `API_AVAILABLE(macos(12.0), ios(15.0))`
(`CATapDescription.h:44`) and Apple's web docs repeat 12.0 for its members —
**ignore that**; the class is inert without the creation function, so 14.2 is
the number that matters.

**Set `LSMinimumSystemVersion` to 14.2 and refuse to launch below it with a
sentence, not a crash.** Two things get better on macOS 26 and neither is worth
raising the floor for:

| macOS 26.0-only | Header | What you do without it |
|---|---|---|
| `CATapDescription.bundleIDs` | `CATapDescription.h:135-136` | resolve PID → `AudioObjectID` yourself via `kAudioHardwarePropertyTranslatePIDToProcessObject` (`AudioHardware.h:634`) |
| `CATapDescription.processRestoreEnabled` — *"save tapped processes by bundle ID when they exit, and restore them to the tap when they start up again"* | `CATapDescription.h:163-167` | **watch `kAudioHardwarePropertyProcessObjectList` and rebuild the tap yourself when a process restarts.** This is the single most underestimated piece of work in the card; see §11. |
| `SpeechTranscriber` (on-device, `Speech`) | [macOS 26.0+](https://developer.apple.com/documentation/speech/speechtranscriber) | `SFSpeechRecognizer` with `requiresOnDeviceRecognition = true`; §5.2 |

For orientation: Apple's release-notes index currently lists macOS Tahoe 26
through **26.6** as shipped and **macOS 27 "Golden Gate" beta 7** as the
current beta
([developer.apple.com](https://developer.apple.com/documentation/macos-release-notes)).
The machine this spec was written on is macOS **15.6.1 (24G90)** — i.e. two
majors behind. Whoever builds this must not assume the owner is on 26.

### 3.3 Every prompt the user reads, quoted exactly

These are not paraphrases. They are the strings the OS will actually put on
screen, read out of
`/System/Library/PrivateFrameworks/TCC.framework/Resources/Localizable.loctable`
on macOS 15.6.1 (24G90) with
`plutil -extract en xml1`. Wording can change between majors; re-read this file
on the owner's actual OS before shipping onboarding copy that quotes it.

| # | When | Key | **What the user reads** | Info.plist key we must supply |
|---|---|---|---|---|
| 1 | first time the tap-bearing aggregate device starts | `REQUEST_ACCESS_SERVICE_kTCCServiceAudioCapture` | **“Anticipy” Would Like Access To Record Your System Audio** | `NSAudioCaptureUsageDescription` |
| 2 | first time the engine opens the input node | `REQUEST_ACCESS_SERVICE_kTCCServiceMicrophone` | **“Anticipy” would like to access the microphone.** | `NSMicrophoneUsageDescription` |
| 3 | `SFSpeechRecognizer.requestAuthorization` (only on the < 26 path, §5.2) | `REQUEST_ACCESS_SERVICE_kTCCServiceSpeechRecognition` | **“Anticipy” Would Like to Access Speech Recognition.** | `NSSpeechRecognitionUsageDescription` |

**Prompt 3 has a problem and it must not be discovered in front of a user.**
The same file carries the subtitle the system shows underneath it:

> `REQUEST_ACCESS_INFO_SERVICE_kTCCServiceSpeechRecognition` = *"Speech data
> from this app will be sent to Apple to process your requests. This will also
> help Apple improve its speech recognition technology."*

That string is unconditional in the table — it does not know that we set
`requiresOnDeviceRecognition = true`. So on macOS 14.2–25.x, **the OS tells the
owner their speech goes to Apple at the exact moment our onboarding is telling
them it stays on the Mac.** Two of the three options are bad:

- Say nothing and let the contradiction stand. Unacceptable; it is the one
  promise this product is made of.
- Pre-empt it in our own sheet, immediately before: *"macOS is about to say
  Apple gets a copy. We ask for on-device recognition, which Apple's own
  documentation says 'prevent[s] an SFSpeechRecognitionRequest from sending
  audio over the network' — but we can only ask, and only when your Mac
  supports it. If it does not, we will tell you and stop."*
  ([requiresOnDeviceRecognition](https://developer.apple.com/documentation/speech/sfspeechrecognitionrequest/requiresondevicerecognition):
  *"Set this property to `true` to prevent an `SFSpeechRecognitionRequest` from
  sending audio over the network… The request only honors this setting if the
  `supportsOnDeviceRecognition` property is also `true`."*)
- On macOS 26+, use `SpeechTranscriber` and **never show prompt 3 at all**.
  Whether `SpeechAnalyzer`/`SpeechTranscriber` needs Speech Recognition
  authorization is **UNVERIFIED** — Apple's page does not say. It is a
  ten-minute test on a 26 machine and it is in §15.

Take the second option below 26 and the third at 26+, and **refuse to run at
all if `supportsOnDeviceRecognition` is false** rather than silently uploading.
That refusal is a product state with a sentence, not an error.

### 3.4 What the two channels buy, which is the thing to protect

The pendant/phone path has spent months on the question *whose voice was that*
— `Audio/SpeakerTagger.swift` (sherpa-onnx embeddings, 20 s ring buffer),
`Audio/VoiceRoster.swift` (cosine 0.78 with a 0.05 margin), and the linkage
that has plausibly bricked five iOS builds. The Brief's own honest line:
*"Attribution shipped but unproven in the wild… Until proven, unattributed
lines must never mint actions."* (`docs/BRIEF.html:498`)

On the Mac, for a call, that question is answered by **which wire the sample
arrived on**. FAR is definitionally not the owner. NEAR is definitionally this
side of the call.

Two honest limits, and neither is fatal:

1. **NEAR is "this side", not "the owner".** Anyone in the room with him is on
   it. Say "this side of the call" in the data model and never write
   `speaker: "owner"` from channel alone. If `SpeakerTagger` is ever ported to
   the Mac it refines NEAR; it is not required for the Mac to be useful, which
   is the opposite of the phone's situation.
2. **FAR is "everything the tapped process played", not "the other
   participants".** A shared YouTube clip, a notification chime, and hold music
   all land on FAR. That is a transcription-quality problem, not an attribution
   problem.

This is the strongest argument in the card and it is worth stating to Omar in
one line: **the Mac is where "who said that" stops being a model's opinion.**

### 3.5 The alternative that was considered and rejected: ScreenCaptureKit

`SCStreamConfiguration.capturesAudio` is
[macOS 13.0+](https://developer.apple.com/documentation/screencapturekit/scstreamconfiguration/capturesaudio)
and `captureMicrophone` is
[macOS 15.0+](https://developer.apple.com/documentation/screencapturekit/scstreamconfiguration/capturemicrophone),
so one framework could carry both streams with a **lower floor** (13.0 vs
14.2). Rejected anyway, on the prompt:

> `REQUEST_ACCESS_SERVICE_kTCCServiceScreenCapture` = *"“Anticipy” would like
> to capture the contents of the system display."*

We would be asking a stranger for **their screen** in order to take notes on a
call. That is a larger grant than the feature needs, it is the grant most
likely to be refused, and it is the grant that gets a company on a list. The
Core Audio tap asks for audio and gets audio.

Two caveats recorded so the decision can be re-opened honestly:

- Apple's `SCShareableContent` page **does not state** that screen-recording
  permission is required. That it is required is my own knowledge plus the
  existence of `kTCCServiceScreenCapture` and `CGRequestScreenCaptureAccess()`
  ([macOS 10.15+](https://developer.apple.com/documentation/coregraphics/cgrequestscreencaptureaccess())).
  If someone proves SCK audio-only needs no screen grant, §3.5 changes.
- I could **not** verify the widely-repeated claim that macOS 15+ re-prompts
  periodically for screen recording. The macOS 15 release notes do not mention
  it; they mention only that *"Applications utilizing deprecated APIs for
  content capture such as `CGDisplayStream` & `CGWindowListCreateImage` can
  trigger system alerts"*
  ([macOS 15 release notes](https://developer.apple.com/documentation/macos-release-notes/macos-15-release-notes)).
  Do not build an argument on either side of that claim.

---

## 4. (2) Is a system extension or a virtual audio device required?

**No. This is the pivotal question and the answer is a clean no, verified three
ways on this machine.**

Apple's article
([Capturing system audio with Core Audio taps](https://developer.apple.com/documentation/coreaudio/capturing-system-audio-with-core-audio-taps))
describes the whole mechanism as tap → aggregate device → read, and names no
driver, no plug-in and no extension anywhere in it. The one sentence I have
verbatim from it is the permission behaviour: *"The first time you start
recording from an aggregate device that contains a tap, the system prompts you
to grant the app system audio recording permission."* **"No driver is needed"
is my reading of that article, not a sentence Apple wrote** — so it is
corroborated below by measurement rather than left on a citation.

Measured here, 2026-08-25:

```
$ systemextensionsctl list
0 extension(s)

$ ls /Library/Audio/Plug-Ins/HAL/
OculusRemoteDesktopASP.driver        # unrelated; nothing else
$ ls ~/Library/Audio/Plug-Ins/HAL/
(empty)
```

And the apps that already do this, found by reading every
`/Applications/*.app/Contents/Info.plist` for `NSAudioCaptureUsageDescription`:

| App | Its own string, verbatim |
|---|---|
| zoom.us | *"Please allow access in order to capture audio from other apps."* |
| Slack | *"This app needs access to audio capture"* |
| Discord | *"This app needs access to audio capture"* |
| Figma | *"This app needs access to audio capture"* |
| Claude | *"This app needs access to audio capture"* |
| Visual Studio Code | *"An application in Visual Studio Code wants to use Audio Capture."* |
| Lovable | *"Lovable needs system audio capture access to enable screen sharing with audio in your projects."* |

Seven apps capture system audio on this Mac. **Zero of them installed a driver
to do it.** (Note in passing how bad six of those seven strings are. Ours goes
in §4.2.)

### 4.1 Why this is the question that decides the card

The world before macOS 14.2 required Soundflower, BlackHole, Loopback or a
vendor's own HAL plug-in — a `.driver` bundle written into `/Library`, an admin
password, `coreaudiod` restarted, and on modern macOS a **system extension
approval in Privacy & Security followed by a reboot**. That is not a thing a
cold stranger completes. It is barely a thing a developer completes without
reading a support article.

With the tap, a stranger's install is: **drag to Applications, open, click
Allow twice.** No password, no reboot, no `/Library`, no kext, no
`systemextensionsctl`. That is why this card is buildable at all.

### 4.2 The two strings we owe the user

Written in the voice `app/ios/Anticipy/Info.plist` already uses, which is
honest to the point of being uncomfortable and should stay that way:

```
NSAudioCaptureUsageDescription
  Anticipy listens to the other side of your calls — the audio your meeting
  app is playing — so it can write the note. The sound never leaves this Mac
  and is deleted when the note is written. You start every recording yourself.

NSMicrophoneUsageDescription
  Anticipy listens through your microphone so the note has your half of the
  conversation too. The sound never leaves this Mac. You start every
  recording yourself.
```

Both of those sentences are **promises this spec has to keep**, and §5 and §10
are how they are kept and how they are checked.

### 4.3 The thing that actually stops a stranger, and it is not the OS

```
$ security find-identity -v -p codesigning
  1) … "Apple Development: Created via API (ZJ49TWB9LG)"
  2) … "iPhone Distribution: Omar Ebrahim (49T86P9XGW)"
     2 valid identities found
```

**There is no "Developer ID Application" certificate.** Without one, a
downloaded `.app` cannot be signed for distribution outside the App Store,
cannot be notarized, and Gatekeeper refuses it on a stranger's Mac with a
dialog that offers no "open anyway" on first launch. The `.env.local` in this
tree does carry `APP_STORE_CONNECT_KEY_ID` and `APP_STORE_CONNECT_ISSUER_ID`,
which `notarytool` can authenticate with — so the tooling half exists and the
certificate half does not.

That is an account action on Omar's Apple Developer membership, it takes
minutes plus Apple's turnaround, and **it blocks the last leg of the gate in
§10, not the first**. Note also the recorded history here: the Brief lists
*"TestFlight rejects builds with the speaker frameworks silently during
processing"* (`docs/BRIEF.html:504`) — this team has already lost weeks to an
Apple distribution failure that produced no email. Get the certificate early
and test `spctl` on a machine that has never seen the app, before writing the
note-taking.

**On the Mac App Store instead:** all seven audio-capturing apps above are
un-sandboxed direct downloads (`codesign -d --entitlements` shows no
`com.apple.security.app-sandbox` on any of them; zoom.us carries
`com.apple.security.device.audio-input` and nothing sandbox-shaped). **I could
not determine whether a sandboxed build can hold a process tap** — no sandboxed
example exists on this machine to inspect. Treat Developer ID as the plan and
the App Store as an open question (§15).

---

## 5. (3) Where the audio and the transcript live, against LOCAL-FIRST

`design/LOCAL-FIRST.md` rule 1 is the shortest sentence in this repo:
**"RAW AUDIO NEVER LEAVES A DEVICE. Not to Deepgram, not to anyone."**

### 5.1 The retention table, which is the spec

| Artifact | Where it lives | How long | Who can read it |
|---|---|---|---|
| FAR + NEAR PCM | RAM ring buffer, and an on-disk spool **only** while a meeting is open | **deleted at note-write.** Default retention is zero. | this process |
| the spool file, if the app is killed mid-meeting | `~/Library/Application Support/ai.anticipy.mac/spool/<uuid>.caf` | swept on next launch after the note is written or the meeting is abandoned; hard ceiling 24 h then deleted unread | the owner's user account |
| verbatim two-channel transcript | `~/Library/Application Support/ai.anticipy.mac/meetings/<uuid>.json` | **kept, on the Mac, indefinitely, and never uploaded** | the owner |
| the **note** (summary, decisions, the owner's own commitments) | on the Mac **and** posted to PocketBase as one `events` row | as long as the account exists | the owner, the worker |
| an optional "keep the audio" toggle | Settings, **default OFF**, per-meeting override | if ON, audio is kept beside the transcript, on the Mac, with a visible size counter and a one-click delete-all | the owner |

Two rules that are not negotiable and should be written as comments at the call
sites, because the next agent will not read this file:

1. **The verbatim transcript does not travel.** LOCAL-FIRST rule 3: *"What
   travels is the smallest conclusion that works."* A meeting transcript is
   mostly **other people's speech**, which is a category the phone has never
   sent and should not start sending because a Mac made it easy. What travels
   is the note plus, at most, the owner's own attributed lines.
2. **Audio is never a file the product hands to anything.** Not to an upload,
   not to an attachment, not to `evidence` (which exists for JPEGs and is
   capped at 400 000 bytes anyway,
   `backend/pb_migrations/1700000045_evidence.js`). §10 leg 4 is a
   deterministic check that no code path in `app/mac/**` can post audio bytes
   anywhere.

### 5.2 Transcription, and the vendor whose name is already in this repo

**On-device only.** macOS 26+: `SpeechTranscriber`
([macOS 26.0+](https://developer.apple.com/documentation/speech/speechtranscriber)),
checking `isAvailable` and `installedLocales` before promising anything.
macOS 14.2–25.x: `SFSpeechRecognizer` with `requiresOnDeviceRecognition = true`
and a **hard refusal** if `supportsOnDeviceRecognition` is false.

The reason this needs a paragraph rather than a line is that this repo has
already lost this argument once, in the other direction, and the loss is still
shipping:

- `backend/pb_hooks/transcription_token.pb.js` mints a 60-second Deepgram JWT.
- `app/ios/Anticipy/Audio/TranscriberClient.swift` streams **raw pendant Opus
  frames** to `wss://api.deepgram.com/v1/listen`.
- `.env.local` in this tree carries `DEEPGRAM_API_KEY`.
- `app/ios/Anticipy/Info.plist` says so to the user's face:
  *"When it is connected, pendant audio is sent to Deepgram for live
  transcription."*
- The Brief lists it as an open violation: *"Local-first is violated today
  where pendant audio streams to a cloud transcriber; the local path exists
  with zero call sites."* (`docs/BRIEF.html:505`)
- And `design/LOCAL-FIRST.md`'s own scoreboard already ruled on it: *"the
  earlier idea of moving phone STT to Deepgram is DEAD on this law."*

**A Mac meeting recorder is the single most tempting place in this product to
repeat that mistake**, because cloud STT is better at multi-speaker
far-field audio than anything on-device, and the quality difference will be
visible in the first demo. Refuse it on the law, before the demo, in writing:
routing meeting audio — *other people's* meeting audio, recorded without their
having chosen this product — to a vendor is a strictly worse version of the
violation the repo is already trying to remove. If the transcription quality is
not good enough, LAW 5's fix order says **senses first**: better mic routing,
better channel separation, a better local model. Not a vendor.

### 5.3 What the note costs against the law, said out loud

Writing the note is a summarisation call. Today `brain/` makes those against
OpenRouter, and `design/LOCAL-FIRST.md` scores triage as *"CLOUD TODAY — the
biggest open gap"* while permitting **text** to travel. So:

- **Audio: on-device, always. No exception exists and none will be granted.**
- **Note generation: cloud text call is acceptable today** on exactly the terms
  the phone already has — text, never audio — and only over the material the
  owner chose to record.
- **Its local-first posture, stated as rule 5 requires:** the note generator is
  a single, isolated call with a fixed prompt shape, so it is the first thing
  in this product that can move to a local model without touching anything
  else. Name the later: when on-device triage lands (LOCAL-FIRST build order
  item 3), the Mac note is the pilot, because it runs on a machine with
  headroom that a phone does not have.

---

## 6. (4) How a meeting is detected and started, and who decides

### 6.1 Recommendation: **explicit start, automatic offer.** Never auto-record.

The app watches for a meeting and **offers**. It never begins capture without a
click. Concretely: the menu-bar item turns from grey to amber with a one-line
banner — *"Zoom is using your microphone. Record this?"* — and a click starts
it. No click, no capture, and the offer disappears when the signal does.

### 6.2 The detection signal, and why it is legal under LAW 1

Core Audio exposes process objects. From `AudioHardware.h` on this machine:

```
kAudioHardwarePropertyProcessObjectList            = 'prs#',   (:633)
kAudioHardwarePropertyTranslatePIDToProcessObject  = 'id2p',   (:634)
kAudioProcessPropertyIsRunningInput                = 'piri',   (:1982)
    "A UInt32 where a value of 0 indicates that the process is not running any
     IO or there is not any active input streams, and a value of 1 indicates
     that the process is running IO and there is at least one active input
     stream."
kAudioProcessPropertyIsRunningOutput               = 'piro',   (:1983)
```

**The signal is: some process that is not us is running input AND output at the
same time.** That is a two-way conversation happening on this machine, stated
in the only terms the OS offers, and it is a fact about *plumbing* — which
process holds which stream — not about what anybody said. LAW 1's senses
carve-out (*"audio plumbing, timestamps, transport"*) covers it exactly, and
so does the seatbelt carve-out (*"checking what a plan TOUCHES is structure"*).

**Do not hard-code a list of meeting-app bundle IDs as the detector.** A bundle
list is legal here — it is identity, not meaning — but it is *wrong*, because
it is a maintenance treadmill that fails on the meeting app nobody thought of
and fires on the one that changed its identifier. Use the input+output signal
as the trigger; use bundle identifiers **only** to order and label the UI
("Zoom" reads better than "us.zoom.xos") and to hold the owner's per-app
never-offer list. If somebody later writes `if bundleID.contains("zoom")` to
decide *what the words mean*, that is the violation, and it will not be this
line that causes it.

This is also the generalisation `overnight/RESEARCH-NOTES.md:22` already
recorded a year of work ago — *"macOS names the app holding the microphone…
it also identifies a Zoom call, FaceTime, system dictation, any recorder"* —
and it was correctly deferred then because the phone was the only ear. On a Mac
app it is not a cross-device design any more. It is one property read.

### 6.3 Why not automatic, defended against the card's own word

The card says **"automatically"**. This spec is refusing that word for capture
and keeping it for detection, and here is the defence, in four parts.

**(a) The App Store guideline says so, and it says so about exactly this.**
Guideline 2.5.14, quoted in full:

> *"Apps must request explicit user consent and provide a clear visual and/or
> audible indication when recording, logging, or otherwise making a record of
> user activity. This includes any use of the device camera, microphone,
> screen recordings, or other user inputs."*
> ([App Store Review Guidelines](https://developer.apple.com/app-store/review/guidelines/))

A Developer ID build is not reviewed, so this is not a gate we must pass — but
it is Apple's written statement of what "acceptable" means on their platform,
by the company whose OS this runs on, and shipping against it while asking that
same OS for two privacy grants is a bad bet.

**(b) There is a second person in every one of these recordings, and consent
law knows it.** US federal law is one-party consent (18 U.S.C. § 2511), but
roughly a dozen states require **all-party** consent — California, Delaware,
Florida, Illinois, Maryland, Massachusetts, Montana, Nevada, New Hampshire,
Pennsylvania, Washington
([Reporters Committee recording guide](https://www.rcfp.org/introduction-to-reporters-recording-guide/)).
**Provenance, so nobody mistakes this for research I did:** this list is
inherited from the ios-reality lens, which read that page; I did not re-fetch
it this session, and it is journalism rather than legal advice. §15 sends it to
counsel. An
auto-recorder makes that decision on the owner's behalf, silently, for every
call he takes, in whatever state he is in. An explicit start makes it his,
once, per meeting, with the other party's names on screen.

**(c) The product already ruled on this, in the fifty moments.**
`docs/BRIEF.html:209`, moment 18:

> *"In a meeting you say 'we should probably rethink pricing' — a team musing,
> nobody assigned. → Remembered, never acted. 'We' in a meeting is a team's
> thought, not your errand."*

The Brief's stance on meetings is **restraint**. A recorder that starts itself
is the opposite posture, and it is the posture that produces the recording
nobody meant to make.

**(d) The signal is not clean enough to be trusted unattended.** Input+output
running simultaneously also fires for: system dictation, Voice Memos while
music plays, a browser tab with a mic-enabled demo, Wispr Flow (installed on
this very machine, `overnight/RESEARCH-NOTES.md:14`), and any VoIP call the
owner would never want written down — a doctor, a lawyer, a family
conversation. Auto-record turns every one of those into a file.

### 6.4 What the owner's control actually is

| Control | Behaviour |
|---|---|
| menu-bar item | grey = idle, **amber = a meeting is offered**, **red + elapsed time = recording**. The state is legible from across a room. |
| global hotkey | start / stop. One key, configurable, shown in onboarding. |
| **Stop and forget** | ends the meeting and deletes the audio, the transcript and the note, locally, with nothing posted. This is the button people actually need and it must be as prominent as Stop. |
| **Undo, 15 seconds** | after the note is written and posted, a countdown offers to retract. Retraction deletes the local note and DELETEs the posted row. Anything past 15 s is edited, not retracted. |
| never-offer list | per bundle identifier. One click from the offer banner: *"Never offer for Zoom."* |
| the ledger | a window listing every meeting the app has ever recorded, with size, retention state, and delete. Nothing is recorded that is not in this list. |

---

## 7. (5) What the other participants are told

### 7.1 The honest baseline: **nothing.**

There is no OS-level notice of a Core Audio tap. The far end sees nothing, hears
nothing, and gets no indication of any kind. The local microphone indicator in
Control Center is shown **to the owner**, on the owner's own screen (my own
knowledge, not an Apple citation) — the far end cannot see it. Granola's entire
pitch is that no bot appears in the participant list; that is the same fact,
sold as a feature.

Contrast, because it is the standard being set: Apple's own call recording on
iPhone **announces itself audibly to both parties** before it begins
([Apple Support](https://support.apple.com/en-us/121583) — verified by the
ios-reality lens against that page; I did not re-fetch it). Apple decided that a
recording nobody was told about was not shippable on their own hardware. We
should not decide differently and hope nobody notices.

So: **the OS tells them nothing, therefore the product must, and the product
must do it through a mechanism that can be checked.**

### 7.2 Three mechanisms, in descending order of how real they are

**(a) The extension types it into the meeting's own chat.** For anything
running in Chrome — Google Meet, Zoom Web, Teams web — the extension already
drives the browser (`extension/agent_loop.js`, `scripting`, `<all_urls>`). It
can put one sentence in the meeting chat at the moment recording starts:

> *"Heads up — I'm taking notes with Anticipy, which transcribes this call on
> my computer. Say the word and I'll stop."*

This is the only mechanism in this product that **actually reaches the other
participants**, it is verifiable (the message either posted or it did not), and
it is the strongest single answer to §9's "adds functionality to the Chrome
extension". It is also the leg of §10 that a mock cannot fake, because a real
meeting chat is a real artifact with a real timestamp.

**(b) Native meeting apps: a card the owner reads aloud.** The Zoom and Teams
desktop apps cannot be typed into. There, recording start shows a card with the
sentence and a **"I've told them"** button that must be pressed before capture
begins. Yes, that is checkable only by the owner's honesty. Say so in the copy
rather than pretending: the button records that *he said he told them*, and the
ledger stores which meetings were announced by which mechanism. Half-honest
beats silent, and it is auditable.

**(c) All-party mode.** A setting — on by default when the owner's timezone or
stated location is in an all-party jurisdiction, and available to everyone —
where **capture will not start** until (a) or (b) has completed. Not a warning.
A refusal.

### 7.3 What is deliberately not proposed

- **No recording of a call the owner is not on.** The tap can capture any
  process; the product will only ever offer for a process that is running input
  *and* output, i.e. a conversation the owner is in.
- **No covert mode, no hidden menu-bar option, no "discreet" anything.** If a
  feature request arrives asking for the indicator to be hideable, that is the
  request this section exists to refuse.
- **No claim of legal compliance anywhere in the UI.** The product says what it
  does; it does not tell a user their recording is lawful. §15 sends the
  question to counsel, which is where it belongs.

---

## 8. (6) How the result reaches the brain — and the path it depends on is dead

### 8.1 The wire already exists, and needs nothing deployed

Verified in the tree, this session:

- **Auth.** `owners` is a PocketBase auth collection; `auth-with-password` is
  explicitly exempted from the guard (`backend/pb_hooks/guard.pb.js:368`). A
  Mac app signs in with the same email and password as the phone.
- **The door.** `backend/pb_hooks/guard.pb.js:448` —
  `if (!recordId && method === "POST" && b.owner_ref === authId) return e.next();`
  — a signed-in owner may POST an `events` row carrying their own `owner_ref`.
  **No new route, no new hook, no new collection, no migration.**
- **The field.** `events.source` is a plain `text` field added additively by
  `backend/pb_migrations/1700000004_segments.js:51,66` (its comment says
  `phone | pendant`). A new value `mac` needs **no migration at all**.
- **The identity.** `device_id` is how this product names a build —
  `AnticipyApp.swift:236` builds `"iphone-b\(CFBundleVersion)"`. The Mac's is
  `"mac-b<CFBundleVersion>"`, and §10 leg 1 pins it, which is what makes a
  hand-inserted row fail the gate.

That is the whole integration. It is remarkably small, and it is small because
someone already did the work of making the phone's wire generic.

### 8.2 What must NOT be posted, and this is a cost question

Today the worker fetches `kind="transcript" && decision=""`
(`brain/worker.py:2700-2707`) and triages **every line individually** through
`anticipy.hear()`. A one-hour meeting at ~130 wpm is on the order of 300–600
lines. Posting a meeting as transcript rows would mean:

- **hundreds of model calls for one meeting**, against a system the Brief
  already describes as needing *"Segment-granularity triage… the single flip
  that … cuts model calls ~15×"* (`docs/BRIEF.html:500`), unbuilt;
- **the brain reasoning over other people's speech as if it were the owner's**,
  which moment 18 forbids and which the LIBRARY card is separately building the
  defence for (*"provenance gates action … imported text may be quoted, never
  obeyed"*, `docs/BOARD-STATE-2026-08-24.md:135`) — also unbuilt.

There is one benign interaction worth knowing about: dense arrivals would arm
the existing **meeting posture** (`brain/worker.py:2466`, `meeting_heard`),
which queues acts for a single digest instead of interrupting. That is a
threshold over row *arrivals*, not content, so it is LAW 1-clean, and it is the
correct behaviour. But it is a mitigation, not a plan — and the Brief already
records it as miscalibrated: *"90 seconds of silence ends a 'meeting'; the
recorded call contained two longer in-call silences. The digest would have
fired mid-call twice."* (`docs/BRIEF.html:501`)

**So: one row per meeting, `kind="meeting_note"`, at close.** Fields:
`source="mac"`, `device_id="mac-b<N>"`, `owner_ref`, `capture_started_at` and
`capture_ended_at` (UTC ISO with milliseconds, matching
`ISO8601DateFormatter.anticipyUTC`), and `text` = the note. Optionally a small
number of `kind="transcript"` rows carrying **only NEAR-channel lines the owner
explicitly marked as his own commitments** — zero by default.

### 8.3 The thing this depends on that does not exist

`kind="meeting_note"` is **invisible to today's worker**, because
`fetch_unprocessed` asks for `kind="transcript"`. A row posted this way lands in
the database and nothing reads it.

So the brain-side prerequisite is exactly one thing, and it must be named as a
dependency rather than smuggled into this card: **a worker path that ingests a
meeting note into memory as remembered-but-not-actionable material.** That is
one fetch, one call into `brain/memory.py`'s ingest, and a provenance tag that
LIBRARY's origins gate can read. Whoever owns SORTER or LIBRARY should design
it; this spec's contribution is to say that without it, **the note is stored
and never understood, and the card is half-built.**

Do not "solve" this by posting the note as `kind="transcript"` to make the
existing loop pick it up. It would work, and it would hand a paragraph of six
people's speech to a judge that has no provenance gate. That is the shortcut
this section exists to close.

### 8.4 The dead path, stated precisely, because "it's broken" is not precise

| Link | State, measured 2026-08-25 | What it means for this card |
|---|---|---|
| backend `/api/health` | **200** | the Mac's door is open |
| `events` POST by a signed-in owner | **proven** — `iphone-b75` delivered 313 rows through this exact contract | the Mac is not walking into an unproven API |
| iPhone → server | **DEAD.** Newest speech of all time 2026-08-24 03:34:24.685Z, 37.6 h ago. Builds 76–80: **zero rows, ever, of any kind** (`research/2026-08-25-the-ears-stopped.md`) | the Mac does **not** inherit this: different OS, different binary, different distribution. But it means the Mac would become **the only working ear in the product**, which raises what §6.4's "Stop and forget" and §10's store-and-forward are worth |
| worker → PocketBase | **UNPROVEN.** Zero server-written rows in 24 h. `are_the_ears_live.py` says so itself: *"the whole system was idle, so this window proves nothing"* | nothing downstream of the POST is currently demonstrated to run. §10 leg 3 must observe a **server reaction**, not just our own row |
| pendant | **unreachable from macOS, and its host is the dead phone** | the card's third clause is not buildable here, by anybody, today |

**Store-and-forward is therefore mandatory, not a nicety.** Mirror the phone's
disk-backed queue (`AnticipyApp.swift:203`, `@AppStorage("unsentLines")`): a note that
cannot be posted is written to disk, bound to the account that produced it,
retried oldest-first, and **shown in the ledger as unsent with a count**. The
phone's 30-hour silence went unnoticed for 30 hours partly because nothing
surfaced it. LOCAL-FIRST rule 4 requires the capture side to keep working
offline; this is that, plus the visible counter that would have caught the
phone.

---

## 9. (7) What "adds functionality to the Chrome extension" concretely means

Three things, in descending order of value. All three are additive to
`extension/` and none changes the hands.

### 9.1 Meeting identity — the extension answers "whose meeting was that?"

The tap knows *audio is coming out of Chrome*. It does not know it is a Google
Meet with six named people about Q3 pricing. The extension does: it can read
the active tab's URL (`meet.google.com/abc-defg-hij`), its `document.title`,
and the participant names the meeting UI has already rendered into the DOM.

That is the difference between a ledger entry reading *"43 minutes, Chrome"*
and one reading *"Q3 pricing sync — Laura, Tejas, +2"*. It costs no new
permission (the extension already holds `tabs`, `scripting`, `<all_urls>`) and
no new consent from anybody, and it is the input the note generator needs to
write a note worth reading.

**Provenance rule attached, because this is imported text:** participant names
scraped from a page are *untrusted attacker-controllable strings* — the same
category `brain/memory.py:1528` already flags about calendar titles. They may
label a meeting and may be quoted in a note. They may **never** be treated as
facts about people, and they may never mint an action.

### 9.2 The announcement — the extension is the only thing that can tell anyone

§7.2(a). One sentence typed into the meeting's own chat at recording start.
This is the only mechanism in the product that reaches a third party, and it is
the leg of the gate that produces a real artifact.

### 9.3 A tab-audio fallback that needs no macOS permission at all

`chrome.tabCapture.getMediaStreamId()` plus an offscreen document captures a
tab's audio inside Chrome
([developer.chrome.com](https://developer.chrome.com/docs/extensions/reference/api/tabCapture)).
Its documented restrictions are a feature here, not a limitation:

> *"It can only be called after the user invokes an extension, such as by
> clicking the extension's action button."*
> *"Capture can only be started on the currently active tab after the extension
> has been invoked, similar to the way that activeTab works."*

**Explicit start is structurally enforced by the API.** This path covers the
owner who declines the system-audio prompt, and anyone on macOS below 14.2 —
at the cost of only working for meetings inside Chrome, and of adding the
`tabCapture` and `offscreen` surfaces to a manifest that is currently 0.11.0.

### 9.4 How the two halves talk: native messaging, not a socket

`chrome.runtime.connectNative()` / `sendNativeMessage()`, with the
`nativeMessaging` permission, and a host manifest the Mac installer writes to
`~/Library/Application Support/Google/Chrome/NativeMessagingHosts/ai.anticipy.mac.json`
([developer.chrome.com](https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging)).

Chosen over the two alternatives on the law, not on taste: a localhost
WebSocket puts meeting identity on a network interface for no reason, and a
round-trip through PocketBase sends the participant list to a server to tell an
app on the same machine what tab is in front of it. Native messaging is
**stdin/stdout between two processes on one Mac** — the most local-first
transport available, and the documented one.

### 9.5 What this costs the extension, said plainly

The extension is currently distributed as a **self-hosted unpacked zip** the
stranger loads in developer mode, and `overnight/stranger_gate.py:735`
(`leg_1_hands_downloadable`) already fails the whole product when the served
zip does not match the source byte-for-byte at the pinned version. **Every
change in this section bumps the extension version and puts a new rebuild
through that leg.** Budget for it, and re-run `stranger_gate` rather than the
tests — Law 3.

---

## 10. (8) The gate leg, written so it cannot pass on a mock

`overnight/mac_ear_gate.py`. Five legs, run in order, first failure sets the
verdict, and a leg that cannot be tested **fails** — the `done_gate.py` house
rules verbatim. Exit 0 only when all five pass.

The design principle, which is the reason for each leg's shape: **anything a
developer can produce alone, at a desk, without a second human, is not
evidence.** `done_gate.leg_6_stranger` already encodes this — *"Leg 6 cannot be
faked. It requires a real cold stranger… No proof, NOT DONE, forever."* Legs 3
and 4 below are that same instrument aimed at this card.

### Leg 1 — `leg_1_the_mac_was_heard` (LIVE; no fixture exists to point it at)

Reads **production** over HTTPS with the service token, the way
`are_the_ears_live.py` does. Passes only when the `events` collection contains
at least one row where:

- `source == "mac"` and `kind == "meeting_note"`;
- `owner_ref` is non-empty and resolves to a real owner;
- `created` is inside `--hours` (default 24);
- and `device_id == "mac-b" + CFBundleVersion` **read from `app/mac/Info.plist`
  in the tree the gate is run from.**

That last clause is the anti-staleness tooth, borrowed from
`stranger_gate.leg_1_hands_downloadable`: a row from last week's build fails,
so the leg cannot go green on a success somebody had once. There is no local
database to substitute; the only way to satisfy it is for a real signed-in Mac
to have really posted.

### Leg 2 — `leg_2_it_was_a_meeting_not_a_keystroke` (sanity floor, and honest about it)

On that row: `capture_ended_at - capture_started_at >= 300` seconds, `text`
between 200 and 4000 characters, and both timestamps parse as UTC ISO with
milliseconds.

**This leg is not the teeth and must not be described as such.** A determined
faker can write these numbers. It exists to fail the accidental pass — a
one-second row, an empty note, a timestamp in local time — which is the class
of failure that actually happens.

### Leg 3 — `leg_3_a_real_room` (the teeth: a human, and another human)

Requires `overnight/mac_proof.json`, absent by default, red forever without it:

```json
{
  "date": "2026-…",
  "event_id": "<the PocketBase row id from leg 1>",
  "started_at": "…Z",
  "meeting_title": "…",
  "other_participants": ["…", "…"],
  "they_were_told": true,
  "announcement_mechanism": "chat" | "spoken",
  "announcement_sentence": "…",
  "chat_message_permalink_or_screenshot": "…",
  "stopped_by": "owner" | "meeting-ended",
  "audio_deleted_at": "…Z"
}
```

The leg then **fetches `event_id` from production** and fails unless its
`capture_started_at` is within ten minutes of `started_at`, and its
`device_id`/`source` match leg 1. So the file cannot describe a meeting that
production does not corroborate, and production cannot corroborate a meeting
the file does not describe.

`other_participants` must be non-empty and `they_were_told` must be `true`.
**A recording of yourself talking to yourself does not pass this gate**, which
is precisely the demo an implementer would otherwise ship.

### Leg 4 — `leg_4_no_audio_ever_left` (deterministic, over the source)

A repo-side check — legal under LAW 1's gates-and-evals carve-out, and the
reason it is a gate leg rather than a code review:

- no file under `app/mac/**` contains `deepgram`, `assemblyai`, `api.openai.com/v1/audio`, `rev.ai`, `speechmatics`, `whisper` as a network host;
- no `URLSession`/`URLRequest` in `app/mac/**` sets a body or `Content-Type` of `audio/*`, `application/octet-stream` over a `.caf`/`.wav`/`.m4a`/`.opus` path, or a multipart part named for one;
- `SFSpeechRecognitionRequest.requiresOnDeviceRecognition` is set `true` at **every** construction site, and there are zero sites that do not set it;
- `Info.plist` declares `NSAudioCaptureUsageDescription` and `NSMicrophoneUsageDescription` and **not** `NSScreenCaptureUsageDescription` (§3.5's decision, pinned so it cannot drift back);
- production holds zero `evidence` rows for this owner with a non-image mime type.

This is the leg that makes the Deepgram repeat impossible to land quietly, and
it is the leg most likely to be softened by a future agent in a hurry. It is
not a threshold over meaning; it is a property of the source tree.

### Leg 5 — `leg_5_a_stranger_can_install_it` (LIVE, and red today)

The download the product names answers; the artifact is a `.dmg`; the `.app`
inside is signed with a **Developer ID Application** identity, notarized, and
stapled; and `spctl -a -vv --type exec` on the extracted app reports
`accepted` with `source=Notarized Developer ID`.

**This leg is red right now and the reason is §4.3: no such certificate
exists on this machine.** Red is the law working. It is the cold-stranger
question made machine-checkable, it is the same shape as
`stranger_gate.leg_1_hands_downloadable`, and it must not be softened to
"the zip downloads" to reach green.

### What the gate deliberately does not do

- It does not read audio, transcripts, or note text. Like
  `are_the_ears_live.py`, it never requests a `text` column it does not need,
  so it cannot measure meaning even by accident.
- It does not assert the note is *good*. Note quality is an eval
  (`overnight/evaluate.py`'s machinery), not a gate leg.
- It does not run on a schedule or write anything. Read-only against
  production, safe to run at any time.

---

## 11. Cost and effort, honestly

**This is weeks, not days. Six to eight weeks for one competent person**, and
that estimate already assumes the pendant clause is dropped and the brain-side
ingest belongs to someone else.

| Piece | Size | Why it is that size |
|---|---|---|
| Mac target, menu bar, onboarding, permission flows, ledger | ~1 week | Greenfield. XcodeGen exists for iOS but the project is iOS-only; a Mac target is a new `project.yml` and a new signing story. |
| **Tap + aggregate device + mic + device-change survival** | **1.5–2 weeks** | The part everyone underestimates. Default-device changes mid-call, AirPods connecting, sample-rate mismatch between the tap format and the mic, the aggregate device disappearing, `coreaudiod` restarting — and **below macOS 26 you must rebuild the tap yourself every time the tapped process restarts**, because `processRestoreEnabled` does not exist (`CATapDescription.h:167`). Chrome respawns its audio helper routinely. |
| On-device transcription, two channels, with a 14.2 fallback path | ~1 week | Two engines behind one interface (`SpeechTranscriber` on 26+, `SFSpeechRecognizer` below), plus the refusal path when on-device is unsupported, plus the §3.3 consent-copy problem. |
| Note generation, local store, retention, delete-everything | ~1 week | The store is easy. Retention, "stop and forget", the 15-second undo, and the ledger being *true* are not. |
| Chrome extension: identity, announcement, native messaging host | ~1 week | Plus a manifest bump and another pass through `stranger_gate` leg 1 (§9.5). |
| Distribution: Developer ID, notarization, DMG, updates | 0.5–1 week **plus Apple's turnaround** | And this team has a recorded history of silent Apple distribution failures (`docs/BRIEF.html:504`). Start it first, not last. |
| The gate, and one real signed meeting | ~0.5 week | Leg 3 needs a real meeting with real people who were really told. That is a calendar dependency, not a coding one. |

**What is genuinely cheap**, and worth saying so the estimate is believed:
the server integration is **zero** (§8.1 — no route, no hook, no migration),
and speaker attribution is **free** (§3.4 — two wires instead of an embedding
model that has plausibly bricked five iOS builds).

**What is not in the estimate at all:** the brain-side ingest (§8.3), fixing
the phone, anything pendant, and legal review.

---

## 12. Law compliance

| Law | How this spec stands |
|---|---|
| **LAW 1** — no pattern-match decides meaning | The only pattern-matching proposed is `kAudioProcessPropertyIsRunningInput/Output` over process objects (§6.2) — plumbing, explicitly carved out — and the deterministic checks in §10 leg 4, which are gate-and-eval. Bundle identifiers label UI and hold a never-offer list; they are forbidden from deciding what anything means, and §6.2 says why in the place someone would reach for it. **No word list, no regex over speech, anywhere in this design.** |
| **LAW 2** — tape ships with an expiry | Nothing here is a string patch over meaning, so no `TAPE:` comment and no `tape_gate` entry is owed. If an implementer finds themselves wanting one — e.g. a bundle-ID list to decide *which meetings matter* — that is the design going wrong; §6.2 and LAW 5 name the alternative. |
| **LAW 3** — nothing is fixed until its leg is green against LIVE | §10 legs 1, 3 and 5 all read production or the signed artifact. The `.dmg` leg is deliberately live because this repo has served stale artifacts twice. Repo-green proves nothing about a Mac app a stranger downloads. |
| **LAW 4** — state lives in files | This file, and `overnight/mac_proof.json` when the meeting happens. §15's open questions are here, not in a chat. |
| **LAW 5** — senses → context → examples → tier → structure | This card **is** the senses rung, and that is why it is worth doing while the phone is broken: it adds an ear the product has never had, with attribution the phone cannot achieve. No behavioural rule is proposed anywhere in this document. |
| **LAW 6** — the owner is not the review loop | Written to be attacked. §13 is the attack surface named in advance; §15 hands back everything I could not settle rather than deciding it quietly. |
| **LOCAL-FIRST 1** — raw audio never leaves a device | §5.1 and §5.2, with §10 leg 4 as the mechanical enforcement. The refusal is written out with the Deepgram precedent attached because that is the mistake this card is most likely to repeat. |
| **LOCAL-FIRST 3** — smallest conclusion travels | The verbatim transcript stays on the Mac; one note row travels (§5.1, §8.2). This is *stricter* than what the phone does today, on purpose: a meeting is other people. |
| **LOCAL-FIRST 4** — degrade gracefully, keep capturing offline | §8.4's store-and-forward, with the unsent counter that the phone lacked. |
| **LOCAL-FIRST 5** — state your posture, name the later | §5.3: note generation is a cloud **text** call today, isolated to one call site, and is nominated as the first pilot for on-device triage. |

---

## 13. What would kill this

- **Simultaneous microphone capture turns out to be impossible while a meeting
  app holds the input device.** macOS has no exclusive-input rule equivalent to
  iOS's audio-session interruption, and I believe multiple clients can open the
  same input device — **but I did not test it, and this spec must not be
  believed on it.** If NEAR cannot be captured while Zoom is running, §3.4's
  whole attribution advantage collapses and the design falls back to a global
  tap plus voice separation, which is a different and much worse card. **Test
  this first. It is thirty minutes and it decides the architecture.**
- **The tap does not survive a real hour.** Device changes, helper-process
  restarts, and format renegotiation are where this class of app actually
  breaks, and below macOS 26 the restart case is entirely on us.
- **On-device transcription is not good enough for far-field multi-speaker
  audio**, and the demo makes that obvious. This is the moment the Deepgram
  argument comes back. §5.2 refuses it in advance; LAW 5 says fix the senses.
- **The Developer ID certificate does not arrive**, and the app remains a thing
  only this team can install (§4.3, §10 leg 5).
- **The note is posted and nothing ever reads it** (§8.3), so the card ships as
  a very good local recorder that the brain cannot see. This is the most likely
  way to be 90% done and stuck.
- **Someone builds automatic recording anyway** because the card says
  "automatically", and the first complaint comes from a person who was in a
  room, not from a user.

---

## 14. Decisions made without the owner

Recorded so Omar can overturn them cheaply rather than discover them:

1. **Explicit start over automatic**, against the literal word on the card
   (§6.3). Detection stays automatic.
2. **macOS 14.2 floor**, accepting that macOS 13 users are excluded, in
   exchange for not asking for screen-recording permission (§3.2, §3.5).
3. **Core Audio taps over ScreenCaptureKit**, on the prompt the user reads
   (§3.5).
4. **The verbatim transcript never leaves the Mac** — stricter than what the
   phone does today (§5.1).
5. **One `meeting_note` row per meeting, not transcript lines** — which means
   the note does nothing until §8.3 is built (§8.2).
6. **The pendant clause is out of scope** (§8.4).
7. **The announcement is a product feature, not an optional setting** (§7.2),
   with an all-party mode that refuses to record.

---

## 15. Handed back

Everything I could not settle, and who has to settle it. Nothing on this list
is a coin-flip an implementer should make alone.

**To whoever holds a Mac, before any code — these are measurements, not
opinions, and three of them can change the architecture:**

1. **Can the app capture the microphone while Zoom/Meet holds it?** §13's first
   bullet. Thirty minutes. If no, this design changes shape.
2. **Does `SpeechTranscriber` (macOS 26+) require Speech Recognition
   authorization?** If no, prompt 3 and its "sent to Apple" subtitle disappear
   entirely on 26+, and §3.3's copy problem is a legacy-path-only problem.
3. **What does a tap actually deliver from Chrome?** Chrome plays audio from a
   helper process, not the main bundle. Below macOS 26 there is no `bundleIDs`
   targeting, so this must be measured: which `AudioObjectID` carries Meet's
   audio, and does it survive a helper restart?
4. **Does a tap-bearing aggregate device change what the owner hears?**
   `muteBehavior` defaults to `CATapUnmuted` (`CATapDescription.h:20-21`), so it
   should not — confirm on real hardware with real AirPods, because "the app
   muted my meeting" is an uninstall.

**To Omar:**

5. **Buy the Developer ID Application certificate** (§4.3). Nothing ships to a
   stranger without it, and it gates §10 leg 5.
6. **Mac App Store or Developer ID?** All seven comparable apps on this machine
   are un-sandboxed direct downloads, and I could not determine whether a
   sandboxed build can hold a process tap. If MAS matters, someone must test
   that before the target is configured.
7. **Is the announcement negotiable?** §7 treats "the other participants are
   told" as a product requirement. If the answer is that it should be a
   setting, say so now — it changes §6.4, §7.2 and §10 leg 3.
8. **Is "meetings" the right unit at all**, or is the real want "the Mac is a
   second ear all day"? The tap makes both possible; they are very different
   products, and moment 18's restraint reads differently for each.

**To legal counsel — not to an agent, and not to Omar's judgement:**

9. **All-party consent exposure** in the jurisdictions the owner and his
   counterparties actually sit in. The RCFP guide cited in §6.3(b) is
   journalism, not advice.
10. **Whether recording a call with EU participants is defensible at all**, and
    on what basis. Signal worth weighing: Apple's own call recording is
    unavailable across the EU and eighteen other jurisdictions
    ([Apple Support](https://support.apple.com/guide/iphone/record-and-transcribe-a-call-iph57c6590e9/ios)
    — again read by the ios-reality lens, not re-fetched here).
11. **What the announcement sentence must say** to be worth anything, and
    whether "I've told them" as a checkbox has any value.

**To whoever owns SORTER / LIBRARY:**

12. **The meeting-note ingest** (§8.3): one worker path, memory-only,
    provenance-tagged so the origins gate can refuse to let it mint an action.
    Without it this card is half-built.
13. **The digest settle window**, already recorded as miscalibrated
    (`docs/BRIEF.html:501`). A Mac recorder will make it fire mid-meeting more
    often, not less.

**To whoever owns the phone:**

14. **`research/2026-08-25-the-ears-stopped.md` is still open**, and until it
    closes the pendant clause of this card cannot start and the product has one
    ear at most. The Mac does not fix it and must not be sold as fixing it.
