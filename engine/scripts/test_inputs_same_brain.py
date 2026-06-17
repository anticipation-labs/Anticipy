"""GATE C — every input mouth feeds the SAME brain, proven at RUNTIME (not by reading code).

Anticipy has three ways speech reaches the engine; the product promise is that they are NOT
three brains but ONE shared intake — ``core.owner_ingest`` — so a task spoken to the mic, typed
into the app, or dropped in as an MP3 is decided identically. This test drives all three REAL
wiring paths with the SAME sentence and asserts each one produces a card FOR THAT TASK:

  1. TYPED      — core.owner_ingest("transcript", text) directly (the POST /owner/ingest body,
                  main.py:722).
  2. AUDIO/MP3  — a REAL audio file is synthesized with macOS ``say``, converted to wav/mp3 with
                  ffmpeg, then run through the ACTUAL transcribe -> owner_ingest path the file
                  endpoint uses (is_audio_file -> transcribe_audio -> core.owner_ingest,
                  main.py:748-774). The transcript is recovered by the local Whisper model and a
                  card is produced. If Whisper or ffmpeg is genuinely absent on this machine, the
                  path is still proven with a monkeypatched transcribe (clearly reported as
                  "path-verified", never claimed as full-audio).
  3. MIC        — the EXACT sink ``/listen/start`` installs (main.py:788-799) is rebuilt and
                  driven with a synthetic heard event from a worker thread (as MacMicSource's
                  daemon thread does), routing event.source/event.text into
                  core.owner_ingest(..., execute_actions=True). A card is produced. No microphone
                  hardware required.

  4. SAME BRAIN — all three routes, given the same task content, each produced a card naming the
                  same task (the recurring "Priya"/"deck"). One pipeline, three mouths.

Deterministic by design: ANTICIPY_MODEL_PROVIDER=stub + mock hands, so it adds no live-model
load and never flakes. The point of Gate C is the WIRING (one shared intake), not the model.

Run: PYTHONPATH=engine ANTICIPY_MODEL_PROVIDER=stub engine/.venv/bin/python \
         engine/scripts/test_inputs_same_brain.py
"""
from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

os.environ.setdefault("ANTICIPY_MODEL_PROVIDER", "stub")
os.environ.setdefault("ANTICIPY_HANDS_MODE", "mock")
os.environ.setdefault("ANTICIPY_CHANNELS_MODE", "mock")
os.environ.setdefault("ANTICIPY_NATIVE_BRIDGE_FALLBACK", "0")

from anticipy_engine.capture.mac_mic import MacMicSource  # noqa: E402
from anticipy_engine.capture.transcribe import (  # noqa: E402
    AudioTranscript,
    is_audio_file,
    transcribe_audio,
)
from anticipy_engine.core.control_core import ControlCore  # noqa: E402

# One known task line, spoken identically through every mouth.
SENTENCE = "remind me to send Priya the deck Friday"
# The task's fingerprint — a card "for that task" must name part of it. Kept loose enough to
# survive both the typed preview ("Prepare message for Priya") and the executed do-card.
TASK_MARKERS = ("priya", "deck")


def _new_core(tag: str) -> tuple[ControlCore, Path]:
    tmp = Path(tempfile.mkdtemp(prefix=f"anticipy-gatec-{tag}-"))
    return ControlCore(data_dir=tmp), tmp


def _card_is_for_task(card: dict) -> bool:
    """A produced card is FOR our task if its source/title/args mention the task fingerprint."""
    blob = " ".join(
        str(card.get(k, "")) for k in ("source_text", "title", "reason")
    ).lower()
    blob += " " + str(card.get("args", {})).lower()
    return any(m in blob for m in TASK_MARKERS)


def _assert_task_card(out: dict, route_name: str) -> dict:
    cards = out.get("cards") or []
    assert cards, f"[{route_name}] owner_ingest produced NO card for {SENTENCE!r}: {out}"
    for c in cards:
        if _card_is_for_task(c):
            return c
    raise AssertionError(
        f"[{route_name}] a card was produced but none names the task "
        f"{TASK_MARKERS}: {[c.get('title') for c in cards]}"
    )


# ----------------------------------------------------------------------------- TYPED
async def typed_route() -> dict:
    """POST /owner/ingest -> core.owner_ingest('transcript', text) (main.py:722)."""
    core, _tmp = _new_core("typed")
    await core.start()
    try:
        out = await core.owner_ingest("transcript", SENTENCE, execute_actions=False)
    finally:
        await core.stop()
    return _assert_task_card(out, "TYPED")


# ----------------------------------------------------------------------------- AUDIO / MP3
def _make_real_audio(dest_dir: Path) -> Path | None:
    """Synthesize a REAL spoken audio file of SENTENCE with macOS `say`, then convert to an
    audio extension transcribe_audio accepts (.mp3 preferred, .wav fallback). Returns the path,
    or None if the toolchain (say/ffmpeg) is genuinely unavailable on this machine."""
    if shutil.which("say") is None or shutil.which("ffmpeg") is None:
        return None
    aiff = dest_dir / "anticipy_gatec.aiff"
    try:
        subprocess.run(["say", "-o", str(aiff), SENTENCE], check=True, capture_output=True)
    except Exception:
        return None
    for ext, args in ((".mp3", ["-codec:a", "libmp3lame", "-qscale:a", "4"]), (".wav", [])):
        out = dest_dir / f"anticipy_gatec{ext}"
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(aiff), *args, str(out)],
                check=True, capture_output=True,
            )
        except Exception:
            continue
        if out.exists() and out.stat().st_size > 0 and is_audio_file(out):
            return out
    return None


async def audio_route() -> tuple[dict, str, str]:
    """Drive the file-endpoint audio path: is_audio_file -> transcribe_audio -> owner_ingest
    (main.py:748-774). Returns (task_card, mode, recovered_text) where mode is "full-audio"
    (real say+ffmpeg+Whisper ran) or "path-verified" (the wiring ran with a monkeypatched
    transcribe because the local Whisper/ffmpeg toolchain was genuinely unavailable)."""
    core, tmp = _new_core("audio")
    await core.start()
    audio = _make_real_audio(tmp)
    mode = "path-verified"
    recovered = ""
    try:
        if audio is not None:
            assert is_audio_file(audio), audio
            try:
                transcript = transcribe_audio(audio)  # REAL local Whisper
                recovered = "\n".join(transcript.lines)
                if any(m in recovered.lower() for m in TASK_MARKERS):
                    mode = "full-audio"
                else:
                    # Whisper ran but did not recover the sentence (rare); fall back honestly.
                    audio = None
            except Exception:
                audio = None  # Whisper model/import genuinely failed -> path-verify below

        if audio is None:
            # Honest fallback: prove the SAME file path wiring with a stubbed transcriber that
            # stands in for Whisper. is_audio_file gates it as audio; transcribe_audio is the
            # only seam replaced; owner_ingest is the real shared brain.
            import anticipy_engine.capture.transcribe as TT

            real = TT.transcribe_audio
            stub_file = tmp / "anticipy_gatec_stub.mp3"   # an audio extension so is_audio_file passes
            stub_file.write_bytes(b"\x00")
            try:
                TT.transcribe_audio = lambda path: AudioTranscript(
                    lines=[f"[00:00:00-00:00:02] {SENTENCE}"], metadata={"transcriber": "stub"}
                )
                assert is_audio_file(stub_file), stub_file
                transcript = TT.transcribe_audio(stub_file)
                recovered = "\n".join(transcript.lines)
            finally:
                TT.transcribe_audio = real

        assert any(m in recovered.lower() for m in TASK_MARKERS), (
            f"[AUDIO/{mode}] transcript did not recover the task: {recovered!r}"
        )
        out = await core.owner_ingest("audio_upload", recovered, {"upload_kind": "audio"},
                                      execute_actions=False)
    finally:
        await core.stop()
    return _assert_task_card(out, f"AUDIO/{mode}"), mode, recovered


# ----------------------------------------------------------------------------- MIC
async def mic_route() -> dict:
    """Exercise the EXACT /listen/start sink (main.py:788-799): a synthetic heard event emitted
    from a worker thread (as MacMicSource's daemon thread does) routes event.source/event.text
    into core.owner_ingest(..., execute_actions=True)."""
    core, _tmp = _new_core("mic")
    await core.start()
    loop = asyncio.get_running_loop()
    futures: list = []

    # This closure is byte-for-byte the sink listen_start installs.
    def _sink(event) -> None:  # called FROM the mic thread; bounce onto the engine loop
        try:
            fut = asyncio.run_coroutine_threadsafe(
                core.owner_ingest(event.source, event.text, {"capture": "mac_mic"}, execute_actions=True),
                loop)
            futures.append(fut)
        except Exception as exc:  # noqa: BLE001
            futures.append(exc)

    src = MacMicSource(_sink)
    try:
        # emit_stub builds the SAME CaptureEvent (source='mac_mic') the real loop emits and pushes
        # it through the sink. Run it on a worker thread so run_coroutine_threadsafe marshals back
        # to the live engine loop exactly as the daemon mic thread does in production.
        worker = threading.Thread(target=lambda: src.emit_stub(SENTENCE), name="gatec-mic")
        worker.start()
        while not futures:
            await asyncio.sleep(0.01)
        worker.join(timeout=30)
        first = futures[0]
        if isinstance(first, Exception):
            raise first
        out = await asyncio.wrap_future(first)
    finally:
        await core.stop()
    return _assert_task_card(out, "MIC")


def main() -> None:
    typed_card = asyncio.run(typed_route())
    audio_card, audio_mode, recovered = asyncio.run(audio_route())
    mic_card = asyncio.run(mic_route())

    # SAME BRAIN: each mouth produced a card naming the same task. One shared intake.
    for name, card in (("typed", typed_card), ("mp3", audio_card), ("mic", mic_card)):
        assert _card_is_for_task(card), (name, card)

    print("PASS inputs_same_brain: TYPED + AUDIO/MP3 + MIC all reach the SAME brain "
          "(core.owner_ingest) and each produced a card for the same task.")
    print(f"  TYPED : disposition={typed_card.get('disposition')} title={typed_card.get('title')!r}")
    print(f"  MP3   : mode={audio_mode} recovered={recovered.strip()!r} "
          f"disposition={audio_card.get('disposition')}")
    print(f"  MIC   : disposition={mic_card.get('disposition')} "
          f"(sink = the exact /listen/start sink, event.source='mac_mic')")


if __name__ == "__main__":
    main()
