"""Trivia answer fetch.

Two lanes per planning/07-trivia-fire/DESIGN.md:

Lane A. Local cache: ``cache.lookup``. ~1-5 ms p50. The killer demo
        depends on this lane.

Lane B. Grounded web LLM. The planning doc names Perplexity Sonar
        Small Online; the website's model broker currently allowlists
        only DeepSeek and Kimi, so we route the cache miss through the
        same ``platform_adapter.model_call`` channel the rest of the
        engine uses. The prompt asks for a 1-2 sentence factual
        answer; the LLM is unable to actually browse, so this lane is
        best-effort and clearly marked as "no live source". A future
        wiring change can expand the allowlist to include
        ``perplexity/sonar`` and ``-online`` model variants.

Return shape (always a dict, never None):

    {
        "ok": bool,
        "lane": "cache" | "llm" | "no_answer",
        "topic": str,
        "answer": str,
        "source": str,
        "score": float | None,
        "elapsed_ms": float,
        "error": str (empty if ok),
    }
"""

from __future__ import annotations

import os
import time
from typing import Optional

from . import cache


# Lane B model selection. The website's broker allowlist (see
# src/app/api/engine/model/route.ts) does not include perplexity sonar
# variants. Fall back to a Kimi model that is allowlisted and is the
# fastest first-token member of the cascade today.
_LLM_MODEL = os.environ.get(
    "ANTICIPY_TRIVIA_LLM_MODEL", "moonshotai/kimi-k2.6"
)

# How long we are willing to wait on the LLM lane. 1.2 s keeps the
# end-to-end p95 under 2 s once cache misses fall through. Past this
# we return ``no_answer`` so the deliver layer can degrade gracefully
# instead of hanging the pipeline.
_LLM_TIMEOUT_S = float(os.environ.get("ANTICIPY_TRIVIA_LLM_TIMEOUT", "1.2"))

_LLM_SYSTEM_PROMPT = (
    "You answer trivia questions in 1 to 2 short sentences for a voice "
    "assistant. Speak the answer in plain English with no markdown, no "
    "URLs, no quotes, no em-dashes, no parentheticals about uncertainty. "
    "If you do not know the answer with high confidence, reply exactly "
    "with: I do not know that one."
)


def _llm_lookup(question: str, deadline: float) -> dict:
    """Call the platform model adapter for a trivia-shaped answer.

    Returns lane="llm" on success, lane="no_answer" on failure or
    timeout. Never raises.
    """
    remaining = deadline - time.monotonic()
    if remaining <= 0.05:
        return {
            "ok": False,
            "lane": "no_answer",
            "topic": question,
            "answer": "I do not know that one.",
            "source": "",
            "score": None,
            "elapsed_ms": 0.0,
            "error": "deadline expired before LLM call",
        }
    t0 = time.monotonic()
    try:
        from app.anticipy.platform_adapter import model_call
    except Exception as exc:
        return {
            "ok": False,
            "lane": "no_answer",
            "topic": question,
            "answer": "I do not know that one.",
            "source": "",
            "score": None,
            "elapsed_ms": 0.0,
            "error": f"platform_adapter import failed: {type(exc).__name__}: {exc}",
        }
    try:
        result = model_call(
            system=_LLM_SYSTEM_PROMPT,
            user=question.strip(),
            max_tokens=120,
            temperature=0.0,
            json_mode=False,
            timeout_s=min(remaining, _LLM_TIMEOUT_S),
            model=_LLM_MODEL,
        )
    except Exception as exc:
        return {
            "ok": False,
            "lane": "no_answer",
            "topic": question,
            "answer": "I do not know that one.",
            "source": "",
            "score": None,
            "elapsed_ms": round((time.monotonic() - t0) * 1000, 2),
            "error": f"{type(exc).__name__}: {exc}",
        }
    elapsed_ms = round((time.monotonic() - t0) * 1000.0, 2)
    if not result.ok or not result.content:
        return {
            "ok": False,
            "lane": "no_answer",
            "topic": question,
            "answer": "I do not know that one.",
            "source": "",
            "score": None,
            "elapsed_ms": elapsed_ms,
            "error": str(result.error or "empty llm content"),
        }
    text = result.content.strip()
    # The model returns plain text. Strip any wrapping quotes and any
    # accidental em-dashes the model might have emitted despite the
    # prompt instruction.
    text = text.strip("\"' \n\t").replace("—", "-").replace("–", "-")
    if text.lower().startswith("i do not know"):
        return {
            "ok": False,
            "lane": "no_answer",
            "topic": question,
            "answer": "I do not know that one.",
            "source": "",
            "score": None,
            "elapsed_ms": elapsed_ms,
            "error": "model declined",
        }
    return {
        "ok": True,
        "lane": "llm",
        "topic": question,
        "answer": text,
        "source": f"{_LLM_MODEL} via model broker",
        "score": None,
        "elapsed_ms": elapsed_ms,
        "error": "",
    }


def fetch(question: str,
          *,
          allow_llm: Optional[bool] = None,
          deadline_s: float = 1.6) -> dict:
    """Get an answer for ``question``.

    Lane A first (cache); on miss optionally fall through to Lane B
    (LLM). ``allow_llm`` defaults to True unless
    ``ANTICIPY_TRIVIA_DISABLE_LLM=1``.

    ``deadline_s`` bounds total wall-clock. Cache lookup is essentially
    free; the LLM call respects the remaining time inside the deadline.
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
    llm_allowed = (
        True if allow_llm is None
        else bool(allow_llm)
    )
    if os.environ.get("ANTICIPY_TRIVIA_DISABLE_LLM", "").strip() == "1":
        llm_allowed = False
    if not llm_allowed:
        return {
            "ok": False,
            "lane": "no_answer",
            "topic": question,
            "answer": "I do not know that one.",
            "source": "",
            "score": None,
            "elapsed_ms": round((time.monotonic() - t0) * 1000, 2),
            "error": cache_err or "cache miss, llm lane disabled",
        }
    llm_result = _llm_lookup(question, deadline=deadline)
    llm_result["elapsed_ms"] = round(
        (time.monotonic() - t0) * 1000.0, 2
    )
    if not llm_result["ok"] and cache_err:
        llm_result["error"] = f"{cache_err}; {llm_result.get('error', '')}".strip("; ")
    return llm_result


__all__ = ["fetch"]
