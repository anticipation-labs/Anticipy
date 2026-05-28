"""
Goal decomposition.

Two entry points:

  - plan_task(goal, tracker) — legacy URL/sub-goals/success-string shape,
    still used by ``app/agent.py`` and friends.

  - plan(task, initial_axtree_or_dom, user_id) — new multi-agent shape:
    returns a structured ``Plan`` with 3-7 steps (each with goal +
    success_criteria), explicit ``required_facts`` for the verifier, and
    an ``unreachable`` short-circuit. Routed through the role-keyed cascade
    so the planner runs on a *different* model from the executor (multi-
    agent diversity prevents single-model rationalization).

WIRE-ME: ``app/agent.py`` should call ``plan(...)`` once at task start, then:
  - if ``Plan.unreachable``: short-circuit with ``Plan.unreachable_reason``
    as the wearer message;
  - otherwise pass ``Plan.required_facts`` to the verifier and
    ``Plan.steps`` to the executor's loop.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from app.models import (
    CostTracker,
    DegradedResponse,
    llm_call_json,
)


logger = logging.getLogger("engine.planner")

PLAN_TEMPLATE = (
    'You are a web task planner. Given a user goal, produce a plan.\n\n'
    'Output ONLY valid JSON with these keys:\n'
    '- "url": the best starting URL for the task (use https://)\n'
    '- "sub_goals": array of 2-6 short action steps\n'
    '- "success": what the page should show when done\n\n'
    'User goal: '
)

# Schemes the agent is allowed to navigate to. Anything else (javascript:,
# data:, file:, chrome:, about:) is rejected outright and we fall back to a
# Google search.
_ALLOWED_SCHEMES = {"http", "https"}


def _is_safe_url(url: str) -> bool:
    """Return True if the URL is well-formed http(s) with a real host."""
    if not url or not isinstance(url, str):
        return False
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        return False
    if not parsed.netloc:
        return False
    # Reject loopback / link-local hosts so the agent doesn't poke our own
    # internal services if a user's prompt tricks the LLM into suggesting them.
    host = parsed.hostname or ""
    blocked_hosts = {
        "localhost", "127.0.0.1", "0.0.0.0", "::1",
        "metadata.google.internal", "169.254.169.254",
    }
    if host.lower() in blocked_hosts:
        return False
    if host.startswith("10.") or host.startswith("192.168.") or host.startswith("169.254."):
        return False
    return True


def _extract_url_from_goal(goal: str) -> str | None:
    """Extract an explicit URL or domain from the user's goal text."""
    # Match full URLs
    url_match = re.search(r'https?://\S+', goal)
    if url_match:
        candidate = url_match.group(0).rstrip('.,;)')
        if _is_safe_url(candidate):
            return candidate
        return None

    # Match domain names like "books.toscrape.com" or "opentable.com"
    domain_match = re.search(r'\b([\w-]+\.[\w-]+\.\w+|[\w-]+\.(?:com|org|net|io|ca|co|app|dev))\b', goal, re.IGNORECASE)
    if domain_match:
        candidate = "https://" + domain_match.group(0)
        if _is_safe_url(candidate):
            return candidate

    return None


async def plan_task(goal: str, tracker: CostTracker) -> dict:
    """
    Break a goal into a plan with starting URL, sub-goals, and success indicator.
    Returns a dict with keys: url, sub_goals, success.
    Falls back to a Google search if planning fails or the LLM proposes an
    unsafe URL.
    """
    if not goal or not goal.strip():
        return {
            "url": "https://www.google.com",
            "sub_goals": [],
            "success": "",
        }

    # First: try to extract URL directly from the goal text
    explicit_url = _extract_url_from_goal(goal)

    messages = [
        {
            "role": "user",
            "content": PLAN_TEMPLATE + goal[:200],
        }
    ]
    try:
        result = await llm_call_json(messages, tracker, temperature=0.0, max_tokens=200)
    except Exception:
        result = None

    if result and isinstance(result, dict) and "url" in result:
        url = result.get("url", "") or ""
        if isinstance(url, str) and url and not url.startswith("http"):
            url = "https://" + url
        # Validate URL safety before trusting it
        if not _is_safe_url(url):
            url = ""
        # Prefer explicit URL from goal if LLM gave a different domain
        if explicit_url and url:
            try:
                explicit_domain = urlparse(explicit_url).netloc
                llm_domain = urlparse(url).netloc
                if explicit_domain != llm_domain:
                    url = explicit_url
            except Exception:
                url = explicit_url
        elif explicit_url and not url:
            url = explicit_url
        if not url:
            url = explicit_url or "https://www.google.com"

        sub_goals_raw = result.get("sub_goals", [goal])
        sub_goals = (
            [str(g)[:200] for g in sub_goals_raw[:6]]
            if isinstance(sub_goals_raw, list)
            else [goal]
        )
        success = result.get("success", "Task completed")
        if not isinstance(success, str):
            success = "Task completed"
        return {
            "url": url,
            "sub_goals": sub_goals or [goal],
            "success": success[:200],
        }

    # Fallback: use explicit URL if found, otherwise Google search
    if explicit_url:
        return {
            "url": explicit_url,
            "sub_goals": [goal],
            "success": "Task completed",
        }

    search_query = re.sub(r"\s+", "+", goal.strip())[:80]
    # Strip any non-URL-safe chars defensively
    search_query = re.sub(r"[^\w+\-]", "", search_query)
    return {
        "url": f"https://www.google.com/search?q={search_query}",
        "sub_goals": [goal],
        "success": "Task completed",
    }


# ─────────────────────────────────────────────────────────────────────────
# New multi-agent Planner — structured Plan output, role-keyed LLM
# ─────────────────────────────────────────────────────────────────────────


@dataclass
class PlanStep:
    """One actionable step the executor should follow.

    success_criteria must be observable: URL contains, element appears,
    text appears in body, value extracted into the result message.
    """

    step: int
    goal: str
    success_criteria: str


@dataclass
class Plan:
    """Output of the new multi-agent planner.

    Attributes:
        steps: 3-7 ordered steps for the executor.
        required_facts: facts named by the user task that the executor
            MUST surface in its done() message — the verifier checks
            for them. Empty list when the task has none (e.g. "create a
            calendar event tomorrow at 3pm").
        unreachable: True when the planner judges the task genuinely
            unreachable from a non-authenticated browser state (banking,
            healthcare, captcha gate, account creation).
        unreachable_reason: One-sentence wearer-friendly explanation when
            unreachable=True. Empty otherwise.
        starting_url: Best-guess starting URL the executor should open.
            Falls back to a Google search when no URL was extractable.
        success: Plain-English description of what success looks like.
    """

    steps: list[PlanStep] = field(default_factory=list)
    required_facts: list[str] = field(default_factory=list)
    unreachable: bool = False
    unreachable_reason: str = ""
    starting_url: str = ""
    success: str = ""


# 3-7 step plan with success criteria, required facts, and an unreachable
# short-circuit. The executor consumes the steps; the verifier consumes the
# required_facts.
_PLANNER_SYSTEM = """\
You are the Planner in a multi-agent browser-automation team.

You are given:
  - <task>: the user's wearer-facing goal.
  - <initial_state>: the URL, title, and a compact snapshot of the page
    the executor is currently on (DOM excerpt or accessibility tree).

Your single output is a JSON plan that the Executor will follow step by
step. Another agent (the Verifier) will later check that what you listed
in required_facts actually appears in the executor's done() message and on
the relevant follow-up page.

Rules:
  - 3 to 7 steps. No more, no fewer. Steps are ordered.
  - Every step has BOTH "goal" (one short sentence) AND "success_criteria"
    (an observable check: URL contains, element appears, text appears in
    body, value extracted into the result message).
  - DO NOT hardcode site rules. Steps describe intent (e.g. "search for the
    item"); the executor figures out which selector to click.
  - required_facts: facts the USER named in the task (specific dates,
    proper nouns, exact prices, named people). Empty list if there are none.
  - Set unreachable=true only when the task genuinely cannot complete from a
    fresh, signed-out browser session (banking/healthcare with mandatory
    login, captcha gate the agent can't pass, account creation requiring
    real human KYC). Otherwise unreachable=false.
  - starting_url: the best opening URL for the task. Use https://. If you
    don't know, propose a Google search query URL.

Reply with strict JSON only, this shape:
{
  "steps": [
    {"step": 1, "goal": "...", "success_criteria": "..."},
    ...
  ],
  "required_facts": ["...", ...],
  "unreachable": false,
  "unreachable_reason": "",
  "starting_url": "https://...",
  "success": "<one sentence — what the wearer should see>"
}
"""


def _truncate_state(state: str, limit: int = 4000) -> str:
    """The accessibility-tree / DOM snapshot can be large; cap it so the
    prompt fits comfortably in any of the role chain's context windows."""
    if not isinstance(state, str):
        return ""
    if len(state) <= limit:
        return state
    head = state[: limit // 2]
    tail = state[-limit // 2 :]
    return f"{head}\n…[snipped {len(state) - limit} chars]…\n{tail}"


def _coerce_steps(raw: list | None) -> list[PlanStep]:
    """Coerce LLM output into PlanStep dataclasses.

    Trim to 7 max, drop invalid entries, renumber sequentially. Returns an
    empty list when nothing usable came back.
    """
    if not isinstance(raw, list):
        return []
    out: list[PlanStep] = []
    for idx, item in enumerate(raw[:7], start=1):
        if not isinstance(item, dict):
            continue
        goal = str(item.get("goal") or "").strip()
        criteria = str(item.get("success_criteria") or "").strip()
        if not goal or not criteria:
            continue
        out.append(PlanStep(step=idx, goal=goal[:200], success_criteria=criteria[:240]))
    return out


def _coerce_required_facts(raw) -> list[str]:
    if not isinstance(raw, list):
        return []
    facts: list[str] = []
    for f in raw:
        s = str(f or "").strip()
        if s and len(s) <= 200:
            facts.append(s)
    return facts


def _fallback_plan(task: str) -> Plan:
    """Heuristic plan for when the LLM cascade fails entirely.

    Re-uses ``plan_task``'s URL extraction to keep the executor moving even
    in degraded mode.
    """
    explicit = _extract_url_from_goal(task) if task else None
    if explicit:
        starting = explicit
    else:
        q = re.sub(r"\s+", "+", (task or "").strip())[:80]
        q = re.sub(r"[^\w+\-]", "", q)
        starting = f"https://www.google.com/search?q={q}" if q else "https://www.google.com"

    return Plan(
        steps=[
            PlanStep(step=1, goal="Open the relevant page",
                     success_criteria="Page loads with expected content visible"),
            PlanStep(step=2, goal="Locate the target element or action",
                     success_criteria="Target element is on the page"),
            PlanStep(step=3, goal="Complete the action and confirm result",
                     success_criteria="Confirmation text or expected effect appears"),
        ],
        required_facts=[],
        unreachable=False,
        unreachable_reason="",
        starting_url=starting,
        success="Task completed with visible confirmation",
    )


async def plan(
    task: str,
    initial_axtree_or_dom: str = "",
    user_id: str = "",
    *,
    tracker: CostTracker | None = None,
) -> Plan:
    """Produce a 3-7 step Plan for the given task.

    Routed through the role-keyed cascade: planner role → Gemini Flash
    primary, Cerebras / Groq / Kimi fallbacks. The executor uses a
    DIFFERENT chain (executor role → Cerebras primary, then Pixtral, etc.)
    so single-model rationalization is broken (cop-out #16).

    Args:
        task: user-facing goal. Trimmed to 600 chars in the prompt.
        initial_axtree_or_dom: snapshot of the page the executor is on at
            plan time. Used for grounding ("the search box is on the page").
            Pass empty string when no snapshot available.
        user_id: forwarded to cost_watch for the audit trail. May be empty.
        tracker: optional shared CostTracker. A fresh one is created when
            None.

    Returns:
        Plan dataclass. ``steps`` is non-empty (falls back to a 3-step
        heuristic when the LLM is unavailable).
    """
    task = (task or "").strip()
    if not task:
        return _fallback_plan(task)

    state_snippet = _truncate_state(initial_axtree_or_dom or "")

    user_payload = (
        f"<task>{task[:600]}</task>\n\n"
        f"<initial_state>\n{state_snippet or '(no snapshot)'}\n</initial_state>\n\n"
        "Output the JSON per your system prompt."
    )

    messages = [
        {"role": "system", "content": _PLANNER_SYSTEM},
        {"role": "user", "content": user_payload},
    ]

    tracker = tracker or CostTracker()

    try:
        result = await llm_call_json(
            messages,
            tracker,
            temperature=0.1,
            max_tokens=900,
            role="planner",
            user_id=user_id or None,
        )
    except Exception:
        logger.exception("planner cascade raised; falling back to heuristic plan")
        return _fallback_plan(task)

    if isinstance(result, DegradedResponse) or not isinstance(result, dict):
        logger.warning("planner cascade unavailable; returning heuristic plan")
        return _fallback_plan(task)

    steps = _coerce_steps(result.get("steps"))
    required_facts = _coerce_required_facts(result.get("required_facts"))

    unreachable = bool(result.get("unreachable", False))
    unreachable_reason = str(result.get("unreachable_reason") or "").strip()[:200]

    starting_url_raw = str(result.get("starting_url") or "").strip()
    # Only prefix https:// to bare-domain candidates ("example.com"). If the
    # value already carries a scheme — even a hostile one like javascript: —
    # leave it intact so the safety check below catches it.
    if starting_url_raw and "://" not in starting_url_raw and ":" not in starting_url_raw:
        starting_url_raw = "https://" + starting_url_raw
    if not _is_safe_url(starting_url_raw):
        # Prefer an explicit URL from the task itself; fall back to search.
        explicit = _extract_url_from_goal(task)
        if explicit:
            starting_url_raw = explicit
        else:
            q = re.sub(r"\s+", "+", task)[:80]
            q = re.sub(r"[^\w+\-]", "", q)
            starting_url_raw = (
                f"https://www.google.com/search?q={q}" if q else "https://www.google.com"
            )

    success = str(result.get("success") or "Task completed").strip()[:200]

    if unreachable and not unreachable_reason:
        unreachable_reason = "I can't complete this from a signed-out browser state."

    if not steps and not unreachable:
        # Shape valid but empty steps — fall back rather than ship an
        # executor that has nothing to do.
        logger.info("planner returned empty steps; using heuristic plan")
        fb = _fallback_plan(task)
        fb.required_facts = required_facts
        fb.starting_url = starting_url_raw or fb.starting_url
        fb.success = success or fb.success
        return fb

    return Plan(
        steps=steps,
        required_facts=required_facts,
        unreachable=unreachable,
        unreachable_reason=unreachable_reason,
        starting_url=starting_url_raw,
        success=success,
    )


__all__ = [
    "plan_task",
    "plan",
    "Plan",
    "PlanStep",
]
