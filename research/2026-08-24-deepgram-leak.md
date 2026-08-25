# The Deepgram leak — is it live, what leaves, and what it costs to close

**Date:** 2026-08-24 · **Tree:** `/Users/josegaelcruzlopez/Desktop/anticipy-omize`
· **Branch:** `jose_anticipy_system` · **Method:** read-only investigation, no
product code touched.

**One-line verdict:** it is **not dead code and not a day-one stranger risk** —
it is a fully wired path that the owner reaches in **two taps on hardware he
already owns**, and the repo's own record of *why* it is safe
(`docs/FOLLOWUPS.md:41-43`, "latent only because the firmware is
BUILT_AND_VERIFIED_NOT_FLASHED") **is wrong**.

---

## 1. Is it live

### The path, end to end, with line numbers

| # | Step | Evidence |
|---|---|---|
| 1 | Owner taps **Settings → Pendant → "Pair a pendant"** | `app/ios/Anticipy/Views/SettingsView.swift:159` — `Button("Pair a pendant") { pendant.startScan() }`. This is the **only** call site of `startScan()` in the app. |
| 2 | The app scans for BLE service `19B10000-E8F2-537E-4F6C-D104768A1214` | `app/ios/Anticipy/BLE/PendantManager.swift:20`, `:158` |
| 3 | It connects to the **first** peripheral advertising that service — no name filter, no allow-list | `app/ios/Anticipy/BLE/PendantManager.swift:235-243` (`didDiscover` → `central.connect(p)` unconditionally) |
| 4 | It subscribes to the audio characteristic on every connection | `app/ios/Anticipy/BLE/PendantManager.swift:283` — `setNotifyValue(true, for: c)` |
| 5 | Reassembled Opus frames fire `onOpusFrame` | `app/ios/Anticipy/BLE/PendantManager.swift:300` |
| 6 | On `isSignedIn && pendant.state == .connected`, a SwiftUI `.task` starts the lane | `app/ios/Anticipy/AnticipyApp.swift:70-75` |
| 7 | Frames are forwarded to the Deepgram client verbatim | `app/ios/Anticipy/AnticipyApp.swift:1008` — `pendant.onOpusFrame = { frame in transcriber.send(opusFrame: frame) }` |
| 8 | A 60-second JWT is fetched from Anticipy's own backend | `app/ios/Anticipy/AnticipyApp.swift:1016`, `app/ios/Anticipy/Backend/AnticipyBackend.swift:186-197` |
| 9 | The socket opens to Deepgram and raw Opus starts flowing | `app/ios/Anticipy/Audio/TranscriberClient.swift:26-34`, `:39-46` |
| 10 | Finalized text re-enters as an ordinary heard line | `app/ios/Anticipy/AnticipyApp.swift:264-266` |

The client is instantiated at **`app/ios/Anticipy/AnticipyApp.swift:166`**
(`private let pendantTranscriber = TranscriberClient()`). It is not behind a
build flag, a debug guard, a feature toggle, or a remote config. There is no
`#if DEBUG`, no `ProcessInfo` check, no `@AppStorage` gate anywhere on this
path. The **only** preconditions are: signed in, and a pendant connected.

### The backend half is live in production right now

Unauthenticated probe of the live URL in `AnticipyApp.swift:154`:

```
$ curl -X POST https://backend-production-61e0a.up.railway.app/transcription/token
401 {"error":"sign in first"}
```

`401` — not `404`. `backend/pb_hooks/transcription_token.pb.js:8` is **deployed
and serving on production**. The route that mints Deepgram credentials exists on
the live system today. (LAW 3 check, performed, not assumed.)

### Why "latent because the firmware is not flashed" is wrong

`docs/FOLLOWUPS.md:41-43` and `research/2026-08-24-engine-options.md:630-632`
both rest the safety case on
`firmware/BUILD_RECEIPT.json:3` → `"BUILT_AND_VERIFIED_NOT_FLASHED"`. Reading
that receipt in full, that status describes **one specific image** — the
2026-07-25 *dual-hatch DFU bridge* build whose stated `purpose` is
"First firmware image containing BOTH software routes into the Adafruit nRF52
bootloader." It says nothing about what the pendant is running now. Three facts
from the repo contradict the inference:

1. **`firmware/source/DUAL_HATCH_RECEIPT.json`** states the image's purpose is
   *"for a pendant whose RESET button cannot be pressed."* You do not build a
   recovery bridge for a device that does not exist. A physical pendant exists.
2. **`firmware/BUILD_RECEIPT.json:112`** names the parent image
   (`anticipy-v2.0.1/zephyr/zephyr.uf2`, sha `36424986…`) as the *"control
   parent candidate"* under a path literally named
   `firmware-authorized-flash-20260723-07/recoverable-candidate/`. The parent
   was flashed; the dual-hatch successor was not.
3. **`PROOF_REPORT.md:109-111`** records the end state already having happened
   once: *"Cloud transcription (Deepgram, your key) on REAL pendant audio — Your
   66s capture transcribed by Deepgram nova-2: word-for-word correct, including
   'The password is seventeen forty eight.'"* And `PROOF_REPORT.md:121` names
   the board's firmware: *"the exact release tag running on your board
   (v2.0.1-Omi)."*

And the app does not require *Anticipy* firmware at all. `19B10000-…-768A1214`
is the **Omi/Friend audio service UUID**, shared by the whole Omi lineage, and
`didDiscover` (`PendantManager.swift:235-243`) connects to anything advertising
it. Any off-the-shelf Omi-lineage pendant in range pairs and streams.

### But there is no stranger, and that is the honest ceiling on severity

`docs/BRIEF.html:504`: *"TestFlight rejects builds with the speaker frameworks
silently during processing (missing privacy manifests suspected). **Build 76
installs by cable**; distribution needs this solved."* The current source is
build 76 (`app/ios/project.yml:120`). **There is no public distribution
channel today.** The reachable population is the owner and anyone he cable-
installs onto.

### Severity, stated plainly

Not dead code. Not a stranger-on-day-one exposure. **It is a live,
unflagged, two-tap path on hardware that exists, whose backend half is
serving on production, blocked from the public only by an unrelated
TestFlight packaging failure.** The safety margin is an accident, not a
design, and it disappears the moment the privacy-manifest problem is fixed —
which is on somebody's list as a *goal*.

---

## 2. What leaves the phone

### Pendant lane only. The phone microphone cannot reach Deepgram.

`TranscriberClient.send(opusFrame:)` has exactly one caller in the entire
codebase: `AnticipyApp.swift:1008`, fed only by `pendant.onOpusFrame`. The phone
mic path (`PhoneListener` → `SFSpeechRecognizer`) never touches it. Verified by
exhaustive grep over `app/ios/**/*.swift`.

### What actually goes over the wire

**Raw, undecoded, un-gated Opus audio** — every frame the pendant emits, with no
VAD, no energy gate, no silence suppression anywhere in app or firmware
(`docs/BRIEF.html:328` records the grep: zero VAD hits). The pendant streams
continuously. `firmware/source/src/config.h:23-26`: Opus 16 kHz mono, 32 kbps,
`RESTRICTED_LOWDELAY`/CELT, 160-sample (10 ms) frames.

The URL declares what Deepgram is asked to do with it
(`TranscriberClient.swift:27`):

```
wss://api.deepgram.com/v1/listen?encoding=opus&sample_rate=16000&channels=1
  &punctuate=true&smart_format=true&interim_results=false&endpointing=500
```

Note what is **absent**: `mip_opt_out=true`.
`research/2026-08-24-engine-options.md:615-620` establishes that without it,
Deepgram's own docs reserve the right to retain *"fractional increments of data
for the continued improvement of our voice AI models."* So the audio is not only
leaving the phone, it is leaving under the default retention posture.

Everyone in earshot of the pendant is captured, including people who never
touched the app.

### What the owner is actually told

**The iOS Bluetooth permission prompt — honest** (`app/ios/project.yml:182`):

> "Anticipy connects to your pendant over Bluetooth. When it is connected,
> pendant audio is sent to Deepgram for live transcription. Only needed if you
> have a pendant."

**Settings → "Between us" — honest** (`SettingsView.swift:367`):

> "If you use a pendant, its Opus audio goes to Deepgram to become text. My
> backend gives this phone a short-lived token; the Deepgram account key stays
> on the server."

**Settings → Pendant, while streaming — honest** (`SettingsView.swift:142`):

> "Pendant audio goes to Deepgram for live transcription; finalized text then
> follows the same Anticipy path as phone speech."

**Home status pill — honest** (`ContentView.swift:874`).

**Onboarding — silent.** `OnboardingView.swift:410` is the only pendant mention:
*"If you ever have an Anticipy pendant, you can pair it in Settings. You don't
need one. Your phone is enough."* No Deepgram, no cloud. Defensible — onboarding
never asks for Bluetooth, and the permission prompt at pairing time does say it.

### The one screen that lies — and it is the screen about listening

This is a finding I did not find recorded anywhere in the repo.

The Settings **"Listening"** section branches on `session.listener.isListening`
(`SettingsView.swift:80`) — the **phone microphone only**. With a pendant
connected and the phone mic off, the branch taken is `SettingsView.swift:101-106`:

> Button: **"Start listening"**
> Caption: **"Nothing is being heard, and nothing is being written down."**

…and the section headline, `listeningState` (`SettingsView.swift:597-612`),
returns:

> **"I'm not listening."**

All three are false at that moment. The pendant is streaming raw audio to a
third-party vendor. The Pendant section further down the same screen says the
true thing, so the app contradicts itself on one scroll.

Worse, the pause controls do not reach the pendant at all. `stopNow()`,
`pause(minutes:)` and `stopListening()` (`SettingsView.swift:623-633`,
`AnticipyApp.swift:1166-1169`) touch only `listener` and `keepListening`.
`startPendantTranscription` (`AnticipyApp.swift:1003-1005`) reads neither
`keepListening` nor `listeningPauseUntil`. **"Pause for 15 minutes" does not
pause the pendant.** "Until I turn it back on" does not turn it off.

That is the same failure shape as the docs-ex-88 rule this codebase enforces
everywhere else — the app describing a state it is not in — except here the
state it is misdescribing is a live audio upload.

---

## 3. Why the replacement does not run

I read `LocalTranscriber.swift` in full (41 lines). **"The compliant replacement
is written" is an overstatement, and its own header is false on its face.**

### It claims a UI that was deleted

`app/ios/Anticipy/Audio/LocalTranscriber.swift:6`:

> `/// Selected by the Local/Cloud toggle in Settings.`

There is no such toggle. `grep -rn transcriptionEngine` over the whole tree
returns **zero hits in any source file** — only two archaeological references in
`design/CONSUMER-READINESS-2026-08-03.md:71,256`. Git explains it:
`LocalTranscriber.swift` was born in commit `219a5505` *"local/cloud
transcription toggle, UI polish, full-chain + Deepgram + local STT proofs"* —
written **for** that picker. The consumer-readiness pass then deleted the picker
as a UI that claimed a capability the app did not have
(`CONSUMER-READINESS-2026-08-03.md:256` records the removal as a completion
criterion). The picker went; the class stayed, orphaned, still describing its
dead parent. **Written and forgotten**, in the most literal sense.

### It is not a drop-in — the types do not meet

`LocalTranscriber.append(pcmBuffer: AVAudioPCMBuffer)` (`:34`) wants **decoded
PCM**. `PendantManager.onOpusFrame` produces **compressed Opus `Data`**
(`PendantManager.swift:60`). There is **no Opus decoder anywhere in the iOS
target** — verified by grep for `opus_decode`, `opus_decoder`, `libopus`,
`OpusDecoder` across `app/ios/`: zero hits outside the firmware tree. The single
`AVAudioConverter` in the app (`SpeakerTagger.swift:72`) is a PCM-format
downmixer, not a codec.

`AUDIT-2026-07-21.md:78` recorded this exact gap thirteen months of commits ago
and it has never been closed.

### It would reintroduce a class of bug the app already fixed

`LocalTranscriber` creates **one** `SFSpeechAudioBufferRecognitionRequest`
(`:17-30`), never swaps it, and emits only on `result.isFinal` with a
`lastEmitted` string-inequality dedupe. Compare what the phone lane needed to
work: `PhoneListener.swift` is **1,061 lines** of exactly the machinery this
41-line class lacks — orphan-buffer replay across request swaps capped at 600
(`:158-176`, `:390-407`), a 4-second watchdog with distinct
recover/swap/rotate outcomes (`:662-672`), `TranscriptCursor` (766 lines of
word-level emission tracking), `TranscriptFlushPolicy` (2.6 s debounce, 8 s
ceiling — the ceiling exists because of a recorded 2026-08-16 live failure where
250 words became 71 characters).

Dropping `LocalTranscriber` in would not restore the law with the feature
intact. It would restore the law and hand back a transcriber that emits roughly
one line per conversation.

### Verdict on question 3

Unfinished **and** wired to a flag that no longer exists **and** written and
forgotten — all three, in that order. The honest sentence is: *the compliant
replacement is a 41-line sketch that cannot accept the pendant's data type and
was built for a UI that has since been deleted.* Anything stronger than that in
the repo — including `docs/FOLLOWUPS.md:44` ("The law-abiding replacement is
already written and unplugged") and
`research/2026-08-24-engine-options.md:632-636` — overstates it.

---

## 4. The options, with their costs

The pendant lane genuinely has **no on-device path today**. Removing Deepgram
removes a working feature. Both directions are priced.

### Option A — Disable the lane now. Cost: hours. Loses the pendant feature.

Make `TranscriberClient.connect` unreachable: stop the `.task` at
`AnticipyApp.swift:70-75` from starting the lane, or have `connect` refuse. Then
fix the three screens.

The honest degraded copy is **already written**. `SettingsView.swift:143` has
*"The pendant is connected, but its transcription stream is not live yet."* and
`ContentView.swift:875` has a sibling. Both render whenever `pendantCapturing`
is false, which is exactly the state this produces. `ContentView.swift:875-876`
needs a small edit — it currently says *"I'm opening its secure transcription
stream"*, which is a transient claim being made permanent.

Also required, and not optional: fix the Listening section so it stops saying
"Nothing is being heard" while a pendant is connected, and make the pause
controls cover the pendant.

- **What it costs:** the pendant becomes a battery-powered paperweight — BLE
  connects, battery shows, no words. For a product whose defining example
  (`docs/BRIEF.html`) is *"The promise never got a calendar entry — it lives
  solely in what the pendant heard"*, that is a real loss, not a cosmetic one.
- **What it buys:** the law holds today, on the current build, before the
  TestFlight blocker is solved and the population stops being one person.
- **Law 2 posture:** this is not tape — nothing is being patched over. It is a
  capability withdrawal. The `TAPE:` marker belongs on the *remaining* dead
  Deepgram code if it is kept in the tree at all; cleanest is to delete
  `TranscriberClient.swift` and `backend/pb_hooks/transcription_token.pb.js`
  outright and let the gate leg assert their absence.

### Option B — Build the on-device pendant path, then delete Deepgram. ~4-5 days.

Roughly the shape already drafted at
`research/solutions-2026-08-24/designs.json:296`, which I read and largely agree
with:

1. **Decode** (~1 d). Two candidate routes, and the choice must be benched, not
   assumed:
   - `kAudioFormatOpus` **does exist** in the iOS SDK — confirmed present at
     `iPhoneOS26.2.sdk/…/CoreAudioBaseTypes.h:432`. If `AudioConverter` will
     decode the pendant's 16 kHz `RESTRICTED_LOWDELAY`/CELT 10 ms packets, this
     is a zero-dependency decoder. **Unverified — bench it first.**
   - Otherwise vendor `firmware/source/src/lib/opus-1.2.1`, which is **already
     in the repo**, as a static library target. Costs an `xcprivacy` manifest —
     and note the app already has an unsolved privacy-manifest problem blocking
     TestFlight (`docs/BRIEF.html:504`), so this route risks deepening it.
2. **Engine seam** (~2 d). Extract `PhoneListener`'s recognition core (request
   construction incl. `contextualStrings`/`requiresOnDeviceRecognition` at
   `:712-724`, `TranscriptCursor`, `TranscriptFlushPolicy`, orphan replay,
   watchdog) behind an `append(AVAudioPCMBuffer)` inlet. Both lanes then share
   the machinery that took months to get right. **Delete `LocalTranscriber`** —
   its lifecycle is the documented bug, not the fix.
3. **Delete the cloud** (~0.5 d) and prove it (~1 d).

- **Free upside worth naming:** on the shared engine, pendant lines finally get
  `SpeakerTagger` and real capture timestamps. Today `heard(line, from: .pendant)`
  (`AnticipyApp.swift:265`) passes **no speaker and no `at:`** — pendant lines
  can never carry the owner/other verdict, and they are timestamped at arrival.
- **Open risk that must be measured, not guessed:** whether iOS will run two
  concurrent on-device `SFSpeechRecognizer` tasks (phone mic + pendant). If not,
  arbitration is needed.

### Option C — Keep Deepgram under a declared expiry.

Legal under LAW 2 only with a `TAPE:` comment in `TranscriberClient.swift`
naming the real fix **and** a gate leg that stays red until it lands. Buys the
feature at the price of an ongoing, disclosed, red-on-the-scoreboard violation
of `design/LOCAL-FIRST.md` rule 1. Defensible only as a *dated* bridge with
Option B funded behind it.

### Option D — Amend the law.

Priced for completeness, and it is the weakest. `research/2026-08-24-engine-options.md:645`
already refused Deepgram **on the merits** — last on independent accuracy among
the candidates, self-hosting NVIDIA-Linux-only at $15–30k/yr plus $60–280 per
user per month. So the case for keeping it cannot rest on quality or cost. It
would have to rest on "it is the only thing that works today," which is true and
is exactly what Option A/B are for.

### The smallest honest fix

**Option A, today, with Option B funded behind it.** Hours of work; breaks one
feature that the app already has honest copy for; makes the law true on the
build that exists rather than on a build that might. Anything that leaves audio
flowing needs Option C's tape **and** its red leg, or it is a rejected diff
under LAW 2.

---

## 5. The gate leg that should exist

### Nothing enforces the law. Something enforces its opposite.

`grep -rn "deepgram\|LOCAL-FIRST\|raw audio" overnight/` returns **zero** legs.
`overnight/done_gate.py` (6 legs) and `overnight/tejas_gate.py` (8 legs, all
green as of this run) have nothing on local-first. `overnight/fellowship_gate.py`,
named in `CLAUDE.md`, **does not exist in this tree** — worth someone's
attention independently.

Worse, the only test that touches this path **pins the violation in place**.
`tests/test_pendant_transcription_wiring.py` (4 tests, all passing) asserts:

```python
assert "transcriber.send(opusFrame: frame)" in app     # :26
assert "pendantTranscriber.onTranscript" in app        # :27
assert "Deepgram" in content                           # :43  (ContentView.swift)
```

**Fixing the leak turns this file red.** That is the inverse of a LAW 2 expiry
leg: a green test that enforces the breach and reports the fix as a regression.
It is the second instance of the pattern tonight's audit named — a gate leg that
fails when tape is *removed*.

### The leg to add — `overnight/done_gate.py`, LEG 7

Written in the house style (`LegFailed`, real source, fails-if-untestable). It
stays **red until the audio path is actually gone**, which is what LAW 2 asks of
a tape marker:

```
LEG 7 — RAW AUDIO NEVER LEAVES THE PHONE

RED unless ALL of:
  a) "api.deepgram.com" appears nowhere under app/ios/Anticipy/**/*.swift
  b) backend/pb_hooks/transcription_token.pb.js does not exist
  c) POST {backendURL}/transcription/token returns 404 on the LIVE host
     (today it returns 401 — the route is deployed and serving)
  d) no screen claims silence while a capture lane is running:
     SettingsView's Listening branch and listeningState must consider the
     pendant, not listener.isListening alone
  e) the pause/stop controls reach every capture lane:
     startPendantTranscription must read keepListening / listeningPauseUntil

While an approved tape bridge stands (Option C only), the leg reports
`fail` rather than `FAIL`-with-no-expiry ONLY if TranscriberClient.swift
carries a TAPE: comment naming the real fix and a dated owner decision.
No tape marker => hard FAIL. Tape whose leg went green => the tape gets
DELETED, per LAW 2.
```

`(c)` is the LAW 3 half and it is cheap — one `curl`, the same check I ran
above, in the `overnight/is_it_live.py` idiom. `(d)` and `(e)` are string/AST
checks over Swift source; they are gate legs, which LAW 1 explicitly permits
("Gates and evals — deterministic tests of outcomes").

### And rewrite `tests/test_pendant_transcription_wiring.py`

Its three violation-pinning assertions must be inverted before any fix lands, or
the fix arrives looking like a break. Its two genuinely valuable tests —
that the long-lived `DEEPGRAM_API_KEY` never enters iOS source (`:7-12`) and
that token exchange requires a signed-in owner and is short-lived (`:15-21`) —
should survive as-is until the hook is deleted, then go with it.

---

## 6. What I could not determine

1. **Whether `DEEPGRAM_API_KEY` is actually set in the Railway environment.**
   This is the single fact that most changes severity and I cannot read it from
   here: `transcription_token.pb.js:9-11` returns `503` for a missing key, but
   the `401` auth check at `:8` fires first, so an unauthenticated probe cannot
   distinguish "configured" from "not configured." If the variable is unset, the
   leak is dormant **by configuration** — one env-var edit away from live, and
   still a live code path. **Someone with Railway access should run
   `railway variables | grep DEEPGRAM` and record the answer in this file.**

2. **Whether any build containing the Deepgram wiring was ever installed on a
   device.** The wiring landed 2026-08-12 in commit `062796db` ("release:
   certify Anticipy Codex Version 1.0.4"). The newest xcarchive in the repo is
   `Anticipy-b30.xcarchive`, created 2026-08-02 (`Info.plist` → build 30,
   v1.0.2), and `strings` on its binary finds `19B10000` but **no** Deepgram
   URL. Source is now build 76. So no artifact in this tree proves the bytes
   shipped — only that they compile and that the backend half is deployed.

3. **Whether `AudioConverter`/`kAudioFormatOpus` can decode the pendant's exact
   packets.** The constant exists in the iOS 26.2 SDK. Whether Apple's decoder
   accepts 16 kHz `RESTRICTED_LOWDELAY`/CELT 10 ms raw packets outside a
   container is untested here. It is the difference between a half-day and a
   full day plus a vendored library plus another privacy manifest. **Bench it
   before costing Option B precisely.**

4. **Whether the pendant currently in Omar's possession is powered, charged, and
   in range of a phone running build 76.** I established the hardware exists and
   that the protocol matches; I could not establish that the two are presently
   in the same room.

5. **`overnight/fellowship_gate.py` does not exist**, though `CLAUDE.md` names it
   as one of three scoreboards to run and believe. Out of scope here; flagging
   it because "run the gates" currently cannot mean what the file says it means.

---

## Law compliance of this report

- **LAW 1** — no pattern-matching over natural language is proposed. Everything
  in §5 is a gate leg, which LAW 1 permits by name.
- **LAW 2** — no tape is proposed. If Option C is chosen instead, it ships with
  a `TAPE:` comment **and** LEG 7 red, or it is a rejected diff.
- **LAW 3** — the live check was performed, not assumed: `POST
  /transcription/token` on production returns `401`, so the route is deployed.
  §5(c) makes that check permanent.
- **LAW 4** — this file is the state. `docs/FOLLOWUPS.md:38-47` should be
  corrected to point here, because its stated reason for safety is wrong.
- **LAW 5** — Option B is a senses fix (decode + a real recognition engine),
  which is step 1 of the fix order. No rule is proposed while she is deaf.
- **LAW 6** — flagged without being asked: the Listening-section falsehood
  (§2), the pause controls not reaching the pendant (§2), the test that pins
  the violation (§5), the missing `fellowship_gate.py` (§6).
