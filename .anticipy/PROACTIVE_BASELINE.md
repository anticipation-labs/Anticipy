# PROACTIVE ENGINE BASELINE ASSESSMENT (read-only, test-only)

Date 2026-05-16. No file in engine/app/proactive/ or anywhere else
was modified. This is an assessment only.

## Step 1 — Inventory (what the code actually does + deps)

engine/app/proactive/ has 24 .py files. Two generations coexist: the
legacy 5-layer cascade (engine.py, interpreter.py, donna.py,
reversibility.py, urgency.py, speaker_id.py, dispatcher.py, notifier.py,
notes.py, context.py, decider.py, memory_extractor.py, donna_voice.py,
types.py) and the v-final-prototype "Pod A" cascade the user named. The
Pod A modules:

- __init__.py: re-exports both generations. Pod A imports (line 50-53):
  `from .demand_detection import DemandDecision, DemandDetector`,
  `from .hedge_filter import HedgeFilter, HedgeResult, MemoryWriteSpec`,
  `from .intent_extraction import IntentExtractor, IntentSlots, TypedIntent`,
  `from .pipeline import PipelineResult, PodAPipeline`. Docstring line 13:
  "Audio never enters this package — only diarized user-voice transcript
  chunks". Heavy ML deps documented as loaded lazily inside __init__.

- pipeline.py (PodAPipeline): orchestrator. Imports
  `from app.proactive.demand_detection import DemandDecision, DemandDetector`,
  `from app.proactive.hedge_filter import HedgeFilter, HedgeResult`,
  `from app.proactive.intent_extraction import IntentExtractor, TypedIntent`.
  Lazy: `from app.proactive.asr import get_asr` (in from_wav),
  `from supabase import create_client` (in _ensure_supabase). Does
  Stage 1 -> 1.5 -> 2 -> publish to Supabase anticipy_intents_v2. Its
  from_wav explicitly does NOT call VAD or diarization ("for fixture
  WAVs the whole clip is assumed to be the wearer").

- asr.py (ASR / get_asr): Parakeet TDT 0.6B v3.
  `from parakeet_mlx import from_pretrained` (lazy, inside __init__);
  top-level numpy via callers only. transcribe_file(path) for WAV;
  stream(Iterable[bytes]) for chunked PCM. Dep parakeet_mlx + mlx.

- vad.py (VAD / get_vad): Silero VAD. Top-level `import numpy as np`;
  inside __init__ `import torch`, `from silero_vad import load_silero_vad`.
  Provides filter(chunks). NOT called by pipeline.from_wav.

- diarization.py (Diarizer / get_diarizer): top-level
  `import numpy as np`; inside __init__
  `from pyannote.audio import Inference, Model`, `import torch`. Requires
  ~/.anticipy/wearer_voiceprint.npy (raises RuntimeError if missing).
  NOT called by pipeline.from_wav.

- demand_detection.py (Stage 1): `from app.proactive.llm_adapter import
  make_json_llm_call`. One LLM call, returns DemandDecision; fails open
  (actionable=True) on cascade failure.

- hedge_filter.py (Stage 1.5): `from app.proactive.llm_adapter import
  make_json_llm_call`. Default backend="cascade" (LLM). Loads few-shot
  from engine/data/synth/gold_standard.jsonl. backend="adapter" path
  (QLoRA at ~/.anticipy/adapters/hedge_filter_v1/) exists but is NOT
  default and NOT on the pipeline path.

- intent_extraction.py (Stage 2): `from app.proactive.hedge_filter
  import HedgeResult`, `from app.proactive.llm_adapter import
  make_json_llm_call`. One LLM call, returns TypedIntent.

- llm_adapter.py: `from app.models import CostTracker,
  DegradedResponse, llm_call_json_str, llm_call_text`. Routes the
  cascade through the engine's existing provider chain
  (Gemini -> Groq -> Mistral -> DeepSeek). Returns "" on full failure.

Dependency reachability (engine/.venv, literal check):
  parakeet_mlx: INSTALLED
  mlx:          INSTALLED
  torch:        INSTALLED
  silero_vad:   INSTALLED
  pyannote.audio: NOT IMPORTABLE -> ModuleNotFoundError: No module named 'pyannote'
  pyannote.core:  NOT IMPORTABLE -> ModuleNotFoundError: No module named 'pyannote'
  supabase:     INSTALLED
  numpy:        INSTALLED
gold_standard.jsonl: present, 17 rows. WAV fixtures: 17 .wav present.

## Step 2 — Entry and exit points (literal signatures)

Entry (engine/app/proactive/pipeline.py, class PodAPipeline):
  async def from_text(self, utterance: str, user_id: str,
      source: str = "typed", utterance_window: Optional[dict] = None,
      context_transcript: Optional[str] = None,
      context_memory: Optional[str] = None) -> PipelineResult
  async def from_wav(self, path: Path, user_id: str,
      source: str = "mac_mic") -> PipelineResult

Exit: PipelineResult (frozen dataclass) with field
  intent: Optional[TypedIntent]  (plus demand, hedge, published,
  memory_written, utterance, user_id).

Audio path: ONLY prerecorded WAV files via from_wav. There is NO live
microphone entry. pipeline.py docstring lines 14-15: "Streaming
(from_mic) is provided by the Mac app's audio harness, not here". No
from_mic method exists on PodAPipeline. asr.stream() and vad.filter()
accept Iterable[bytes] but no code anywhere captures microphone audio
and feeds them; the only references are docstring examples. The V4 Mac
app (desktop/) has zero audio code. The referenced "Mac app's audio
harness" does not exist in the repo.

## Step 3 — Dependency reality check (literal output)

  --- import app.proactive (full package __init__) ---
  app.proactive: IMPORTED OK
  --- import PodAPipeline + construct ---
  PodAPipeline: IMPORTED + CONSTRUCTED OK -> PodAPipeline
  --- import ASR class (parakeet) ---
  asr module import OK (model load is lazy, not triggered here)

(Two pre-existing config warnings printed first: "JWT_SECRET not set",
"PROFILE_ENCRYPTION_KEY not set" — dev-default warnings from app
config, not import errors.) The package imports cleanly despite
pyannote missing because pyannote is only used lazily inside
Diarizer.__init__, which the pipeline path never instantiates.

## Step 4 — Fixture test (literal, 5 runs, no rounding)

Command: `python tests/test_proactive_pipeline.py audio` (AUDIO mode =
full Parakeet ASR -> Stage 1/1.5/2 cascade against the 17 WAV
fixtures, real LLM calls). Test PASS_THRESHOLD = 14/17.

  run 1: 15/17  (passes_threshold true)
  run 2: 16/17  (passes_threshold true)
  run 3: 14/17  (passes_threshold true)
  run 4: 15/17  (passes_threshold true)
  run 5: 15/17  (passes_threshold true)

All 5 runs at or above the 14/17 floor; none below. ASR transcripts
in the per-item output were accurate (e.g. "I should probably text
Sarah back.", "I gotta remember to email John."). The recurring miss
is gs_04 "We should maybe grab dinner sometime" (expected
STORE_AS_LATENT, classified REFUSE in 4 of 5 runs; PASS in run 5) —
the borderline hedging/brainstorm case. The full audio-file pipeline
genuinely runs end-to-end and emits real, mostly-correct typed
classifications.

## Step 5 — Real audio test (live microphone)

NOT PERFORMED, because live microphone capture is not wired into the
pipeline at all. This is stated plainly, not substituted with a WAV.
Evidence: pipeline.py exposes only from_text and from_wav; no
from_mic; pipeline.py docstring defers streaming to a "Mac app's
audio harness" that does not exist in the repo; no mic-capture
library (sounddevice / pyaudio / wave / AVFoundation) is used
anywhere in engine/app or engine/scripts; the V4 Mac app has no
audio code. asr.stream(Iterable[bytes]) and VAD().filter() are
capable streaming primitives but nothing produces live frames for
them.

What wiring a live mic would require (for the report only, not done):
1. A capture source producing 16 kHz mono int16 PCM in ~512-sample
   (32 ms) frames (Python sounddevice InputStream, or the Tauri/Swift
   side via AVFoundation), plus the macOS microphone TCC permission
   grant (one-time OS dialog).
2. Feed frames through the EXISTING primitives:
   VAD().filter(frames) -> ASR().stream(speech_frames) to get live
   TranscriptSegments.
3. A new PodAPipeline.from_mic orchestrator that buffers finalized
   segments into an utterance window and calls from_text (the
   Stage 1 -> 1.5 -> 2 path) — mirroring what from_wav already does
   after ASR.
The building blocks (VAD.filter, ASR.stream, from_text) exist; the
capture source and the from_mic glue do not.

## Step 6 — VERDICT

(b) FIXABLE SCAFFOLDING.

Why this and not (a): the user's definition of the proactive engine
is "take microphone audio and emit a typed Intent." There is no
microphone path anywhere — only prerecorded-WAV input. The
wearer-vs-others diarization gate (the component that decides which
speaker fires the cascade) is non-functional: pyannote.audio is not
installed and no wearer voiceprint exists, and pipeline.from_wav
bypasses diarization entirely. So it is not safe to call this
"produces sane Intents from real [live] audio, safe to build on".

Why this and not (c): the core cascade demonstrably works end to end
on real file audio. Five consecutive AUDIO-mode runs scored
15/16/14/15/15 of 17, every run at or above the project's own 14/17
floor, with accurate Parakeet transcription and real Stage 1/1.5/2
typed classifications. The structure is sound and the hard part (the
LLM cascade + ASR) genuinely runs. That is not "scrap and rebuild".

The structure exists and the cascade works on prerecorded audio;
specific named things are missing/broken, with an exact repair path:

1. No live-microphone capture exists. Repair: add a 16 kHz mono
   int16 capture source + a PodAPipeline.from_mic that feeds
   VAD().filter -> ASR().stream -> from_text. Building blocks already
   present.
2. pyannote.audio not installed + no ~/.anticipy/wearer_voiceprint.npy.
   Repair: `uv pip install 'pyannote.audio>=3.3'`, run
   engine/scripts/enroll_wearer.py, and route from_wav/from_mic
   through Diarizer so only wearer segments fire (currently bypassed).
3. Accuracy sits in the 14-16/17 band (borderline hedging cases like
   gs_04). Repair path already designed in-code: the hedge_filter
   backend="adapter" QLoRA path (~/.anticipy/adapters/hedge_filter_v1/),
   not yet trained/present; the cascade backend is the working
   stopgap and clears the 14/17 floor.

None of these is an architecture flaw; each is a named, scoped,
buildable gap. Verdict: (b) FIXABLE SCAFFOLDING.

Decision to keep / fix / scrap is Omar's. No repair started. Stop.
