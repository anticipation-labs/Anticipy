# Brief 09 — Local speaker recognition (roadmap §7.2, promoted to NOW)

## STATUS 2026-08-05: brain + backend halves SHIPPED and live-proven.
Done: events.speaker migration deployed; hear(speaker=…) → "(Voice check)"
triage context with the measured-evidence rule; honesty-wall fallback
(5 unit tests); proof/speaker_gate_proof.py 4/4 live (the friend's "I'll
get into it" never reaches Omar's desk, his own voice starts real work);
proof/speaker_live_test.py — the fully-local human test (enroll on the Mac
mic → record a conversation → diarize + owner-match + whisper-transcribe
on-device → live triage per tagged line) ran end-to-end: owner 0.99/0.92,
friend 0.23, and only the owner's "I will book the table right now"
became an act. REMAINING (this brief's open scope): the iOS half —
enrollment UX + on-device tagging in the app via sherpa-onnx's iOS
support, stamping `speaker` on transcript events. Sections below are the
build order for exactly that.

Omar, 2026-08-05: *"We want local everything… solve the speaker recognition
part, because that can affect how we see everything as a whole."*

He is right that it is the keystone: tonight's live test showed the two
misses that no amount of triage cleverness can fix — *"can you look into
flights… I'll get into it"* (WHO committed? without knowing who spoke, the
brain cannot tell his promise from his friend's) and every addressee
classification currently rests on wording alone.

## Already PROVEN (do not re-litigate the approach)

`proof/local_diarization_poc.py`, run on the Mac 2026-08-05, zero cloud:
- Diarization: 22.7s two-voice conversation → 2 speakers, boundaries within
  ~0.4s, same voice re-identified across an interruption, **3.8x realtime
  on CPU**. iPhone with quantization will be faster.
- Voice profile: enroll on ~9s of speech; owner-vs-owner **0.923**,
  owner-vs-stranger **0.236**. Threshold 0.6 has an ocean on each side.
- Stack: sherpa-onnx (has iOS/Swift support) + pyannote-segmentation-3.0
  (~7MB) + an embedding model (~40MB, quantizable). All on-device.

## Architecture (the tag travels, the voice never does)

1. **Enrollment (day zero + Settings)**: she asks him to read two sentences;
   the 512-dim owner embedding is computed on-device and stored on-device
   (Keychain/App Support). The raw audio is discarded. NOTHING voice-shaped
   ever leaves the phone — only a word.
2. **Live tagging (phone mic today, pendant audio tomorrow — same code
   path, the pendant only captures and streams to the phone)**: per
   utterance, compute the embedding of the segment that produced the
   transcript line; compare to the owner profile and to a rolling in-memory
   set of session speakers. Emit ONE tag per line:
   `speaker: "owner" | "other" | "unknown"` (unknown = too short/noisy to
   call — the brain must treat missing/unknown as today's behaviour, the
   honesty-wall pattern from the addressee work).
3. **Transport**: new optional `speaker` field on transcript events (PB
   migration, additive). Old app builds simply never set it.
4. **Brain**: worker passes `(Speaker: the owner himself | someone else |
   unknown)` into triage exactly like the addressee stickiness rides along.
   Triage rules gain ONE line: a commitment voiced by someone who is NOT
   the owner is never the owner's commitment ("I'll get into it" from the
   friend ≠ Omar's promise) — evidence, not vibes. The deterministic
   honesty wall stays: no tag → behaviour unchanged.

## Definition of done
- Enrollment flow in onboarding + Settings (re-enroll), premium feel, her
  voice asking — no developer-speak.
- Tags stamped on live phone-mic transcript lines end-to-end in production.
- Triage provably uses them: replay tonight's Paris-flights transcript with
  speaker tags → the friend's "I'll get into it" stays ambient; Omar's own
  identical words become his commitment.
- The 0.6 threshold + models benchmarked with the PoC script ON REAL
  RECORDINGS of Omar (not just `say` voices) before shipping; record the
  numbers in this file.
- Offline tests for: tag plumbed, unknown-tag fallback, non-owner
  commitment suppression, owner match across a session.
- No regression: dinner_demo_proof + second_scenario_proof stay green
  (they carry no tags — the fallback path IS their test).

## Scope limits
- iOS work stays in the app target; no server-side audio processing —
  "local everything" is the point.
- Do NOT block transcription on tagging: tag asynchronously and PATCH the
  event if needed; hearing must never wait on an embedding.
- Battery: batch embeddings per utterance (not per buffer); measure.
