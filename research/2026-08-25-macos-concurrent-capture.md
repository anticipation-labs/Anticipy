# Can the Mac hear BOTH sides at once? Measured, on 2026-08-25.

> The experiment the MAC spec asked for before any code
> (`docs/superpowers/specs/2026-08-25-macos-meeting-recorder.md` §13 first
> bullet, §15 item 1), run on the machine it was written on.
>
> **Answer: YES for the microphone, and it is the strong kind of yes.**
> Two processes captured the same live microphone at the same time, both
> getting real audio, in every contention mode this machine can produce —
> including exclusive hog mode, which is the strongest exclusion primitive
> Core Audio offers. §3.4's attribution advantage stands.
>
> **The experiment also found something the spec does not contain, and it is
> the more dangerous of the two findings: on macOS an ungranted capture does
> not fail. It succeeds and delivers silence.** §4 below. Every API returned
> `noErr`, the IOProc was called 94 times a second with a well-formed buffer
> list, and every sample in it was `0.0` for fifteen seconds. An app that
> trusts return codes records an hour of nothing and posts a note about it.
>
> **What is still NOT proven: the far channel was never heard.** The tap ran,
> concurrently, at full rate — but this machine has never been granted System
> Audio Recording, so what it delivered was the silence described above. FAR
> is proven to *run alongside* NEAR; it is not proven to *carry the far side
> of a call*. §6 says exactly what a human must do to close that, and §7 is
> the honest ledger of what remains open.

---

## 1. The machine, and the floor

```
$ sw_vers
  ProductName:     macOS
  ProductVersion:  15.6.1
  BuildVersion:    24G90
$ uname -m
  arm64                      # Apple silicon, MacBook Air
$ swiftc --version
  Apple Swift version 6.2.4, Xcode 26.3 (17C529)
```

The floor the spec names is real and this machine clears it. Read from the SDK
on this machine, not from memory
(`MacOSX26.2.sdk/…/CoreAudio.framework/Headers/AudioHardwareTapping.h:43-44`):

```c
extern OSStatus
AudioHardwareCreateProcessTap(CATapDescription* inDescription,
                              AudioObjectID*  outTapID)
                              API_AVAILABLE(macos(14.2)) API_UNAVAILABLE(ios, watchos, tvos);
```

15.6.1 ≥ 14.2, so process taps are available here. Also confirmed, matching §4:

```
$ systemextensionsctl list
  0 extension(s)
$ ls /Library/Audio/Plug-Ins/HAL/
  OculusRemoteDesktopASP.driver     # unrelated
```

**No driver, no kext, no system extension was installed to make any of this
work.** The taps below were created by an ordinary program.

Two spec claims about macOS 26-only members are confirmed from
`CATapDescription.h`: `bundleIDs` (:135-136) and `processRestoreEnabled` (:166-167) are
both annotated `API_AVAILABLE(macos(26.0))`, i.e. unavailable here. Below macOS 26 you resolve PID →
`AudioObjectID` yourself and you rebuild the tap yourself when the tapped
process restarts. That work is real and it is in §11 of the spec.

---

## 2. The instruments

Three small programs, committed so this is re-runnable rather than a story:

| Program | What it does | Path |
|---|---|---|
| `audioprocs` | enumerates `kAudioHardwarePropertyProcessObjectList` and prints, per process, `kAudioProcessPropertyIsRunningInput` / `…IsRunningOutput`. This IS the §6.2 detection signal. | `app/macos/Tools/audioprocs.swift` |
| `holder` | a SEPARATE process that holds the default input device — `plain`, `vpio` (Voice-Processing IO, what conferencing apps use), or `hog` (exclusive access) | `app/macos/Tools/holder.swift` |
| `dual` | opens NEAR (`AVAudioEngine` input tap) and FAR (`AudioHardwareCreateProcessTap` → tap-bearing aggregate device → IOProc) and reports per-second buffer counts and peak amplitude for both | `app/macos/Tools/dual.swift` |

One command runs the whole thing:

```
sh app/macos/Tools/run_concurrent_capture_probe.sh              # self-contained
sh app/macos/Tools/run_concurrent_capture_probe.sh --with-zoom  # the faithful one, needs a human
```

**Peak amplitude is the load-bearing column.** Buffer counts only say the
plumbing is turning over; the peak says whether anything was in them. §4 is why
that distinction is the whole point.

---

## 3. The proxies, and how faithful each one is

I could not get real Zoom to hold the microphone. **Zoom IS installed on this
machine** (`/Applications/zoom.us.app`) and was already running as
`us.zoom.xos` pid 79315 — the spec's author assumed otherwise. But launching it
changed nothing: watched for 14 seconds after `open -a zoom.us`, Zoom never
appeared in the process list with `in=1`. **Zoom opens the input device only
inside a meeting or its audio test, and both require a click I cannot make.**

So these are the proxies actually used, stated plainly:

| Proxy | What it stands in for | How faithful |
|---|---|---|
| `holder vpio` — a second process on `kAudioUnitSubType_VoiceProcessingIO` via `AVAudioEngine.setVoiceProcessingEnabled(true)` | Zoom/Meet/Teams holding the mic | **High on the dimension that matters.** VPIO is the audio unit conferencing apps use precisely because they need AEC/AGC/NS. It is the same HAL client type, and it took input+output exactly as a meeting app does. It is not Zoom's binary. |
| `holder hog` — a second process owning `kAudioDevicePropertyHogMode` on the input device | the worst case Core Audio permits any app to impose | **This is the pessimistic bound, and it is the strongest argument here.** Hog mode is the only exclusive-access mechanism Core Audio offers. If hog does not lock us out, no application can, because there is nothing stronger for Zoom to use. |
| `com.apple.CoreSpeech` — macOS dictation, holding `in=1` on its own | "macOS itself can be one", as the card put it | **Real, and un-arranged.** An Apple system process held the input device through several of the runs below without my asking. At those moments three processes had the microphone open at once. |
| `afplay` playing a generated 90 s tone | the far side of a call playing out | Fine as a tap TARGET. Says nothing about Zoom's own output routing (§7). |

**The honest gap:** none of these is Zoom's actual binary. What closes it is §6,
and it takes a human ninety seconds.

---

## 4. The runs

### 4.1 Baseline — the microphone alone

```
NEAR format: 48000 Hz, 1 ch          NEAR: started
  t=1..6   +10 buffers/s   peak 0.0084 – 0.0736
SUMMARY  NEAR buffers=60 frames=288000
```

Real audio: a quiet room reads a peak around 0.008–0.01, a nearby noise 0.07.
Remember these numbers; §4.4 turns on them.

### 4.2 The microphone WHILE a Voice-Processing process holds it — the card's question

`holder vpio` (pid 46157) running first. `audioprocs` while it ran:

```
objID    pid      in     out    bundle / name
145      46157    1      1      ./holder
```

`in=1 out=1` — the §6.2 detection signal, fired by a conferencing-shaped
process, exactly as the spec predicted. Then, with it still holding the device:

```
NEAR format: 48000 Hz, 3 ch          NEAR: started
  t=1..8   +10 buffers/s   peak 0.0019 – 0.0022
SUMMARY  NEAR buffers=80 frames=384000
  holder, concurrently: buffers=180, still +10/s throughout
```

**Both processes captured the live microphone at the same time, both receiving
real audio, neither disturbing the other.** This is the answer.

### 4.3 Both channels at once, under contention — the full §3.1 design

`holder vpio` holding the mic, `afplay` playing a tone (pid 47610), `dual`
opening NEAR and a tap on afplay. `audioprocs` at that moment shows the
detector discriminating correctly:

```
112      2698     1      0      com.apple.CoreSpeech     <- listens only: not a conversation
145      46157    1      1      ./holder                 <- two-way: THIS is the signal
146      47610    0      1      afplay                   <- plays only: not a conversation
```

```
FAR: tap created, AudioObjectID=153
FAR tap format: status=0  48000 Hz, 2 ch, flags=9
FAR: aggregate device 154 created
FAR: started (48000 Hz, 2 ch)

  t   NEAR buf  (+d)   NEARpk    FAR buf  (+d)   FARpk    both?
  1        10 (+10)   0.0020         91 (+91)   0.0000    YES
 ...
 10       100 (+10)   0.0021        936 (+94)   0.0000    YES

SUMMARY  seconds in which BOTH delivered: 10/10      exit=0
```

**Ten seconds out of ten with both streams live.** A tap was created and drained
through an aggregate device while a separate process held the microphone and a
third process played audio — no driver, no extension, no admin password, no
reboot. Structurally, §3.1 works.

And then the column that matters: **`FARpk` is `0.0000`.** §4.4.

### 4.4 The finding the spec does not have: ungranted capture succeeds and delivers silence

Every step of the FAR path reported success. `AudioHardwareCreateProcessTap`
returned `noErr`. The aggregate device was created. `AudioDeviceStart` returned
`noErr`. The IOProc was called 94 times a second at exactly 48 kHz. The buffer
list was well-formed — dumped on the first callback:

```
FAR first-callback buffer list: mNumberBuffers=1 [ch=2 bytes=4096 data=true]
```

4096 bytes = 512 frames × 2 ch × 4 bytes float32, non-null pointer. And every
sample in it was zero, for fifteen seconds, 1410 buffers, 721 920 frames.

This machine has never granted System Audio Recording. **No prompt appeared** —
I checked; `UserNotificationCenter` had been up eleven hours and had no windows.
TCC denied silently.

Then the same thing happened to the **microphone**, which proves it is a
property of TCC and not of taps. Run from the terminal, `dual` inherits the
terminal's microphone grant and reads real audio. Packaged as a signed `.app`
with its own bundle identity (`ai.anticipy.mac.tapprobe`) and launched through
LaunchServices — no grant of its own — it read:

```
NEAR format: 48000 Hz, 3 ch     NEAR: started
  t=1..6   +10 buffers/s   peak 0.0000
```

Ten buffers a second. All zeros. `engine.start()` did not throw.

**So on macOS, "the capture started" and "the capture is recording" are
different facts, and nothing in the API separates them.** The only thing that
does is looking at the samples. This is now enforced in code:
`app/macos/Anticipy/Capture/CaptureStreamHealth.swift`, whose entire reason for
existing is these two windows, which differ by 0.0021 and by nothing else:

| | buffers | frames | elapsed | peak | Core Audio said |
|---|---|---|---|---|---|
| ungranted tap | 1410 | 721 920 | 15 s | **0.0000** | `noErr` |
| granted mic, quiet room | 80 | 384 000 | 8 s | **0.0021** | `noErr` |

The test is identity with zero, not a tolerance — a tolerance wide enough to
feel safe swallows the quiet room and starts telling owners mid-meeting that
their microphone is off. The runner mutation-tests that.

### 4.5 The pessimistic bound: hog mode does not lock us out

`holder hog` took exclusive ownership of the input device, confirmed by
read-back:

```
holder mode=hog pid=53807 inputDevice=80 "MacBook Air Microphone"
  hog set scope=global status=0 readback_owner_pid=53807
  hog result: ok
```

With the device hogged by another process, a second process captured it anyway,
with real audio at the baseline level:

```
NEAR format: 48000 Hz, 1 ch     NEAR: started
  t=1..8   +10 buffers/s   peak 0.0082 – 0.0111
```

**Hog mode is the strongest exclusion Core Audio offers and it did not exclude
us.** That is what makes the answer in §5 a strong yes rather than a lucky one:
there is no stronger mechanism available to Zoom.

Caveat, stated because it is real: this is the built-in "MacBook Air
Microphone". Hog semantics can differ on USB and aggregate devices.

### 4.6 A side finding the implementation must survive: the format renegotiates

The NEAR input format was not stable. It changed with what else held the device:

| Condition | `AVAudioEngine.inputNode` format |
|---|---|
| nothing else holding the mic | 48000 Hz, **1 ch** |
| a VPIO process holding the mic | 48000 Hz, **3 ch** |
| a hog-mode process holding the mic | 48000 Hz, **1 ch** |
| inside the VPIO holder itself | 48000 Hz, **7 ch** |

**A meeting app joining or leaving changes the channel count under a running
engine.** This is precisely the "format renegotiation" the spec's §11 estimate
calls the underestimated part, and here is a measurement of it happening on an
idle desk in under a minute. Anything that caches the input format at start and
assumes it holds for an hour is wrong.

---

## 5. The answer, in the terms the card asked for

**Can the app capture the MICROPHONE while another process holds the input
device? YES.** Measured four ways on macOS 15.6.1: against a plain HAL client,
against a Voice-Processing IO client, against an Apple system process
(CoreSpeech), and against an exclusive hog-mode owner. In every case a second
process opened the same live microphone and received real, non-zero audio, and
in every case the first process kept receiving audio too.

**Therefore §3.4 stands.** The Mac gets speaker attribution from the wiring —
FAR is definitionally not the owner, NEAR is definitionally this side — and the
card does NOT collapse into "a global tap plus voice separation". The spec's
`macOS has no exclusive-input rule equivalent to iOS's audio-session
interruption` was a belief; it is now a measurement, and the belief was right.

**Can the app capture both channels concurrently? Structurally yes, acoustically
unproven.** NEAR and FAR ran together 10/10 and 15/15 seconds with the tap
delivering at full rate. But FAR delivered zeros, because of §4.4, so this
experiment has never actually *heard* the far side. Do not report that half as
proven.

**HARNESS LAW 3 applies to this document.** Nothing here has run on a signed,
notarized, granted app, and none of it has touched production. What is proven is
a property of macOS on one machine, not a working product.

---

## 6. What a human with Zoom open has to run, exactly

Ninety seconds, and it converts §5's second paragraph from unproven to proven.

**First, grant the two permissions once** — this is what §4.4 showed is
missing, and neither can be granted from a script:

1.  System Settings → Privacy & Security → **Microphone** → enable your
    terminal (or the Anticipy app once it exists).
2.  System Settings → Privacy & Security → **System Audio Recording** → same.
    If it is not listed, run the probe once first so it registers.

**Then:**

3.  Open Zoom and **join a meeting** — `https://zoom.us/test` is Zoom's own echo
    test and needs no account — or Settings → Audio → **Test Mic**. Confirm
    Zoom's input level meter is moving.
4.  With Zoom hearing you, run:

    ```
    sh app/macos/Tools/run_concurrent_capture_probe.sh --with-zoom
    ```

5.  **Talk, and play the echo test's playback, while it runs.**

**What proves what:**

- `us.zoom.xos` (or a Zoom helper) appearing with `in=1` in the `audioprocs`
  table **at the same time** as `NEARpk` being non-zero → the microphone was
  captured out from under real Zoom. Closes the §3 fidelity gap.
- `FARpk` non-zero while Zoom plays the echo back → the far channel genuinely
  carries the other side. Closes §5's second paragraph, and is the first real
  evidence for §3.1.
- **A rising buffer count with a peak of exactly `0.0000` is a FAILURE, not a
  pass.** Go back to step 1.

Two more things only a human on a Mac can settle, both still open from spec §15:

- **§15 item 3** — which `AudioObjectID` carries Google Meet's audio, given
  Chrome plays from a helper process, and whether the tap survives a helper
  restart. `audioprocs --all` lists the helpers by bundle ID; it printed
  `com.google.Chrome.helper` twice on this machine.
- **§15 item 4** — whether a tap-bearing aggregate device changes what the
  owner hears. `muteBehavior` was set to `CATapUnmuted` in every run above and
  nothing audibly changed, but nobody was on a call and no AirPods were
  connected, so this is not yet an answer.

---

## 7. What is still unknown, listed so nobody mistakes this for a finished card

1. **The far side has never been heard.** §4.4, §6. The single biggest gap.
2. **Real Zoom has never held the mic against us.** §3. The proxy argument is
   strong — hog mode is the pessimistic bound — but it is an argument.
3. **The tap has not survived a real hour**, a device change, AirPods
   connecting, or a `coreaudiod` restart. The longest run here was 15 seconds.
   §4.6 shows the format moving on an idle desk; an hour on a call will be
   worse.
4. **The helper-restart case is entirely unbuilt and unmeasured.** Below
   macOS 26 there is no `processRestoreEnabled`, and Chrome respawns its audio
   helper routinely.
5. **On-device transcription has not been touched.** Not `SpeechTranscriber`,
   not `SFSpeechRecognizer`, not `supportsOnDeviceRecognition` on this hardware.
6. **Whether a sandboxed build can hold a process tap** — still open, spec §15
   item 6.

---

## 8. Two things this experiment does not fix, and one the spec gets wrong

**Gate leg 5 is red and nothing here changed that.** Re-measured today:

```
$ security find-identity -v -p codesigning
  1) "Apple Development: Created via API (ZJ49TWB9LG)"
  2) "iPhone Distribution: Omar Ebrahim (49T86P9XGW)"
     2 valid identities found
```

**There is still no Developer ID Application certificate.** The probe app in
§4.4 was ad-hoc signed, which is fine for a measurement and useless for a
stranger. A cold stranger cannot install this app today, no matter how good the
capture core is. That is an account action on Omar's membership (spec §15 item
5), and the note in §4.4 sharpens why it should happen early: **TCC would not
even prompt for the ad-hoc build.** The "drag to Applications, open, click Allow
twice" story in §4.1 of the spec is UNVERIFIED, and the one attempt to verify it
produced a silent denial rather than a prompt. It may well be the missing
certificate; it may be that the app was in `/private/tmp`. Either way, nobody
has yet seen the two prompts the spec quotes in §3.3.

**"Automatically" stays refused for capture and kept for detection.** Nothing
measured here weakens spec §6.3. The detector is now real code
(`MeetingOfferPolicy`) whose return type is an offer or nothing, with no
vocabulary for starting a recording, and the runner fails if it acquires one.

**The pendant is MUTE, and it is worse than the spec knew.** §8.4 of the spec
treats the pendant as blocked upstream by the dead phone. It is now blocked
downstream too: the pendant's cloud transcriber was deleted on 2026-08-24 for
breaking `design/LOCAL-FIRST.md` rule 1, and there is no on-device replacement —
`LocalTranscriber.swift` is 43 lines with zero call sites, it wants
`AVAudioPCMBuffer` while the pendant emits Opus `Data`, and there is no Opus
decoder in the target. **Anywhere the spec says the pendant is merely
unreachable from macOS, read: the pendant cannot transcribe anything, for
anyone, on any host, today.** The card's third clause ("automatically syncs
notes with the pendant") is not deferred. It is dead until somebody builds an
on-device transcriber for it.

---

## 9. Law compliance for what was built

| Law | How this stands |
|---|---|
| **LAW 1** | `MeetingOfferPolicy` reads only which PROCESS holds which STREAM — `IsRunningInput`/`IsRunningOutput` — which is the senses carve-out verbatim. Bundle identifiers label the banner and key the owner's never-offer list; the runner FAILS if one becomes a predicate, and that leg is mutation-tested. `CaptureStreamHealth` asks whether a sample differs from zero; it never sees a transcript. **No word list, no regex over speech, anywhere.** |
| **LAW 2** | No tape. Nothing here is a string patch over meaning, so no `TAPE:` comment and no `tape_gate` entry is owed. |
| **LAW 3** | Said out loud in §5 and §7: this proves a property of macOS on one machine. Nothing has run signed, granted, or against production. Gate leg 5 is still red (§8). |
| **LAW 4** | This file, plus the probe committed under `app/macos/Tools/` so the measurement is re-runnable rather than remembered. |
| **LAW 5** | This is the senses rung, which is where the fix order says to start. No behavioural rule was written. §4.4 exists *because* the sense was measured rather than assumed. |
| **LAW 6** | §3 names its own proxies' weaknesses, §5 refuses to call the far channel proven, §7 is the attack surface, and §8 says the spec's install story is unverified. |
| **LOCAL-FIRST 1** | No audio was written to disk and none left this machine. The runner greps the whole `app/macos` tree for cloud speech vendors and fails on a hit; mutation-tested. |

---

## 10. What was built alongside this, and what it counts

The experiment came first because it decides the architecture. Only after it
answered did any product code get written, and it is deliberately the smallest
honest slice: **two pure types and no app.** No UI, no Xcode target, no Chrome
extension work, no pendant — the pendant is mute (§8) and the rest is weeks
(spec §11).

| File | What it decides |
|---|---|
| `app/macos/Anticipy/Capture/MeetingOfferPolicy.swift` | whether to OFFER to record. Its return type is an offer or nothing; it has no vocabulary for starting one. §6.2's signal, built from §4.3's measured rows. |
| `app/macos/Anticipy/Capture/CaptureStreamHealth.swift` | whether a running stream is carrying audio or is §4.4's silence. Exists only because of §4.4. |
| `app/macos/Tests/CaptureCoreTests.swift` | **30 checks.** |
| `app/macos/Tests/run_capture_core_tests.sh` | four deterministic source-tree legs, run before the checks compile |

```
$ sh app/macos/Tests/run_capture_core_tests.sh
  the detector offers and cannot record, and no app name is a predicate
  silence is identity with zero, as measured
  … 30 × PASS …
  all capture-core checks passed
$ echo $?
  0
```

**Correction to the record.** The commit that introduced these files
(`e7a8e731`) says "31 checks" in its message. The true count is **30**,
`grep -c '^PASS'` against a clean run. History is not rewritten in this repo, so
the number is corrected here, where a reader can act on it. Nothing else in that
message is affected — the mutation results below are as stated.

The four source-tree legs were each mutation-tested by introducing exactly the
thing they forbid, and each returned exit 2:

| Mutation | Leg that caught it |
|---|---|
| `extension MeetingOfferPolicy { func startRecording() {} }` | the detector may not learn to record |
| `var isZoom: Bool { (bundleID ?? "").contains("zoom") }` | no meeting-app name may become a predicate |
| `peakAmplitude == 0` → `peakAmplitude < 0.005` | silence is identity with zero, not a tolerance |
| a cloud speech vendor named in a comment | LOCAL-FIRST rule 1 / spec gate leg 4 |

Clean, the runner returns 0. This matters because this repo has found gate rules
that passed by matching nothing; a leg that has never been made to fail is not
known to work.

**These are unit checks over pure functions. They are not LAW 3 evidence for
anything.** No signed app exists, no permission has been granted, nothing has
been posted to production, and `overnight/mac_ear_gate.py` — the spec's five
legs — has not been written. The card is at its first rung.
