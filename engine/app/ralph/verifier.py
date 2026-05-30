"""Two-layer verification for the Ralph loop (Phase 4-4).

Layer 1 — Cheap deterministic, per step:
    verify_step(pre_state_hash, post_state_hash, expected_url=None,
                expected_url_pattern=None, expected_selector=None,
                current_url=None, current_dom=None) -> bool

    Cost: $0. Catches ~90% of step failures by checking that the page
    actually changed (DOM hash flipped), the URL matches an expected
    pattern, and an expected post-action selector is present.

Layer 2 — Vision judge, end-of-goal only:
    judge_goal(goal_text, final_screenshot_path, *, llm=None) -> dict

    Cost: ~$0.0003 per call. Asks a multimodal LLM:
        "Did this complete the goal '$GOAL'? Be initially doubtful.
         Answer with one of: success | impossible_task |
         reached_captcha | needs_more_steps."

    The llm argument is duck-typed. If not provided we try to import
    app.action_engine.vision_verifier.VisionVerifier at call time; if
    that import fails (Phase 7 not landed yet, or in unit tests) we
    return verdict='needs_more_steps' rather than blow up. The Ralph
    loop interprets needs_more_steps as "do not yet mark done".

    Tests mock the llm via the explicit argument so no real network
    calls happen.

The verifier is pure / side-effect free; persistence belongs to the
loop module.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger("app.ralph.verifier")


VALID_VERDICTS: tuple[str, ...] = (
    "success",
    "impossible_task",
    "reached_captcha",
    "needs_more_steps",
)


@dataclass
class JudgeResult:
    """End-of-goal verdict, mirrors the dict returned by judge_goal()."""

    verdict: str
    reason: str = ""
    raw: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {"verdict": self.verdict, "reason": self.reason, "raw": self.raw}


# --- Layer 1: deterministic ---------------------------------------------


def _url_matches(current_url: Optional[str], expected: Optional[str], pattern: bool) -> bool:
    """Return True if expected is None (no constraint) or matches."""
    if expected is None:
        return True
    if not current_url:
        return False
    if pattern:
        try:
            return bool(re.search(expected, current_url))
        except re.error:
            logger.warning("invalid regex for expected_url_pattern: %s", expected)
            return False
    return expected in current_url


def verify_step(
    pre_state_hash: Optional[str],
    post_state_hash: Optional[str],
    *,
    expected_url: Optional[str] = None,
    expected_url_pattern: Optional[str] = None,
    expected_selector: Optional[str] = None,
    current_url: Optional[str] = None,
    current_dom: Optional[str] = None,
    require_state_change: bool = True,
) -> bool:
    """Cheap deterministic step verification.

    Args:
        pre_state_hash:  normalized DOM+URL hash captured before the
                         action (may be None for the first step).
        post_state_hash: normalized DOM+URL hash captured after the
                         action (None means the executor never
                         re-snapshotted; counts as failure).
        expected_url:    substring expected in the post-action URL.
        expected_url_pattern: regex expected to match the post-action
                         URL. Mutually exclusive with expected_url
                         (if both given, pattern wins).
        expected_selector: substring expected to appear in current_dom
                         after the action.
        current_url:     URL after the action.
        current_dom:     normalized DOM after the action.
        require_state_change: when True (default), pre == post means
                         the action didn't move the page; treat as
                         failure unless other checks override.

    Returns True iff every supplied check passes. None checks are
    skipped. If the caller supplies no checks at all, returns True.
    """
    # post_state_hash must exist; absence means the executor never
    # re-snapshotted, which we treat as failure (action might not have
    # run).
    if post_state_hash is None:
        return False

    if require_state_change and pre_state_hash is not None:
        if pre_state_hash == post_state_hash:
            return False

    if expected_url_pattern is not None:
        if not _url_matches(current_url, expected_url_pattern, pattern=True):
            return False
    elif expected_url is not None:
        if not _url_matches(current_url, expected_url, pattern=False):
            return False

    if expected_selector is not None:
        if not current_dom or expected_selector not in current_dom:
            return False

    return True


# --- Layer 2: vision judge ---------------------------------------------


_JUDGE_SYSTEM_PROMPT = (
    "You are an end-of-goal verifier for an autonomous browser agent. "
    "You receive a goal description and a final screenshot. "
    "Be initially DOUBTFUL: assume the agent failed unless the "
    "screenshot is clear proof of completion. "
    "Reply with strict JSON only (no markdown), shape: "
    '{"verdict": "<one of success|impossible_task|reached_captcha|needs_more_steps>", '
    '"reason": "<short justification, <=140 chars>"}'
)


def _parse_judge_reply(raw: str) -> JudgeResult:
    """Tolerantly parse a JSON verdict from the LLM."""
    if not raw or not raw.strip():
        return JudgeResult(verdict="needs_more_steps", reason="empty reply", raw=raw)
    # Strip code fences if any.
    s = raw.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?", "", s, count=1).strip()
        if s.endswith("```"):
            s = s[:-3].strip()
    # Try strict parse first.
    try:
        data = json.loads(s)
    except json.JSONDecodeError:
        # Look for the first {...} block.
        m = re.search(r"\{.*\}", s, re.DOTALL)
        if not m:
            return JudgeResult(
                verdict="needs_more_steps", reason="unparseable judge reply", raw=raw
            )
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return JudgeResult(
                verdict="needs_more_steps", reason="unparseable JSON in judge reply", raw=raw
            )
    verdict = str(data.get("verdict") or "").strip().lower().replace("-", "_")
    if verdict not in VALID_VERDICTS:
        # Map common synonyms.
        if verdict in ("done", "ok", "yes", "complete", "completed"):
            verdict = "success"
        elif verdict in ("captcha",):
            verdict = "reached_captcha"
        elif verdict in ("no", "incomplete", "more", "more_steps"):
            verdict = "needs_more_steps"
        elif verdict in ("impossible", "blocked"):
            verdict = "impossible_task"
        else:
            return JudgeResult(
                verdict="needs_more_steps",
                reason=f"unknown verdict '{verdict}'",
                raw=raw,
            )
    reason = str(data.get("reason") or "")[:240]
    return JudgeResult(verdict=verdict, reason=reason, raw=raw)


def judge_goal(
    goal_text: str,
    final_screenshot_path: Optional[str],
    *,
    llm: Optional[Any] = None,
    final_dom: Optional[str] = None,
) -> JudgeResult:
    """Ask the vision judge whether the goal completed.

    Args:
        goal_text:      the original goal sentence.
        final_screenshot_path: path to a PNG/JPEG of the final page.
                        May be None (we still ask, with text only).
        llm:            duck-typed object exposing one of:
                          - .judge_goal(goal, screenshot_path) -> str
                          - .chat(prompt) -> object with .content / .text
                          - callable(prompt) -> str
                        If None, the function attempts an import
                        fallback at call time and degrades to
                        needs_more_steps when no LLM is available.
        final_dom:      optional text snapshot of the page to give
                        the judge extra context (no images required).

    Returns a JudgeResult.
    """
    if llm is None:
        llm = _try_import_default_llm()
    if llm is None:
        logger.info("no LLM available for judge_goal; returning needs_more_steps")
        return JudgeResult(
            verdict="needs_more_steps",
            reason="no judge LLM available",
            raw=None,
        )

    prompt = _build_judge_prompt(goal_text, final_screenshot_path, final_dom)

    raw: Optional[str] = None
    try:
        # 1. Preferred: a custom .judge_goal(...) interface.
        if hasattr(llm, "judge_goal"):
            raw = str(llm.judge_goal(goal_text, final_screenshot_path))
        # 2. .chat({...}) -> response object.
        elif hasattr(llm, "chat"):
            resp = llm.chat(prompt)
            raw = getattr(resp, "content", None) or getattr(resp, "text", None) or str(resp)
        # 3. Plain callable.
        elif callable(llm):
            raw = str(llm(prompt))
        else:
            return JudgeResult(
                verdict="needs_more_steps",
                reason=f"llm object of type {type(llm).__name__} has no chat/judge interface",
                raw=None,
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("judge_goal LLM call failed: %s", exc)
        return JudgeResult(
            verdict="needs_more_steps",
            reason=f"judge LLM raised: {exc}",
            raw=None,
        )

    return _parse_judge_reply(raw or "")


def _build_judge_prompt(
    goal_text: str,
    final_screenshot_path: Optional[str],
    final_dom: Optional[str],
) -> dict[str, Any]:
    """Construct the prompt payload. Shape mirrors llm_judge's style."""
    user_lines: list[str] = [
        f"GOAL: {goal_text.strip()[:500]}",
    ]
    if final_screenshot_path:
        user_lines.append(f"FINAL_SCREENSHOT: {final_screenshot_path}")
    if final_dom:
        user_lines.append(f"FINAL_DOM_SNIPPET (first 1KB):\n{final_dom[:1024]}")
    user_lines.append("Did the agent complete the goal? JSON only.")
    return {
        "system": _JUDGE_SYSTEM_PROMPT,
        "user": "\n\n".join(user_lines),
        "screenshot_path": final_screenshot_path,
    }


def _try_import_default_llm() -> Optional[Any]:
    """Best-effort: load the project's default vision judge if present.

    Phase 7 will land an official llm_router. Until then we look for
    app.action_engine.vision_verifier.VisionVerifier. Failures are
    swallowed; the caller degrades to needs_more_steps.
    """
    try:
        from app.action_engine.vision_verifier import VisionVerifier  # type: ignore
    except Exception:  # noqa: BLE001
        return None
    try:
        return VisionVerifier()
    except Exception:  # noqa: BLE001
        return None


__all__ = [
    "JudgeResult",
    "VALID_VERDICTS",
    "judge_goal",
    "verify_step",
]
