"""Real-voice text-to-speech with cache and provider fallback.

The default macOS ``/usr/bin/say`` voice sounds like 2008 Mac Alex.
Anticipy is Apple-quality. The user hears the agent through an earbud;
the voice must sound human. This module replaces ``say`` with a real
TTS provider, while keeping ``say`` as a last-resort failsafe.

Provider precedence (first that is available wins):

1. ElevenLabs (``ELEVENLABS_API_KEY`` env var). Uses the
   ``eleven_turbo_v2_5`` model: low latency (typical 300-700 ms first
   byte), strong quality, plain-English prosody. Default voice is
   Sarah (mature, reassuring, confident) per ElevenLabs' premade
   library; the voice id ``EXAVITQu4vr4xnSDxMaL`` is the canonical
   Sarah voice as of 2026-05.

2. Amazon Polly (``AWS_ACCESS_KEY_ID`` plus ``AWS_SECRET_ACCESS_KEY``
   plus ``boto3`` installed). Uses Joanna in the ``neural`` engine.
   Slower install footprint (boto3 brings in a chunk of AWS SDK), so
   only used when ElevenLabs is not configured.

3. macOS ``say`` failsafe. Preserved verbatim so the engine still
   speaks something when neither cloud provider is reachable. Quality
   drops to 2008, but the user still hears the answer.

Cache layout:

    ~/.anticipy/v7/tts_cache/<sha256>.mp3

Key is ``sha256(provider + ":" + voice_name + ":" + text)`` so
provider changes or voice swaps do not collide. Cache hits skip the
network round-trip and play in well under 50 ms (afplay spawn cost).

Public API:

    synth_speech(text, voice_name="default") -> bytes
        Returns MP3 (or AAC/CAF, whatever the active provider serves)
        audio bytes. Reads from cache when possible. Writes to cache
        on cache miss.

    play_speech(text, voice_name="default") -> dict
        Synthesizes (or reads from cache) and plays the audio through
        the default macOS audio device via ``afplay``. Returns a
        delivery record describing the path taken (cache hit, provider,
        latencies, audio path, pid).

    prefetch_phrases(phrases, voice_name="default") -> dict
        Hydrate the cache with a list of phrases. Used at install /
        first run to seed all common trivia answers so the hot path
        hits the cache in ``synth_speech``.

The module is best-effort: every operation that touches network or
the filesystem catches exceptions and degrades to the next step in
the cascade. Callers receive a dict with ``ok``, ``provider``,
``cache_hit``, ``synth_ms``, ``play_ms``, ``path``, and ``error`` so
they can log meaningful telemetry without re-raising.

Environment toggles:

    ANTICIPY_TTS_DISABLE=1                Disable TTS entirely.
    ANTICIPY_TTS_FORCE_SAY=1              Skip cloud providers, use
                                          macOS say only.
    ANTICIPY_TTS_CACHE_DIR=/path          Override the cache directory.
    ANTICIPY_TTS_ELEVEN_VOICE_ID=<id>     Override the default Eleven
                                          voice id.
    ANTICIPY_TTS_ELEVEN_MODEL=<id>        Override the Eleven model.
                                          Default eleven_turbo_v2_5.
    ANTICIPY_TTS_POLLY_VOICE=<name>       Override Polly voice
                                          (default Joanna).

No em-dashes anywhere. Spoken text is what the user will hear, so the
default voice settings favor a calm, neutral, confident delivery.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Iterable, Optional


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DEFAULT_CACHE_DIR = Path.home() / ".anticipy" / "v7" / "tts_cache"

_ELEVEN_DEFAULT_VOICE_ID = "EXAVITQu4vr4xnSDxMaL"  # Sarah, premade
_ELEVEN_DEFAULT_MODEL = "eleven_turbo_v2_5"
_ELEVEN_BASE = "https://api.elevenlabs.io/v1/text-to-speech"

_POLLY_DEFAULT_VOICE = "Joanna"
_POLLY_DEFAULT_ENGINE = "neural"

# Map symbolic voice names to per-provider voice ids. ``default`` is
# the canonical Anticipy voice across providers.
_VOICE_MAP_ELEVEN: dict[str, str] = {
    "default": _ELEVEN_DEFAULT_VOICE_ID,
    "sarah": "EXAVITQu4vr4xnSDxMaL",
    "george": "JBFqnCBsd6RMkjVDRZzb",
    "charlie": "IKne3meq5aSn9XLyUdCD",
}

_VOICE_MAP_POLLY: dict[str, str] = {
    "default": _POLLY_DEFAULT_VOICE,
    "sarah": "Joanna",
    "george": "Matthew",
    "charlie": "Joey",
}

_PROVIDER_LOCK = threading.Lock()
_AFPLAY_LOCK = threading.Lock()
_AFPLAY_PROC: list[subprocess.Popen] = []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_disabled() -> bool:
    return (os.environ.get("ANTICIPY_TTS_DISABLE", "").strip() == "1")


def _force_say() -> bool:
    return (os.environ.get("ANTICIPY_TTS_FORCE_SAY", "").strip() == "1")


def _cache_dir() -> Path:
    raw = os.environ.get("ANTICIPY_TTS_CACHE_DIR", "").strip()
    if raw:
        return Path(raw).expanduser()
    return _DEFAULT_CACHE_DIR


def _ensure_cache_dir() -> Path:
    p = _cache_dir()
    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return p


def _normalize_text(text: str) -> str:
    """Stable normalization for cache keys. Whitespace folded, no
    case change so capitalized acronyms are not collided with words."""
    if not text:
        return ""
    return " ".join(text.split())


def _cache_key(provider: str, voice_name: str, text: str) -> str:
    norm = _normalize_text(text)
    raw = f"{provider}::{voice_name or 'default'}::{norm}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _cache_path(provider: str, voice_name: str, text: str,
                ext: str = "mp3") -> Path:
    key = _cache_key(provider, voice_name, text)
    return _ensure_cache_dir() / f"{key}.{ext}"


def _read_cache(provider: str, voice_name: str, text: str,
                ext: str = "mp3") -> Optional[bytes]:
    p = _cache_path(provider, voice_name, text, ext=ext)
    if not p.is_file():
        return None
    try:
        return p.read_bytes()
    except Exception:
        return None


def _write_cache(provider: str, voice_name: str, text: str,
                 audio: bytes, ext: str = "mp3") -> Optional[Path]:
    if not audio:
        return None
    p = _cache_path(provider, voice_name, text, ext=ext)
    tmp = p.with_suffix(p.suffix + ".part")
    try:
        tmp.write_bytes(audio)
        os.replace(tmp, p)
        return p
    except Exception:
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass
        return None


# ---------------------------------------------------------------------------
# Provider selection
# ---------------------------------------------------------------------------

def _eleven_available() -> bool:
    return bool(os.environ.get("ELEVENLABS_API_KEY", "").strip())


def _polly_available() -> bool:
    if not os.environ.get("AWS_ACCESS_KEY_ID", "").strip():
        return False
    if not os.environ.get("AWS_SECRET_ACCESS_KEY", "").strip():
        return False
    try:
        import boto3  # noqa: F401
    except Exception:
        return False
    return True


def _say_available() -> bool:
    if sys.platform != "darwin":
        return False
    return bool(shutil.which("say") or os.path.exists("/usr/bin/say"))


def active_provider() -> str:
    """Return the provider that will be used for a fresh synthesis.

    ``elevenlabs`` if the API key is set; ``polly`` if AWS creds plus
    boto3; ``say`` if running on macOS with /usr/bin/say. ``none``
    means no TTS is currently available.
    """
    if _is_disabled():
        return "none"
    if _force_say():
        return "say" if _say_available() else "none"
    if _eleven_available():
        return "elevenlabs"
    if _polly_available():
        return "polly"
    if _say_available():
        return "say"
    return "none"


# ---------------------------------------------------------------------------
# Provider implementations
# ---------------------------------------------------------------------------

def _eleven_voice_id_for(voice_name: str) -> str:
    explicit = os.environ.get("ANTICIPY_TTS_ELEVEN_VOICE_ID", "").strip()
    if explicit:
        return explicit
    key = (voice_name or "default").lower()
    return _VOICE_MAP_ELEVEN.get(key, _ELEVEN_DEFAULT_VOICE_ID)


def _eleven_model() -> str:
    explicit = os.environ.get("ANTICIPY_TTS_ELEVEN_MODEL", "").strip()
    return explicit or _ELEVEN_DEFAULT_MODEL


def _synth_eleven(text: str, voice_name: str,
                  timeout: float = 12.0) -> dict[str, Any]:
    """Synthesize via ElevenLabs. Returns
    ``{"ok": bool, "audio": bytes, "ext": "mp3", "synth_ms": float,
       "error": str}``.
    """
    api_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not api_key:
        return {"ok": False, "audio": b"", "ext": "mp3",
                "synth_ms": 0.0, "error": "ELEVENLABS_API_KEY missing"}
    voice_id = _eleven_voice_id_for(voice_name)
    model = _eleven_model()
    body = json.dumps({
        "text": text,
        "model_id": model,
        "voice_settings": {
            "stability": 0.55,
            "similarity_boost": 0.75,
            "style": 0.0,
            "use_speaker_boost": True,
        },
    }).encode("utf-8")
    req = urllib.request.Request(
        url=f"{_ELEVEN_BASE}/{voice_id}",
        data=body,
        method="POST",
        headers={
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
    )
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            audio = r.read()
            status = r.getcode()
    except urllib.error.HTTPError as exc:
        body_text = ""
        try:
            body_text = exc.read().decode("utf-8", "replace")[:300]
        except Exception:
            pass
        return {
            "ok": False,
            "audio": b"",
            "ext": "mp3",
            "synth_ms": round((time.monotonic() - t0) * 1000.0, 2),
            "error": f"elevenlabs http {exc.code}: {body_text}",
        }
    except Exception as exc:
        return {
            "ok": False,
            "audio": b"",
            "ext": "mp3",
            "synth_ms": round((time.monotonic() - t0) * 1000.0, 2),
            "error": f"{type(exc).__name__}: {exc}",
        }
    synth_ms = round((time.monotonic() - t0) * 1000.0, 2)
    if status >= 300 or not audio:
        return {"ok": False, "audio": b"", "ext": "mp3",
                "synth_ms": synth_ms,
                "error": f"elevenlabs non-2xx status={status}"}
    return {"ok": True, "audio": audio, "ext": "mp3",
            "synth_ms": synth_ms, "error": ""}


def _polly_voice_for(voice_name: str) -> str:
    explicit = os.environ.get("ANTICIPY_TTS_POLLY_VOICE", "").strip()
    if explicit:
        return explicit
    key = (voice_name or "default").lower()
    return _VOICE_MAP_POLLY.get(key, _POLLY_DEFAULT_VOICE)


def _synth_polly(text: str, voice_name: str,
                 timeout: float = 12.0) -> dict[str, Any]:
    """Synthesize via Amazon Polly. Requires boto3."""
    try:
        import boto3
    except Exception as exc:
        return {"ok": False, "audio": b"", "ext": "mp3",
                "synth_ms": 0.0,
                "error": f"boto3 import failed: {exc}"}
    voice = _polly_voice_for(voice_name)
    engine = (os.environ.get("ANTICIPY_TTS_POLLY_ENGINE", "").strip()
              or _POLLY_DEFAULT_ENGINE)
    t0 = time.monotonic()
    try:
        client = boto3.client("polly")
        resp = client.synthesize_speech(
            Text=text,
            OutputFormat="mp3",
            VoiceId=voice,
            Engine=engine,
        )
        audio_stream = resp.get("AudioStream")
        if audio_stream is None:
            return {"ok": False, "audio": b"", "ext": "mp3",
                    "synth_ms": round((time.monotonic() - t0) * 1000.0, 2),
                    "error": "polly returned no audio stream"}
        audio = audio_stream.read()
    except Exception as exc:
        return {"ok": False, "audio": b"", "ext": "mp3",
                "synth_ms": round((time.monotonic() - t0) * 1000.0, 2),
                "error": f"{type(exc).__name__}: {exc}"}
    synth_ms = round((time.monotonic() - t0) * 1000.0, 2)
    if not audio:
        return {"ok": False, "audio": b"", "ext": "mp3",
                "synth_ms": synth_ms,
                "error": "polly returned empty audio"}
    return {"ok": True, "audio": audio, "ext": "mp3",
            "synth_ms": synth_ms, "error": ""}


# ---------------------------------------------------------------------------
# Public synthesis API
# ---------------------------------------------------------------------------

def synth_speech(text: str, voice_name: str = "default") -> bytes:
    """Synthesize ``text`` to audio bytes.

    Returns the audio payload as bytes (MP3 for cloud providers,
    empty bytes when the cascade falls through to ``say`` which has no
    file output, or when the cascade fails entirely). The caller can
    distinguish ``len(audio) == 0`` to know it must fall back to
    ``say``-style direct playback via ``play_speech``.
    """
    if _is_disabled() or not (text and text.strip()):
        return b""
    provider = active_provider()
    if provider == "elevenlabs":
        cached = _read_cache("elevenlabs", voice_name, text)
        if cached:
            return cached
        out = _synth_eleven(text, voice_name)
        if out["ok"]:
            _write_cache("elevenlabs", voice_name, text, out["audio"],
                         ext=out["ext"])
            return out["audio"]
        # Try Polly as a deeper fallback when Eleven failed.
        if _polly_available():
            out2 = _synth_polly(text, voice_name)
            if out2["ok"]:
                _write_cache("polly", voice_name, text, out2["audio"],
                             ext=out2["ext"])
                return out2["audio"]
        return b""
    if provider == "polly":
        cached = _read_cache("polly", voice_name, text)
        if cached:
            return cached
        out = _synth_polly(text, voice_name)
        if out["ok"]:
            _write_cache("polly", voice_name, text, out["audio"],
                         ext=out["ext"])
            return out["audio"]
        return b""
    # provider == "say" or "none": no audio bytes available.
    return b""


# ---------------------------------------------------------------------------
# Playback
# ---------------------------------------------------------------------------

def _spawn_afplay(audio_path: Path) -> dict[str, Any]:
    """Play an audio file with macOS afplay in the background. Kills
    any prior afplay so the previous answer does not bleed into the
    new one mid-sentence (matches deliver.py semantics for /usr/bin/say).
    """
    if sys.platform != "darwin":
        return {"ok": False, "spawned": False, "error": "not macOS"}
    bin_path = shutil.which("afplay") or "/usr/bin/afplay"
    if not Path(bin_path).exists():
        return {"ok": False, "spawned": False,
                "error": "afplay binary missing"}
    t0 = time.monotonic()
    try:
        with _AFPLAY_LOCK:
            still_alive = []
            for p in _AFPLAY_PROC:
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
            _AFPLAY_PROC.clear()
            proc = subprocess.Popen(
                [bin_path, str(audio_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
            )
            _AFPLAY_PROC.append(proc)
    except Exception as exc:
        return {"ok": False, "spawned": False,
                "error": f"{type(exc).__name__}: {exc}"}
    return {
        "ok": True,
        "spawned": True,
        "pid": int(proc.pid),
        "spawn_ms": round((time.monotonic() - t0) * 1000.0, 2),
        "bin": bin_path,
        "path": str(audio_path),
    }


def _spawn_say(text: str, *, voice_arg: Optional[str] = None,
               rate: Optional[int] = None) -> dict[str, Any]:
    """Last-resort failsafe: macOS say. Same semantics as the legacy
    trivia/deliver.py path so behavior is preserved when no API key is
    set. Returns the spawn metadata so callers can log it.
    """
    if sys.platform != "darwin":
        return {"ok": False, "spawned": False, "error": "not macOS"}
    bin_path = shutil.which("say") or "/usr/bin/say"
    if not Path(bin_path).exists():
        return {"ok": False, "spawned": False,
                "error": "say binary missing"}
    args = [bin_path]
    if voice_arg:
        args.extend(["-v", str(voice_arg)])
    if rate:
        args.extend(["-r", str(int(rate))])
    args.append(text)
    t0 = time.monotonic()
    try:
        with _AFPLAY_LOCK:
            still_alive = []
            for p in _AFPLAY_PROC:
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
            _AFPLAY_PROC.clear()
            proc = subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
            )
            _AFPLAY_PROC.append(proc)
    except Exception as exc:
        return {"ok": False, "spawned": False,
                "error": f"{type(exc).__name__}: {exc}"}
    return {
        "ok": True,
        "spawned": True,
        "pid": int(proc.pid),
        "spawn_ms": round((time.monotonic() - t0) * 1000.0, 2),
        "bin": bin_path,
    }


def play_speech(text: str, voice_name: str = "default",
                *,
                say_voice: Optional[str] = None,
                say_rate: Optional[int] = None) -> dict[str, Any]:
    """Synthesize (or read cached audio) and play through the default
    audio output device.

    Returns a dict with the path taken so callers can log telemetry:

        {
            "ok": bool,
            "provider": "elevenlabs" | "polly" | "say" | "none",
            "cache_hit": bool,
            "synth_ms": float,
            "play_ms": float,
            "total_ms": float,
            "path": str (audio file when cloud provider was used),
            "pid": int (afplay or say pid),
            "error": str (empty on success),
        }
    """
    t0 = time.monotonic()
    record: dict[str, Any] = {
        "ok": False,
        "provider": "none",
        "cache_hit": False,
        "synth_ms": 0.0,
        "play_ms": 0.0,
        "total_ms": 0.0,
        "path": "",
        "pid": None,
        "error": "",
    }
    if _is_disabled():
        record["error"] = "tts disabled via ANTICIPY_TTS_DISABLE"
        record["total_ms"] = round((time.monotonic() - t0) * 1000.0, 2)
        return record
    if not (text and text.strip()):
        record["error"] = "empty text"
        record["total_ms"] = round((time.monotonic() - t0) * 1000.0, 2)
        return record

    provider = active_provider()
    record["provider"] = provider

    if provider == "elevenlabs" or provider == "polly":
        prov_key = provider
        cached_path = _cache_path(prov_key, voice_name, text)
        if cached_path.is_file():
            record["cache_hit"] = True
            record["synth_ms"] = 0.0
            record["path"] = str(cached_path)
            tp = time.monotonic()
            played = _spawn_afplay(cached_path)
            record["play_ms"] = round(
                (time.monotonic() - tp) * 1000.0, 2)
            if played.get("ok"):
                record["ok"] = True
                record["pid"] = played.get("pid")
            else:
                record["error"] = played.get("error") or "afplay failed"
            record["total_ms"] = round(
                (time.monotonic() - t0) * 1000.0, 2)
            return record
        # cache miss: synthesize fresh
        ts = time.monotonic()
        synth = (_synth_eleven(text, voice_name)
                 if provider == "elevenlabs"
                 else _synth_polly(text, voice_name))
        record["synth_ms"] = round(
            (time.monotonic() - ts) * 1000.0, 2)
        if not synth["ok"]:
            # Cascade down. If we were on Eleven, try Polly. Either
            # way, end on say so the user hears something.
            if provider == "elevenlabs" and _polly_available():
                ts2 = time.monotonic()
                synth = _synth_polly(text, voice_name)
                record["synth_ms"] += round(
                    (time.monotonic() - ts2) * 1000.0, 2)
                if synth["ok"]:
                    record["provider"] = "polly"
                    prov_key = "polly"
            if not synth["ok"]:
                # Final failsafe: macOS say.
                record["error"] = synth.get("error") or "synth failed"
                if _say_available():
                    tp = time.monotonic()
                    said = _spawn_say(
                        text, voice_arg=say_voice, rate=say_rate)
                    record["play_ms"] = round(
                        (time.monotonic() - tp) * 1000.0, 2)
                    record["provider"] = "say"
                    if said.get("ok"):
                        record["ok"] = True
                        record["pid"] = said.get("pid")
                    else:
                        record["error"] = (
                            record["error"]
                            + "; say fallback: "
                            + (said.get("error") or "spawn failed"))
                record["total_ms"] = round(
                    (time.monotonic() - t0) * 1000.0, 2)
                return record
        # Synth succeeded. Write the cache and play from the file.
        stored = _write_cache(prov_key, voice_name, text,
                              synth["audio"], ext=synth["ext"])
        play_path = stored if stored else None
        if play_path is None:
            # Cache write failed; write to a temp file to play.
            tmpdir = _ensure_cache_dir()
            play_path = tmpdir / (
                _cache_key(prov_key, voice_name, text)
                + ".tmp.mp3")
            try:
                play_path.write_bytes(synth["audio"])
            except Exception as exc:
                record["error"] = (
                    f"cache + tmp write failed: {exc}")
                record["total_ms"] = round(
                    (time.monotonic() - t0) * 1000.0, 2)
                return record
        record["path"] = str(play_path)
        tp = time.monotonic()
        played = _spawn_afplay(play_path)
        record["play_ms"] = round(
            (time.monotonic() - tp) * 1000.0, 2)
        if played.get("ok"):
            record["ok"] = True
            record["pid"] = played.get("pid")
        else:
            record["error"] = played.get("error") or "afplay failed"
        record["total_ms"] = round(
            (time.monotonic() - t0) * 1000.0, 2)
        return record

    if provider == "say":
        tp = time.monotonic()
        said = _spawn_say(text, voice_arg=say_voice, rate=say_rate)
        record["play_ms"] = round(
            (time.monotonic() - tp) * 1000.0, 2)
        if said.get("ok"):
            record["ok"] = True
            record["pid"] = said.get("pid")
        else:
            record["error"] = said.get("error") or "say spawn failed"
        record["total_ms"] = round(
            (time.monotonic() - t0) * 1000.0, 2)
        return record

    # provider == "none"
    record["error"] = "no TTS provider available"
    record["total_ms"] = round((time.monotonic() - t0) * 1000.0, 2)
    return record


# ---------------------------------------------------------------------------
# Cache prefetch
# ---------------------------------------------------------------------------

def prefetch_phrases(phrases: Iterable[str],
                     voice_name: str = "default",
                     *,
                     pause_s: float = 0.0) -> dict[str, Any]:
    """Hydrate the cache with a list of phrases.

    Returns a summary dict: count of phrases attempted, count cached
    before this call, count newly synthesized, count of errors, and
    per-phrase totals. ``pause_s`` lets the caller throttle to stay
    well inside the provider's rate limit.
    """
    provider = active_provider()
    out: dict[str, Any] = {
        "provider": provider,
        "voice_name": voice_name,
        "attempted": 0,
        "already_cached": 0,
        "newly_cached": 0,
        "errors": 0,
        "elapsed_ms": 0.0,
        "per_phrase": [],
    }
    if provider in ("none", "say"):
        # Nothing to prefetch on say; it never hits the cache.
        return out
    t0 = time.monotonic()
    for phrase in phrases:
        out["attempted"] += 1
        norm = (phrase or "").strip()
        if not norm:
            out["per_phrase"].append({
                "text": "", "status": "skipped_empty",
                "synth_ms": 0.0})
            continue
        cached_path = _cache_path(provider, voice_name, norm)
        if cached_path.is_file():
            out["already_cached"] += 1
            out["per_phrase"].append({
                "text": norm[:60], "status": "already_cached",
                "synth_ms": 0.0, "path": str(cached_path)})
            continue
        synth = (_synth_eleven(norm, voice_name)
                 if provider == "elevenlabs"
                 else _synth_polly(norm, voice_name))
        if not synth["ok"]:
            out["errors"] += 1
            out["per_phrase"].append({
                "text": norm[:60], "status": "error",
                "synth_ms": synth.get("synth_ms", 0.0),
                "error": synth.get("error", "")})
            if pause_s > 0:
                time.sleep(pause_s)
            continue
        stored = _write_cache(provider, voice_name, norm,
                              synth["audio"], ext=synth["ext"])
        out["newly_cached"] += 1
        out["per_phrase"].append({
            "text": norm[:60], "status": "newly_cached",
            "synth_ms": synth.get("synth_ms", 0.0),
            "path": str(stored) if stored else ""})
        if pause_s > 0:
            time.sleep(pause_s)
    out["elapsed_ms"] = round((time.monotonic() - t0) * 1000.0, 2)
    return out


def prefetch_trivia_seed_answers(voice_name: str = "default",
                                 pause_s: float = 0.0) -> dict[str, Any]:
    """Convenience: pull the answers from the trivia seed_facts module
    and prefetch them all. Importing lazily so this module stays
    callable from places that do not have trivia on the path.
    """
    try:
        from app.trivia.seed_facts import SEED_FACTS  # type: ignore
    except Exception as exc:
        return {"ok": False, "error": f"seed_facts import failed: {exc}",
                "attempted": 0, "newly_cached": 0,
                "already_cached": 0, "errors": 0}
    answers = []
    seen = set()
    for fact in SEED_FACTS:
        ans = ""
        if isinstance(fact, dict):
            ans = (fact.get("answer") or "").strip()
        if ans and ans not in seen:
            seen.add(ans)
            answers.append(ans)
    res = prefetch_phrases(answers, voice_name=voice_name, pause_s=pause_s)
    res["ok"] = True
    return res


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------

def status() -> dict[str, Any]:
    """Snapshot of the TTS subsystem for diagnostics endpoints."""
    cache = _cache_dir()
    files = []
    bytes_total = 0
    if cache.is_dir():
        try:
            for p in cache.iterdir():
                if not p.is_file():
                    continue
                try:
                    size = p.stat().st_size
                except Exception:
                    size = 0
                bytes_total += size
                files.append({"name": p.name, "bytes": size})
        except Exception:
            pass
    return {
        "active_provider": active_provider(),
        "eleven_available": _eleven_available(),
        "polly_available": _polly_available(),
        "say_available": _say_available(),
        "disabled": _is_disabled(),
        "forced_say": _force_say(),
        "cache_dir": str(cache),
        "cache_file_count": len(files),
        "cache_bytes": bytes_total,
    }


__all__ = [
    "active_provider",
    "play_speech",
    "prefetch_phrases",
    "prefetch_trivia_seed_answers",
    "status",
    "synth_speech",
]
