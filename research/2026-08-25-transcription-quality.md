# Microphone and transcription quality — the mechanism, the shortlist, and the measurement

**Date:** 2026-08-25 · **Branch:** `jose_anticipy_system` · **HEAD at writing:**
`8a58e14e`
**Binding:** `HARNESS-LAWS.md` (Law 1, Law 3, Law 5), `design/LOCAL-FIRST.md`
**Scope:** research and decision. Nothing under `app/ios/**`, `brain/**`,
`extension/**` or `proof/**` was modified. Every file cited was read.

**The owner's ask, verbatim:** *"Improve microphone/transcription quality —
currently inconsistent. Options to explore: Deepgram Nova, Apple Foundation
systems, or similar alternatives that will work better. Microphone and
transcription systems aren't perfect yet."*

---

## 0. What this document does NOT repeat

Two files already did most of the engine survey and I am not re-deriving them:

- **`research/2026-08-24-engine-options.md`** — the candidate table, the
  production measurements (221 real `phone_mic` lines, 49% ≤4 words, 42 wpm
  proxy capture, 13 `anticipate` vs 1 `Anticipy`), the §11 experiment design,
  and the refusal of Deepgram on law, money and accuracy.
- **`research/2026-08-24-deepgram-leak.md`** — the pendant lane that is already
  streaming raw Opus to `wss://api.deepgram.com`, its live backend half, and
  the four priced options for closing it.

Read those first. **This document adds four things they do not contain:**

1. Five mechanical findings in the audio front end, from a fresh read of
   `app/ios/Anticipy/Audio/` — including one interaction between two lines of
   `PhoneListener` that nobody has priced, and one whole API surface the app
   has never touched (§1).
2. The shortlist re-scored on the axes the owner actually asked about, with
   **cost per audio-hour and bytes per day computed** rather than quoted, and
   with **offline behaviour treated as a first-class column** — which is where
   Deepgram on the phone mic breaks in a way nobody has written down (§2).
3. **The word-error-rate harness already exists.** The brief for this document
   said there is none. There is: 1,400 lines, pre-registered thresholds,
   57 tests, and a written protocol. It has never been run, and the reason is a
   ~40-line iOS file nobody has written (§3).
4. The precise, pre-registered extension that turns *"Nova is better"* from an
   assertion into a cell you can file (§3.4).

---

## 1. (a) What is actually wrong today — the mechanism

"Inconsistent" is a symptom with **six** distinct mechanisms behind it.
`research/2026-08-24-engine-options.md` §4 named them and measured five against
production; its conclusion — *exactly one of the six is an engine fault, and it
is not the dominant one* — stands and I found nothing that overturns it.

What follows is what a fresh read of the audio layer adds. **All five findings
sit in the senses layer**, which is Law 5 step 1 and Law 1's first named
carve-out. None of them is a rule about meaning.

### 1.1 The microphone is never chosen, and the app never learns which one it got

`grep` across the entire iOS target for the AVAudioSession input-selection
surface returns **zero hits**:

```
setPreferredInput          setPreferredDataSource       setPreferredPolarPattern
availableInputs            dataSources                  supportedPolarPatterns
selectedDataSource         setPreferredSampleRate       setPreferredIOBufferDuration
setPreferredInputNumberOfChannels
```

The whole audio configuration is three lines
(`app/ios/Anticipy/Audio/PhoneListener.swift:365,372,373`):

```swift
try? session.setCategory(.record, mode: .measurement, options: .duckOthers)
try? session.setAllowHapticsAndSystemSoundsDuringRecording(true)
try? session.setActive(true, options: .notifyOthersOnDeactivation)
```

and the tap takes whatever format the route happens to be in
(`PhoneListener.swift:435`, `:451`):

```swift
let format = input.outputFormat(forBus: 0)
input.installTap(onBus: 0, bufferSize: 1024, format: format) { ... }
```

A modern iPhone has three or four microphones. Which one is live, and with what
directional pattern, is decided entirely by iOS from the category and mode —
and **`.measurement` is the mode whose documented purpose is to minimise
system-supplied input processing.** For a phone lying face-up on a table trying
to hear two people at two metres, "whichever mic iOS picks, with whatever
pattern it defaults to, with the processing turned off" is not a configuration.
It is the absence of one.

**Worse: the app cannot tell you which one it got.** `ListenSessionFacts`
(`app/ios/Anticipy/Audio/ListenSessionFacts.swift:87-90`) is the type that
exists precisely to read the session back and journal what it *became* rather
than what was asked for — and it carries exactly three fields:

```swift
let category: Category
let mode: Mode
let lowPower: Bool
```

No route. No port. No data source. No polar pattern. No sample rate. Twenty-one
days of production transcript exist and **not one line of evidence anywhere
says which microphone produced it.**

This is the single largest unexamined lever in the senses layer, and the cost of
looking is one journaled field. `ListenSessionFacts` is deliberately built from
closed enums so a free `String` cannot smuggle transcript into the journal
(see its own header, `:12-46`) — so extending it with a closed-set route/pattern
field is a *bounded* edit that the file's whole design anticipates.

> **Law 1 posture:** reading and selecting an audio route is audio plumbing.
> It decides no meaning. Legal, and Law 5 step 1.
>
> **Honesty about magnitude:** I am claiming this is *unexamined*, not that it
> is *the* cause. Whether `.measurement` even permits data-source or polar-pattern
> selection on iPhone is undocumented from where I sit, and I did not verify it.
> The fix is to *read it at runtime and journal it* — which is a measurement,
> not a guess, and costs nothing to be wrong about.

### 1.2 Two lines that were never considered as a pair

`PhoneListener.swift:365` turns Apple's input signal processing **off**.
`PhoneListener.swift:372` turns the Taptic Engine **on** during recording.

Each carries a long comment defending itself. **Neither comment mentions the
other.** Their stated reasons are unrelated:

- `:360-364` — *".measurement is deliberate and matches Apple's own
  SFSpeechRecognizer sample: minimal input processing…"* (transcription
  fidelity)
- `:366-371` — *"iOS MUTES the Taptic Engine for the whole app while a .record
  session is active, so the buzz can't bleed into the mic. […] without this
  every haptic in the app died"* (the build-32 "I feel no haptics anywhere"
  report)

Read together they say: **iOS mutes the buzzer specifically to keep it out of
the microphone; we overrode that, and we also removed the noise suppression
that would have absorbed it.** Every haptic the app fires now lands in the
recogniser's input with nothing in front of it.

I am not claiming this is large. I am claiming it is a compound nobody priced,
that it is exactly the shape of "inconsistent" (it degrades only at the moments
the owner is touching the phone), and that `ListenJournal` already has the
machinery to correlate haptic events against `flushesByReason` for the price of
one event kind.

### 1.3 The vocabulary fix is in the tree, is vouched for by a green gate leg, and its effect has never been observed

This is the finding the brief warned me to look for, and it is **already
realised one API generation earlier than expected.**

The request is built at `PhoneListener.swift:801-816`:

```swift
let req = SFSpeechAudioBufferRecognitionRequest()
req.shouldReportPartialResults = true
req.contextualStrings = AnticipyVocabulary.current()   // :805
req.taskHint = .dictation                              // :809
req.addsPunctuation = true                             // :813
if recognizer?.supportsOnDeviceRecognition == true {
    req.requiresOnDeviceRecognition = true             // :815
}
```

`AnticipyVocabulary.current()`
(`app/ios/Anticipy/Audio/AnticipyVocabulary.swift:14-38`) returns
`["Anticipy", "Tejas", "OpenTrade", "pendant"]` + the owner's first and last
name + every roster name, deduped and **capped at 60** (`:37`) against Apple's
documented ~100.

The gate that vouches for this is `overnight/tejas_gate.py:378-391`, leg 7,
*"THE RECOGNIZER KNOWS ITS OWN NAME"*. Read what it actually does:

```python
if "contextualStrings" not in listener:
    raise LegFailed(...)
if "Anticipy" not in re.sub(r"//.*", "", listener).split("contextualStrings")[-1][:400]:
    raise LegFailed(...)
```

**It greps the source file.** It proves the string is present. It cannot
observe a single word of biasing. And `:805` and `:815` are both set on the
same request — so the open question is whether `contextualStrings` functions
at all under `requiresOnDeviceRecognition = true`, for which
`research/2026-08-24-engine-options.md` §12(4) found **no primary source either
way.**

So the state of play is:

| | |
|---|---|
| A vocabulary fix that looks correct | **shipped** |
| A gate leg that reports it green | **green** |
| Any observation that it changed one word | **none, ever** |
| Production evidence window it has had | **≤14 minutes** (§7 of the engine-options doc: leg 7 landed `6e277694` at 03:48 UTC; the last transcript line of any kind arrived 03:34 UTC) |

That is the `SpeechTranscriber`-ignores-`AnalysisContext.contextualStrings`
trap, *already sprung*, on the incumbent API, today. The lesson generalises
past the specific API: **on this codebase, "the biasing is configured" and "the
biasing happens" are different claims and only one of them is checked.**

> **Weight I put on the `SpeechTranscriber` claim:** the brief tells me a
> separate audit is re-testing whether that claim is sound. **My recommendation
> does not depend on it.** If `SpeechTranscriber` turns out to honour
> contextual strings after all, exactly one thing in this document changes:
> row 2 of §2's table gains a "yes" in the vocabulary column and moves up the
> ranking. Nothing in §1, §3, or the recommendation moves, because none of them
> rests on that claim — they rest on *the incumbent's* biasing being unobserved,
> which is a repo fact I verified myself at `tejas_gate.py:378-391`.

> **Law 1 posture, stated sharply because this is the tempting place to break
> it:** biasing an *acoustic decoder* toward a lexicon is senses work — legal.
> A post-hoc pass that rewrites `"anticipate"` → `"Anticipy"` by edit distance
> over a word list is **a pattern-matcher deciding what a human meant**, and it
> would be tape under Law 2 with all of Law 2's price. The engine-options doc
> already says this (§8, Foundation Models). I am restating it because it is
> the cheapest-looking fix in this entire document and it is forbidden.

### 1.4 There is no voice-activity detection anywhere

`grep` for `SpeechDetector`, `VAD`, `voiceActivity`, `rms`, `energy` over
`PhoneListener.swift`: **zero hits** (one unrelated comment match).

The app has no independent signal that speech occurred. It knows only what the
recogniser tells it, and it detects a dead recogniser by a 4-second staleness
watchdog on partial results — a *decoder-liveness* proxy, not a
*speech-presence* one.

This is why the headline production symptom is unattributable from the device.
`research/2026-08-24-engine-options.md` §4(b) measured isolated two-word
fragments — `"All of these"`, `"Help me understand"`, `"Status"` — sitting in
≥2.6s of silence on *both* sides, 72% of the time. From the phone's own
records, **nothing distinguishes "nobody was speaking in those 2.6 seconds"
from "somebody was speaking and the decoder returned nothing."** Those are
opposite diagnoses with opposite fixes and the device cannot tell them apart.

A VAD is pure senses-layer pattern matching over an audio signal. Law 1's first
carve-out names this category by name. `sherpa-onnx` — already linked and
already shipping in the binary for speaker embeddings
(`app/ios/Anticipy/Audio/SpeakerTagger.swift:167`) — carries Silero VAD, so this
is a config object, not a dependency.

### 1.5 Segmentation is confirmed as a sentence-cutter, not a shard-maker

`app/ios/Anticipy/Audio/TranscriptFlushPolicy.swift:24`:

```swift
init(utteranceGap: TimeInterval = 2.6, maxHold: TimeInterval = 8)
```

2.6s debounce, 8s ceiling. This matches the engine-options doc's §4(d)
measurement exactly: the 7–9s inter-line bucket produces **18.7-word** lines at
~140 wpm — the ceiling firing mid-sentence during continuous speech. It is a
real bug, it is worth fixing, and it **cannot** be the shard cause: cut marking
buys ~5 points (49.3% → 44.4% upper bound) against a §8 gate that needs <25%.

### 1.6 Ranking the mechanisms

| # | Mechanism | Engine's fault? | Evidence |
|---|---|---|---|
| 1 | Whole sessions lost (25h gaps) | **No** — interruption cliff + blind watchdog | engine-options §2, §4(a) |
| 2 | Words missed (~30% capture) | **Unknown — the open question** | §1.1, §1.2, §1.4 above; engine-options §4(b) |
| 3 | Words wrong (`anticipate` 13:1) | **Yes, partly** — and the fix is shipped-but-unobserved | §1.3 above |
| 4 | Sentences cut (8s ceiling) | No — segmentation | §1.5 |
| 5 | Duplicate republication (4%) | No — echo threshold | engine-options §4(e) |
| 6 | Delivery failures (no `source` on 50%) | No — transport | engine-options §4(f) |

**Mechanism 2 is the one that decides the owner's question, and it is the one
nobody has measured.** Everything in §2 below is a bet on which half of it is
true, and §3 is how you stop betting.

---

## 2. (b) The ranked shortlist, with the trade named

### 2.0 First, a correction the owner's ask needs

**"Apple Foundation systems" and "Apple's new speech API" are two different
frameworks and only one of them transcribes anything.**

`FoundationModels` (iOS 26) is a ~3B-parameter on-device **text** LLM. It has no
audio input anywhere in the framework and no ASR capability whatsoever. The
speech framework is `SpeechAnalyzer` / `SpeechTranscriber` / `DictationTranscriber`.
`research/2026-08-24-engine-options.md` §8 establishes this against Apple's own
documentation; I am flagging it here because the ask names the wrong one and a
shortlist that quietly evaluated a language model as an ear would be answering a
different question.

Foundation Models is not useless here — as an on-device post-processor it could
in principle repair punctuation or normalise entities — but it is **not a
candidate for this decision**, and under Law 1 it could only ever be asked to
*understand*, never used as a fuzzy-match rule over a candidate list (§1.3).

### 2.1 Cost per audio-hour — computed, not quoted

Derived from the published monthly figures in
`research/2026-08-24-engine-options.md` §9 (which are that document's arithmetic
over Deepgram's per-minute rates), divided by actual audio-hours:

| Deepgram Nova-3 streaming | $/month, 16 h/day | audio-hours/month | **$/audio-hour** |
|---|---|---|---|
| promotional rate | $138 | ~486 | **~$0.28** |
| regular rate | $222 | ~486 | **~$0.46** |
| regular + diarization | $279 | ~486 | **~$0.58** |

At 16 h/day, one user: **~$3,350/year.** Every local option on this list is
**$0.00/audio-hour**, forever, for every user.

### 2.2 Bytes per day — the number nobody has stated

The pendant encodes Opus 16 kHz mono at 32 kbps
(`firmware/source/src/config.h:23-26`, per the deepgram-leak doc). At that rate:

- **14.4 MB per audio-hour**
- **~230 MB/day** at 16 h/day
- **~7 GB/month, per user, uplink**

Routing the *phone microphone* to a cloud STT means adding an encoder and
carrying the same bill. On cellular that is a data-plan line item and a radio
that never sleeps.

### 2.3 The table

Axes are the owner's: accuracy, latency, battery, cost/hour of always-on audio,
offline behaviour, privacy posture against `design/LOCAL-FIRST.md`.

| Rank | Option | Accuracy (this product's conditions) | Latency | Battery | $/audio-hr | **Offline** | LOCAL-FIRST posture |
|---|---|---|---|---|---|---|---|
| **1** | **`SFSpeechRecognizer`, front end fixed** (incumbent) | dictation-grade; 1-min task cap; biasing present but **unobserved** (§1.3) | sub-second partials | **unmeasured** (see 2.4) | **$0.00** | **full capture** | **compliant.** `requiresOnDeviceRecognition` set at `:815` |
| **2** | **`sherpa-onnx` streaming Zipformer** | model-dependent; Parakeet-TDT-v3 ≈6.1% WER on Open ASR LB | RTF 0.06–0.11 documented | **unmeasured** | **$0.00** | **full capture** | **compliant.** Already linked and shipping (`SpeakerTagger.swift:167`); adds **Silero VAD**, which §1.4 says the app needs; **keeps the iOS 16.0 floor** (`project.yml:5`) |
| **3** | **`SFSpeechLanguageModel`** (iOS 17+, on the incumbent) | not an engine change — a *stronger* biasing that carries **pronunciations**, which a phrase list cannot express | unchanged | unchanged | **$0.00** | full capture | **compliant.** Unused anywhere in the app |
| **4** | **`SpeechTranscriber`** (iOS 26) | best on LibriSpeech (2.12%, vendor-published); **loses to whisper small.en on earnings22** (14.0% vs 12.8%) — weight the conversational number | word-level `CMTimeRange`; free `SpeechDetector` VAD | unmeasured | **$0.00** | full capture | compliant — but **iOS 26 floor + an undocumented hardware gate**, and it forfeits vocabulary (§1.3 caveat) |
| **5** | **WhisperKit / whisper.cpp on-device** | whisper small.en 12.8% on earnings22 | streaming supported; word timestamps | **unmeasured; large-v3-turbo is ~1.6 GB** — not an all-day resident | **$0.00** | full capture | compliant, but custom vocabulary is **Pro-only, $1.33/device/mo, 1,000-license minimum**; free tier gets `initial_prompt` only. New dependency where sherpa-onnx is already in the binary |
| **6** | **`DictationTranscriber`** (iOS 26) | per Apple, **the same models as on-device `SFSpeechRecognizer`** | same as 4 | unmeasured | $0.00 | full capture | compliant — and **the trap arm**: costs the iOS floor to buy approximately nothing |
| **7** | **Deepgram Nova-3** | **5.2% WER** on Artificial Analysis AA-WER v2 — **last of eleven**, behind ElevenLabs Scribe v2 (2.2%), Azure (2.4%), AssemblyAI (3.1%). **First on throughput** at 523× realtime | `endpointing=500` **plus network RTT** | **radio hot 16 h/day** — see 2.4 | **$0.28–0.58** | **see 2.5 — this is the finding** | **VIOLATION.** See §2.6 |
| — | **Apple Foundation Models** | **not an ASR** | — | — | — | — | not a candidate (§2.0) |

Every external number in this table is sourced in
`research/2026-08-24-engine-options.md` §12, which also labels which ones come
from parties selling the thing they benchmarked. I have not re-fetched them and
I am not laundering them into facts here.

### 2.4 Battery: unmeasured on **both** sides, and that is the finding

`research/2026-08-24-engine-options.md` §12 records that **no credible battery
or thermal measurement exists for continuous all-day on-device ASR on an
iPhone** — the circulating figures are content-farm output. That is honest and
it cuts against the local options.

But the same honesty must be applied to the cloud option, and it has not been:
routing 16 h/day of audio off the phone means **the cellular or Wi-Fi uplink is
transmitting continuously for sixteen hours**, carrying the 230 MB/day from
§2.2. Continuous radio transmit is one of the largest drains on a phone.
Nobody has measured that either.

So the honest statement is: **battery is unknown for every option on this
list**, the structural costs differ (ANE vs radio), and neither has been put on
a device. It belongs in the measurement (§3.4), not in this table as a
confident number.

### 2.5 Offline behaviour is where Deepgram breaks, and it is not written down anywhere

`design/LOCAL-FIRST.md` rule 4 is binding and explicit:

> *"Cloud components must degrade gracefully when unreachable **AND devices must
> keep capturing when offline** (store-and-forward already exists; protect it)."*

The app already honours this: `PhoneListener` transcribes locally and the
resulting **text** goes into store-and-forward. Text is small, and a backlog of
text is a backlog of conclusions.

**Route the phone microphone to a cloud STT and that stops working**, and there
are only two ways out, both bad:

1. **Lose all capture when the network is down.** A dropped signal, a lift, a
   basement, a plane — and the product that exists to never miss the promise
   misses every promise made in that window. Directly violates rule 4.
2. **Buffer raw audio to disk until the network returns.** Now the phone is
   *persisting raw audio* — 14.4 MB per hour of it — waiting to upload. That is
   strictly worse than the status quo for privacy: rule 1 forbids raw audio
   *travelling*, and rule 2 forbids biometrics being *stored*. A disk queue of
   raw room audio is both hazards at once, and it is the direct consequence of
   the choice, not an implementation detail you can engineer away.

**Every local option keeps capturing offline for free.** This is not a
tiebreaker; for an always-on always-listening product it is close to a
requirement, and I could find no place in the repo where it had been named.

### 2.6 Deepgram Nova against LOCAL-FIRST — the trade, made explicit

The owner asked for this option by name. The owner's own written law refuses it
by name. My job is to price both sides honestly and hand the decision back.

**On the merits, honestly and without the law:**

- Nova-3 is **fast** — 523× realtime, first place on throughput — and its
  streaming stack is mature, with keyterm prompting (500 tokens, far more
  headroom than `contextualStrings`' ~100) that would address §1.3's name
  problem directly and observably.
- It is **no longer the accuracy leader**: 5.2% WER, last of eleven on
  Artificial Analysis' independently-corrected benchmark. Its streaming
  diarization measures **39.1% DER, last place** — though that benchmark is
  published by a competitor and should be discounted accordingly.
- Its **default retention is not zero**: suppression requires `mip_opt_out=true`
  **per request**, a parameter a developer can forget. The existing pendant
  socket at `TranscriberClient.swift:27` **does not set it**
  (`research/2026-08-24-deepgram-leak.md` §2).
- **There is no on-device option.** Deepgram's edge work targets the Qualcomm
  Hexagon NPU on Snapdragon X Windows PCs. Self-hosting is **NVIDIA GPU,
  Linux x86-64, Enterprise-plan only** — it cannot run on anything in this
  building, and it changes *who holds* the audio, not *whether it travels*.

**What adopting it costs against the law:**

`design/LOCAL-FIRST.md` rule 1 — *"RAW AUDIO NEVER LEAVES A DEVICE. Not to
Deepgram, not to anyone."* — and the scoreboard row for phone transcription,
which already adjudicated this exact proposal: *"the earlier idea of moving
phone STT to Deepgram is **DEAD on this law**."* Adopting Nova for the phone
mic means:

| Cost | Detail |
|---|---|
| Rule 1 | Broken outright, on the primary capture lane, by design |
| Rule 4 | Broken (§2.5) — offline capture ends, or raw audio goes to disk |
| Rule 3 | Broken — the *stream* travels, not the conclusion |
| Everyone in the room | Captured. Not just the owner; anyone within earshot who never touched the app |
| Money | ~$3,350/user/year at 16 h/day |
| Bytes | ~7 GB/month/user of uplink |
| The law's status | It stops being a law. Rules 2 and 3 are enforced by nothing but this file's own authority; overruling rule 1 on the flagship lane is the precedent that the others are negotiable |

**What the law was protecting, and whether the reason still holds.**

Read the preamble, not just the rules: *"Devices are the home of his life; the
cloud is a courier and a pair of hands, never the archive of who he is."* The
law is protecting **the archive**, and the specific thing it identifies as the
archive is *the raw stream* — because a transcript is a conclusion and a
recording is a life.

That reason **still holds, and has gotten stronger since the law was written**,
for three reasons the law did not know about:

1. **The population is about to stop being one person.** The only thing keeping
   the existing pendant leak from reaching strangers is an unrelated TestFlight
   packaging failure (`docs/BRIEF.html:504`), which is on somebody's list as a
   goal (`research/2026-08-24-deepgram-leak.md` §1).
2. **The offline consequence (§2.5) was never priced** and it is worse than the
   privacy cost it is usually traded against.
3. **The accuracy case that would have justified it has evaporated.** In 2025
   Deepgram was plausibly the best ears money could buy. In 2026 it is 5.2% and
   eleventh. **You would be spending the law to buy fourth-best accuracy.**

**What would have to change for the law to be amendable.** Not "the owner says
so" — the owner can say so at any time and it is his call. I mean: what would
make the amendment *earn its price*.

- Nova would have to **win the bake-off in §3 on this product's own audio**, by
  a margin large enough to matter — not on LibriSpeech, not on a vendor's blog.
- **Every local option in §2.3 would have to have been tried and lost.** Options
  1, 2 and 3 have not been tried at all. Spending an architecture law while the
  free options are untested is not a trade, it is a skipped step.
- The offline answer would have to be **stated**, in writing, and it is one of
  the two bad ones in §2.5.
- `mip_opt_out=true` would be **mandatory** and gate-enforced, not a parameter.
- The disclosure would have to reach **the people in the room**, not just the
  owner — which no product has ever solved and which this one cannot either.
- And the amendment would ship with a **`TAPE:` comment and a red gate leg**
  under Law 2 if it were framed as a bridge, or as an honest, dated rewrite of
  `design/LOCAL-FIRST.md` if it were framed as a new position. Silently
  contradicting the file is the one option that is not available.

**My assessment, offered as input and not as the decision:** the law should
stand, because the thing it was protecting is more exposed now than when it was
written, and because Deepgram in 2026 is a speed product being considered for an
accuracy problem. **But the decision is the owner's, and if he takes it, the
paragraph above is the price list, not an argument.**

*(Separately and urgently: the pendant lane is **already** streaming raw Opus to
Deepgram today, un-flagged, two taps away, with the backend half live in
production. That is not this decision — it is
`research/2026-08-24-deepgram-leak.md`'s decision, it is older than this
question, and it should not wait on it.)*

---

## 3. (c) The measurement

### 3.1 The premise of this section is wrong, and that is the good news

The brief for this document says: *"There is no word-error-rate harness here.
Say exactly how one would be built."*

**There is one. It is better than what I would have specified.** Built
2026-08-24, commits `76ca23ad` and `22342f74`:

| File | What it is |
|---|---|
| `proof/engine_or_audio.py` | **1,400 lines.** The scorer, the decision rule, the CLI. Standard library only. |
| `proof/reference_decode.py` | Pluggable reference decoder + an honest report of what is actually installed on this Mac |
| `proof/fixtures/read_aloud_script.txt` | **370-word ground-truth script.** 13 × "Anticipy", 5 × "OpenTrade", 4 × "Tejas", 4 × "pendant" |
| `proof/RECORDING-PROTOCOL.md` | One page for a human holding a phone |
| `tests/test_engine_or_audio.py` + `tests/test_reference_decode.py` | **57 tests** |

It has everything the brief asked me to specify and several things it did not:

- **Corpus:** three ~3-minute recordings of one page — arm A (today's config,
  2 m, screen up), arm B (identical + `setVoiceProcessingEnabled(true)`), arm C
  (close-mic control).
- **Ground truth:** the printed script, read aloud. Exact.
- **Metrics, three per cell, never one** — because capture rate alone would
  score a decoder that stutters every word as perfect:
  **word capture rate**, **word error rate**, **insertion rate**, plus
  **per-name hit rate and what each miss became** (`Anticipy: 3/13 heard as
  'antisope' ×9` — the line that tells you whether biasing moved anything).
- **Alignment:** Levenshtein over normalised tokens, two-objective
  (edit distance, then match count), cross-checked against brute-force
  enumeration on 400 random pairs.
- **Thresholds pre-registered as module constants**
  (`proof/engine_or_audio.py:70,74,84,90,114`) with a test whose entire job is
  to make moving one a visible act.
- **A validity gate** that voids the whole run if the reference decoder cannot
  clear 0.85 on the clean control — the difference between an experiment and a
  number.
- **Refusals with reasons**, publishing `None` rather than a low number, because
  a wrong file and a starved microphone both score low on capture.
- **Provenance lines** (`#anticipy: arm=A decoder=sf_ctx wav=… sha256=…`) that
  catch two failures no arithmetic over text can catch: a transcript filed under
  the wrong arm, and a toggle that was never wired producing identical bytes
  that read as the strongest possible finding.
- **An attempt cap** (`MAX_RECORDING_ATTEMPTS = 2`), because a credibility check
  that may be retried without limit is a maximum over attempts, not a
  measurement.

### 3.2 It has never been run, and the reason is ~40 lines of Swift

```
$ ls proof/runs
ls: proof/runs: No such file or directory
```

`proof/RECORDING-PROTOCOL.md`, first bullet under "Before you start":

> *"A build of the app carrying the **scratch recorder** — the thing that writes
> the microphone tap to a WAV file and can decode it offline. **If you do not
> have that build, stop**; it is the missing piece and nothing here works
> without it."*

`grep` for a scratch recorder across `app/ios/` — `AVAudioFile`,
`AudioFileCreate`, any tap-to-disk writer: **zero hits.**

**That is the whole blockage.** A team built a 1,400-line adversarially-hardened
measuring instrument, a 370-word script, a written protocol, a pluggable
reference decoder and 57 tests — and the experiment has produced nothing,
because nobody wrote the file that saves the microphone tap to a WAV. The
harness's own source says so in as many words at `proof/engine_or_audio.py:262`:
*"The scratch recorder DOES NOT EXIST YET."*

**Everything else in this document is downstream of that file.** Section 1's
open question (which half of mechanism 2 is true), section 2's entire ranking,
and any claim anybody ever makes about Nova all resolve the same way: through a
recording that cannot currently be made.

### 3.3 What the existing harness answers, and what it does not

**It answers, on today's engine:** is the audio starved or is the decoder weak
(R1/R2); is `.measurement` the bug (R3); is `contextualStrings` inert under
`requiresOnDeviceRecognition` (R4 — i.e. **§1.3, settled empirically**).

**It does not answer the owner's question.** Its `DECODERS` map
(`proof/engine_or_audio.py:239`) is:

```python
"sf_ctx", "sf_noctx", "reference", "speech_transcriber"
```

and its rules R1–R4 are all *engine-versus-audio-path*. **There is no
engine-versus-engine rule and no shortlist arm.** A typo'd decoder name is
rejected rather than ignored (`tests/test_engine_or_audio.py:751`), so a Nova
transcript cannot even be filed today, let alone scored.

### 3.4 The extension that makes "Nova is better" checkable — pre-registered

Written here **before any recording exists**, in the harness's own discipline
(*"Deciding the bar after seeing the result is how a bake-off gets talked into
the wrong conclusion"*). It is a spec rather than a patch **deliberately**: the
thresholds below are the owner's to ratify, the 57-test suite pins every
existing constant, and four other agents are live in this tree tonight. A
threshold an agent slipped in is exactly the failure the pinning test exists to
prevent.

**1. New decoder keys** in `DECODERS` (`proof/engine_or_audio.py:239`) — one per
shortlist row in §2.3:

```python
"sherpa_zipformer":  "sherpa-onnx streaming Zipformer, on-device, hotwords on",
"whisperkit":        "WhisperKit on-device",
"sf_customlm":       "SFSpeechRecognizer + SFSpeechLanguageModel (pronunciations)",
"deepgram_nova3":    "Deepgram Nova-3 streaming, keyterm prompting, mip_opt_out=true",
```

**2. A new rule, R5 — MIGRATION_JUSTIFIED.** All arms decode **the same WAV**,
so provenance `sha256` equality is the precondition and the existing
`_distinct()` machinery (`:744`) inverts to enforce it.

```python
#: R5. A shortlist decoder must beat the incumbent (sf_ctx) on the SAME WAV by
#: this much on word capture before a migration is justified. Two numbers,
#: because a decoder that wins on words and loses on names moves the product
#: backwards: names are what decide who gets messaged.
MIGRATION_CAPTURE_MARGIN = 0.10
MIGRATION_NAME_MARGIN    = 0.10

#: R5's floor. A challenger that wins by 10 points while both sit at 0.25 has
#: won nothing worth a migration — that is a starved-microphone result with a
#: ranking painted on it, and R1 should be firing instead.
MIGRATION_MIN_ABSOLUTE_CAPTURE = 0.60
```

**R5 fires** when a challenger beats `sf_ctx` on the same WAV by ≥0.10 capture
**and** ≥0.10 name hit rate **and** clears 0.60 absolute.
**R5 reports "could not evaluate"** — never "did not fire" — when the WAV
hashes differ, when R1 has fired (starved audio: the ranking is meaningless),
or when name mentions fall below the existing `MIN_NAME_MENTIONS = 8`.

**3. A cost column that is not a WER.** The harness scores text; it cannot see
money, battery or bytes. The manifest gains three declared fields per cell —
`dollars_per_audio_hour`, `bytes_per_audio_hour`, `offline_capture` (bool) —
which the report **prints beside** the accuracy numbers and never folds into
them. §2.5 is the reason: a decoder that wins on WER and cannot capture offline
has not won this product's question, and a single blended score would hide that.

**4. Battery, on the device, as a fourth arm.** §2.4 says battery is unmeasured
for *every* option. The cheapest honest instrument: run each candidate for one
hour on a charged device with the screen off, and record start/end battery
percentage and peak thermal state. `proof/battery/` already has a runner
(`run.mjs`, `score.mjs`, `commit_gate.mjs`) whose shape can be reused. This is
crude and it is enormously better than the zero measurements that exist.

**5. The Deepgram cell's own carve-out, stated so nobody has to decide it in a
hurry.** Filing a `deepgram_nova3` cell requires sending audio to Deepgram.
That audio is **a read-aloud of `proof/fixtures/read_aloud_script.txt`** — a
scripted page containing no real personal content, whose own text says *"nothing
in this recording is a real request, please do not act on any of it."* Measuring
a refused option on a synthetic script is how a refusal becomes evidence-based
instead of dogmatic, and it is Law 1's third carve-out (*"Gates and evals —
deterministic tests of outcomes. Measuring is not programming"*) doing exactly
its job. It is **not** a licence to point the lane at live audio, and the run
must set `mip_opt_out=true`.

**6. The test that must be edited in the same diff.**
`tests/test_engine_or_audio.py::test_the_thresholds_are_pinned_so_moving_one_is_a_visible_act`
enumerates the constants. Adding three means editing it — **which is the point.**
Adding a threshold to this harness is designed to be a visible act, and this
document is the visibility.

### 3.5 The order of operations, so nothing measures a moving target

1. **Write the scratch recorder.** ~40 lines: tap → WAV, plus offline decode
   through `SFSpeechRecognizer` with and without `contextualStrings`, plus the
   provenance line. It is the only blocking dependency in this entire document.
   *(iOS tree — out of my scope tonight; specified in
   `.superpowers/sdd/agc-harness-report.md`.)*
2. **Journal what the session became** (§1.1) — route, data source, polar
   pattern, sample rate — as closed-set fields on `ListenSessionFacts`. Without
   it, arms A and B may differ by which microphone iOS chose and nobody will
   ever know.
3. **Record the three arms** per `proof/RECORDING-PROTOCOL.md`. Twenty minutes,
   one room, one phone.
4. **Run `proof/engine_or_audio.py --run`.** R1–R4 fire or refuse. §1.3 is
   settled empirically for the first time.
5. **Only then** extend with R5 and the shortlist arms, and only for the
   candidates the first four rules left standing.

---

## 4. (d) Recommendation

**Do not choose an engine yet — you cannot, and the reason is forty lines of
Swift, not a lack of analysis.** This repo already contains a pre-registered,
adversarially-hardened word-error-rate harness with a 370-word ground-truth
script, a written recording protocol, a pluggable reference decoder and 57
tests; it has produced exactly zero measurements because nobody has written the
scratch recorder that saves the microphone tap to a WAV, and `proof/runs/` does
not exist. Write that file, journal what the audio session actually became
(`ListenSessionFacts` records category, mode and low-power and **nothing about
which of the phone's four microphones is live or with what polar pattern** —
the app has never once called `setPreferredInput`, `setPreferredDataSource` or
`setPreferredPolarPattern`, and 21 days of production transcript cannot say
which mic produced them), record the twenty minutes the protocol asks for, and
run the harness. My prediction, stated in advance so it can be wrong: **arm A
comes back starved, R1 fires, the engine is exonerated, and the two things that
move the number are the undeployed build plus the audio front end** — with the
one genuine engine fault, the product's own name arriving as "anticipate" 13
times in 14, fixed by `SFSpeechLanguageModel`'s pronunciations on the incumbent
rather than by any migration. On Deepgram Nova specifically: it is honestly
worth measuring on a scripted page and honestly not worth its price — it is
eleventh of eleven on independent accuracy (5.2% WER), costs ~$0.46 per
audio-hour against $0.00 for every local option, moves ~7 GB/month per user off
the phone, and **ends offline capture or forces raw audio onto disk**, which
breaks `LOCAL-FIRST` rule 4 as squarely as rule 1 and has never been written
down; the law it would cost is protecting more people now than when it was
written, and you would be spending it to buy fourth-best ears. That call is the
owner's, and §2.6 is the price list rather than an argument.

### What would change my mind

| Finding | Effect |
|---|---|
| **R2 fires** — a strong reference decoder gets ≥0.75 off arm A while `sf_ctx` trails by ≥0.30 | The audio is fine and the decoder is losing it. **The migration is justified on evidence** and §2.3's ranking becomes the live question. I would go to `sherpa-onnx` first (floor-safe, already linked, adds the VAD §1.4 wants) and `SpeechTranscriber` as an additive iOS 26 arm. |
| **R3 fires** — arm B beats arm A by ≥0.15 | `.measurement` is the bug. One line, every iOS version, ship it, and most of this document becomes moot. |
| **R4 fires** — name hit rate moves <0.10 with vs without `contextualStrings` | §1.3 confirmed: `tejas_gate` leg 7 is green over an inert setting. Vocabulary work moves to `SFSpeechLanguageModel` immediately and leg 7 gets rewritten to observe rather than grep. |
| **The route journal shows iOS picking a bottom-firing mic with a directional pattern** on a table-top phone | §1.1 becomes the headline and a mic/pattern selection lands before any engine work. |
| **A Nova cell wins R5 by a wide margin on the same WAV** while the local arms cluster low | The accuracy argument in §2.6 collapses. The law argument does not — but the trade becomes real rather than lopsided, and it goes back to the owner with numbers. |
| **`SpeechTranscriber` turns out to honour `AnalysisContext.contextualStrings`** (the audit now running) | Row 4 of §2.3 gains a vocabulary "yes" and moves up. **Nothing else in this document moves** — §1.3 rests on the *incumbent's* biasing being unobserved, which I verified myself at `tejas_gate.py:378-391`. |
| **The phone is found to have been capturing normally all along** | Then §1.6 mechanism 1 is not dominant, mechanism 2 is a larger share of the complaint, and the engine question gets more urgent, not less. |

---

## 5. Law compliance of this document

- **LAW 1** — Every proposal here sits in the senses layer: audio route
  selection, session mode, VAD, acoustic biasing, and a WAV-scoring eval. None
  decides what a human's words mean. I explicitly **forbid** the tempting fix —
  a post-hoc edit-distance rewrite of `"anticipate"` → `"Anticipy"` — as a
  pattern-matcher deciding meaning (§1.3). The harness extension in §3.4 is
  Law 1's third carve-out by name: *"Gates and evals — deterministic tests of
  outcomes. Measuring is not programming."*
- **LAW 2** — No tape is proposed. If the owner adopts Deepgram as a dated
  bridge rather than a permanent position, §2.6 states the price: a `TAPE:`
  comment naming the real fix plus a gate leg that stays red until it lands, or
  it is a rejected diff.
- **LAW 3** — **Partially unmet, and I am saying so rather than papering over
  it.** I attempted to re-run `proof/capture_day.py --hours 48` against live
  production to confirm whether the phone has resumed capturing; **the call was
  blocked by this session's permission classifier and I could not complete it.**
  So the last live capture figure anyone has is the engine-options doc's, from
  2026-08-25 04:15 UTC. Separately: `app/ios/project.yml:166` now reads build
  **79** (bumped in `fa4eb84f`), where the engine-options doc found 76 — **but a
  bumped build number in the repo is not bytes on a phone**, and nothing I can
  read from here establishes which build the device is running. Both facts need
  a live check before anyone acts on them.
- **LAW 4** — This file is the state. Nothing here lives only in a chat.
- **LAW 5** — Every recommendation is step 1 (senses): the scratch recorder,
  the route journal, the audio session mode, VAD, and acoustic biasing. **No
  rule is proposed while she is deaf.** The engine question is step 5 and this
  document defers it on purpose.
- **LAW 6** — Flagged without being asked: the `.measurement` /
  `setAllowHapticsAndSystemSoundsDuringRecording` interaction that neither
  comment mentions (§1.2); `tejas_gate` leg 7 vouching by grep for a fix whose
  effect has never been observed (§1.3); the total absence of route information
  in 21 days of transcript (§1.1); the offline consequence of cloud STT that
  breaks `LOCAL-FIRST` rule 4 and appears nowhere in the repo (§2.5); and the
  brief for this document asserting no WER harness exists when one does (§3.1).

## 6. What I could not verify

1. **Whether the phone is capturing today.** The live check was blocked (§5).
2. **Which build is on the device.** `project.yml` says 79; that is a repo fact,
   not a device fact.
3. **Whether `.measurement` mode permits data-source or polar-pattern selection
   on iPhone.** I did not confirm this either way. §1.1's recommendation is to
   *read it at runtime and journal it*, which is correct regardless of the
   answer.
4. **Whether `contextualStrings` functions under `requiresOnDeviceRecognition`.**
   No primary source either way (engine-options §12(4)). R4 settles it.
5. **Every external benchmark number in §2.3.** Relayed from
   `research/2026-08-24-engine-options.md` §12, which labels which ones were
   published by parties selling the thing benchmarked. Not re-fetched by me.
6. **Battery for anything** (§2.4). Unmeasured for every option on the list.
