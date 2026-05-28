"""LLM-as-judge for verifying agent task completion.

ZERO hardcoded phrase lists. Given a task and the agent's reply, asks
whichever free model has quota right now whether the reply actually
answered the task. Uses the existing MODEL_CHAIN cascade (gemini →
groq → mistral → deepseek → ...) which already handles 429 cooldown +
provider rotation.

Public surface:
    judge_task_response(task, response, expected_facts=None) -> dict
        sync wrapper for non-async callers (test runners, scripts)
    judge_task_response_async(...) -> dict
        the real implementation

The verdict shape is stable so callers can pattern-match it:
    {"passed": bool, "reason": str, "judge_model": str|None}

When the entire LLM cascade is unavailable, the judge fails CLOSED:
returns {"passed": False, "reason": "judge unavailable", ...}. We never
inflate a benchmark by silently passing things we couldn't actually
verify.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from app.models import (
    CostTracker,
    DegradedResponse,
    MODEL_CHAIN,
    llm_call_json,
)

logger = logging.getLogger(__name__)


JUDGE_SYSTEM_PROMPT = """You are an impartial evaluator scoring a browser agent's
task completion. You will be given:
  - the original task the user asked the agent to do
  - the agent's final reply to the user
  - optionally, a hint of facts that should appear in a correct reply

Your job: decide whether the agent's reply REALLY accomplished the task and
provided a real answer to the user.

Reasons to FAIL the agent:
  - reply is a generic apology or "try again" message (not a real answer)
  - reply describes an attempt or a problem rather than the answer
  - reply hallucinates an answer that contradicts the listed facts (when given)
  - reply is empty or trivially short for the task type
  - reply asks the user to do the work themselves

Reasons to PASS the agent:
  - reply contains a substantive real answer to the task
  - the answer is consistent with the listed facts (or at minimum doesn't
    contradict them)
  - if the task asked for something subjective/open-ended (e.g. "tell me a
    headline"), the reply contains real extracted content from a real source

Reply with strict JSON only (no markdown), shape:
  {"passed": true|false, "reason": "<short justification, <=140 chars>"}

Be CRITICAL. A reply that says "I had a hiccup, try again" is a FAIL even if
the underlying task was easy. Quota errors, network errors, sign-in walls —
all FAILS. Do not pass them out of charity.
"""


def _build_judge_prompt(
    task: str,
    response: str,
    expected_facts: list[str] | None,
) -> list[dict[str, Any]]:
    facts_block = ""
    if expected_facts:
        facts_block = (
            "\n\nFacts a correct answer would mention (any one is enough; this is "
            "guidance, not a string-match):\n"
            + "\n".join(f"  - {f}" for f in expected_facts)
        )
    user = (
        f"TASK:\n{task.strip()}\n\n"
        f"AGENT'S FINAL REPLY:\n{(response or '').strip()[:4000]}"
        f"{facts_block}\n\n"
        f"Score it. JSON only."
    )
    return [
        {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


async def judge_task_response_async(
    task: str,
    response: str,
    expected_facts: list[str] | None = None,
    *,
    tracker: CostTracker | None = None,
) -> dict[str, Any]:
    """Ask an LLM whether the agent's reply answered the task.

    Returns: {"passed": bool, "reason": str, "judge_model": str|None}
    """
    if not MODEL_CHAIN:
        return {
            "passed": False,
            "reason": "no LLM providers configured for judge",
            "judge_model": None,
        }
    tracker = tracker or CostTracker()
    messages = _build_judge_prompt(task, response, expected_facts)
    try:
        verdict = await llm_call_json(
            messages,
            tracker,
            temperature=0.0,
            max_tokens=200,
        )
    except Exception as exc:
        logger.warning("judge cascade raised: %s", exc)
        return {"passed": False, "reason": f"judge raised: {exc}", "judge_model": None}

    if isinstance(verdict, DegradedResponse):
        return {
            "passed": False,
            "reason": "every provider in the judge cascade was unavailable",
            "judge_model": None,
        }
    if not isinstance(verdict, dict):
        return {
            "passed": False,
            "reason": f"judge returned non-dict: {str(verdict)[:120]}",
            "judge_model": None,
        }

    passed = bool(verdict.get("passed"))
    reason = str(verdict.get("reason") or "")[:240]
    return {
        "passed": passed,
        "reason": reason,
        "judge_model": verdict.get("judge_model"),
    }


def judge_task_response(
    task: str,
    response: str,
    expected_facts: list[str] | None = None,
) -> dict[str, Any]:
    """Sync wrapper. Callers in async contexts should use the _async form
    directly."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is None:
        return asyncio.run(
            judge_task_response_async(task, response, expected_facts=expected_facts)
        )
    # We're inside a running loop. Schedule on a new thread.
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(
            asyncio.run,
            judge_task_response_async(task, response, expected_facts=expected_facts),
        )
        return fut.result()


__all__ = ["judge_task_response", "judge_task_response_async"]
