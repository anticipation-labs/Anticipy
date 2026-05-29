"""Trivia delivery: TTS plus an in-memory recent-fires queue.

Two surfaces:

1. macOS TTS via ``/usr/bin/say``. Fires in a background thread so the
   trigger pipeline never blocks on the audio device. The brief calls
   out the Mac TTS as the demo surface; the BLE / APNs surfaces from
   the planning doc are out of scope for this commit.

2. ``recent_fires()`` returns the last N (default 10) fires. The
   popover polls ``GET /api/trivia/recent`` for this list. Each fire
   includes the raw utterance, the answer, the source, latencies, and
   a UTC timestamp.

The TTS process is forked and we do not wait on it. macOS's ``say``
buffers the entire phrase before emitting audio, so we measure
"speech-ready latency" as the time from call to subprocess spawn,
which is what the user perceives as the answer arriving. The actual
audio plays asynchronously.

Disabled by ``ANTICIPY_TRIVIA_DISABLE_TTS=1`` for headless test
environments. The recent-fires log still records the event.
"""

from __future__ import annotations

import collections
import os
import shutil
import subprocess
import sys
import threading
import time
from typing import Any, Optional


_RECENT_MAX = int(os.environ.get("ANTICIPY_TRIVIA_RECENT_MAX", "32"))
_RECENT: collections.deque = collections.deque(maxlen=_RECENT_MAX)
_RECENT_LOCK = threading.Lock()
_TTS_LOCK = threading.Lock()
_TTS_PROC: list[subprocess.Popen] = []  # active processes; we cancel
                                        # earlier ones if a new fire
                                        # arrives.


def _say_path() -> Optional[str]:
    """Locate macOS ``say``. Falls back to None on non-Darwin."""
    if sys.platform != "darwin":
        return None
    return shutil.which("say") or "/usr/bin/say"


def _spawn_say(text: str, *, voice: Optional[str] = None,
               rate: Optional[int] = None) -> dict:
    """Fire ``say`` in the background. Returns spawn metadata.

    On non-Mac (or when ``ANTICIPY_TRIVIA_DISABLE_TTS=1``) this returns
    ``{"spawned": False, "reason": "..."}`` so callers can degrade
    gracefully without raising.
    """
    if os.environ.get("ANTICIPY_TRIVIA_DISABLE_TTS", "").strip() == "1":
        return {"spawned": False, "reason": "tts_disabled_env"}
    say_bin = _say_path()
    if not say_bin or not os.path.exists(say_bin):
        return {"spawned": False, "reason": "say_unavailable"}
    args = [say_bin]
    if voice:
        args.extend(["-v", str(voice)])
    if rate:
        args.extend(["-r", str(int(rate))])
    args.append(text)
    t0 = time.monotonic()
    try:
        with _TTS_LOCK:
            # Kill any earlier still-running say. The previous answer
            # should not bleed into the new one mid-sentence.
            still_alive = []
            for p in _TTS_PROC:
                if p.poll() is None:
                    try:
                        p.terminate()
                    except Exception:
                        pass
                    still_alive.append(p)
            for p in still_alive:
                try:
                    p.wait(timeout=0.2)
                except Exception:
                    pass
            _TTS_PROC.clear()
            proc = subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
            )
            _TTS_PROC.append(proc)
    except Exception as exc:
        return {
            "spawned": False,
            "reason": f"{type(exc).__name__}: {exc}",
        }
    return {
        "spawned": True,
        "pid": int(proc.pid),
        "spawn_ms": round((time.monotonic() - t0) * 1000.0, 2),
        "bin": say_bin,
    }


def deliver(utterance: str, answer_payload: dict,
            *,
            trigger_result: Optional[dict] = None,
            voice: Optional[str] = None,
            rate: Optional[int] = None,
            received_at: Optional[float] = None) -> dict:
    """Speak the answer (via ``say``) and append a recent-fires entry.

    Returns a dict describing the delivery: tts spawn metadata, total
    latency from ``received_at`` to spawn (or now), and the queued
    fire entry. Safe in any environment; falls back cleanly when TTS
    is unavailable.
    """
    text = ""
    if isinstance(answer_payload, dict):
        text = str(answer_payload.get("answer") or "")
    if not text:
        text = "I do not know that one."
    tts = _spawn_say(text, voice=voice, rate=rate)
    now = time.time()
    rcv = float(received_at if received_at is not None else now)
    total_ms = round(max(0.0, (now - rcv) * 1000.0), 2)
    entry: dict[str, Any] = {
        "ts": now,
        "ts_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "utterance": utterance,
        "answer": text,
        "source": str(answer_payload.get("source") or "") if isinstance(
            answer_payload, dict) else "",
        "lane": str(answer_payload.get("lane") or "") if isinstance(
            answer_payload, dict) else "",
        "topic": str(answer_payload.get("topic") or "") if isinstance(
            answer_payload, dict) else "",
        "score": answer_payload.get("score") if isinstance(
            answer_payload, dict) else None,
        "answer_ms": answer_payload.get("elapsed_ms") if isinstance(
            answer_payload, dict) else None,
        "trigger": trigger_result,
        "tts": tts,
        "total_latency_ms": total_ms,
    }
    with _RECENT_LOCK:
        _RECENT.appendleft(entry)
    return entry


def recent_fires(limit: int = 10) -> list[dict]:
    """Return the most recent ``limit`` fires, newest first."""
    if limit <= 0:
        return []
    with _RECENT_LOCK:
        rows = list(_RECENT)
    return rows[:limit]


def clear_recent() -> int:
    """Test helper: drop the recent-fires queue. Returns prior length."""
    with _RECENT_LOCK:
        n = len(_RECENT)
        _RECENT.clear()
    return n


__all__ = ["clear_recent", "deliver", "recent_fires"]
