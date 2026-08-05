"""OMAR'S OWN TEST — the whole speaker-recognition loop, on your Mac, local.

Everything here runs on this machine: voice separation, owner matching,
transcription. No audio ever leaves your Mac. The only network call is the
final (optional) step, where each tagged line is run through Anticipy's
real triage so you can watch the DECISION change with the voice.

How to test it like a human:

  1) Enroll yourself (10 seconds, read anything):
       python3 proof/speaker_live_test.py enroll
  2) Record a conversation — talk, and have a friend (or a video, or your
     own Wispr-style dictation) say some lines too:
       python3 proof/speaker_live_test.py listen 30
  3) Watch. For every utterance you get:
       [OWNER 0.87] "let's do dinner tomorrow at seven"   -> act ...
       [OTHER 0.31] "yeah I'll book it, my treat"         -> ignore (their promise)

  No mic handy? Same loop over any 16k mono wav:
       python3 proof/speaker_live_test.py wav conversation.wav

Models (~150MB once, local forever) are fetched by:
       python3 proof/speaker_live_test.py setup

This is the demo of brief 09 before the iPhone build exists: the iPhone
will do exactly this per line and send ONLY the one word (owner/other)
with the transcript.
"""
from __future__ import annotations

import os
import sys
import time
import wave

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
MODELS = os.path.join(HERE, "..", ".speaker-models")
SEG_DIR = os.path.join(MODELS, "sherpa-onnx-pyannote-segmentation-3-0")
EMB = os.path.join(MODELS, "emb.onnx")
WHISPER = os.path.join(MODELS, "sherpa-onnx-whisper-tiny.en")
PROFILE = os.path.join(MODELS, "owner_profile.npy")
OWNER_THRESHOLD = 0.60

URLS = {
    "seg.tar.bz2": ("https://github.com/k2-fsa/sherpa-onnx/releases/download/"
                    "speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2"),
    "emb.onnx": ("https://github.com/k2-fsa/sherpa-onnx/releases/download/"
                 "speaker-recongition-models/3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx"),
    "whisper.tar.bz2": ("https://github.com/k2-fsa/sherpa-onnx/releases/download/"
                        "asr-models/sherpa-onnx-whisper-tiny.en.tar.bz2"),
}


def setup() -> None:
    import subprocess
    os.makedirs(MODELS, exist_ok=True)
    for name, url in URLS.items():
        dest = os.path.join(MODELS, name)
        if name == "emb.onnx" and os.path.exists(EMB):
            continue
        if name != "emb.onnx" and os.path.exists(dest.replace(".tar.bz2", "")):
            continue
        print(f"fetching {name} …")
        subprocess.run(["curl", "-sL", "-o", dest, url], check=True)
        if name.endswith(".tar.bz2"):
            subprocess.run(["tar", "xf", dest, "-C", MODELS], check=True)
    print("models ready.")


def _sherpa():
    import sherpa_onnx
    return sherpa_onnx


def record(seconds: float) -> np.ndarray:
    import sounddevice as sd
    print(f"recording {seconds:.0f}s — speak…")
    audio = sd.rec(int(seconds * 16000), samplerate=16000, channels=1,
                   dtype="float32")
    sd.wait()
    return audio.reshape(-1)


def load_wav(path: str) -> np.ndarray:
    w = wave.open(path, "rb")
    assert w.getframerate() == 16000 and w.getnchannels() == 1, "need 16k mono"
    return (np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
            .astype(np.float32) / 32768.0)


def _embedder():
    so = _sherpa()
    return so.SpeakerEmbeddingExtractor(
        so.SpeakerEmbeddingExtractorConfig(model=EMB))


def embed(ex, samples: np.ndarray) -> np.ndarray:
    st = ex.create_stream()
    st.accept_waveform(16000, samples)
    st.input_finished()
    return np.array(ex.compute(st))


def cos(a, b) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


def enroll() -> None:
    samples = record(10)
    ex = _embedder()
    np.save(PROFILE, embed(ex, samples))
    print(f"enrolled. profile stored locally at {PROFILE} — the raw audio "
          f"was not kept.")


def _recognizer():
    so = _sherpa()
    return so.OfflineRecognizer.from_whisper(
        encoder=os.path.join(WHISPER, "tiny.en-encoder.int8.onnx"),
        decoder=os.path.join(WHISPER, "tiny.en-decoder.int8.onnx"),
        tokens=os.path.join(WHISPER, "tiny.en-tokens.txt"))


def run_pipeline(samples: np.ndarray, brain: bool) -> None:
    so = _sherpa()
    if not os.path.exists(PROFILE):
        print("no owner profile — run `enroll` first")
        sys.exit(1)
    owner = np.load(PROFILE)
    sd_ = so.OfflineSpeakerDiarization(so.OfflineSpeakerDiarizationConfig(
        segmentation=so.OfflineSpeakerSegmentationModelConfig(
            pyannote=so.OfflineSpeakerSegmentationPyannoteModelConfig(
                model=os.path.join(SEG_DIR, "model.onnx"))),
        embedding=so.SpeakerEmbeddingExtractorConfig(model=EMB),
        clustering=so.FastClusteringConfig(num_clusters=-1, threshold=0.5),
        min_duration_on=0.3, min_duration_off=0.5))
    ex = _embedder()
    rec = _recognizer()

    t0 = time.time()
    segments = sd_.process(samples).sort_by_start_time()
    print(f"diarized {len(samples)/16000:.1f}s in {time.time()-t0:.1f}s "
          f"(local). segments: {len(segments)}")

    anticipy = None
    if brain:
        from brain.anticipy_core import Anticipy
        from brain.llm import LLM
        from brain.memory import Memory
        llm = LLM()
        if llm.live:
            anticipy = Anticipy(memory=Memory(llm=llm), llm=llm,
                                owner_id="live-test")
            anticipy._queue_job = lambda g, p, hold=False, explicit=False: "job"
            anticipy._pending_jobs = lambda: []
            anticipy.notify_owner = lambda m, channel="sms": {"ok": True}
        else:
            print("(no OPENROUTER_API_KEY — showing tags without decisions)")

    for seg in segments:
        chunk = samples[int(seg.start * 16000):int(seg.end * 16000)]
        score = cos(owner, embed(ex, chunk))
        tag = "owner" if score >= OWNER_THRESHOLD else "other"
        st = rec.create_stream()
        st.accept_waveform(16000, chunk)
        rec.decode_stream(st)
        text = st.result.text.strip()
        label = f"[{tag.upper()} {score:.2f}]"
        if not text:
            print(f"{label} (unintelligible segment {seg.start:.1f}-{seg.end:.1f}s)")
            continue
        line = f"{label} \"{text}\""
        if anticipy:
            out = anticipy.hear(text, speaker=tag)
            d = out["decision"]
            line += f"\n        -> {d.decision}" + (f" ({d.goal})" if d.goal else "")
        print(line)


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    if cmd == "setup":
        setup()
    elif cmd == "enroll":
        setup()
        enroll()
    elif cmd == "listen":
        seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 30
        run_pipeline(record(seconds), brain=True)
    elif cmd == "wav":
        sys.path.insert(0, os.path.dirname(HERE))
        run_pipeline(load_wav(sys.argv[2]), brain=True)
    else:
        print(__doc__)


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(HERE))
    main()
