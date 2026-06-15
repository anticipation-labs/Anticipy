"""MacMicSource — REAL always-on microphone capture for this engine.

It records the Mac microphone in rolling windows with ffmpeg (avfoundation — no extra Python
dependency; ffmpeg is already required for the MP3 path), transcribes each window locally with
the same Whisper transcriber the upload path uses (``capture/transcribe.py``), and emits the
heard text through the capture sink — which the engine feeds straight into the proactive brain.

Always-on: ``start()`` launches a daemon loop; ``stop()`` ends it. Words only — it never acts
itself; it just hands what it heard to the engine, which decides act/ask/silent. Device + window
are env-configurable (``ANTICIPY_MIC_DEVICE`` index, ``ANTICIPY_MIC_WINDOW_SECONDS``). Whisper
on silence tends to hallucinate stock phrases ("you", "thank you", "thanks for watching"); those
are filtered so a quiet room never fabricates a task.

``emit_stub`` is kept so tests can inject a fake utterance without real audio.
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from .base import CaptureSource
from .transcribe import transcribe_audio
from ..shared.schema import CaptureEvent

_TS = re.compile(r"^\s*\[?\d{1,2}:\d{2}:\d{2}(?:-\d{1,2}:\d{2}:\d{2})?\]?\s*")
# stock things Whisper emits on (near-)silence — never a real utterance worth acting on
_NOISE = {
    "you", "thank you", "thanks for watching", "bye", "so", "okay", "ok", "um", "uh",
    "silence", "music", "applause",
}


def _clean_line(line: str) -> str:
    return _TS.sub("", line).strip()


def _is_noise(text: str) -> bool:
    t = text.strip().lower().strip(" .!?♪[]")
    return (len(t) < 4) or (t in _NOISE)


class MacMicSource(CaptureSource):
    name = "mac_mic"

    def __init__(self, sink, *, device: str | None = None, window_seconds: float | None = None) -> None:
        super().__init__(sink)
        self._running = False
        self._thread: threading.Thread | None = None
        self._device = str(device if device is not None else os.environ.get("ANTICIPY_MIC_DEVICE", "2"))
        self._window = float(window_seconds if window_seconds is not None
                             else os.environ.get("ANTICIPY_MIC_WINDOW_SECONDS", "8"))
        self.last_error: str | None = None
        self.windows = 0
        self.utterances = 0

    # ---- lifecycle ----
    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="anticipy-mac-mic", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    def emit_stub(self, text: str) -> CaptureEvent:
        """Inject a fake utterance as if the mic heard it (used by tests; no real audio)."""
        return self._emit(text)

    # ---- the always-on loop ----
    def _loop(self) -> None:
        while self._running:
            wav = None
            try:
                wav = self._record_window()
                if wav is None:
                    continue
                self.windows += 1
                transcript = transcribe_audio(Path(wav))
                text = " ".join(_clean_line(l) for l in transcript.lines if _clean_line(l)).strip()
                if text and not _is_noise(text):
                    self.utterances += 1
                    self._emit(text)   # -> sink -> the engine's proactive brain
            except Exception as exc:  # the loop must outlive any one bad window
                self.last_error = f"{type(exc).__name__}: {exc}"
                time.sleep(0.5)
            finally:
                if wav:
                    self._safe_unlink(wav)

    def _record_window(self) -> str | None:
        """Capture one rolling window of mic audio to a temp wav (mono 16k for Whisper)."""
        fd, path = tempfile.mkstemp(suffix=".wav", prefix="anticipy-mic-")
        os.close(fd)
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-f", "avfoundation", "-i", f":{self._device}",
            "-t", str(self._window), "-ac", "1", "-ar", "16000", "-y", path,
        ]
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=self._window + 15)
        except Exception as exc:
            self.last_error = f"record: {type(exc).__name__}: {exc}"
            self._safe_unlink(path)
            return None
        if r.returncode != 0 or not os.path.exists(path) or os.path.getsize(path) == 0:
            self.last_error = (r.stderr.decode("utf-8", "replace")[-160:] if r.stderr else "empty recording")
            self._safe_unlink(path)
            return None
        return path

    @staticmethod
    def _safe_unlink(path: str) -> None:
        try:
            os.unlink(path)
        except OSError:
            pass
