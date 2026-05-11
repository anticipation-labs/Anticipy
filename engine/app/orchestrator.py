"""
Orchestrator — the agent loop that drives the multi-agent quality
scaffolding over a thin-relay browser bridge.

This module is the GLUE between:

    extension_v2 (WSBridge over /ws/agent)
                ↑                ↓
                │  commands  /  results
                │
    orchestrator.run_task(...)
                │
                ├─ trajectory_cache.cache_hit_for() — replay-on-near-dup
                ├─ planner.plan()                  — 3-7 step Plan
                ├─ MemoryStore.search()            — wearer-context block
                ├─ get_few_shot_examples()         — past-trajectory exemplars
                ├─ executor (llm_call_json, role="executor")
                ├─ critic.criticize()              — per-step verdict
                ├─ DynamicBudget.step_outcome()    — soft/hard caps + no-progress
                ├─ reflector.reflect()             — pivot/abort after stall
                └─ verifier.verify_at_done()       — deterministic effect check

Cop-out coverage:
  - #4 (no fixed step ceiling): DynamicBudget owns termination.
  - #6 (silent half-completion): verify_at_done is mandatory.
  - #8 (trusting the executor's done): we re-fetch state via the bridge.
  - #10 (per-site rules): every code path is generic.
  - #14/#15 (no audit / silent overspend): cost_watch.assert_under_cap()
    runs once at task start; provider chains log every paid call.
  - #16 (single-model rationalization): planner / critic / reflector /
    executor are role-keyed onto different model families.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from urllib.parse import urlparse

from app import critic as critic_mod
from app import planner as planner_mod
from app import reflector as reflector_mod
from app import trajectory_cache
from app import verifier as verifier_mod
from app.cost_watch import CostCapExceeded, assert_under_cap
from app.dynamic_budget import DynamicBudget
from app.memory import MemoryStore, make_memory_store
from app.models import CostTracker, DegradedResponse, llm_call_json
from app.planner import Plan, PlanStep
from app.ws_bridge import (
    BridgeClosed,
    BridgeTimeout,
    CommandFailed,
    TaskCancelled,
    WSBridge,
)


logger = logging.getLogger("engine.orchestrator")


# ── Message templates ──────────────────────────────────────────────────
# Wearer-facing strings live here so the orchestrator never accidentally
# leaks JSON, model names, or stack traces. messages.py covers the legacy
# /ws/task path; these are short, declarative versions for the streaming
# popup.

_MSG_PLAN_DONE = "Plan ready — starting now."
_MSG_PLAN_UNREACHABLE = "I can't complete this from a signed-out browser."
_MSG_BUDGET_STOP = "I've spent enough effort on this — stopping cleanly."
_MSG_VERIFIER_FAIL = (
    "I started but couldn't fully confirm it finished. Want me to retry?"
)
_MSG_REFLECTOR_ABORT = (
    "I couldn't make this work. Want to try again with a different approach?"
)
_MSG_COST_CAP = (
    "Spending cap reached this month — engine paused until reset."
)
_MSG_GENERIC_FAILURE = (
    "Something went wrong on my end. Please try again in a moment."
)
_MSG_CACHE_HIT_REPLAY = "I've done this before — replaying the known steps."
_MSG_CRITIC_UNSAFE = "Stopping — that action would be unsafe to take."


# ── Public result shape ────────────────────────────────────────────────


@dataclass
class TaskOutcome:
    """The orchestrator's flat return type. ``success=True`` means the
    deterministic verifier confirmed the effect surface; ``False`` means
    we're surfacing an honest failure (verifier rejected, reflector
    aborted, budget stop, cost cap, cancel)."""

    success: bool
    message: str
    deliverable: dict | None = None
    task_kind: str = "generic"
    steps_taken: int = 0
    cache_hit: bool = False
    aborted_reason: str = ""

    def to_dict(self) -> dict:
        return {
            "success": bool(self.success),
            "message": self.message,
            "deliverable": self.deliverable,
            "task_kind": self.task_kind,
            "steps_taken": int(self.steps_taken),
            "cache_hit": bool(self.cache_hit),
            "aborted_reason": self.aborted_reason or "",
        }


# ── task_kind heuristic ────────────────────────────────────────────────


# Phase-1 heuristic: keyword/phrase matches mapped to the seven verified
# kinds in end_state_verifier. Each kind has REQUIRED phrases (any
# substring match wins) AND optional CO-WORDS (all of which must appear
# anywhere in the task for the kind to fire). Phase-2 will add an LLM
# router so we don't miss colloquialisms like "shoot Sarah a note".
_TASK_KIND_RULES: list[tuple[str, tuple[str, ...], tuple[tuple[str, ...], ...]]] = [
    # email_send — the strongest single signal is "email" / "draft" / "compose".
    # "send" alone is too broad (you can send messages, comments, forms).
    ("email_send",
        ("email", "draft", "compose", "reply", "forward"),
        (("send", "message"),),
    ),
    ("calendar_create",
        ("create event", "schedule", "calendar", "meeting",
         "book a meeting", "add event"),
        (),
    ),
    ("comment_post",
        ("comment", "post a comment", "reply on", "leave a note"),
        (),
    ),
    # cart_add — primary phrase is "add to cart"; co-word fallback for
    # "add … cart" (e.g. "add the milk to my cart").
    ("cart_add",
        ("add to cart", "buy", "purchase", "checkout", "place order"),
        (("add", "cart"),),
    ),
    ("form_submit",
        ("submit", "fill out the form", "fill the form", "submit a form",
         "register", "sign up for"),
        (),
    ),
    ("read_extract",
        ("find", "what is", "what's", "tell me", "look up", "extract",
         "price of", "headline", "search for", "summary of"),
        (),
    ),
]


def classify_task_kind(task_text: str) -> str:
    """Best-effort categorisation of the user's task.

    Returns one of the keys in ``end_state_verifier._DISPATCH``:
    ``read_extract``, ``email_send``, ``calendar_create``, ``comment_post``,
    ``cart_add``, ``form_submit``, ``generic``.

    Phase-1 keyword/co-word heuristic. Earlier kinds in
    ``_TASK_KIND_RULES`` win on overlap.
    """
    if not isinstance(task_text, str) or not task_text.strip():
        return "generic"
    blob = task_text.lower()
    for kind, phrases, co_word_groups in _TASK_KIND_RULES:
        for p in phrases:
            if p in blob:
                return kind
        for group in co_word_groups:
            if all(w in blob for w in group):
                return kind
    return "generic"


# ── Executor ───────────────────────────────────────────────────────────


_EXECUTOR_SYSTEM = """\
You are the Executor in a multi-agent browser-automation team.

You drive a real browser through a thin DOM bridge. Your job each turn is
to choose ONE next action, given:

  - <task>: the wearer's overall goal.
  - <plan>: the ordered steps from the Planner.
  - <step_idx>: which plan step you're attempting.
  - <history>: a compact log of past actions and critic verdicts.
  - <state>: the current page (URL + title + truncated DOM).

Your ONE output is a JSON action. The bridge supports these primitives:

  - {"action": "navigate", "url": "..."}
  - {"action": "click", "selector": "css selector"}
  - {"action": "type", "selector": "...", "text": "...", "submit": false}
  - {"action": "extract", "selector": "..."}
  - {"action": "screenshot"}
  - {"action": "wait", "seconds": 1.5}
  - {"action": "done", "message": "...", "subject": "...", "title": "...",
     "answer": "...", "required_facts": ["..."]}

Rules:
  - Output STRICT JSON only — no markdown, no commentary.
  - Selectors are PURE CSS only. Browser `querySelector` is the engine —
    jQuery selectors will fail silently. Specifically:
      * NO `:contains("text")` — that's jQuery, not CSS.
      * NO `:has(... :contains(...))` chains.
    For text-targeting, prefer extracting a LARGER container (e.g.
    `.infobox` or `#mw-content-text`) and rely on the returned visible
    text. The "extract" action returns ALL visible text inside the
    selector — you can scan that text for the value you need before
    emitting `done`.
  - When you reach a page that has the answer, use a SINGLE broad
    extract on a parent container, then go straight to `done` with the
    answer pulled from the returned text.
  - PREFER DIRECT URL NAVIGATION over search-box typing for known topics:
      * Wikipedia: `navigate https://en.wikipedia.org/wiki/<Topic_With_Underscores>`
        e.g. "Eiffel Tower" → `https://en.wikipedia.org/wiki/Eiffel_Tower`
      * IMDb: `navigate https://www.imdb.com/find?q=<query>`
      * Amazon: `navigate https://www.amazon.com/s?k=<query>`
    Search-box typing is fragile (form-submit timing); direct nav is
    reliable.
  - CRITICAL: The "extract" action returns ALL VISIBLE TEXT of the
    selected element in the `result.text` field. After ANY successful
    extract that returns non-empty text, your NEXT action MUST be `done`
    with the answer parsed from that text. DO NOT repeat extract on
    different selectors hoping for a more targeted match — the text you
    have is enough; read it. If the answer is in `state` already, emit
    `done` immediately without another extract.
  - When the task is fact-finding, your "done" payload MUST include the
    answer and any required_facts the planner declared.
  - When the task involves an effect (sending, posting, adding), your
    "done" payload MUST include identifying fields the verifier will look
    for (e.g. ``subject``, ``title``, ``cart_url``, ``source_url``).
  - If the page asks for sign-in, payment, or a captcha you cannot solve,
    emit ``{"action": "done", "message": "blocked: <one sentence>"}``
    and let the verifier fail the task honestly.

Output shape:
  {"action": "...", ...}
"""


def _truncate(text: str, limit: int = 4000) -> str:
    if not isinstance(text, str):
        return ""
    if len(text) <= limit:
        return text
    head = text[: limit // 2]
    tail = text[-limit // 2 :]
    return f"{head}\n…[snipped {len(text) - limit} chars]…\n{tail}"


def _serialize_history(history: list[dict]) -> str:
    if not history:
        return "(no history)"
    lines: list[str] = []
    for h in history[-12:]:
        verdict = h.get("verdict", "?")
        action = h.get("action", "?")
        reason = h.get("reason", "")
        lines.append(f"  [{verdict}] {action} — {reason}"[:240])
    return "\n".join(lines)


def _serialize_plan(plan: Plan | None) -> str:
    if plan is None or not plan.steps:
        return "(no plan)"
    lines: list[str] = []
    for s in plan.steps:
        lines.append(f"  {s.step}. {s.goal} — success: {s.success_criteria}")
    return "\n".join(lines)


async def _executor_step(
    *,
    task: str,
    plan: Plan,
    step_idx: int,
    history: list[dict],
    state_snippet: str,
    user_id: str,
    nudge: str | None,
    tracker: CostTracker,
) -> dict | None:
    """Ask the Executor LLM for the next action.

    Returns the parsed action dict, or ``None`` when the cascade fails
    entirely (orchestrator treats that as a no_progress signal).
    """
    user_payload = (
        f"<task>{task[:600]}</task>\n\n"
        f"<plan>\n{_serialize_plan(plan)}\n</plan>\n\n"
        f"<step_idx>{step_idx}</step_idx>\n\n"
        f"<history>\n{_serialize_history(history)}\n</history>\n\n"
        f"<state>\n{_truncate(state_snippet)}\n</state>\n\n"
        "Output the JSON action now."
    )
    system = _EXECUTOR_SYSTEM
    if nudge:
        system = f"{system}\n\n[Budget nudge]\n{nudge}\n"
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_payload},
    ]
    try:
        result = await llm_call_json(
            messages,
            tracker,
            temperature=0.1,
            max_tokens=600,
            role="executor",
            user_id=user_id or None,
        )
    except Exception:
        logger.exception("executor cascade raised")
        return None
    if isinstance(result, DegradedResponse) or not isinstance(result, dict):
        logger.warning("executor cascade unavailable")
        return None
    return result


# ── Bridge dispatch for executor actions ───────────────────────────────


async def _apply_action(
    bridge: WSBridge,
    action: dict,
) -> dict:
    """Translate one executor action dict into bridge calls.

    Returns ``{"ok": bool, "result": ..., "error": ...}``. Never raises
    TaskCancelled — that propagates so the orchestrator unwinds cleanly.
    Other bridge errors (timeout, command failed) are caught and reflected
    as ``ok=False`` so the loop can keep going via the critic's
    no_progress branch.
    """
    verb = str((action or {}).get("action") or "").strip().lower()
    try:
        if verb == "navigate":
            url = str(action.get("url") or "")
            if not url:
                return {"ok": False, "error": "navigate missing url"}
            # Bridge `navigate` uses content.js's `window.location.href = url`,
            # which requires content.js to already be running in a NON-blank
            # tab. The seed tab created by ensureTabGroup is `about:blank`
            # which chrome.scripting.executeScript REFUSES to inject into.
            # Workaround: route navigate through bridge.create_tab — that
            # uses chrome.tabs.create({url}) which opens at the real URL,
            # bypassing the about:blank inject restriction entirely.
            data = await bridge.create_tab(url)
            # Settle for SSR + initial JS to land.
            await asyncio.sleep(4.0)
            return {"ok": True, "result": data}
        if verb == "click":
            sel = str(action.get("selector") or "")
            if not sel:
                return {"ok": False, "error": "click missing selector"}
            data = await bridge.click(sel)
            await asyncio.sleep(1.5)
            return {"ok": True, "result": data}
        if verb == "type":
            sel = str(action.get("selector") or "")
            text = str(action.get("text") or "")
            submit = bool(action.get("submit", False))
            if not sel:
                return {"ok": False, "error": "type missing selector"}
            data = await bridge.type(sel, text, submit=submit)
            # type+submit triggers form submission → full page navigation.
            # 5s is generous but matches realistic page load time.
            if submit:
                await asyncio.sleep(5.0)
            return {"ok": True, "result": data}
        if verb == "extract":
            sel = action.get("selector")
            sel = str(sel) if isinstance(sel, str) else None
            fallback_chain = []
            text = ""
            # First try the requested selector. Catch BridgeTimeout / errors
            # here so we always run the fallback chain to body — outer except
            # block would otherwise short-circuit the fallback.
            try:
                text = await bridge.extract(sel) or ""
            except TaskCancelled:
                raise
            except Exception as e:
                fallback_chain.append(f"{sel!r} threw {type(e).__name__}: {str(e)[:80]}")
            # If empty or threw, retry after 2s
            if not text:
                fallback_chain.append(f"{sel!r} empty, retrying after 2s")
                await asyncio.sleep(2.0)
                try:
                    text = await bridge.extract(sel) or ""
                except TaskCancelled:
                    raise
                except Exception as e:
                    fallback_chain.append(f"retry {sel!r} threw {type(e).__name__}: {str(e)[:80]}")
            # If STILL empty, body fallback
            if not text:
                fallback_chain.append(f"{sel!r} retry empty, trying body")
                try:
                    text = await bridge.extract("body") or ""
                    fallback_chain.append(f"body returned {len(text)} chars")
                except TaskCancelled:
                    raise
                except Exception as e:
                    fallback_chain.append(f"body threw {type(e).__name__}: {str(e)[:80]}")
            logger.info("extract trace: sel=%r final_len=%d chain=%s", sel, len(text), fallback_chain)
            return {"ok": True, "result": {"text": text, "_debug_fallbacks": fallback_chain, "_engine_version": "v0511-fallback-catches-timeout"}}
        if verb == "screenshot":
            url = await bridge.screenshot()
            return {"ok": True, "result": {"dataUrl": url}}
        if verb == "wait":
            secs = float(action.get("seconds") or 1.0)
            secs = max(0.0, min(10.0, secs))
            await asyncio.sleep(secs)
            return {"ok": True, "result": {"waited": secs}}
        if verb == "done":
            return {"ok": True, "result": {"done": True}}
        return {"ok": False, "error": f"unknown action {verb!r}"}
    except TaskCancelled:
        raise
    except (BridgeTimeout, BridgeClosed, CommandFailed) as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:  # defensive — never let bridge bugs crash the loop
        logger.exception("bridge action raised: %s", verb)
        return {"ok": False, "error": str(exc)}


# ── Trajectory replay (cache hit) ──────────────────────────────────────


async def _replay_trajectory_steps(
    bridge: WSBridge,
    cached: dict,
) -> tuple[bool, list[dict]]:
    """Replay the actions from a near-duplicate cached trajectory.

    Returns ``(completed_ok, history)``. ``completed_ok`` is True when we
    reached an action of kind "done" without any bridge error.
    """
    raw_steps = cached.get("steps") or []
    if not isinstance(raw_steps, list) or not raw_steps:
        return False, []
    history: list[dict] = []
    for raw in raw_steps[:60]:  # absolute hard cap on cached replay
        if not isinstance(raw, dict):
            continue
        action = raw.get("action") if isinstance(raw.get("action"), dict) else raw
        if not isinstance(action, dict):
            continue
        verb = str(action.get("action") or "").lower()
        outcome = await _apply_action(bridge, action)
        history.append({
            "verdict": "replay",
            "action": action,
            "reason": "" if outcome.get("ok") else outcome.get("error", ""),
        })
        if not outcome.get("ok"):
            return False, history
        if verb == "done":
            return True, history
    return False, history


# ── Memory + few-shot context ──────────────────────────────────────────


def _format_few_shot(trajectories: list[dict]) -> str:
    if not trajectories:
        return ""
    lines = ["[Past similar tasks]"]
    for t in trajectories[:3]:
        summary = (t.get("task_summary") or "").strip()[:200]
        outcome = t.get("outcome") or "?"
        sim = float(t.get("similarity") or 0.0)
        lines.append(f"  - [{outcome} sim={sim:.2f}] {summary}")
    return "\n".join(lines)


def _format_memories(mems: list) -> str:
    if not mems:
        return ""
    lines = ["[Wearer context]"]
    for m in mems[:5]:
        kind = getattr(m, "kind", "?")
        key = getattr(m, "key", "?")
        value = getattr(m, "value", {})
        snippet = ""
        if isinstance(value, dict):
            snippet = (
                value.get("text")
                or value.get("name")
                or value.get("notes")
                or ""
            )
            snippet = str(snippet)[:120]
        lines.append(f"  - {kind}/{key}: {snippet}")
    return "\n".join(lines)


# ── The main loop ──────────────────────────────────────────────────────


async def run_task(
    task: str,
    user_id: str,
    bridge: WSBridge,
    task_id: str,
    *,
    memory_store: MemoryStore | None = None,
    monthly_cap_usd: float = 10.0,
    soft_cap: int = 30,
    hard_cap: int = 100,
) -> dict:
    """Run one task end-to-end. Returns ``TaskOutcome.to_dict()``.

    Args:
        task: wearer-facing goal in plain English.
        user_id: account id (matches engine_users.id).
        bridge: live ``WSBridge`` connected to the extension. The caller is
            responsible for spawning the inbound reader loop.
        task_id: opaque task identifier supplied by the extension; used
            only for logging.
        memory_store: injectable for tests. Defaults to the production
            store (Supabase if configured, in-process otherwise).
        monthly_cap_usd: passed straight to ``cost_watch.assert_under_cap``.
        soft_cap, hard_cap: forwarded to ``DynamicBudget``.

    Notes:
        - The orchestrator NEVER raises through to the caller; failures
          surface via ``TaskOutcome``. The only exception is
          ``TaskCancelled`` from the bridge, which propagates so the route
          handler can close the WebSocket cleanly.
    """
    started_ts = time.time()
    task_kind = classify_task_kind(task)
    tracker = CostTracker()
    # Tracks whether trajectory has been persisted yet. Helps the early-
    # exit paths (max_pivots, reflector_abort, verifier mismatch, plan
    # unreachable, cost cap) ALL produce a row instead of just the
    # verifier-completion paths.
    _traj_written = [False]

    async def _stream(step: int, message: str) -> None:
        try:
            await bridge.stream_step(step, message)
        except Exception:
            pass

    # ── 0. Pre-flight: cost cap ────────────────────────────────────────
    try:
        await assert_under_cap(monthly_cap_usd=float(monthly_cap_usd))
    except CostCapExceeded:
        logger.warning("orchestrator: cost cap exceeded; pausing engine")
        return TaskOutcome(
            success=False,
            message=_MSG_COST_CAP,
            task_kind=task_kind,
            aborted_reason="cost_cap",
        ).to_dict()
    except Exception:
        # Never let cost_watch errors block real work — log + proceed.
        logger.exception("orchestrator: cost_watch.assert_under_cap raised")

    # ── 1. Trajectory cache: near-duplicate short-circuit ──────────────
    try:
        cached = await trajectory_cache.cache_hit_for(user_id, task)
    except Exception:
        logger.exception("orchestrator: cache_hit_for raised")
        cached = None

    if cached:
        await _stream(0, _MSG_CACHE_HIT_REPLAY)
        replayed_ok, replay_history = await _replay_trajectory_steps(bridge, cached)
        if replayed_ok:
            # Still verify — replay can't claim success without re-checking
            # the effect surface (cop-out #8).
            try:
                done_payload = _last_done_payload(replay_history) or {}
                verification = await verifier_mod.verify_at_done(
                    task_kind=task_kind,
                    task_text=task,
                    agent_done_payload=done_payload,
                    bridge=bridge,
                    user_id=user_id,
                )
            except TaskCancelled:
                raise
            except Exception:
                logger.exception("orchestrator: verifier raised on cache replay")
                verification = None

            if verification is not None and verification.passed:
                outcome = TaskOutcome(
                    success=True,
                    message=str(_last_done_message(replay_history) or "Done."),
                    deliverable=done_payload,
                    task_kind=task_kind,
                    steps_taken=len(replay_history),
                    cache_hit=True,
                )
                await _record_trajectory(
                    user_id=user_id,
                    task=task,
                    history=replay_history,
                    outcome="success",
                    started_ts=started_ts,
                    cost_usd=tracker.total_usd if hasattr(tracker, "total_usd") else 0.0,
                    intent_id=task_id,
                )
                return outcome.to_dict()
        # Replay failed verification — fall through to a normal plan.
        logger.info("orchestrator: cache replay rejected by verifier; full plan")

    # ── 2. Plan ────────────────────────────────────────────────────────
    # Snapshot the current page so the planner has grounding state.
    try:
        initial_dom = await bridge.get_dom_snapshot()
    except TaskCancelled:
        raise
    except Exception:
        logger.exception("orchestrator: initial DOM snapshot failed")
        initial_dom = ""

    # Inject wearer context + few-shot examples into the planner prompt.
    mem_store = memory_store or make_memory_store(prefer_supabase=True)
    try:
        memories = await mem_store.search(user_id, task, k=5)
    except Exception:
        logger.exception("orchestrator: memory search raised")
        memories = []
    try:
        few_shots = await trajectory_cache.get_few_shot_examples(
            user_id, task, k=3
        )
    except Exception:
        logger.exception("orchestrator: few-shot retrieval raised")
        few_shots = []

    augmented_state = "\n\n".join(filter(None, [
        _format_memories(memories),
        _format_few_shot(few_shots),
        f"[Initial page state]\n{_truncate(initial_dom, 3000)}",
    ]))

    try:
        plan = await planner_mod.plan(
            task=task,
            initial_axtree_or_dom=augmented_state,
            user_id=user_id,
            tracker=tracker,
        )
    except TaskCancelled:
        raise
    except Exception:
        logger.exception("orchestrator: planner raised")
        plan = planner_mod._fallback_plan(task)  # type: ignore[attr-defined]

    if plan.unreachable:
        msg = plan.unreachable_reason or _MSG_PLAN_UNREACHABLE
        return TaskOutcome(
            success=False,
            message=msg,
            task_kind=task_kind,
            aborted_reason="plan_unreachable",
        ).to_dict()

    await _stream(1, _MSG_PLAN_DONE)

    # Open the plan's starting URL if we don't already match it.
    if plan.starting_url:
        try:
            current_url = await bridge.get_url()
        except TaskCancelled:
            raise
        except Exception:
            current_url = ""
        if not _same_origin(current_url, plan.starting_url):
            try:
                await bridge.navigate(plan.starting_url)
            except TaskCancelled:
                raise
            except Exception:
                logger.exception("orchestrator: starting nav failed")

    # ── 3. Plan → execute → critic loop ────────────────────────────────
    budget = DynamicBudget(soft_cap=soft_cap, hard_cap=hard_cap)
    history: list[dict] = []

    async def _exit_with_record(
        outcome_obj: TaskOutcome,
        outcome_str: str = "fail",
    ) -> dict:
        """Write a trajectory row then return the TaskOutcome dict. Use this
        for every early-exit return so we never lose visibility on aborts.
        Reads `history` from the enclosing closure.
        """
        if not _traj_written[0]:
            try:
                await _record_trajectory(
                    user_id=user_id,
                    task=task,
                    history=history,
                    outcome=outcome_str,
                    started_ts=started_ts,
                    cost_usd=getattr(tracker, "total_usd", 0.0) or 0.0,
                    outcome_message=outcome_obj.message or "",
                )
                _traj_written[0] = True
            except Exception:
                logger.exception("_exit_with_record: trajectory write failed")
        return outcome_obj.to_dict()

    consecutive_no_progress = 0
    pending_nudge: str | None = None
    last_done_payload: dict | None = None
    last_done_message: str = ""
    # Hard-cap pivots. Reflector resetting consecutive_no_progress=0 each
    # pivot can otherwise loop forever. After 2 pivots without success
    # we abort hard.
    reflector_pivots_used = 0
    MAX_PIVOTS = 2
    # Carry the most recent extract's text into the next executor's state
    # context, otherwise the agent can't see what it just extracted and
    # re-extracts the same selector forever.
    last_extract_text: str = ""

    step_idx = 0
    while True:
        step_idx += 1
        if bridge.cancelled:
            raise TaskCancelled(bridge.cancel_reason or "cancelled")

        # Snapshot before the action — needed for critic.
        try:
            before_state = await bridge.get_dom_snapshot()
            before_url = await bridge.get_url()
        except TaskCancelled:
            raise
        except Exception:
            before_state = ""
            before_url = ""

        # Map plan-relative step index — the planner has 3-7 steps, but the
        # executor may need multiple actions per step. Best-effort map.
        plan_step_idx = min(step_idx, len(plan.steps)) if plan.steps else step_idx

        # Stitch the last extract's returned text into state so the
        # executor can SEE what it just extracted and emit done with the
        # answer instead of re-extracting forever.
        state_for_executor = before_state or before_url
        if last_extract_text:
            state_for_executor = (
                f"<last_extract_text>\n{_truncate(last_extract_text, 6000)}\n</last_extract_text>\n\n"
                f"{state_for_executor}"
            )
        action = await _executor_step(
            task=task,
            plan=plan,
            step_idx=plan_step_idx,
            history=history,
            state_snippet=state_for_executor,
            user_id=user_id,
            nudge=pending_nudge,
            tracker=tracker,
        )
        pending_nudge = None  # consumed

        if action is None:
            history.append({"verdict": "no_progress", "action": "(executor unavailable)", "reason": "cascade failed"})
            consecutive_no_progress += 1
            decision = budget.step_outcome(step_idx, made_progress=False)
            if not decision.should_continue:
                await _stream(step_idx, decision.reason)
                break
            if consecutive_no_progress >= 2:
                if reflector_pivots_used >= MAX_PIVOTS:
                    # Hard stop — keep going past 2 pivots = wasted LLM calls.
                    return await _exit_with_record(TaskOutcome(
                        success=False,
                        message="Couldn't make progress after 2 pivots. Stopping.",
                        task_kind=task_kind,
                        steps_taken=step_idx,
                        aborted_reason="max_pivots",
                    ))
                outcome = await _maybe_reflect(
                    task=task,
                    plan=plan,
                    history=history,
                    bridge=bridge,
                    user_id=user_id,
                    tracker=tracker,
                )
                if outcome is not None:
                    plan, abort = outcome
                    if abort:
                        return await _exit_with_record(TaskOutcome(
                            success=False,
                            message=abort,
                            task_kind=task_kind,
                            steps_taken=step_idx,
                            aborted_reason="reflector_abort",
                        ))
                    consecutive_no_progress = 0
                    reflector_pivots_used += 1
                else:
                    # Reflector returned None (LLM cascade failed). Treat
                    # as a "soft pivot" — increment the counter so the
                    # MAX_PIVOTS guard fires instead of looping forever.
                    reflector_pivots_used += 1
                    consecutive_no_progress = 0
            continue

        verb = str(action.get("action") or "").lower()
        await _stream(step_idx, _action_to_message(action))

        # Capture done payload BEFORE applying the action — done is a
        # signalling action with no bridge effect.
        if verb == "done":
            last_done_payload = dict(action)
            last_done_message = str(action.get("message") or "Done.")
            history.append({
                "verdict": "done",
                "action": action,
                "reason": last_done_message,
            })
            break

        outcome = await _apply_action(bridge, action)

        # If this was an extract, hold onto the returned text so the next
        # executor step can see it (so the agent doesn't re-extract).
        if verb == "extract" and outcome.get("ok"):
            txt = ""
            try:
                txt = str(outcome.get("result", {}).get("text") or "")
            except Exception:
                txt = ""
            if txt:
                last_extract_text = txt
        elif verb in ("navigate", "click", "type"):
            # New page = old extract text is stale; clear.
            last_extract_text = ""

        try:
            after_state = await bridge.get_dom_snapshot()
            after_url = await bridge.get_url()
        except TaskCancelled:
            raise
        except Exception:
            after_state = ""
            after_url = ""

        # Deterministic verdict overrides for actions where the critic
        # would otherwise misread the page-state diff:
        #   - extract returning non-empty text IS progress (DOM doesn't
        #     change but we have new information). The critic would call
        #     it no_progress because before_state == after_state.
        #   - Only call the LLM critic when the verdict isn't obvious.
        if verb == "extract" and last_extract_text:
            verdict = critic_mod.CriticResult(
                verdict="progress",
                reason=f"extract returned {len(last_extract_text)} chars of text",
            )
        elif verb == "extract" and not last_extract_text:
            verdict = critic_mod.CriticResult(
                verdict="no_progress",
                reason="extract returned no text — selector likely missed",
            )
        else:
            # Critic verdict (LLM-based for non-extract actions)
            try:
                verdict = await critic_mod.criticize(
                    action_taken=action,
                    before_state=before_state or before_url,
                    after_state=after_state or after_url,
                    plan=plan,
                    step_idx=plan_step_idx,
                    user_id=user_id,
                    tracker=tracker,
                )
            except TaskCancelled:
                raise
            except Exception:
                logger.exception("orchestrator: critic raised")
                verdict = critic_mod.CriticResult(
                    verdict="no_progress",
                    reason="critic raised",
                    confidence=0.0,
                )

        # Stash debug info from outcome.result into reason for extract
        # so failed runs in Supabase show WHY extract returned empty.
        reason_str = verdict.reason or (outcome.get("error") or "")
        if verb == "extract":
            result_dict = outcome.get("result", {}) if isinstance(outcome.get("result"), dict) else {}
            ver = result_dict.get("_engine_version", "OLD-NO-VERSION-MARKER")
            dbg = result_dict.get("_debug_fallbacks", [])
            reason_str = f"{reason_str} | ver={ver} | dbg={dbg}"
        history.append({
            "verdict": verdict.verdict,
            "action": action,
            "reason": reason_str,
        })

        # Hard-stops
        if verdict.verdict == "unsafe":
            await _stream(step_idx, _MSG_CRITIC_UNSAFE)
            return await _exit_with_record(TaskOutcome(
                success=False,
                message=verdict.reason or _MSG_CRITIC_UNSAFE,
                task_kind=task_kind,
                steps_taken=step_idx,
                aborted_reason="critic_unsafe",
            ))

        if verdict.verdict == "done":
            last_done_payload = dict(action)
            last_done_message = str(action.get("message") or "Done.")
            break

        made_progress = verdict.verdict == "progress"
        if made_progress:
            consecutive_no_progress = 0
        else:
            consecutive_no_progress += 1

        decision = budget.step_outcome(step_idx, made_progress=made_progress)
        if decision.nudge:
            pending_nudge = decision.nudge
        if not decision.should_continue:
            await _stream(step_idx, decision.reason)
            break

        # Reflection after 2 consecutive no_progress.
        if consecutive_no_progress >= 2:
            if reflector_pivots_used >= MAX_PIVOTS:
                return await _exit_with_record(TaskOutcome(
                    success=False,
                    message="Couldn't make progress after 2 pivots. Stopping.",
                    task_kind=task_kind,
                    steps_taken=step_idx,
                    aborted_reason="max_pivots",
                ))
            ref_outcome = await _maybe_reflect(
                task=task,
                plan=plan,
                history=history,
                bridge=bridge,
                user_id=user_id,
                tracker=tracker,
            )
            if ref_outcome is not None:
                plan, abort = ref_outcome
                if abort:
                    return await _exit_with_record(TaskOutcome(
                        success=False,
                        message=abort,
                        task_kind=task_kind,
                        steps_taken=step_idx,
                        aborted_reason="reflector_abort",
                    ))
                consecutive_no_progress = 0
                reflector_pivots_used += 1
            else:
                reflector_pivots_used += 1
                consecutive_no_progress = 0

    # ── 4. End-state verification ──────────────────────────────────────
    try:
        verification = await verifier_mod.verify_at_done(
            task_kind=task_kind,
            task_text=task,
            agent_done_payload=last_done_payload or {},
            bridge=bridge,
            user_id=user_id,
        )
    except TaskCancelled:
        raise
    except Exception:
        logger.exception("orchestrator: verify_at_done raised")
        verification = None

    if verification is None or not verification.passed:
        # Honest failure — never silently claim success.
        msg = (
            getattr(verification, "honest_message", "") or _MSG_VERIFIER_FAIL
        )
        await _record_trajectory(
            user_id=user_id,
            task=task,
            history=history,
            outcome="fail",
            outcome_message=msg,
            started_ts=started_ts,
            cost_usd=getattr(tracker, "total_usd", 0.0),
            intent_id=task_id,
        )
        return TaskOutcome(
            success=False,
            message=msg,
            task_kind=task_kind,
            steps_taken=step_idx,
            aborted_reason="verifier_failed",
        ).to_dict()

    # ── 5. Success path ────────────────────────────────────────────────
    await _record_trajectory(
        user_id=user_id,
        task=task,
        history=history,
        outcome="success",
        outcome_message=last_done_message,
        started_ts=started_ts,
        cost_usd=getattr(tracker, "total_usd", 0.0),
        intent_id=task_id,
    )

    return TaskOutcome(
        success=True,
        message=last_done_message or "Done.",
        deliverable=last_done_payload or None,
        task_kind=task_kind,
        steps_taken=step_idx,
    ).to_dict()


# ── Helpers ────────────────────────────────────────────────────────────


def _last_done_payload(history: list[dict]) -> dict | None:
    for h in reversed(history):
        action = h.get("action")
        if isinstance(action, dict) and (action.get("action") or "").lower() == "done":
            return action
    return None


def _last_done_message(history: list[dict]) -> str:
    p = _last_done_payload(history)
    if p:
        m = p.get("message")
        if isinstance(m, str) and m.strip():
            return m
    return ""


def _action_to_message(action: dict) -> str:
    """Render an executor action as a wearer-friendly progress string.

    Generic — never names sites or exposes selectors verbatim.
    """
    verb = str((action or {}).get("action") or "").lower()
    if verb == "navigate":
        return "Opening the page..."
    if verb == "click":
        return "Following a link..."
    if verb == "type":
        return "Filling in the details..."
    if verb == "extract":
        return "Reading the page..."
    if verb == "screenshot":
        return "Looking at the page..."
    if verb == "wait":
        return "Waiting for the page to load..."
    if verb == "done":
        msg = str(action.get("message") or "")
        return msg or "Wrapping up..."
    return "Working on the next step..."


def _same_origin(a: str, b: str) -> bool:
    if not a or not b:
        return False
    try:
        pa = urlparse(a)
        pb = urlparse(b)
        return (
            pa.scheme == pb.scheme
            and (pa.hostname or "").lower() == (pb.hostname or "").lower()
            and pa.path.rstrip("/") == pb.path.rstrip("/")
        )
    except Exception:
        return False


async def _maybe_reflect(
    *,
    task: str,
    plan: Plan,
    history: list[dict],
    bridge: WSBridge,
    user_id: str,
    tracker: CostTracker,
) -> tuple[Plan, str] | None:
    """Run the Reflector. Returns (new_plan, abort_message).

    - On ``pivot``: returns (new_plan, "")
    - On ``abort``: returns (plan, abort_message)  # plan unchanged
    - On ``continue`` or any failure: returns None — orchestrator keeps
      going with the original plan and the no-progress streak resets.
    """
    try:
        current_state = await bridge.get_dom_snapshot()
    except TaskCancelled:
        raise
    except Exception:
        current_state = ""

    # Build the (action, verdict) tuples reflector expects.
    history_for_ref: list[dict] = [
        {
            "action": h.get("action"),
            "verdict": h.get("verdict"),
            "reason": h.get("reason", ""),
        }
        for h in history
    ]

    try:
        result = await reflector_mod.reflect(
            task=task,
            current_plan=plan,
            history=history_for_ref,
            current_state=current_state,
            user_id=user_id,
            tracker=tracker,
        )
    except TaskCancelled:
        raise
    except Exception:
        logger.exception("orchestrator: reflector raised")
        return None

    if result.decision == "pivot" and result.new_plan is not None:
        logger.info(
            "orchestrator: reflector pivoted to new plan with %d steps",
            len(result.new_plan.steps),
        )
        return (result.new_plan, "")
    if result.decision == "abort":
        msg = result.abort_message or _MSG_REFLECTOR_ABORT
        return (plan, msg)
    return None


async def _record_trajectory(
    *,
    user_id: str,
    task: str,
    history: list[dict],
    outcome: str,
    started_ts: float,
    cost_usd: float,
    outcome_message: str = "",
    intent_id: str = "",
) -> None:
    """Persist the run to engine_trajectories. Never raises."""
    try:
        domain = _domain_from_history(history)
        steps_serializable = [
            {
                "verdict": h.get("verdict", "?"),
                "action": h.get("action") if isinstance(h.get("action"), dict) else str(h.get("action", "")),
                "reason": h.get("reason", ""),
            }
            for h in history
        ]
        await trajectory_cache.record_trajectory(
            user_id=user_id,
            task_summary=task[:500],
            domain=domain or "unknown",
            steps=steps_serializable,
            outcome=outcome,
            outcome_message=outcome_message,
            total_steps=len(steps_serializable),
            duration_ms=int((time.time() - started_ts) * 1000),
            cost_usd=float(cost_usd or 0.0),
            intent_id=intent_id or None,
        )
    except Exception:
        logger.debug("orchestrator: record_trajectory failed", exc_info=True)


def _domain_from_history(history: list[dict]) -> str:
    """Best-effort: pull the first navigate URL we tried, return its host."""
    for h in history:
        action = h.get("action")
        if isinstance(action, dict) and str(action.get("action", "")).lower() == "navigate":
            url = str(action.get("url") or "")
            try:
                host = urlparse(url).hostname or ""
                if host:
                    return host.lower()
            except Exception:
                continue
    return ""


__all__ = [
    "TaskOutcome",
    "classify_task_kind",
    "run_task",
]
