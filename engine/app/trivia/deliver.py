"""Trivia delivery: TTS plus an in-memory recent-fires queue.

Two surfaces:

1. Real-voice TTS via ``app.product.tts``. Cloud providers
   (ElevenLabs primary, Polly fallback) produce human-sounding audio
   for the user's earbud. The macOS ``/usr/bin/say`` path is kept as
   a last-resort failsafe so the trigger pipeline never fails silent
   when neither cloud provider is configured. The hot-path latency
   is preserved by pre-seeding the cache: a fresh ElevenLabs synth is
   300 to 700 ms over ``say``, but a cache hit (the common case for
   seeded trivia answers) plays in well under 50 ms.

2. ``recent_fires()`` returns the last N (default 10) fires. The
   popover polls ``GET /api/trivia/recent`` for this list. Each fire
   includes the raw utterance, the answer, the source, latencies, and
   a UTC timestamp.

The TTS process is spawned and we do not wait on it; the call returns
once playback has been kicked off. We measure "speech-ready latency"
as the time from call to subprocess spawn (afplay for cached audio,
say for the failsafe), which is what the user perceives as the
answer arriving. The actual audio plays asynchronously.

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

    Kept as the last-resort failsafe inside ``_deliver_audio`` when no
    real-voice provider is available. On non-Mac (or when
    ``ANTICIPY_TRIVIA_DISABLE_TTS=1``) this returns
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


def _deliver_audio(text: str, *, voice: Optional[str] = None,
                   rate: Optional[int] = None) -> dict:
    """Route the spoken answer through the real-voice TTS module,
    falling back to ``say`` if the new module is unavailable.

    Returns a dict with the same shape as ``_spawn_say`` so the
    deliver record schema does not change: ``spawned``, ``pid``,
    ``spawn_ms``, plus the new ``provider``, ``cache_hit``,
    ``synth_ms``, and ``total_ms`` from the cloud path.
    """
    if os.environ.get("ANTICIPY_TRIVIA_DISABLE_TTS", "").strip() == "1":
        return {"spawned": False, "reason": "tts_disabled_env",
                "provider": "none"}
    try:
        from app.product import tts as _tts  # lazy import
    except Exception as exc:
        # Fallback path: legacy say. Keeps trivia speaking even if
        # the new module is broken at import time.
        out = _spawn_say(text, voice=voice, rate=rate)
        out["provider"] = "say"
        out["tts_import_error"] = f"{type(exc).__name__}: {exc}"
        return out
    rec = _tts.play_speech(text)
    return {
        "spawned": bool(rec.get("ok")),
        "pid": rec.get("pid"),
        "spawn_ms": float(rec.get("play_ms", 0.0)),
        "synth_ms": float(rec.get("synth_ms", 0.0)),
        "total_ms": float(rec.get("total_ms", 0.0)),
        "provider": rec.get("provider", "none"),
        "cache_hit": bool(rec.get("cache_hit", False)),
        "path": rec.get("path", ""),
        "reason": rec.get("error", "") or "ok",
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
    tts = _deliver_audio(text, voice=voice, rate=rate)
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
