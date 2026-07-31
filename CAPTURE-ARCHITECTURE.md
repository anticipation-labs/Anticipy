# Anticipy — Ambient Capture & Context Architecture

Design produced 2026-07-31 from six parallel research lenses (endpointing/turn-detection,
wearable prior art incl. Omi, topic segmentation, BLE/Opus transport, streaming ASR, LLM
batching). It replaces the current 'every spoken line is triaged alone' model, which is the
root cause of fragmented capture and context-free questions.

---

## ARCHITECTURE

## THE ONE DESIGN: "Segments, not lines" — a five-level unit hierarchy with capture-time as the only clock

### Level 0 — FRAME (phone, on-device, free)
Silero VAD v6.2.1 CoreML (`FluidInference/silero-vad-coreml`, MIT, 1.2 MB, 309K params, ~23x realtime on Apple silicon). 512-sample / 32 ms chunks @ 16 kHz, LSTM state carried across chunks, reset every 5 s (Pipecat's `_MODEL_RESET_STATES_TIME`) to stop drift on all-day audio.
```
vad_threshold_on   = 0.50
vad_threshold_off  = 0.35          # hysteresis, universal across all shipped stacks
min_speech_ms      = 250
pre_roll_ms        = 300           # ring buffer, so word onsets aren't clipped
```
**This layer exists for exactly one output: authoritative `speech_start_at` / `speech_end_at` wall-clock timestamps, and therefore a real `gap_before_ms`.** Anticipy has no such number today. That single number resolves cases (a), (b) and (d).

### Level 1 — UTTERANCE (phone, on-device, free)
Close the acoustic segment at **200 ms** of VAD silence (Pipecat `stop_secs = 0.2`, deliberately short *because a semantic model runs downstream*). Then run **Smart Turn v3** (BSD-2, open weights + open data + open training script, 8 MB int8 ONNX, ~12 ms on a modern CPU, right-aligned 8 s audio window) — it only ever runs during silence, so it costs nothing while someone is speaking.
```
eot_min_delay_s    = 0.30
eot_recheck_ms     = 200           # re-ask every 200 ms of continued silence
eot_max_hold_s     = 4.00          # hard ceiling; between AssemblyAI-conservative 3.6 s and Krisp's 5 s max-hold
```
"complete" → close utterance. "incomplete" → hold open until `eot_max_hold_s`, then force-close (`eot: "timeout"`). This is what makes "what time is the demo day" + [1.8 s] + "Monday" one utterance instead of two.

### Level 2 — TURN (phone, on-device, free) — **this is the new wire unit**
Merge consecutive utterances whose inter-gap `< TURN_MERGE_S = 2.0` (LiveKit `false_interruption_timeout`). Force-flush any single turn at `MAX_TURN_S = 45` of continuous speech (below LiveKit's 60 s `max_buffered_speech`; keeps prompts bounded).

A turn is POSTed as one `events` row with the **turn envelope** — the single new contract between every capture source and the brain:
```json
{ "kind":"transcript", "text":"...",
  "source":"phone"|"pendant", "device_id":"iphone-b17", "boot_id":"…", "seq":812,
  "capture_started_at":"2026-07-31T18:22:41.120Z",   // ISO8601 UTC, ms, PHONE clock
  "capture_ended_at":  "2026-07-31T18:22:46.980Z",
  "gap_before_ms": 34120, "eot":"semantic"|"timeout"|"forced", "backfill": false }
```

### Level 3 — SEGMENT (server, `brain/segmenter.py`) — the open row
A segment is **a PocketBase row that stays open with a rolling `last_speech_at`**, not a stream. This is the Omi mechanism, and it is the whole answer to "no start/stop button": disconnect, reconnect, app backgrounding, BLE dropout — none of them are boundaries. Only capture-time silence is.
```
CONTINUE_S     = 45      # gap below this → append to open segment, ZERO model calls
MAX_SEGMENT_S  = 1800    # 30 min hard ceiling → force-close, then immediately relink
```
**Case (a), the 10–40 s gap, is resolved here for free by rule 1.** 45 s is chosen deliberately: it sits above the owner's stated 40 s worst case and far inside "same conversation" territory (Kummerfeld ACL 2019: 94.9% of consecutive same-conversation messages are within 2 minutes; Halfaker WWW 2015 within-session μ spans ~32 s–6600 s), while being 200x the human modal turn gap of 0–200 ms (Stivers PNAS 2009) so it can never be mistaken for turn-level endpointing.

### Level 4 — THREAD (server) — closed segments linked by continuity
Closing a segment is **not final and is never undone**. When the next turn arrives after a closed segment, `decide_link(gap_s, turn, prev_segment)` runs:
```
LINK_MAX_S  = 1200   # 20 min — above this, never link
GATE_BAND_S = 300    # 5 min — below: default LINK; above: default NEW
```
1. `gap < CONTINUE_S` → **append** to the still-open segment. Free.
2. `gap >= LINK_MAX_S` → **new root segment**. Free.
3. Free prefilter against the closed segment's stored entities + one-line summary:
   - shares ≥1 proper noun, or ≥2 content words → **LINK**, free.
   - turn is anaphoric/short (<8 words, no new entities, opens with `so / anyway / okay / right / back to / where were we / and / but / it / that / they / he / she`) → **LINK** if `gap < GATE_BAND_S`; else escalate.
   - turn is substantive (≥8 words) with its own new entities and zero overlap → **NEW** if `gap >= GATE_BAND_S`; else escalate.
4. Escalate → **one** cheap `continuity` call (`{"same_topic":true|false}`). Capped at 1 per segment open. On timeout/failure: default LINK below `GATE_BAND_S`, NEW above.

**Case (b), the 5-minute gap, is resolved here** — usually free (someone returning to a topic almost always re-mentions an entity), at worst one nano-tier call. A LINK sets `parent_segment` and inherits the parent's rolling summary + entities + any unanswered `ask` into the new segment's triage context. Nothing already triaged is re-triaged, nothing already dispatched is undone.

### Server-side ordering rule (the trap to design around from day one)
**Every boundary decision keys off `capture_started_at`/`capture_ended_at`, never PocketBase `created`.** Omi's shipped bug #6551 — backlog audio arriving in 1–3 min chunks each becoming a separate conversation because the timer was evaluated against *arrival* time — is exactly what Anticipy would inherit the first time BLE hiccups or the phone loses signal. Turns are placed into segments by capture time regardless of arrival order.

**Late/backfilled turns:** a turn whose span falls inside or adjacent to an already-closed segment is inserted into it and the segment is marked `dirty`. A dirty segment is re-triaged **once**, after `BACKFILL_SETTLE_S = 90` with no further inserts, with a `supersedes` pointer. Only jobs still in `awaiting_confirm` are cancelled and re-minted; anything released, running or done is never touched. A turn older than `LATE_MAX_S = 6h` is written to memory but never triaged — no acting on stale intent.

---

## WHAT GETS SENT TO THE BRAIN, AND WHEN — three batching triggers

Priority order, evaluated at every turn close:

**Trigger A — DIRECT ADDRESS (fast lane).** Free regex on the turn: the wake name, or a second-person imperative/question aimed at the assistant (`remind me`, `can you`, `look up`, `what time is`, `add to my`, plus the existing `_RECALL_RE` question shape in `anticipy_core.py:159`). Fires **immediately** — segment stays open. The payload is **the whole open segment plus the linked parent's summary**, not the bare line. Latency: turn close (0.2–4.0 s) + worker poll (≤2 s) + one plan call ≈ 6–10 s, i.e. unchanged from today.
*Safety valve:* a fast-lane turn may only produce a **read-only** goal (reuse `is_consequential()` in `anticipy_core.py:65`, which already classifies this for free). Anything consequential waits for segment close, where there is more context. This kills the "the fast lane acted on a stranger's question across the room" failure mode without needing speaker ID.

**Trigger B — SEGMENT CLOSE (main lane).** `CONTINUE_S = 45` of capture-time silence closes the segment → **one** gate call + (if it passes) **one** plan call over the entire segment transcript with turn timestamps and gap markers rendered inline, plus the thread summary. This is the fix for case (d): "what time is the demo day Monday" is never seen alone again.

**Trigger C — MID-SEGMENT FLUSH (responsiveness inside a long conversation).** A 20-minute meeting must not wait 20 minutes. At each turn close, flush if:
```
FLUSH_WORDS   = 120    # new untriaged words
FLUSH_SECONDS = 90     # since this segment's last triage
```
whichever fires first (in continuous speech at ~130 WPM the word trigger wins at ~55 s). The payload is the **whole segment so far**, with turns after `triaged_through_seq` marked `[NEW]`; the prompt instructs the model to propose work only for `[NEW]` turns and treat the rest as context. Idempotency is the `triaged_through_seq` cursor, on top of the existing `claim()` pattern in `worker.py:118`.

---

## COST TIERS

**Tier 0 — free / on-device / deterministic (zero tokens):** Silero VAD, Smart Turn v3, turn merge, segment idle timer, all timestamp arithmetic, the entity-overlap continuity prefilter, direct-address regex, the `<2 words = fragment` guard (`anticipy_core.py:191`), and Omi's two free short-circuits: `word_count > 120` → gate auto-passes with **no LLM call**; `< 6 content words and no direct address` → gate auto-fails with no call.

**Tier 1 — cheapest model (`ANTICIPY_GATE_MODEL`, e.g. `gemini-2.5-flash-lite`).** Exactly three jobs: `segment_gate` (does this segment contain any actionable owner intent? + emit the one-line summary — which is reused as thread context and as the continuity anchor, so it is never a wasted call), `continuity` (same-topic yes/no, capped 1 per segment open), and `memory_extract` (moved from per-line to per-segment: fewer calls, richer entities).

**Tier 2 — strong model (`ANTICIPY_PLAN_MODEL`).** The actual triage decision (ignore/ask/act + goal + missing + assumption), run **only** on gate-passing segments, over the full segment + thread summary + graph recall. **Because the gate eliminates most segments first, the planner can move UP a tier at lower total cost.** Per the north-star note that the planner on the cheapest model is the biggest quality lever, this is the point of the whole redesign.

**Arithmetic.** Today a 4-minute conversation ≈ 25 lines ≈ 25 triage calls + 25 extraction calls = 50 cheap calls, each contextless. After: 1 segment → 1 gate + 1 extraction + (if it passes) 1 strong plan call ≈ 3 calls. Strictly cheaper even with a 10x more expensive planner, and every call finally has context.

---

## OFFLINE EVALUATION (kills the "human-in-the-loop testing is slow and expensive" problem)

`brain/segmenter.py` is written as **pure functions over a list of turn dicts** — no PocketBase, no network. The worker writes every turn envelope to a JSONL log. Two new harnesses:
- `proof/replay_segments.py` — replay real logs through segmentation + triage under any parameter set; diff decisions.
- `proof/gap_histogram.py` — after ~2 weeks of logs, fit a 2-component Gaussian mixture on `log2(gap_seconds)` (Halfaker WWW 2015; Mehrotra WWW 2017 applied the identical method to Cortana and derived ~2 min, vs ~24 min for Bing — the correct threshold is a property of *your own* logged distribution, not a number you pick). Replace the hand-set `CONTINUE_S = 45` with the fitted valley. Evaluate boundary quality with **Pk / WindowDiff, not F1** (arXiv:2512.17083).

---

## DECISIONS (and what was rejected)

**Segment = an open DB row with rolling `last_speech_at`, not a stream.** Rejected: keeping the stream/session as the boundary (what the system effectively does today, where an `SFSpeechAudioBufferRecognitionRequest` swap is an implicit boundary). Grounded in Omi's `LiveConversationController.prepare()`, which on every reconnect asks exactly one question: `now − finished_at >= timeout ? finalize+new : rejoin`. A row makes disconnects, backgrounding and BLE dropouts structurally incapable of creating a boundary. It's also the smallest possible change: PocketBase already exists, this is one collection plus one lookup on ingest.

**All boundary logic keys off capture time, never arrival time.** Rejected: using PocketBase `created` (free, already there). Omi's open bug #6551 is the counterexample in production: Limitless backlog arriving in 1–3 min chunks becomes N separate conversations even when the chunks are seconds apart, because the timeout is evaluated on the live path against arrival time. Anticipy's pendant *is* store-and-forward, so this failure is guaranteed, not hypothetical. Step 1 of the migration uses arrival time as a stopgap precisely so it can't be forgotten in step 2.

**`CONTINUE_S = 45 s`, not Omi's 120 s.** Rejected: copying Omi's shipped 120 s default (and its hard 120 s floor). Omi is a *recorder* — it can afford to decide two minutes late. Anticipy has an ask/act lane where a direct command must land in seconds; that is the single biggest architectural difference and the main thing that cannot be copied wholesale. 45 s covers the owner's stated 10–40 s case with margin, is 200x the human modal turn gap (Stivers PNAS 2009: unimodal peak 0–200 ms), and sits deep inside same-conversation territory (Kummerfeld ACL 2019: 94.9% of consecutive same-conversation messages within 2 min). Its lateness is then bounded by the fast lane and the 120-word flush, not by the timer.

**A three-tier hierarchy, with only tier 3 being new work.** Rejected: tuning the existing 2.6 s timer in `PhoneListener.swift:68`. On LiveKit's public `eot-bench` a pure silence-threshold VAD **false-cuts 55.6% of turns at a 300 ms budget and still needs 1.6 s of silence to reach 5%**, versus 543 ms for a semantic model. Silence thresholds are not a tuning problem, they are the wrong signal for "did this thought finish." The 2.6 s value is also fragile in the opposite direction: it currently depends on SFSpeechRecognizer *partial text stability*, which is why a whole conversation once arrived as one line.

**Smart Turn v3 for semantic EOT.** Rejected: LiveKit Turn Detector v1 (strongest on the benchmark — 9.9% false-cutoff at 300 ms vs a 55.6% VAD baseline — but the weights are under the proprietary LiveKit Model License and v1 is cloud-gated, contradicting the on-device privacy constraint) and Krisp (commercial SDK). Smart Turn v3 is BSD-2 with **open weights, open data and an open training script** — the only one that can ship on-device, be fine-tuned on Anticipy's own audio, and owe nobody. 8 MB int8 ONNX is the only semantic EOT plausibly small enough for a phone.

**Silero VAD over TEN VAD and Apple `SpeechDetector`.** Rejected: TEN VAD (320 KB iOS arm64 lib, RTF 0.0050 on A11, 10 ms resolution, and a credible claim that Silero's *offset* timestamp lags several hundred ms — which matters when you're measuring gaps) because its license carries conditions and Silero has pre-converted CoreML/MLX exports plus MIT with zero friction; a few hundred ms of offset lag is irrelevant against a 45 s threshold. Rejected: iOS 26 `SpeechDetector`/`SpeechAnalyzer` as the *dependency* because it forces an iOS 26 floor today — but it is the right migration target and step 5 should abstract behind a protocol so it drops in.

**Ambiguous-band escalation is gated by a free prefilter, not always-on.** Rejected: running a same-topic LLM check on every segment open (simple, uniform, but a per-boundary tax on the cheapest model all day). Rejected: pure timer (Bee's "conversation end pointing" — VAD *combined with semantic content analysis* — is the only shipping wearable that doesn't rely on a pure timer, and it's the one that gets this right). Entity overlap is free because `memory.py` already extracts people/places/topics per episode; a person returning to a topic almost always re-mentions an entity, so the model call is genuinely rare.

**Closing is not final; linking is additive.** Rejected: reopening a closed segment and re-running triage over the merged whole (cleaner conceptually, but it means retracting decisions and cancelling dispatched jobs — unacceptable when the owner tests daily and a job may already be running in his browser). A LINK inherits context forward and never rewrites history. Only the backfill path re-triages, and only for `awaiting_confirm` jobs.

**Split gate/plan into two model tiers.** Rejected: one `gemini-2.5-flash` call doing both jobs (today's design in `orchestrator.py:96`). Omi's `model_config.py` splits `conv_discard` onto the nano tier and `conv_structure`/`conv_action_items` a tier up; `should_discard_conversation` additionally short-circuits with **zero LLM calls** above 100 words. Splitting lets the act/plan decision get a *better* model at *lower* total cost, because the gate eliminates most segments first.

**MCU does energy gating only; all VAD/EOT/segmentation lives on the phone.** Rejected: on-MCU Silero. The nRF52840 Sense is a 64 MHz Cortex-M4F with 256 KB RAM already spending its power on Opus+BLE; the true always-on tier in this space is dedicated analog/neuromorphic silicon at 30 µW–560 µW, not software on a Cortex-M4F. Omi's measured data justifies a *crude* gate anyway: **~79% of always-on streamed time is non-speech (avg 27.3 WPM across all streamed hours; 19.2% of hours at 0–5 WPM)**. That's a radio/battery lever, and RMS-over-rolling-floor captures nearly all of it.

**Do not import Omi's VAD *cost* argument.** Omi's 10–20% savings are Deepgram savings — they pay per streamed second. Anticipy uses Apple on-device STT, so STT cost is already zero. VAD is worth building here for (i) pendant battery and (ii) real timestamps — not as an STT-cost lever.

**A physical/UI "this is one thing" marker stays on the roadmap, not the critical path.** Plaud's boundary detector is a button, and it has the strongest quality reputation of the whole cohort. The phone has a screen and the pendant has a programmable button. An explicit marker is cheaper and more reliable than any inference — but it cannot be the primary mechanism for an always-on pendant, so it ships as an override on top of automatic segmentation, not instead of it.

---

## PHONE TODAY / PENDANT LATER

**The design is source-agnostic by construction: everything above Level 2 consumes turn envelopes and nothing else.** `source` is a string field, not a code path.

### Phone mic (today)
`PhoneListener.swift` already owns the mic tap, orphan-buffer replay across recognizer swaps, and the self-healing watchdog — all of that survives untouched. What changes is only the *boundary logic and the output type*: the 2.6 s partial-text-stability timer is replaced by VAD-derived silence + Smart Turn v3, and `onLine: ((String) -> Void)` becomes `onTurn: ((Turn) -> Void)` carrying the timestamps. The recognizer's own `isFinal` and request rotation stop being implicit boundaries — after step 5, a request swap has no effect on turn or segment boundaries at all, which structurally prevents a recurrence of the "whole conversation arrived as one line" incident documented at the top of that file.

### BLE pendant (later) — same pipeline, one new adapter
A new `app/ios/Anticipy/Audio/AudioRouter.swift` is the only new seam. It accepts 16 kHz mono PCM from **either** the `AVAudioEngine` tap **or** decoded pendant Opus frames (`PendantManager.onOpusFrame`, protocol already verified on hardware: service `19B10000`, 3-byte header, codec id 20 = Opus 16 kHz mono), and feeds one identical chain: Silero → Smart Turn → SFSpeech/`SpeechTranscriber` → turn envelope. The server sees `source: "pendant"` and changes nothing.

**Mode 1 — pendant in range (live).** Opus frames stream in, phone decodes, identical path. The phone's clock stamps the turn. This is the only mode that gets the fast lane.

**Mode 2 — pendant out of range (store-and-forward).** The XIAO isn't reliable for real-time streaming, and *that is the norm, not a failure*: Limitless stores 35 h on-device and background-syncs over BLE; Plaud stores 64 GB and syncs over a dedicated Wi-Fi link; Bee sends processed features, not raw audio. **Do not try to make BLE streaming reliable — design for backlog.**
- The pendant writes energy-gated Opus to flash with a per-frame offset from its own boot counter (RMS above a rolling floor + 8 dB for ≥120 ms opens; `hangover_ms = 4000` and `pre_roll_ms = 300`, Omi's shipped tuning; this alone removes ~79% of airtime).
- On connect, the phone writes a **BLE time-sync**: it records `(phone_wall_clock, pendant_boot_counter)` and never trusts the MCU's absolute clock. Backlog frames are then rewritten into the phone clock domain: `capture_started_at = sync_epoch + (frame_offset − sync_offset)`.
- Backlog decodes through the same `AudioRouter` **faster than realtime**, producing normal turn envelopes with `backfill: true`.

### The two rules that make Mode 2 work, and that Omi gets wrong
1. **Turns are placed into segments by `capture_started_at`, not arrival.** Backlog turns therefore reassemble the original conversation regardless of when the phone happened to reconnect. This is precisely the bug in Omi #6551 that would otherwise shatter one walk-outside conversation into N segments.
2. **`backfill: true` suppresses the fast lane.** A question the owner asked 40 minutes ago must not fire a browser job the instant the pendant reconnects. Backfilled turns route only through the segment-close path, and anything older than `LATE_MAX_S = 6h` is written to memory but never triaged.

Backfill that lands inside an already-closed segment marks it `dirty`; after `BACKFILL_SETTLE_S = 90` with no further inserts it re-triages once, cancelling and re-minting only jobs still sitting in `awaiting_confirm`.

### What the pendant explicitly does NOT do
No VAD model, no endpointing, no segmentation, no transcription. Energy gating and Opus only. Nothing in this space runs on a 64 MHz Cortex-M4F with 256 KB RAM that's already busy with Opus and a radio.

### Known pendant-only gap (name it, don't pretend it's solved)
Continuous ambient audio means the pendant hears background conversations that are not the wearer, and every commercial EOT model assumes a single near-field speaker. The only work that addresses this is arXiv:2603.13379 — primary-speaker segmentation *in front of* the endpointer, 1.14 M params, 36 ms median latency, 87.7% end-to-end recall vs Smart Turn v3's 58.9%. Until that exists in the app, the mitigations are: the read-only-goal restriction on the fast lane, the entity-overlap continuity prefilter (a stranger's topic won't overlap), and the confirmation gate that already holds everything consequential.

---

## MIGRATION — seven shippable steps

Seven steps. **Every step is independently shippable, reversible by an env var, and leaves the daily-testing path working.** No step changes both the phone and the server at once.

---

**STEP 1 — Segments exist, but change nothing (server only).**
- New `backend/pb_migrations/1700000004_segments.js`: collection `segments` (`owner`, `status: open|closed`, `started_at`, `last_speech_at`, `ended_at`, `turn_count`, `word_count`, `summary`, `entities`, `parent_segment`, `triaged_through_seq`, `dirty`, `supersedes`) plus additive fields on `events` (`capture_started_at`, `capture_ended_at`, `gap_before_ms`, `seq`, `boot_id`, `source`, `backfill`, `segment`). All nullable — old app builds keep posting exactly as they do now.
- New `brain/segmenter.py`: pure functions (`decide_link`, `should_flush`, `place_turn`) over plain dicts, plus a thin `SegmentStore` over PocketBase.
- `brain/worker.py`: after `anticipy.hear(line)`, additionally attach the event to a segment, using `created` as capture time when the new fields are absent. Append the turn envelope to a JSONL log.
- **Triage still runs per line, unchanged. Zero behavior change.**
- *Verify:* run a normal day. Segment boundaries in the log match where conversations actually started/stopped; decisions are byte-identical to before.

**STEP 2 — Real timestamps (iOS, additive).**
- `PhoneListener.swift`: add `struct Turn {text, startedAt, endedAt, gapBeforeMs, eot, seq}` and `onTurn`. Keep `onLine` as a shim so nothing else breaks. Track `lastSpeechEndAt` across `flushTail()` calls; derive `gapBeforeMs` from the existing `lastResultAt`/`silenceFlush` state — **no VAD yet**. Leave `utteranceGap = 2.6` alone.
- `AnticipyApp.swift`: `heard(_ line: String)` → `heard(_ turn: Turn)`; replace the in-memory `unsent: [String]` (which dies with the process — a real data-loss bug the pendant will expose) with a disk-backed `Audio/TurnQueue.swift`.
- `Backend/AnticipyBackend.swift`: `pushEvent` gains the timing fields.
- Server prefers `capture_*` when present, falls back to `created`.
- *Verify:* logged `gap_before_ms` matches a stopwatch on a deliberate 30 s pause; a force-quit mid-conversation loses no lines; an old TestFlight build still works.

**STEP 3 — Segment triage, in shadow (server, flag-gated).**
- `ANTICIPY_SEGMENT_TRIAGE = off | shadow | on` (default `off`, so a deploy is a no-op).
- `brain/anticipy_core.py`: add `hear_segment(segment)`; `hear(line)` becomes a thin wrapper so every existing test and `proof/` script keeps passing. Delete the `_prev` single-previous-line hack (`anticipy_core.py:145,199-202`) only when the flag flips — segments subsume it.
- `brain/orchestrator.py`: add `Brain.triage_segment(segment_text, thread_summary, new_from_seq)`. New prompt renders turns with timestamps and `[gap: 34s]` markers inline and marks post-cursor turns `[NEW]`, with the instruction that only `[NEW]` turns may generate work. `Brain.triage(line)` stays.
- In `shadow`, the segment decision is computed and logged but per-line decisions still drive everything.
- *Verify:* one day of shadow. Diff the two decision streams; specifically confirm the demo-day shape now carries its surrounding turns. Then flip to `on`.
- **On flip:** the worker marks member events `decision="segmented"` on attach (so the 2 s poll doesn't replay them), and PATCHes the real decision back onto member events when the segment triages — so `AnticipySession.refresh()` (`AnticipyApp.swift:151-168`) and the "act" haptic keep working with **no iOS change**.
- *Rollback:* set the flag to `shadow`.

**STEP 4 — Split the model tiers (server).**
- `brain/llm.py`: `LLM.for_job(job)` reading `ANTICIPY_GATE_MODEL` / `ANTICIPY_PLAN_MODEL` / `ANTICIPY_EXTRACT_MODEL`, all defaulting to today's `ANTICIPY_MODEL` so the default deploy is unchanged.
- `orchestrator.py`: add `Brain.gate(segment)` on the gate model, with the two free short-circuits (>120 words → auto-pass; <6 content words and no direct address → auto-fail).
- `memory.py`: `ingest_segment(text, started_ts, ended_ts, segment_id)`; add columns to `episodes` via idempotent `ALTER TABLE ... ADD COLUMN` (existing rows and existing recall keep working); add a `segment_entities` table for the free continuity prefilter.
- Then, and only then, raise `ANTICIPY_PLAN_MODEL`.
- *Verify:* cost per hour of speech drops even with the better planner; re-run `proof/run_e2e_scenarios.py` and the HARD-task set.

**STEP 5 — Real endpointing (iOS, flag-gated).**
- `Audio/VoiceActivity.swift` (Silero v6 CoreML) and `Audio/TurnEndpointer.swift` (Smart Turn v3 ONNX, CoreML EP) behind an `@AppStorage("useNeuralEndpointing")` flag, defaulting **off**. When off, the existing 2.6 s timer runs exactly as today.
- Flip on: VAD silence `0.2 s` → Smart Turn → merge `< 2.0 s` → turn. Write both boundary sets to the log for a day before trusting it.
- *Verify:* replay the day's audio-derived turn log through `proof/replay_segments.py` under both boundary sets; confirm no line loss and better-formed turns. *Rollback:* one toggle in Settings.

**STEP 6 — Thread linking (server).**
- Implement `decide_link` bands 3 and 4, `parent_segment` inheritance, `Brain.continuity` on the gate model.
- Add the **fast lane** (Trigger A) with the read-only-goal restriction, reusing `is_consequential()`.
- *Verify:* the 5-minute-gap case — leave the room mid-topic, return, resume. One thread, context carried. Count the escalations: it should be rare.

**STEP 7 — Pendant path.**
- `Audio/AudioRouter.swift`; wire `PendantManager.onOpusFrame` into it; BLE time-sync write on connect; `backfill: true` on replayed backlog; server-side late-turn insertion + `dirty` re-triage.
- Firmware: RMS energy gate with 300 ms pre-roll / 4000 ms hangover, flash buffering with boot-counter offsets.
- *Verify:* record a conversation with the phone in another room, walk back, confirm it reassembles as **one** thread and produces **zero** immediate job dispatches from stale questions.

**Ongoing (any time after step 1):** once ~2 weeks of turn logs exist, run `proof/gap_histogram.py` and replace `CONTINUE_S = 45` with the fitted GMM valley from the owner's own gap distribution.

---

## RISKS

**1. Latency regression on the ambient path.** `CONTINUE_S = 45` means a non-direct-address act can be up to 45 s + poll late, where today it fires within ~3 s. *Mitigations:* the fast lane (Trigger A) for anything addressed to Anticipy or shaped like an answerable question, and the 120-word / 90 s mid-segment flush. *Watch for:* the owner saying "she used to be quicker." If it bites, lower `FLUSH_SECONDS` before lowering `CONTINUE_S` — lowering `CONTINUE_S` reintroduces fragmentation.

**2. The fast lane acts on someone else's speech.** The pendant hears the whole room and no commercial EOT model handles a non-primary speaker. *Mitigations:* read-only goals only on the fast lane (`is_consequential()` already free); the existing confirmation gate holds everything else; entity-overlap prefilter. *Residual:* a stranger's read-only question can still spawn a browser research job. Acceptable (costs a page load), and the real fix — primary-speaker segmentation, arXiv:2603.13379 — is a later project, not a blocker.

**3. Double-acting on mid-segment flushes.** The same turn triaged twice mints two jobs and two texts — this exact failure happened live on 2026-07-30 (6 jobs from one line). *Mitigations:* `triaged_through_seq` cursor per segment, the `[NEW]`-only instruction in the prompt, and the existing claim-before-side-effects pattern in `worker.py:118`. *This is the single highest-risk mechanical change and step 3's shadow mode exists mainly to catch it.*

**4. Pendant clock skew / backlog reassembly.** If the phone trusts the MCU's absolute clock, or if arrival time leaks into any boundary decision, one walk outdoors shatters into N segments (Omi #6551 verbatim). *Mitigation:* BLE time-sync recording `(phone_wall_clock, pendant_boot_counter)` at connect and rewriting all offsets into the phone clock; a unit test that feeds out-of-order turns to `place_turn` and asserts one segment.

**5. Segment bloat.** A 30-minute meeting with no 45 s silence produces one enormous segment and unbounded prompts. *Mitigations:* `MAX_SEGMENT_S = 1800` force-close followed by an immediate relink (so context survives the split), `MAX_TURN_S = 45`, and a token cap on the rendered segment that keeps the most recent turns plus the thread summary.

**6. The gate silently swallows real intent.** A cheap model returning "not actionable" is now a hard stop where today every line at least reached triage. *Mitigations:* the free >120-word auto-pass; direct-address auto-pass; **log every gate rejection with its text** and review the rejections for the first week. *Watch for:* recall dropping on the HARD task set — that's the signature.

**7. Feed and haptics break in the app.** `AnticipySession.refresh()` reconciles per-line `decision` values and buzzes on `"act"`. If segment triage stops writing decisions onto member events, the feed shows "Thinking…" forever. *Mitigation:* the PATCH-back-to-member-events rule in step 3, verified before the flag flips.

**8. Smart Turn v3 on an A-series is slower than advertised.** Its 12 ms figure was measured on a server CPU, ONNX Runtime iOS has no dedicated ANE execution provider, and worst measured was 94.8 ms. *Mitigation:* it only runs during silence, so even 150 ms is invisible; the `eot_max_hold_s = 4.0` ceiling bounds the damage if it stalls; the flag in step 5 reverts to the timer.

**9. Parameter values are borrowed from stacks with a reply-latency budget Anticipy doesn't have.** Every published Pareto number is scored against "the agent must speak within 300–600 ms." Adopting their *operating points* would make Anticipy far too eager. *Mitigation:* the chosen values already sit at the conservative end (AssemblyAI's conservative preset, 800 ms min / 3600 ms max / 0.7, is the right neighborhood — not any stack's default); and `proof/gap_histogram.py` replaces the guesses with fitted values from the owner's own data. Halfaker's own caution applies: only trust the fit if the log₂-gap histogram actually shows a valley between 1 minute and 1 day.

**10. iOS 26 dependency creep.** `SpeechAnalyzer`/`SpeechDetector` is the right long-term target (built explicitly for long-form and distant audio, non-overlapping audio ranges, sample-accurate `.audioTimeRange`, free VAD, models in system storage), but adopting it now forces an iOS 26 floor. *Mitigation:* abstract transcription behind the existing `TranscriberClient` protocol in step 5 so it drops in later without touching the segmenter.

---
