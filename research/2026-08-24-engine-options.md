# Which speech engine — the evidence, and the answer

**Date:** 2026-08-24 (measurements taken 2026-08-25 04:15 UTC)
**Branch:** `jose_anticipy_system`
**Binding:** `HARNESS-LAWS.md`, `design/LOCAL-FIRST.md`,
`docs/superpowers/specs/2026-08-24-voice-capture-design.md` §8
**Scope:** research and recommendation. No product code was written. `app/ios/**`
and `brain/**` were read only.

---

## The answer, first

**The engine is not your problem. Do not migrate anything yet.**

Three findings, each measured tonight against live production, in order of how
much they should change what you do tomorrow:

1. **The phone has captured nothing for 25 hours.** `proof/capture_day.py
   --hours 24` returns **0 lines, 0 words**. The last phone line landed
   2026-08-24 03:34 UTC. That is not a transcription-quality problem. That is
   the microphone being gone, and it is the exact shape of two bugs that are
   fixed in this repo and **not on the device**.

2. **The 41% shard rate is not made of cut sentences, so the boundary fix
   cannot repair it.** Measured over the 221 real `phone_mic` lines in
   production: 49% are ≤4 words, and **72% of those short lines have ≥2.6s of
   silence on both sides**. Nothing about line boundaries can rescue an
   isolated fragment. The most generous possible stitching moves the shard rate
   from **49.3% → 44.4%** — about five points. The §8 gate needs under 25%.
   §6 alone will not get there and was never going to.

3. **Word capture looks unchanged at roughly a third, from a second and newer
   sample.** While actively hearing, the phone delivers **42 words per minute**
   of wall clock against 130–160 wpm of natural speech. That is a *proxy*, not a
   paired measurement — read the caveat in §4(b) before quoting it — but it
   lands on top of the one real paired number this product has (33%, the
   2026-08-23 call). The spec says capture was "never re-measured." It still has
   not properly been, and nothing suggests it improved.

Put together: **a large share of words are being lost before they ever reach a
decoder** — some to sessions that died (finding 1), and some to a signal that
arrives as isolated two-word fragments with live capture either side. A better
decoder fed the same starved signal gets you a better transcript of the third
you already have. That is why the migration is not justified *yet* — not because
SpeechAnalyzer is bad (it is probably the right endgame), but because you cannot
tell a weak decoder from a starved microphone until you have looked, and **one
afternoon of looking is cheaper than a migration.**

The single suspect nobody has tested is in §4 below: the audio session runs in
`.measurement` mode, which exists to *minimise* system signal processing —
including automatic gain control. It has been that way since build 6 and has
never been revisited on evidence.

---

## 1. The §8 gate: NOT MET, and worse, NOT EVALUABLE

The spec pre-registered the gate, correctly, before anyone was invested:

> After §5–§7 ship and one manual session is recorded: shard rate below 25%,
> `speaker` populated on the large majority of owner lines, and word capture
> still under 60%. […] **If capture recovers, it was never the engine.**

Its precondition is "**after §5–§7 ship**". They have not shipped.

| §8 condition | Status | Evidence |
|---|---|---|
| §5–§7 shipped | **NO** | see §2 |
| shard rate < 25% | **NO** — 44% blended, 49% phone-only | `capture_day --hours 72` |
| `speaker` on most owner lines | **NO** — 0 of 221 phone lines | see §3 |
| word capture still < 60% | **probably yes** — ~30% on a proxy, never paired | see §4(b) |

Two of three inputs are failing *because the fixes are not deployed*, so the
gate cannot fire in either direction. **Reading it as "the engine is the
remaining cause" would be reading it backwards**: the spec's whole design was
that attribution and boundaries get fixed *first*, so that what remains is
attributable to the engine. Nothing has been fixed on the device, so nothing
remaining is attributable to anything yet.

The gate is a good gate. Honour it. It has not been run.

---

## 2. The deployment gap — this is the headline

`docs/BOARD-STATE-2026-08-24.md` (PHONE-AS-PENDANT card): **"Build 76 is on the
phone."** `app/ios/project.yml` still reads `CURRENT_PROJECT_VERSION: "76"`.

**Nineteen commits have landed on `app/ios/` since the commit that set 76, and
not one bumped the build number.** The repo's own doctrine, written in that same
file, is *"Bump the version when the bytes change."*

What that means concretely — every one of these is fixed in source and absent
from the device:

| Fixed in repo | Commit | What the device still does |
|---|---|---|
| Phone call permanently ends listening | `a21bda71` | `resumeListeningIfWanted()` is a **total no-op**. `isListening` is never cleared by an interruption, so its guard is false in the one state it exists for. After a call, nothing but the owner toggling the switch by hand brings listening back. |
| Watchdog rotation leg is dead code | `2c4e9ec8` | The leg fired only when `partial.isEmpty`; `partial` is never empty again after the first utterance of a task. A recognizer that goes deaf with nothing pending is **invisible** — UI says Listening over a dead microphone. |
| No cut marking, no `parent_line` | `50d3fea7`, `9fa30c77`, `a71d7ca7` | An 8s ceiling flush ends a *line*, marked as a finished thought. |
| `capture_started_at` is push time, not speech time | `34c61fc7` | `pushEvent` stamps `Date()` at POST. An offline backlog re-dates itself on flush. |
| No journal, no tally, no diagnostics screen | `55c89a71`, `5f98baa2`, `447da8f5` | A failed manual session leaves **nothing to read**. |

**Confirmed against production, not inferred.** Across 1,809 transcript rows in
21 days: `parent_line` is populated on **0**. `capture_day`'s stitcher is
therefore a no-op — `thoughts == lines` exactly in every window (359/359,
542/542, 1858/1858), and `shard_rate == raw_shard_rate` to three decimals. The
measuring stick is measuring pre-cut-marking code, exactly as
`docs/BOARD-STATE-2026-08-24.md:171` warned.

### The 25 hours of silence

```
proof/capture_day.py --hours 24   ->  0 lines, 0 words, "NOTHING ARRIVED"
```

Last `phone_mic` line: **2026-08-24 03:34:24 UTC** (20:34 Aug 23 Pacific).
Now: 2026-08-25 04:15 UTC. **24h 41m with nothing at all.**

Largest gaps between consecutive phone lines in the last 21 days: **29.0h,
26.9h, 18.4h, 9.2h, 3.6h.** Per-owner longest gaps over 30 days run to
1,003,468s (11.6 days).

A phone that hears for a few hours and then goes silent for a day, repeatedly,
is not a transcription-accuracy signature. It is the interruption cliff and the
blind watchdog — **both already fixed, neither deployed**.

**This is the top complaint's most likely single cause, and it has nothing to do
with which engine decodes the audio.**

---

## 3. `speaker` at 0% is 100% explained, with no engine content

`VoiceEnrollView.swift` is referenced from exactly one place in the entire app:
`SettingsView.swift:584`. §5 — the onboarding page and the evidence-triggered
invitation — was never built. With no owner profile, `VoiceRoster.identify`
forces every verdict ambiguous and `SpeakerTagger` returns nil, so
`AnticipyBackend` never writes the field.

Production confirms it exactly: **0 of 221 `phone_mic` rows carry a speaker
tag.**

One caution, because it is misleading in the 30-day report: `capture_day` shows
22% speaker coverage over 720h. All 417 tagged rows have `source: unknown`, and
their values are `other:v1 … other:v369` — 369 distinct voices each appearing
once. That is a proof-script fixture (`proof/speaker_live_test.py` /
`voice_roster_proof.py`), not device capture. **Real device speaker coverage is
0%, everywhere, always.**

No engine on this list would change that number. Speaker attribution here is
`sherpa-onnx` + `speaker-embedding.onnx`, downstream of transcription, and it is
gated on an enrollment screen nobody can reach.

---

## 4. What "inconsistent" means mechanically — measured

Five distinct failures hide under that one word. They have different causes and
different fixes. Measured over the 221 real `phone_mic` lines:

### (a) Whole sessions lost — THE BIGGEST ONE
25 hours of nothing, right now. 29h / 27h / 18h gaps recurring.
**Cause:** the interruption cliff + blind watchdog (§2). **Not the engine.**

### (b) Words missed — THE SECOND BIGGEST
42 words/min captured against 130–160 wpm of natural speech ⇒ **~30% capture**.
72% of short lines sit in ≥2.6s of silence on both sides. Real examples,
verbatim from production:

```
[-3s ... +6s]   "All of these"
[-6s ... +4s]   "Help me understand"
[-3s ... +3s]   "Status"
[-3s ... +6s]   "Based on"
[-6s ... +6s]   "I"
[-329s ... +8s] "I I gonna"
```

These are mid-sentence fragments with silence around them. The recognizer
resolved two words of a sentence and never heard the rest.
**Cause: unknown — this is the one genuinely open question, and §11 is the
experiment that settles it.** Candidate causes, in LAW-5 order: the audio front
end (§6 below), then the decoder.

**Honesty about the 42 wpm instrument, because this repo has twice been burned
by a harness reporting a failure the system did not commit.** It is a *proxy*,
not a paired measurement: it divides words delivered by wall-clock inside a
listening burst, and it assumes somebody was talking for most of that window.
If half the burst was genuinely silent, true capture is nearer 60% than 30%.
So this number **cannot on its own establish the capture rate** — it can only
say the rate is low and has not visibly improved. The reason I state ~30% is
that it lands on top of the one *real* paired measurement this product has —
the 2026-08-23 call, ground truth beside output, **33%** — from a different,
newer sample. Two weak-and-strong instruments agreeing is worth something;
either alone is not. **§11's read-aloud arm exists to replace both with an
exact number.**

### (c) Words wrong
```
01:28:32  "Then I'll go talk to my email and ask all those questions I might bring"
01:28:40  "So I'll go talk to him and ask him all those all these different questions"
```
"talk to my email" for "talk to him". This is the failure mode
`contextualStrings` exists for, and the one that produced
*"anticipate growth there's something.com"*. **A better decoder does help here** —
this is the only one of the five where the engine is genuinely implicated.

### (d) Sentences cut — real, but small, and already fixed in source
Inter-line delta is a clean proxy for which timer fired:

| gap to previous line | n | mean words | ≤4w |
|---|---|---|---|
| 0–3s | 41 | **2.1** | 88% |
| 3–7s | 52 | 6.5 | 54% |
| **7–9s** | **29** | **18.7** | 31% |
| 9–12s | 29 | 15.2 | 24% |

The 7–9s bucket is the 8-second ceiling firing during continuous speech, and it
produces **18.7-word lines**, not shards — 140 wpm, exactly right. **The ceiling
is a sentence-cutting bug, not a shard-producing bug.** That is why cut-marking
buys only ~5 points (49.3% → 44.4% upper bound). It is still worth shipping; it
is just not the shard fix.

### (e) Duplicate republication
9 of 220 consecutive pairs (4%) share ≥60% of their words within 15s — the same
thought sent twice as the recognizer revises. `isEchoOfPrevious` catches the
close ones; its `novel > 2` escape lets these through:
```
+7s  A: "You see and it's currently listening to us right now so if you were to..."
     B: "And it's currently listening to us right now so if you were to..."
```
To a reader this *looks* exactly like "inconsistent transcription". It is not
lost words; it is the same words twice. **Not the engine.**

### (f) Delivery failures
180 of 359 rows in 72h carry **no `source` at all**. Half the pipeline's
provenance is missing. `ListenTally.postsFailed` measures this on the phone side
and is not deployed.

**Summary: of six mechanisms, exactly one — (c) words wrong — is an engine
fault. It is not the dominant one.**

---

## 5. Honest estimate: how much of 41% do the undeployed fixes explain?

Asked directly, answered with numbers rather than confidence.

| Symptom | Explained by undeployed fixes | Confidence |
|---|---|---|
| 25h of zero capture | **~100%** — call cliff + blind watchdog | **High.** The mechanism is read in the diff; the gap shape matches exactly. |
| `speaker` 0% | **100%** — enrollment unreachable | **Certain.** One call site, measured 0/221. |
| Shard rate 41–49% | **~5 points of it** (49.3 → 44.4 upper bound) | **High.** Computed from the rows, generous assumption. |
| Word capture ~30% | **some, and I cannot bound it** — see below | **Low.** The one number here I will not put a figure on. |
| Duplicate lines | 0% — echo threshold untouched | High |

**The one row I am revising against my own first draft.** I initially wrote "~0%"
for word capture, reasoning that none of the landed fixes *adds* words. That is
wrong, and an adversarial pass should catch it. The watchdog fix (`2c4e9ec8`)
rescues a recognizer that has gone deaf **with nothing pending** — and on build
76 that leg is dead for the entire life of every task after its first utterance.
A recognizer that goes deaf at minute two and is not rotated until minute *never*
loses every word spoken after it, inside a session that still looks alive. **That
is a word-capture bug, it is fixed in the repo, and it is not on the phone.**
How many words it costs is exactly what nobody can say without `ListenTally`'s
`swapsByCause`, which is also not deployed.

So the honest statement is narrower than my headline and I am stating the
narrower one: **the undeployed backlog explains the lost sessions and the
attribution completely, about a tenth of the shard rate, and an unknown but
possibly large share of the missing words.** What it demonstrably does *not*
explain is the shape of §4(b) — isolated two-word fragments with live capture
either side, which is a signal problem, not a liveness one.

Anyone who tells you the fixes will take you to <25% shards has not run the
arithmetic. Anyone who tells you the engine is therefore the cause has skipped
LAW 5 step 1.

---

## 6. The untested suspect: the audio session is configured to hear badly

`PhoneListener.swift:311`:

```swift
try? session.setCategory(.record, mode: .measurement, options: .duckOthers)
```

`.measurement` mode exists to **minimise system-supplied input signal
processing** — including automatic gain control — for apps that need a raw
signal to measure. Apple's guidance contrasts it directly with `.voiceChat`,
which "ensures that signals are optimized for voice through system-supplied
signal processing."
([AVAudioSession.Mode](https://developer.apple.com/documentation/avfaudio/avaudiosession/mode-swift.struct),
[Configuring an Audio Session](https://developer.apple.com/library/archive/documentation/Audio/Conceptual/AudioSessionProgrammingGuide/AudioSessionBasics/AudioSessionBasics.html))

The code comment defends it: *".measurement is deliberate and matches Apple's
own SFSpeechRecognizer sample."* That is true, and it is the wrong reference
class. Apple's SpokenWord sample is a hold-the-phone dictation demo — near-field,
one speaker, seconds long. **This product is a phone on a table listening to a
room all day.** Those want opposite front ends. Nothing in the app enables voice
processing: `grep` for `setVoiceProcessingEnabled` / `voiceChat` over
`app/ios/Anticipy/` returns **zero hits**, and this line has not been revisited
since build 6 (`d2218bc1`).

The available alternative, already on the iOS 16 floor:
`AVAudioIONode.setVoiceProcessingEnabled(_:)` (iOS 13+) turns on Apple's voice
processing unit — AGC, noise suppression, echo cancellation — with
`isVoiceProcessingAGCEnabled` exposing the gain stage.
([setVoiceProcessingEnabled](https://developer.apple.com/documentation/avfaudio/avaudioionode/setvoiceprocessingenabled(_:)),
[isVoiceProcessingAGCEnabled](https://developer.apple.com/documentation/avfaudio/avaudioinputnode/isvoiceprocessingagcenabled),
[WWDC23: What's new in voice processing](https://developer.apple.com/videos/play/wwdc2023/10235/))

**This is a hypothesis, not a finding, and I am flagging it as one.** There is a
real counter-argument: voice processing is tuned for two-way near-field calls,
its AEC is pointless with no downlink, and it could plausibly hurt. The point is
that **nobody has measured it**, it costs one line to try, it helps every iOS
version including the 16.0 floor, and under LAW 5 it is step 1 while the engine
is step 5. It goes in the experiment as an arm, not into the codebase as a
decree.

</content>

---

## 7. `contextualStrings` — a correction to a written ruling, and it makes things worse

`docs/DECISIONS-2026-08-24.md:45-46` records: *"`SpeechAnalyzer` has no
`contextualStrings` equivalent."* **That is half wrong, and the truth is worse
than the ruling.**

**The API exists.** `AnalysisContext.contextualStrings` is real and
Apple-documented on iOS 26+, keyed by `ContextualStringsTag` (`static let
general`), attached via `SpeechAnalyzer.setContext(_:)`, capped at ~100 phrases
of one or two words — the same cap as legacy `SFSpeechRecognitionRequest`.
([AnalysisContext.contextualStrings](https://developer.apple.com/documentation/speech/analysiscontext/contextualstrings))
*Relayed from a peer session; Apple's doc pages render client-side and I could
not read the prose myself — see §11.*

**But `SpeechTranscriber` ignores it.** Apple staff, accepted answer, Apple
Developer Forums thread 811083, Jan '26 — **I fetched and confirmed this quote
myself**:

> "However, currently, contextual strings only help transcriptions from the
> `DictationTranscriber` module. The `SpeechTranscriber` module does not
> currently take contextual strings into account."
>
> — Apple_Agent, https://developer.apple.com/forums/thread/811083

The same answer points to `SFSpeechLanguageModel` via
[DictationTranscriber § Improve accuracy](https://developer.apple.com/documentation/speech/dictationtranscriber#Improve-accuracy)
— again, `DictationTranscriber` only.

**Why "exists but inert" is worse than "does not exist."** A missing API is a
compile error: self-announcing, impossible to ship by accident. An API that
exists, accepts your strings, returns without throwing, and silently does
nothing is a **green migration that regresses the guard**. `tejas_gate` leg 7
greps `PhoneListener.swift` for the string `contextualStrings` and for
`"Anticipy"` near it. **A migration to `SpeechTranscriber` that sets
`AnalysisContext.contextualStrings` passes leg 7 while the biasing does not
happen.** That is precisely the failure LAW 3 was written about.

### What that costs, concretely — measured, not asserted

Across 30 days of production transcript:

| token | occurrences |
|---|---|
| `anticipate` (the mistranscription) | **13** |
| `Anticipy` (correct) | **1** |
| `Texas` (for "Tejas", a person) | 1 |

**The product's own name comes out wrong 13 times out of 14 — 93%.** And the
lines it comes out wrong *in* are the lines that mint actions:

```
08-05 23:27  "Griffin anticipate want to send an email to Andy from Barry"
08-24 01:24  "...I'll buy a domain like anticipate growth there's something.com"
08-24 01:26  "Anticipate just told me that's 5 PM CST to PST time"
08-05 00:53  "...hey just wanted to let you know Texas ..."   <- a human, now a US state
```

So the concrete cost of an unbiasable transcriber is not "loses custom
vocabulary." It is:

1. **A domain-purchase goal built on a misheard name** — the recorded incident,
   verbatim in production, on the money shelf.
2. **A send-email goal carrying three name tokens, one already garbage**
   ("Griffin anticipate want to send an email to Andy from Barry"). Downstream,
   `tejas_gate` leg 3 forces an unresolvable name to ASK rather than ACT — so
   the *good* outcome is a wasted interruption against a budget of
   `UNINVITED_TEXTS_PER_DAY = 3`, and the *bad* outcome is a name that resolves
   to the wrong human in Contacts and gets texted. Leg 5 exists because a name
   was invented at the voice layer once already.
3. **A person's name replaced by a place name**, which resolves cleanly and
   wrongly.

`AnticipyVocabulary.current()` carries `["Anticipy", "Tejas", "OpenTrade",
"pendant"]` plus the owner's own first and last name from onboarding plus every
name in `VoiceRoster` — capped at 60. **Those are exactly the tokens that decide
who gets messaged.** Losing biasing on them is not a transcript-cosmetics
regression; it is an action-safety regression.

### One caveat that cuts the other way, and I am flagging it

Those 13 `anticipate` lines are **all from before `contextualStrings` shipped**.
Leg 7 landed in commit `6e277694` at 2026-08-24 03:48 UTC; the last transcript
line of any kind arrived 2026-08-24 03:34 UTC — **14 minutes earlier**.

So: **build 76's vocabulary fix has produced between zero and fourteen minutes
of production evidence, and no phone line has arrived in the 24h 41m since.**
The 1:13 ratio measures the *unbiased* baseline correctly, which is the right
number for pricing a migration. It does **not** prove `contextualStrings` works
here — that is untested in the field, and it should be on the same experiment.

### Therefore option A is a three-way fork, not two

| Arm | Long-form quality | Phrase biasing | Custom LM | What it buys over today |
|---|---|---|---|---|
| `SpeechTranscriber` | best available on-device | **none** | none | no task limit, better far-field/multi-speaker, sample-accurate timestamps — **at the price of §7's 93%** |
| `DictationTranscriber` | per Apple, *the same models and locales as on-device `SFSpeechRecognizer`* | yes | yes (`SFSpeechLanguageModel`) | **very little** — same acoustic models, iOS 26 floor, no vocabulary gain |
| stay on `SFSpeechRecognizer` | dictation-grade | yes (in use) | yes, unused (`SFSpeechLanguageModel`, iOS 17+) | keeps the 16.0 floor, keeps leg 7 |

`DictationTranscriber` is the trap arm: it looks like the safe migration and,
by Apple's own description, delivers approximately nothing while costing the
iOS floor. **If the migration happens it must be `SpeechTranscriber`, and it
must be additive — the SF arm retained for the floor *and* for vocabulary — as
`docs/DECISIONS-2026-08-24.md` already ruled. That ruling's conclusion stands;
its reason needs the correction above.**

The unexplored middle: `SFSpeechLanguageModel` / `SFCustomLanguageModelData`
(iOS 17+) is a genuinely stronger form of biasing than `contextualStrings` and
is **not used anywhere in this app**. It works on the incumbent. Nobody has
tried it.

---

## 8. The candidates, judged on this product's conditions

"This product's conditions" means: a phone on a table or in a pocket, two or
more people, ambient, all day, an invented product name, iOS floor 16.0, and
`design/LOCAL-FIRST.md` rule 1 — *"RAW AUDIO NEVER LEAVES A DEVICE. Not to
Deepgram, not to anyone."*

| | far-field / multi-speaker accuracy | local-first | custom vocabulary | timestamps / VAD | cost, all-day | iOS floor | integration cost |
|---|---|---|---|---|---|---|---|
| **SFSpeechRecognizer** (incumbent) | dictation-grade; 1-min task cap | **compliant** (`requiresOnDeviceRecognition` set — but see §11) | **yes, in use**; `SFSpeechLanguageModel` unused | partials only, no VAD | $0 | **16.0** | zero |
| **SpeechTranscriber** (iOS 26) | *unverified.* Best independent conversational number is **14.0% WER, losing to whisper-small** | **compliant** | **none** (§7) | word-level `CMTimeRange`; free `SpeechDetector` VAD | $0 | **26.0** + a hardware gate | high — new arm, routing policy, asset management |
| **DictationTranscriber** (iOS 26) | per Apple, *same models as on-device SFSpeechRecognizer* | compliant | yes + custom LM | same | $0 | 26.0 | high, for ~nothing |
| **sherpa-onnx ASR** (already linked!) | model-dependent; Parakeet-TDT-v3 ≈6.09% WER on Open ASR LB | **compliant** | hotwords/contextual biasing | VAD + diarization available | $0 + model MB | **16.0** | **low — the runtime already ships** |
| **WhisperKit** | whisper small.en 12.8% WER on earnings22 | compliant | `initial_prompt` only | word timestamps | $0 | 16-ish | medium; ~1.6 GB for large-v3-turbo |
| **Deepgram Nova-3 / Flux** | Nova-3 **5.2%** WER (independent, batch); diarization **39.1% DER, last place** | **VIOLATION** — see §9 | keyterm prompting, 500 tokens | yes; model turn detection (Flux) | **$60–280 / user / month** | n/a | medium, plus a law change |

Sources for every external number are in §12.

### Apple `SpeechAnalyzer` / `SpeechTranscriber` — the probable endgame, with four surprises

The spec calls it *"materially better distant-mic and multi-speaker handling —
exactly the Tejas conditions."* **That claim is not supported by anything I could
find, and one piece of evidence cuts against it.**

1. **The `farField` content hint exists only on `DictationTranscriber`, not on
   `SpeechTranscriber`.** `SpeechTranscriber` has no `ContentHint` type at all
   and its initializer takes no `contentHints:`. The module Apple markets for
   distant audio is the one with no far-field knob.
   ([SpeechTranscriber](https://developer.apple.com/documentation/speech/speechtranscriber),
   [DictationTranscriber](https://developer.apple.com/documentation/speech/dictationtranscriber))
2. **The two accuracy benchmarks that exist bracket the truth and both come from
   interested parties.** On **LibriSpeech** (read audiobooks, close mic)
   SpeechAnalyzer posts **2.12%** WER vs SFSpeechRecognizer's 9.02% — measured by
   [Lyonesse](https://lyonesse.app/blog/apple-speech-api-benchmark.html), who
   *sell a SpeechAnalyzer product and say so*. On **earnings22** (spontaneous,
   multi-speaker, conversational — far closer to this product) SpeechTranscriber
   posts **14.0%** and **loses to WhisperKit small.en at 12.8%** — measured by
   [Argmax](https://www.argmaxinc.com/blog/apple-and-argmax), who *sell
   WhisperKit*. The only disinterested source,
   [MacStories](https://www.macstories.net/stories/hands-on-how-apples-new-speech-apis-outpace-whisper-for-lightning-fast-transcription/),
   measured **speed only** (~2.2× faster than Whisper large-v3-turbo), said *"no
   noticeable difference"* in quality, and noted that all engines *"had similar
   trouble with **last names** and words like **'AppStories'**"* — which is
   precisely this product's failure mode.
   **Weight the earnings22 number, not the LibriSpeech one.**
3. **`isAvailable` can be false on an iOS 26 device.** Reported false with an
   empty `supportedLocales` on iPhone 11 / 11 Pro / SE 2nd gen. There is an
   undocumented hardware gate on top of the OS version, and it does not run in
   the Simulator at all. ([forum 806765](https://developer.apple.com/forums/thread/806765))
4. **There is an open bug on the exact code path a live-mic app uses.**
   `start(inputSequence:)` fed `AnalyzerInput(buffer:bufferStartTime:)` fails
   with `_GenericObjCError` / `nilError`, while the same audio via
   `start(inputAudioFile:)` works. Reproduced on macOS 26.3 / Xcode 26.3, in a
   minimal CLI, with `DictationTranscriber` too.
   ([forum 818005](https://developer.apple.com/forums/thread/818005))

**Genuinely won, and worth having:** no task-duration limit (the root cause of
§4(d), removed rather than managed), word-level `CMTimeRange` timestamps, a free
on-device `SpeechDetector` VAD, and an append-only result stream unless you opt
into volatile results. Also: **no diarization, at all** — the Speech framework
has no speaker API anywhere, so `sherpa-onnx` + `SpeakerTagger` stays either way.

**Verdict: still the probable endgame, but the spec's stated reason for it is
unproven and its stated cost was understated.** Build it as an additive arm when
you build it, and gate the decision on §11's experiment rather than on the
marketing.

### Apple Foundation Models — the owner is conflating two things

`FoundationModels` (iOS 26) is a **~3B-parameter on-device text LLM** —
`SystemLanguageModel` is *"capable of text generation tasks."* Modalities are
text and, from iOS 27, images. **It has no ASR capability whatsoever** and there
is no audio input anywhere in the framework.
([FoundationModels](https://developer.apple.com/documentation/foundationmodels),
[SystemLanguageModel](https://developer.apple.com/documentation/foundationmodels/systemlanguagemodel),
[Apple ML research](https://machinelearning.apple.com/research/apple-foundation-models-2025-updates))

So: **"Apple Foundation systems" and "Apple's new speech API" are two different
frameworks, and only one of them transcribes anything.** The speech one is
`SpeechAnalyzer`. Say so plainly rather than evaluating a language model as an
ear.

It is *not* useless here, but it is not a candidate for this decision. As
on-device post-processing — punctuation repair, entity normalisation — it is
constrained by a **4096-token context shared between input and output**
(TN3193), background rate-limiting, and a model Apple replaces on OS updates.
And per LAW 1 it would have to be asked to *understand*, never used as a
fuzzy-match rule over a candidate list. **A Levenshtein pass that rewrites
"anticipate" to "Anticipy" is a pattern-matcher deciding meaning and would be
tape.** The in-bounds fix is acoustic: bias the recogniser, don't repair its
output.

### The incumbent's unused upgrade: `SFSpeechLanguageModel`

`SFSpeechLanguageModel` / `SFCustomLanguageModelData` (iOS 17+) is a trained
custom language model, and unlike `contextualStrings` **it carries
pronunciations** — which is exactly what an invented product name needs and
exactly what a phrase list cannot express. It works on the incumbent, on the
current floor for anyone at 17+, and it is **used nowhere in this app**.

Apple's own engineer, in the same thread that killed `SpeechTranscriber` biasing:
*"you might also include domain-specific terminology or unusual or made-up words,
but the system may not estimate their pronunciation correctly. **You can provide
a custom language model with correct pronunciations.**"*
([forum 811083](https://developer.apple.com/forums/thread/811083))

This is the cheapest available answer to the 1-in-14 name problem and nobody has
tried it.

### `sherpa-onnx` — already linked, half used, and it is not vestigial

`app/ios/project.yml` pins it **by revision** (`00ad9a19…`), and the target
really does link it (`dependencies: - package: SherpaOnnx, product: sherpa-onnx`).
`tejas_gate` **leg 6** exists solely to keep it linked, because it shipped
disconnected for several builds while a 26 MB model rode along in every binary.

**What it is used for today: speaker embeddings only.**
`SpeakerTagger.swift:167` wraps `SherpaOnnxSpeakerEmbeddingExtractorWrapper` over
`Resources/speaker-embedding.onnx` (26 MB). That is the whole of it.

**What that means for this decision:** the on-device ASR runtime, the VAD, and
the diarization machinery are **already in the binary and already shipping**. An
on-device ASR arm here is a model file and a config object, not a new
dependency, not a new build system, and not an iOS-floor change. That makes
sherpa-onnx the only candidate on this list that can improve capture **on the
16.0 floor**, which is the floor the recruited stranger may well be on.

I have not verified sherpa-onnx's current hotword/contextual-biasing support or
per-model iOS RTF myself — see §12.

---

## 9. Deepgram and LOCAL-FIRST — confronted, not footnoted

**`design/LOCAL-FIRST.md` names Deepgram, by name, twice.** Rule 1: *"RAW AUDIO
NEVER LEAVES A DEVICE. **Not to Deepgram, not to anyone.** If a capability needs
better ears, find a better local model."* And the scoreboard row for phone
transcription: *"the earlier idea of moving phone STT to Deepgram is **DEAD on
this law**."* The spec repeats it in §2.

**Is there a configuration that satisfies local-first? No. Here is exactly what
I checked and why each door is shut.**

| Option | Verdict |
|---|---|
| On-device Deepgram SDK for iOS | **Does not exist.** Deepgram's iOS material is cloud-API WebSocket sample code. Their only on-device work is Nova-3 on the **Qualcomm Hexagon NPU in Snapdragon X Windows PCs** (announced 2026-07-21) — not iOS, not a shipping mobile SDK. ([Deepgram/Snapdragon](https://deepgram.com/learn/deepgram-delivers-real-time-voice-ai-at-the-edge-for-use-with-snapdragon)) |
| Self-hosted / on-prem | **Exists, and cannot run on anything you own.** *"Deepgram only supports NVIDIA GPUs at this time"*; **Linux x86-64 only**; no macOS, no ARM, no Apple Silicon. Needs ≥16 GB GPU VRAM (T4/A10/L4/L40S/A100/H100), 32 GB system RAM. Requires an **Enterprise plan** with per-project authorization. ([deployment environments](https://developers.deepgram.com/docs/self-hosted-deployment-environments), [self-hosted intro](https://developers.deepgram.com/docs/self-hosted-introduction)) Third-party trackers put Enterprise at **$15k–30k/year**. Deepgram's own break-even analysis is **~2,400 audio-hours/month** (≈5 all-day users) before self-hosting beats cloud. ([cost analysis](https://deepgram.com/learn/voice-ai-deployment-cost-cloud-dedicated-self-hosted)) |
| Explicit consented exception | Possible in principle, but note what it costs: **the raw audio still leaves the phone.** Self-hosting changes *who* holds it, not *whether it travels*. Rule 1 is written about the device, not the vendor. Amending it is the owner's call, not an engineer's. |

**Cost at all-day usage, one user** (my arithmetic on Deepgram's published
per-minute rates — note several are flagged *promotional*, so the right number
to budget is the regular column):

| | Nova-3 streaming, promo | regular | + diarization, regular |
|---|---|---|---|
| 8 h/day | $69/mo | $111/mo | $140/mo |
| 16 h/day | $138/mo | $222/mo | **$279/mo** |

([Deepgram pricing](https://deepgram.com/pricing)) At 16 h/day with diarization
that is **~$3,350/year for one user** — for a product whose whole pitch is
listening all day.

**And it is no longer even the accuracy leader.** On Artificial Analysis's
independent AA-WER v2 benchmark (manually corrected ground truth, deliberately
not clean read speech), **Deepgram Nova-3 places last of eleven at 5.2% WER**,
behind ElevenLabs Scribe v2 (2.2%), Azure (2.4%), AssemblyAI Universal-3 Pro
(3.1%) — while placing *first* on throughput at 523× realtime.
([AA speech-to-text](https://artificialanalysis.ai/speech-to-text/non-streaming))
Its streaming diarization measures **39.1% DER / 25.3% missed speech**, last
behind Speechmatics (31.3%) and pyannote (19.8%) — though that benchmark is
published by pyannoteAI, a competitor, so discount it accordingly.
([pyannote benchmark](https://www.pyannote.ai/blog/streaming-diarization-benchmark))
Deepgram in 2026 is a **speed** product, not an **accuracy** product.

One more thing worth knowing: **Deepgram's default is not zero-retention.**
Their docs say *"Deepgram stores fractional increments of data for the continued
improvement of our voice AI models"*; suppressing that requires
**`mip_opt_out=true` per request** — a parameter a developer can forget, not an
account setting.
([MIP program](https://developers.deepgram.com/docs/the-deepgram-model-improvement-partnership-program))
Marketing pages that claim zero retention by default contradict the docs.

### The Deepgram that is already shipping, and that this report will not let pass

`app/ios/Anticipy/Audio/TranscriberClient.swift:27` streams **raw pendant Opus
frames to `wss://api.deepgram.com/v1/listen`**, and `project.yml`'s
`NSBluetoothAlwaysUsageDescription` discloses it to the user in terms:
*"pendant audio is sent to Deepgram for live transcription."*

This is already logged as `docs/FOLLOWUPS.md` item 8, correctly, as a shipped
LOCAL-FIRST violation — latent only because the pendant firmware is
`BUILT_AND_VERIFIED_NOT_FLASHED`. **I am flagging it again here because it is
directly relevant to this decision:** the law-abiding replacement,
`LocalTranscriber.swift`, is already written, already sets
`requiresOnDeviceRecognition = true`, already carries `AnticipyVocabulary` — and
is **never instantiated anywhere in the app**. Its own header claims a
"Local/Cloud toggle in Settings" that does not exist.

So the honest state of play is: **the repo has one cloud ASR integration, it is
dark, it violates the stated law, and the compliant replacement for it is
finished and unplugged.** That is a decision the owner owes before the pendant
ships — not a reason to route the phone mic to Deepgram too.

**Verdict: Deepgram is refused. Not on a close call — on the law, on the money,
and on the accuracy.**

---

## 10. Ranked recommendation

### 1. Ship what is already fixed, then measure. *(not an engine)*

Cut a build. Nineteen iOS commits — including the two that stop a phone call
and a dead recognizer from ending the day — are sitting in the repo where they
help nobody. **The device has produced zero transcript lines in 25 hours.** No
engine choice matters until the app is capturing at all.

Then read `ListeningDiagnosticsView` (already built, already reachable from
Settings, already ships in RELEASE, already exports via `ShareLink`) beside
`proof/capture_day.py`. That pairing answers §4's five failure modes directly:
`flushesByReason["ceiling"]`, `stopsByCause`, `swapsByCause["appReturned"]`,
`postsFailed`, `longestSilenceSeconds`.

**Cost: a build number and a day. Blocks everything else.**

### 2. Fix the audio front end before fixing the decoder. *(not an engine)*

`.measurement` → voice processing, as an experiment (§6). LAW 5 step 1. Helps
every iOS version including the 16.0 floor. One line, and the §11 experiment
tells you whether it is right before it ships.

### 3. `SFSpeechLanguageModel` for the product name. *(the incumbent, upgraded)*

The 1-in-14 name failure (§7) has a purpose-built fix on the current engine,
iOS 17+: a custom LM that carries **pronunciations**, which `contextualStrings`
cannot express. Apple's own engineer recommends exactly this for made-up words.
**Unused in this app.** Cheaper than any migration and it is the only option
that addresses the one failure mode that genuinely *is* the engine's fault.

### 4. `sherpa-onnx` streaming Zipformer — the best *engine* candidate, if one is needed

This surprised me, and it is the most useful thing in this report after the
deployment gap.

- **It is already linked and already shipping.** The pin resolves to
  **v1.13.4** binaries; `Package.swift` at that revision declares
  `platforms: [.iOS(.v15), …]`. **It clears the 16.0 floor.** Apache-2.0.
- **It has real contextual biasing on the streaming path.** `hotwords-file`
  (per-phrase boost), `hotwords-score`, `modeling-unit`, `bpe-vocab`, matched by
  an Aho–Corasick automaton over tokens — and these are **exposed in the Swift
  API** (`hotwordsFile`, `hotwordsScore`, `modelingUnit`, `bpeVocab`,
  `decodingMethod` on the online recogniser config). Requires
  `modified_beam_search` and a transducer model.
  ([hotwords](https://k2-fsa.github.io/sherpa/onnx/hotwords/index.html),
  [SherpaOnnx.swift](https://raw.githubusercontent.com/k2-fsa/sherpa-onnx/master/swift-api-examples/SherpaOnnx.swift))
- **It has Silero VAD**, which the app has none of today.
- Documented streaming Zipformer RTF **0.06–0.11**; the bilingual model is
  documented running real-time on a **Cortex-A7**, so an A-series iPhone has
  enormous headroom. ([zipformer models](https://k2-fsa.github.io/sherpa/onnx/pretrained_models/online-transducer/zipformer-transducer-models.html))

**It is the only candidate that keeps the iOS 16.0 floor, keeps custom
vocabulary, keeps local-first, and adds VAD — with no new dependency.**
`SpeechTranscriber` forfeits vocabulary and the floor; `DictationTranscriber`
forfeits the floor for the same acoustic models; Deepgram forfeits the law.

Caveats I am not hiding: sherpa-onnx **diarization is offline-only** (verified
by source inspection — every implementation file is prefixed `offline-`), so it
cannot replace real-time speaker labelling. That is fine, because *owner vs
other* is **1:N verification against one enrolled voice**, not general
diarization — which is exactly what `SpeakerTagger` + `VoiceRoster` already do,
using this same library's embedding extractor.

### 5. `SpeechTranscriber` as an additive iOS 26 arm — later, and on evidence

Still probably the endgame; the spec is right about the direction. But it is
iOS 26 + an undocumented hardware gate, it forfeits vocabulary silently (§7),
its far-field claim is unverified and its only conversational-audio benchmark
is unflattering, and it has an open bug on the live-mic streaming path (§8).
**Do it when §11 says the decoder is the problem, not before, and build it
beside the SF arm as `docs/DECISIONS-2026-08-24.md` already ruled.**

### 6. WhisperKit — credible, second choice to sherpa-onnx

MIT, `Package.swift` declares **iOS 16**, streaming, word timestamps, VAD. But
its custom-vocabulary feature is **Pro-only at $1.33/device/month with a
1,000-license minimum** ([Argmax pricing](https://www.argmaxinc.com/pricing)),
and large-v3-turbo is ~1.6 GB — not an all-day background resident. Its free
tier's only biasing is Whisper's `initial_prompt`. It brings a new dependency
where sherpa-onnx is already in the binary.

**Worth stealing from it regardless:** **Argmax SpeakerKit** — Pyannote v4 on
Core ML, **~10 MB, iOS 16+, MIT, in the free tier** — against the **26 MB**
`speaker-embedding.onnx` shipping in every build today.
([SpeakerKit](https://www.argmaxinc.com/blog/speakerkit))

### Refused

**Deepgram** — §9. **Apple Foundation Models** — not an ASR at all (§8); the
owner's mention conflates two frameworks. **Kyutai STT** — 1B+ params via MLX is
not an all-day iPhone resident. **whisper.cpp raw** — WhisperKit or sherpa-onnx
dominate it on iOS with less work.

---

## 11. The cheapest experiment that proves or kills the top pick

**One recording. Four decoders. One afternoon. No migration, and no product
code.**

My top pick is *"the engine is not the problem — the audio front end and the
undeployed fixes are."* The experiment that would kill it is the one that runs
**a strong reference decoder over the exact audio the incumbent already hears.**
If a good decoder also gets ~30% of the words off that file, the signal is
starved and no engine on this list saves you. If it gets 90%, the engine is the
cause and §8's migration is justified on evidence — which is exactly what the
spec asked for.

### The setup

**Two recordings, ~10 minutes each, back to back, in the real condition** —
phone on a table, two people, ~2 m, normal room noise. Read a **known script**
for the first half (so word capture has exact ground truth) and talk freely for
the second half, making sure "Anticipy", "Tejas" and the owner's own name each
occur several times.

Capture the buffers **through the app's own audio path** — same `.record`
session, same `inputNode` tap format — writing the tap to a WAV. That is ~40
lines in a **scratch target**, and it matters: a Voice Memos recording is not
what `SFSpeechRecognizer` hears.

- **Arm A:** today's config — `.record, mode: .measurement`.
- **Arm B:** identical, plus `inputNode.setVoiceProcessingEnabled(true)`.

### The decoders (offline, over the saved WAVs, on the Mac or a device)

| # | Decoder | The question it answers |
|---|---|---|
| 1 | `SFSpeechRecognizer`, `requiresOnDeviceRecognition = true`, **with** `contextualStrings` | today's baseline, measured for the first time |
| 2 | same, **without** `contextualStrings` | **does leg 7's fix do anything under `requiresOnDeviceRecognition`?** (§12) |
| 3 | a strong reference — whisper large-v3 or Parakeet-TDT-v3 on the Mac | **is the audio decodable at all?** — the whole experiment |
| 4 | *(only if an iOS 26 device is to hand)* `SpeechTranscriber` | the actual §8 candidate, on real audio |

Score two numbers per cell: **word capture** (recognised / ground-truth words)
and **product-name hit rate** ("Anticipy" correct ÷ mentions — today's baseline
is **1/14**).

### The decision rule, pre-registered *before* anyone runs it

Written down first, per the spec's own §12.4: *"Deciding the bar after seeing
the result is how a bake-off gets talked into the wrong conclusion."*

| Result | Conclusion |
|---|---|
| Decoder 3 on **file A** scores ≲45% word capture | **The audio is starved. The engine is exonerated.** Fix the front end; do not migrate. |
| Decoder 3 on file A scores ≳75% while decoder 1 scores ~30% | **The decoder is the cause. §8's migration is justified** — go to sherpa-onnx (floor-safe) or `SpeechTranscriber` (iOS 26 arm). |
| **File B** beats file A on decoder 1 by ≥15 points | **`.measurement` is the bug.** One-line fix, every iOS version, ship it. |
| Decoder 1 ≈ decoder 2 on name hit rate | **`contextualStrings` is inert under `requiresOnDeviceRecognition`.** `tejas_gate` leg 7 is green over an inert setting — a LAW 3 finding, and the fix is `SFSpeechLanguageModel`. |

**Cost: one scratch target, one Mac script, one afternoon.** It settles the
engine question, the front-end question, and the vocabulary question at once,
and every one of those is currently a belief.

**Do this before writing one line of a new transcriber.**

### The one-day version, if even that is too much

Cut build 77 and read `ListeningDiagnosticsView` after a normal day. It already
reports `flushesByReason["ceiling"]`, `stopsByCause`, `swapsByCause`,
`postsFailed` and `longestSilenceSeconds`. That will not separate a starved mic
from a weak decoder — only the experiment above does that — but it will tell you
in one screen how much of the complaint is lost sessions, which is the finding
this report expects to dominate.

---

## 12. What I could not verify — read this before quoting anything above

Per the brief: vendor benchmarks are marketing until corroborated, and a claim I
could not reach a primary source for is marked as such rather than laundered
into a fact.

**Verified by me, directly:**
- Every production number in §1–§5, §7 — run tonight against
  `backend-production-61e0a.up.railway.app` via `proof/capture_day.py`'s own
  reader. Scripts are in this session's scratchpad; they are re-runnable.
- The Apple staff quote in §7 — I fetched
  [forum 811083](https://developer.apple.com/forums/thread/811083) myself and
  confirmed it verbatim, attribution and date included.
- Every repo claim: build number, commit list, call sites, the sherpa-onnx
  linkage, `.measurement`, the `VoiceEnrollView` single call site.

**Relayed from research agents, primary-sourced but not re-fetched by me:**
Apple's `AnalysisContext.contextualStrings` declaration and its 100-phrase cap;
`SpeechTranscriber.isAvailable` returning false on iPhone 11 / SE2; the
`start(inputSequence:)` bug; sherpa-onnx's `Package.swift` platform floor and
hotwords Swift API; WhisperKit's iOS 16 manifest; SpeakerKit's 10 MB / iOS 16.
Apple's documentation pages render client-side and did not yield prose to
`WebFetch` — **the Apple doc URLs in this report are citations for the reader,
not pages I read.** Re-check any of them before acting on it alone.

**Vendor claims, labelled as such and NOT treated as fact:**
- Apple's "faster and more flexible" / "accurate even at longer distances" —
  **no numbers published at all.**
- Lyonesse's 2.12% LibriSpeech WER — **sells a SpeechAnalyzer product.**
- Argmax's 14.0% vs 12.8% earnings22 — **sells WhisperKit.** (I lean on this one
  anyway because it is the *unflattering* direction for the party publishing it,
  and because earnings22 resembles this product's audio.)
- pyannoteAI's diarization DER table — **sells diarization.**
- Deepgram's "54.2% better than next-best" — stale (Feb 2025); their *measured*
  5.2% is honest, the comparison is not.

**Genuinely unmeasured by anyone, and the decision doc must not pretend
otherwise:**
1. **No published RTF for whisper.cpp on any iPhone newer than an A15**, and
   none with Core ML on iOS. **No published iPhone RTF for WhisperKit,
   FluidAudio, or sherpa-onnx either** — every number those vendors publish is
   an M-series Mac.
2. **No credible battery or thermal measurement for continuous all-day
   on-device ASR on an iPhone.** The figures circulating are content-farm
   output. For an all-day listener this is the *most* important unknown about
   options 4–6 and it must be measured on the target device.
3. **Open ASR Leaderboard RTFx figures are A100 at batch 64** — use them to rank
   WER, never to predict mobile latency.
4. **Whether `contextualStrings` functions under `requiresOnDeviceRecognition`**
   — no primary source either way, and the app sets both. §11 decoder 2.
5. **Whether `SpeechTranscriber` survives backgrounding** — undocumented.
6. **`.measurement` vs voice processing** — a hypothesis I am putting into an
   experiment, not a finding.

**One more caution about search results on this topic:** several SEO sites
confidently describe a **"Deepgram Nova-4"** and **"Whisper-V4"** with precise
WER and latency figures. Neither exists in Deepgram's docs, changelog or pricing
page. Every model claim in §9 was cross-checked against deepgram.com.

---

## 13. If you read only one paragraph

Your phone has sent nothing for twenty-five hours, `speaker` has never once been
populated on a real line, and the shard rate is made of isolated two-word
fragments that no boundary fix can touch. Nineteen iOS commits that address
exactly these are sitting uninstalled behind a build number nobody bumped. The
§8 gate has not been run — it *cannot* be run until they ship. Cut build 77,
spend one afternoon on §11's recording, and you will know whether the engine was
ever the problem. My prediction, stated in advance so it can be wrong: **it was
not**, and the two things that actually move the number are a build and one line
of audio-session configuration.
