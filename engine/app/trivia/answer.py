"""Trivia answer fetch.

Three lanes per planning/07-trivia-fire/DESIGN.md plus the live web
fallback added to fix the "I do not know that one" regression:

Lane A. Local seed cache: ``cache.lookup``. ~1-5 ms p50. The killer
        demo depends on this lane (168 seeded facts).

Lane B. Live web LLM via Perplexity Sonar (OpenRouter). Triggered on
        every cache miss when the trigger fired on a strong question
        opener. ~600-1500 ms typical. Cheapest grounded option
        (perplexity/sonar is ~$1/1M in, $1/1M out, ~$0.0002 per
        question). Results are persisted into the same SQLite db via
        ``cache.live_put`` / ``cache.live_get`` so repeat questions
        hit the SQLite row, not Perplexity.

Lane C. Silence. When Lanes A and B both miss (no API key, network
        failure, low confidence), we return an empty answer string.
        The deliver layer treats an empty answer as "skip TTS". Per
        Omar's directive, silence is better than the engine saying
        "I do not know that one" in a robot voice.

Return shape (always a dict, never None):

    {
        "ok": bool,
        "lane": "cache" | "live" | "live_cache" | "no_answer",
        "topic": str,
        "answer": str,        # may be "" on no_answer (deliver layer
                              # treats this as silence)
        "source": str,
        "score": float | None,
        "elapsed_ms": float,
        "error": str (empty if ok),
    }
"""

from __future__ import annotations

import json
import os
import time
from typing import Optional

from . import cache


# Perplexity Sonar via OpenRouter. perplexity/sonar is the cheapest
# online-search tier (~$1 / 1M input + $1 / 1M output, with a small
# per-request search fee). For a single ~30 token question and ~120
# token answer that lands well under the $0.002 per-task ceiling. We
# cache hits so repeated questions cost zero.
_LIVE_MODEL = os.environ.get(
    "ANTICIPY_TRIVIA_LIVE_MODEL", "perplexity/sonar"
)

# 1.5 s hard deadline on the live lookup. The trivia hot path budget
# is ~2 s total. Past this we return silence so the deliver layer
# does not stall the pipeline.
_LIVE_TIMEOUT_S = float(
    os.environ.get("ANTICIPY_TRIVIA_LIVE_TIMEOUT", "1.5")
)

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

_LIVE_SYSTEM_PROMPT = (
    "You answer trivia questions in 1 to 2 short sentences for a voice "
    "assistant. Speak the answer in plain English. No markdown. No "
    "URLs. No quotes. No em-dashes. No parentheticals about "
    "uncertainty. No citations. No source lists. If you cannot find "
    "the answer with high confidence, reply exactly with: NOIDEA."
)


def _openrouter_api_key() -> str:
    """Read OPENROUTER_API_KEY at call time. The desktop_app loads the
    .env on boot, but tests can monkeypatch the env var directly."""
    return os.environ.get("OPENROUTER_API_KEY", "").strip()


def _live_lookup(question: str, deadline: float) -> dict:
    """Call Perplexity Sonar via OpenRouter for a grounded factual
    answer. Returns lane="live" on success, lane="no_answer" on
    failure or timeout. Never raises.
    """
    import requests  # local import: keeps the dependency narrow

    remaining = deadline - time.monotonic()
    if remaining <= 0.05:
        return {
            "ok": False,
            "lane": "no_answer",
            "topic": question,
            "answer": "",
            "source": "",
            "score": None,
            "elapsed_ms": 0.0,
            "error": "deadline expired before live call",
        }
    api_key = _openrouter_api_key()
    if not api_key.startswith("sk-or-"):
        return {
            "ok": False,
            "lane": "no_answer",
            "topic": question,
            "answer": "",
            "source": "",
            "score": None,
            "elapsed_ms": 0.0,
            "error": "OPENROUTER_API_KEY missing",
        }

    t0 = time.monotonic()
    payload = {
        "model": _LIVE_MODEL,
        "messages": [
            {"role": "system", "content": _LIVE_SYSTEM_PROMPT},
            {"role": "user", "content": question.strip()},
        ],
        "max_tokens": 160,
        "temperature": 0.0,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://anticipy.ai",
        "X-Title": "Anticipy Trivia Live Lookup",
    }
    timeout = min(remaining, _LIVE_TIMEOUT_S)
    try:
        r = requests.post(
            _OPENROUTER_URL,
            headers=headers,
            json=payload,
            timeout=timeout,
        )
    except Exception as exc:
        return {
            "ok": False,
            "lane": "no_answer",
            "topic": question,
            "answer": "",
            "source": "",
            "score": None,
            "elapsed_ms": round((time.monotonic() - t0) * 1000.0, 2),
            "error": f"transport: {type(exc).__name__}: {exc}",
        }
    elapsed_ms = round((time.monotonic() - t0) * 1000.0, 2)
    if r.status_code != 200:
        return {
            "ok": False,
            "lane": "no_answer",
            "topic": question,
            "answer": "",
            "source": "",
            "score": None,
            "elapsed_ms": elapsed_ms,
            "error": f"http {r.status_code}: {r.text[:120]}",
        }
    try:
        j = r.json()
    except Exception as exc:
        return {
            "ok": False,
            "lane": "no_answer",
            "topic": question,
            "answer": "",
            "source": "",
            "score": None,
            "elapsed_ms": elapsed_ms,
            "error": f"json decode: {type(exc).__name__}: {exc}",
        }
    choices = j.get("choices") or []
    if not choices:
        return {
            "ok": False,
            "lane": "no_answer",
            "topic": question,
            "answer": "",
            "source": "",
            "score": None,
            "elapsed_ms": elapsed_ms,
            "error": "no choices in response",
        }
    msg = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
    content = (msg.get("content") or "").strip()
    if not content:
        return {
            "ok": False,
            "lane": "no_answer",
            "topic": question,
            "answer": "",
            "source": "",
            "score": None,
            "elapsed_ms": elapsed_ms,
            "error": "empty content",
        }
    # Normalize: strip wrapping quotes, swap em/en dashes for plain
    # hyphens (Omar's #1 AI tell), drop bracketed citation markers
    # like [1] or [2] that Perplexity sometimes emits despite the
    # prompt.
    text = content.strip("\"' \n\t")
    text = text.replace("—", "-").replace("–", "-")
    import re as _re
    text = _re.sub(r"\s*\[\d+\]", "", text).strip()
    if not text or text.upper().startswith("NOIDEA"):
        return {
            "ok": False,
            "lane": "no_answer",
            "topic": question,
            "answer": "",
            "source": "",
            "score": None,
            "elapsed_ms": elapsed_ms,
            "error": "model declined",
        }
    return {
        "ok": True,
        "lane": "live",
        "topic": question,
        "answer": text,
        "source": f"{_LIVE_MODEL} via openrouter",
        "score": None,
        "elapsed_ms": elapsed_ms,
        "error": "",
    }


def fetch(question: str,
          *,
          allow_live: Optional[bool] = None,
          deadline_s: float = 1.6) -> dict:
    """Get an answer for ``question``.

    Lane A first (seed cache, ~1-5 ms). On miss, check the live
    lookup cache (also SQLite, near-zero cost). On miss, attempt the
    live Perplexity Sonar call. If that also fails, return an empty
    answer so the deliver layer stays silent instead of speaking "I
    do not know that one".

    ``allow_live`` defaults to True unless
    ``ANTICIPY_TRIVIA_DISABLE_LIVE=1``. (Legacy
    ``ANTICIPY_TRIVIA_DISABLE_LLM`` is honored for backward
    compatibility with existing test envs.)

    ``deadline_s`` bounds total wall-clock. Cache lookups are
    essentially free; the live call respects whichever is smaller of
    the remaining budget and the per-call live timeout (1.5 s).
    """
    if not question or not question.strip():
        return {
            "ok": False,
            "lane": "no_answer",
            "topic": "",
            "answer": "",
            "source": "",
            "score": None,
            "elapsed_ms": 0.0,
            "error": "empty question",
        }
    t0 = time.monotonic()
    deadline = t0 + float(deadline_s)

    # Lane A: seed cache.
    try:
        hit = cache.lookup(question)
    except Exception as exc:
        hit = None
        cache_err = f"{type(exc).__name__}: {exc}"
    else:
        cache_err = ""
    if hit:
        return {
            "ok": True,
            "lane": "cache",
            "topic": hit.get("topic", question),
            "answer": hit.get("answer", ""),
            "source": hit.get("source", ""),
            "score": float(hit.get("score", 0.0)),
            "elapsed_ms": round((time.monotonic() - t0) * 1000, 2),
            "error": "",
        }

    # Lane B prep: enabled by default. Honor both the new env var
    # and the legacy LLM-disable env var so old test configs still
    # silence the network path.
    live_allowed = True if allow_live is None else bool(allow_live)
    if os.environ.get("ANTICIPY_TRIVIA_DISABLE_LIVE", "").strip() == "1":
        live_allowed = False
    if os.environ.get("ANTICIPY_TRIVIA_DISABLE_LLM", "").strip() == "1":
        live_allowed = False

    # Live cache (results of prior Lane B calls). Fast SQLite read,
    # zero network. Hits are returned as lane="live_cache" so the
    # deliver-side log can distinguish "Perplexity yesterday" from
    # "seed fact" from "Perplexity right now".
    try:
        live_hit = cache.live_get(question)
    except Exception:
        live_hit = None
    if live_hit:
        return {
            "ok": True,
            "lane": "live_cache",
            "topic": live_hit.get("topic", question),
            "answer": live_hit.get("answer", ""),
            "source": live_hit.get("source", ""),
            "score": None,
            "elapsed_ms": round((time.monotonic() - t0) * 1000, 2),
            "error": "",
        }

    if not live_allowed:
        # Cache miss, live lane disabled. Return silence (empty
        # answer) so deliver does not speak the IDK string.
        return {
            "ok": False,
            "lane": "no_answer",
            "topic": question,
            "answer": "",
            "source": "",
            "score": None,
            "elapsed_ms": round((time.monotonic() - t0) * 1000, 2),
            "error": cache_err or "cache miss, live lane disabled",
        }

    live_result = _live_lookup(question, deadline=deadline)
    live_result["elapsed_ms"] = round(
        (time.monotonic() - t0) * 1000.0, 2
    )
    if live_result.get("ok") and live_result.get("answer"):
        # Persist for future repeats. Best effort; a write failure
        # does not block the response.
        try:
            cache.live_put(
                question,
                live_result.get("answer", ""),
                source=str(live_result.get("source", "")),
            )
        except Exception:
            pass
        return live_result

    if cache_err:
        live_result["error"] = (
            f"{cache_err}; {live_result.get('error', '')}".strip("; ")
        )
    # Final fallback: silence. Empty answer signals deliver to skip
    # TTS instead of speaking the robotic IDK line.
    live_result["answer"] = ""
    live_result["lane"] = "no_answer"
    live_result["ok"] = False
    return live_result


__all__ = ["fetch"]
