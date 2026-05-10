"""
Unit tests for app.orchestrator.run_task.

We mock the bridge, planner, critic, reflector, and verifier so the loop
runs deterministically with no LLM and no real WebSocket. Each test
isolates one orchestrator behaviour:

  - cache hit short-circuits a successful replay
  - normal plan→execute→verify path
  - critic no_progress twice triggers reflector pivot
  - reflector abort surfaces honest failure
  - verifier rejection blocks a "done" claim
  - cancel mid-task propagates cleanly
  - cost-cap pre-flight raises before any work
  - plan unreachable short-circuits
"""

from __future__ import annotations

import os
import sys
from unittest.mock import AsyncMock

# Required env BEFORE importing app modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("JWT_SECRET", "x" * 48)
os.environ.setdefault(
    "PROFILE_ENCRYPTION_KEY",
    "RoUzc1lJ3gkPkHrxoYQzv1trmEJSQbgo6mNhlQYgfJk=",
)

import pytest  # noqa: E402

from app import orchestrator as orch  # noqa: E402
from app.critic import CriticResult  # noqa: E402
from app.planner import Plan, PlanStep  # noqa: E402
from app.reflector import ReflectorResult  # noqa: E402
from app.verifier import DoneVerification  # noqa: E402
from app.ws_bridge import TaskCancelled  # noqa: E402


# ────────────────────────────────────────────────────────────────────
# Fake bridge
# ────────────────────────────────────────────────────────────────────


class FakeBridge:
    """In-memory bridge double. Tracks every command call so tests can
    assert on them; lets tests inject canned return values per primitive.
    """

    def __init__(self) -> None:
        self.cancelled = False
        self.closed = False
        self.cancel_reason = ""
        self.calls: list[tuple[str, tuple, dict]] = []
        self.streamed: list[tuple[int, str]] = []
        self.done_emissions: list[dict] = []
        self.url_seq: list[str] = ["https://example.com/start"]
        self.dom_seq: list[str] = ["<html>start</html>"]
        self.extract_seq: list[str] = ["page text"]
        # Whether a navigate / click / type should error.
        self.action_errors: list[Exception] = []

    async def navigate(self, url: str):
        self.calls.append(("navigate", (url,), {}))
        self.url_seq.append(url)
        if self.action_errors:
            raise self.action_errors.pop(0)
        return {"navigated": True, "url": url}

    async def click(self, selector: str):
        self.calls.append(("click", (selector,), {}))
        return {"clicked": True}

    async def type(self, selector: str, text: str, *, submit: bool = False):
        self.calls.append(("type", (selector, text), {"submit": submit}))
        return {}

    async def extract(self, selector=None):
        self.calls.append(("extract", (selector,), {}))
        return self.extract_seq[0] if self.extract_seq else ""

    async def get_text(self, selector=None):
        return await self.extract(selector)

    async def get_url(self):
        self.calls.append(("get_url", (), {}))
        return self.url_seq[-1] if self.url_seq else ""

    async def get_dom_snapshot(self, *, limit=None):
        self.calls.append(("get_dom_snapshot", (), {}))
        return self.dom_seq[-1] if self.dom_seq else ""

    async def screenshot(self):
        return ""

    async def stream_step(self, step: int, message: str):
        self.streamed.append((step, message))

    async def emit_done(self, success, message, deliverable=None):
        self.done_emissions.append({
            "success": success, "message": message, "deliverable": deliverable,
        })


# ────────────────────────────────────────────────────────────────────
# Fixtures / helpers
# ────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _no_cost_cap(monkeypatch):
    async def _noop(*a, **kw):  # noqa: ARG001
        return None
    monkeypatch.setattr(orch, "assert_under_cap", _noop)


@pytest.fixture(autouse=True)
def _no_supabase_writes(monkeypatch):
    """Don't touch Supabase from the trajectory recorder."""
    async def _noop(*a, **kw):  # noqa: ARG001
        return None
    monkeypatch.setattr(
        orch.trajectory_cache, "record_trajectory", AsyncMock(return_value=None)
    )


@pytest.fixture
def fake_memory_store():
    """Empty memory store — search returns []."""
    class _Store:
        async def search(self, *a, **kw):  # noqa: ARG002
            return []
    return _Store()


def _make_plan(steps_count: int = 2, unreachable: bool = False) -> Plan:
    return Plan(
        steps=[
            PlanStep(step=i + 1, goal=f"goal {i+1}", success_criteria=f"crit {i+1}")
            for i in range(steps_count)
        ],
        required_facts=[],
        unreachable=unreachable,
        unreachable_reason="signed-out wall" if unreachable else "",
        starting_url="https://example.com/start",
        success="task completed",
    )


def _patch_planner(monkeypatch, plan: Plan):
    async def _plan(*a, **kw):  # noqa: ARG001
        return plan
    monkeypatch.setattr(orch.planner_mod, "plan", _plan)


def _patch_few_shot(monkeypatch, examples: list = None):
    async def _few(*a, **kw):  # noqa: ARG001
        return examples or []
    monkeypatch.setattr(
        orch.trajectory_cache, "get_few_shot_examples", _few
    )


def _patch_cache(monkeypatch, cached: dict | None):
    async def _hit(*a, **kw):  # noqa: ARG001
        return cached
    monkeypatch.setattr(orch.trajectory_cache, "cache_hit_for", _hit)


def _patch_critic(monkeypatch, verdicts: list[str]):
    """Return verdicts in order; cycles when exhausted."""
    seq = list(verdicts)
    idx = [0]

    async def _crit(*a, **kw):  # noqa: ARG001
        v = seq[idx[0] % len(seq)] if seq else "progress"
        idx[0] += 1
        return CriticResult(verdict=v, reason="stub", confidence=0.9)

    monkeypatch.setattr(orch.critic_mod, "criticize", _crit)


def _patch_executor(monkeypatch, actions: list[dict]):
    """Return actions in order; raises StopIteration when exhausted (test
    bug catch — tests must seed enough actions to terminate)."""
    seq = list(actions)
    idx = [0]

    async def _exec(*a, **kw):  # noqa: ARG001
        if idx[0] >= len(seq):
            return {"action": "done", "message": "test default exit"}
        a_ = seq[idx[0]]
        idx[0] += 1
        return a_

    monkeypatch.setattr(orch, "_executor_step", _exec)


def _patch_verifier(monkeypatch, passed: bool, honest: str = ""):
    async def _ver(*a, **kw):  # noqa: ARG001
        return DoneVerification(
            passed=passed,
            missing=[] if passed else ["something"],
            evidence=["evidence"] if passed else [],
            honest_message="" if passed else (honest or "verifier said no"),
            task_kind=kw.get("task_kind", "generic"),
        )

    monkeypatch.setattr(orch.verifier_mod, "verify_at_done", _ver)


def _patch_reflector(monkeypatch, decision: str, **kw):
    async def _ref(*a, **kwargs):  # noqa: ARG001
        return ReflectorResult(
            decision=decision,
            new_plan=kw.get("new_plan"),
            abort_message=kw.get("abort_message", ""),
            reasoning="stub",
        )

    monkeypatch.setattr(orch.reflector_mod, "reflect", _ref)


# ────────────────────────────────────────────────────────────────────
# 1. Cache hit short-circuit
# ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cache_hit_replays_and_verifies(monkeypatch, fake_memory_store):
    cached = {
        "id": "cache-1",
        "task_summary": "send Sarah dinner email",
        "domain": "mail.google.com",
        "steps": [
            {"action": {"action": "navigate", "url": "https://mail.google.com"},
             "verdict": "progress"},
            {"action": {"action": "click", "selector": "div.compose"},
             "verdict": "progress"},
            {"action": {"action": "done", "message": "Email sent",
                        "subject": "dinner"},
             "verdict": "done"},
        ],
        "outcome": "success",
        "similarity": 0.95,
    }
    _patch_cache(monkeypatch, cached)
    _patch_planner(monkeypatch, _make_plan(2))
    _patch_few_shot(monkeypatch)
    _patch_verifier(monkeypatch, passed=True)

    bridge = FakeBridge()
    out = await orch.run_task(
        "send Sarah a note about dinner",
        user_id="u1",
        bridge=bridge,
        task_id="t1",
        memory_store=fake_memory_store,
    )

    assert out["success"] is True
    assert out["cache_hit"] is True
    # Replay calls navigate + click + done(no bridge call).
    nav_calls = [c for c in bridge.calls if c[0] == "navigate"]
    assert any(c[1][0] == "https://mail.google.com" for c in nav_calls)


@pytest.mark.asyncio
async def test_cache_hit_with_failed_verifier_falls_through_to_full_plan(
    monkeypatch, fake_memory_store,
):
    cached = {
        "id": "cache-2",
        "task_summary": "test",
        "steps": [
            {"action": {"action": "navigate", "url": "https://example.com"}},
            {"action": {"action": "done", "message": "claim"}},
        ],
        "outcome": "success",
        "similarity": 0.93,
    }
    _patch_cache(monkeypatch, cached)
    _patch_planner(monkeypatch, _make_plan(2))
    _patch_few_shot(monkeypatch)
    # First verifier call (after replay) fails; second (after real plan)
    # passes. We use a side_effect that flips after first invocation.
    call_count = [0]

    async def _ver(*a, **kw):  # noqa: ARG001
        call_count[0] += 1
        return DoneVerification(
            passed=(call_count[0] >= 2),
            missing=[] if call_count[0] >= 2 else ["x"],
            evidence=["e"],
            honest_message="" if call_count[0] >= 2 else "first failed",
            task_kind=kw.get("task_kind", "generic"),
        )

    monkeypatch.setattr(orch.verifier_mod, "verify_at_done", _ver)
    _patch_critic(monkeypatch, ["progress", "done"])
    _patch_executor(monkeypatch, [
        {"action": "click", "selector": "a"},
        {"action": "done", "message": "real plan done"},
    ])

    bridge = FakeBridge()
    out = await orch.run_task(
        "test task", user_id="u1", bridge=bridge, task_id="t",
        memory_store=fake_memory_store,
    )
    # Cache replay rejected → fell through to plan; second verifier passed.
    assert out["success"] is True
    assert out["cache_hit"] is False


# ────────────────────────────────────────────────────────────────────
# 2. Normal plan → execute → verify
# ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_normal_plan_execute_verify_success(monkeypatch, fake_memory_store):
    _patch_cache(monkeypatch, None)
    _patch_planner(monkeypatch, _make_plan(2))
    _patch_few_shot(monkeypatch)
    _patch_verifier(monkeypatch, passed=True)
    _patch_critic(monkeypatch, ["progress", "done"])
    _patch_executor(monkeypatch, [
        {"action": "click", "selector": "a.search"},
        {"action": "done", "message": "Found it", "answer": "42"},
    ])

    bridge = FakeBridge()
    out = await orch.run_task(
        "what is the answer",
        user_id="u1", bridge=bridge, task_id="t",
        memory_store=fake_memory_store,
    )

    assert out["success"] is True
    assert out["message"] == "Found it"
    assert out["task_kind"] == "read_extract"
    assert out["deliverable"]["answer"] == "42"


# ────────────────────────────────────────────────────────────────────
# 3. Critic two no_progress → reflector pivot → continues
# ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_two_no_progress_triggers_pivot(monkeypatch, fake_memory_store):
    _patch_cache(monkeypatch, None)
    _patch_planner(monkeypatch, _make_plan(2))
    _patch_few_shot(monkeypatch)
    _patch_verifier(monkeypatch, passed=True)
    # Two no_progress, then the pivot kicks in, then progress → done.
    _patch_critic(monkeypatch, ["no_progress", "no_progress", "progress", "done"])
    _patch_executor(monkeypatch, [
        {"action": "click", "selector": "a"},
        {"action": "click", "selector": "b"},
        {"action": "click", "selector": "c"},
        {"action": "done", "message": "Done after pivot"},
    ])

    new_plan = _make_plan(3)
    new_plan.steps[0].goal = "pivoted goal"
    pivot_called = [0]

    async def _ref(*a, **kw):  # noqa: ARG001
        pivot_called[0] += 1
        return ReflectorResult(
            decision="pivot",
            new_plan=new_plan,
            abort_message="",
            reasoning="pivot stub",
        )

    monkeypatch.setattr(orch.reflector_mod, "reflect", _ref)

    bridge = FakeBridge()
    out = await orch.run_task(
        "navigate site",
        user_id="u1", bridge=bridge, task_id="t",
        memory_store=fake_memory_store,
    )

    assert pivot_called[0] >= 1, "reflector should have been called at least once"
    assert out["success"] is True


# ────────────────────────────────────────────────────────────────────
# 4. Reflector abort surfaces honest failure
# ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reflector_abort_returns_failure(monkeypatch, fake_memory_store):
    _patch_cache(monkeypatch, None)
    _patch_planner(monkeypatch, _make_plan(2))
    _patch_few_shot(monkeypatch)
    _patch_verifier(monkeypatch, passed=True)
    _patch_critic(monkeypatch, ["no_progress", "no_progress"])
    _patch_executor(monkeypatch, [
        {"action": "click", "selector": "a"},
        {"action": "click", "selector": "b"},
    ])
    _patch_reflector(
        monkeypatch,
        decision="abort",
        abort_message="The site needs login.",
    )

    bridge = FakeBridge()
    out = await orch.run_task(
        "do something",
        user_id="u1", bridge=bridge, task_id="t",
        memory_store=fake_memory_store,
    )
    assert out["success"] is False
    assert "login" in out["message"].lower()
    assert out["aborted_reason"] == "reflector_abort"


# ────────────────────────────────────────────────────────────────────
# 5. Verifier rejection overrides "done" claim
# ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_verifier_rejection_overrides_agent_done(monkeypatch, fake_memory_store):
    _patch_cache(monkeypatch, None)
    _patch_planner(monkeypatch, _make_plan(2))
    _patch_few_shot(monkeypatch)
    _patch_verifier(monkeypatch, passed=False, honest="couldn't confirm")
    _patch_critic(monkeypatch, ["done"])
    _patch_executor(monkeypatch, [
        {"action": "done", "message": "I sent it"},
    ])

    bridge = FakeBridge()
    out = await orch.run_task(
        "send something",
        user_id="u1", bridge=bridge, task_id="t",
        memory_store=fake_memory_store,
    )
    assert out["success"] is False
    assert "couldn't confirm" in out["message"]
    assert out["aborted_reason"] == "verifier_failed"


# ────────────────────────────────────────────────────────────────────
# 6. Cancel mid-task propagates
# ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cancel_mid_task_propagates(monkeypatch, fake_memory_store):
    _patch_cache(monkeypatch, None)
    _patch_planner(monkeypatch, _make_plan(2))
    _patch_few_shot(monkeypatch)
    _patch_critic(monkeypatch, ["progress"])
    _patch_executor(monkeypatch, [
        {"action": "click", "selector": "a"},
        {"action": "click", "selector": "b"},
    ])

    bridge = FakeBridge()

    # Mark cancelled after the first action — the loop should bail before
    # the second iteration via the explicit cancellation check.
    original_click = bridge.click
    iterations = [0]

    async def cancelling_click(selector):
        iterations[0] += 1
        if iterations[0] == 1:
            bridge.cancelled = True
            bridge.cancel_reason = "user_cancel"
        return await original_click(selector)

    bridge.click = cancelling_click  # type: ignore[method-assign]

    with pytest.raises(TaskCancelled):
        await orch.run_task(
            "test cancel",
            user_id="u1", bridge=bridge, task_id="t",
            memory_store=fake_memory_store,
        )


# ────────────────────────────────────────────────────────────────────
# 7. Cost-cap pre-flight
# ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cost_cap_short_circuits(monkeypatch, fake_memory_store):
    from app.cost_watch import CostCapExceeded

    async def _raises(*a, **kw):  # noqa: ARG001
        raise CostCapExceeded(total_usd=11.0, cap_usd=10.0)

    monkeypatch.setattr(orch, "assert_under_cap", _raises)

    bridge = FakeBridge()
    out = await orch.run_task(
        "anything",
        user_id="u1", bridge=bridge, task_id="t",
        memory_store=fake_memory_store,
    )
    assert out["success"] is False
    assert "cap" in out["message"].lower()
    assert out["aborted_reason"] == "cost_cap"
    # No bridge calls — short-circuit before any work.
    assert bridge.calls == []


# ────────────────────────────────────────────────────────────────────
# 8. Plan unreachable
# ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_plan_unreachable_short_circuits(monkeypatch, fake_memory_store):
    _patch_cache(monkeypatch, None)
    _patch_planner(monkeypatch, _make_plan(2, unreachable=True))
    _patch_few_shot(monkeypatch)

    bridge = FakeBridge()
    out = await orch.run_task(
        "do banking",
        user_id="u1", bridge=bridge, task_id="t",
        memory_store=fake_memory_store,
    )
    assert out["success"] is False
    assert "signed-out" in out["message"].lower() or "wall" in out["message"].lower()
    assert out["aborted_reason"] == "plan_unreachable"


# ────────────────────────────────────────────────────────────────────
# 9. classify_task_kind heuristic
# ────────────────────────────────────────────────────────────────────


def test_classify_task_kind_email():
    assert orch.classify_task_kind("send Sarah an email about dinner") == "email_send"


def test_classify_task_kind_calendar():
    assert orch.classify_task_kind("create event Tuesday at 7pm") == "calendar_create"


def test_classify_task_kind_cart():
    assert orch.classify_task_kind("add the milk to my cart") == "cart_add"


def test_classify_task_kind_read():
    assert orch.classify_task_kind("what is the price on Amazon") == "read_extract"


def test_classify_task_kind_generic_fallback():
    assert orch.classify_task_kind("hmmmmmmm") == "generic"


def test_classify_task_kind_empty():
    assert orch.classify_task_kind("") == "generic"
    assert orch.classify_task_kind(None) == "generic"  # type: ignore[arg-type]


# ────────────────────────────────────────────────────────────────────
# 10. Critic "unsafe" hard-stops
# ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_critic_unsafe_aborts(monkeypatch, fake_memory_store):
    _patch_cache(monkeypatch, None)
    _patch_planner(monkeypatch, _make_plan(2))
    _patch_few_shot(monkeypatch)
    _patch_critic(monkeypatch, ["unsafe"])
    _patch_executor(monkeypatch, [
        {"action": "click", "selector": "a.delete"},
    ])

    bridge = FakeBridge()
    out = await orch.run_task(
        "do unsafe thing",
        user_id="u1", bridge=bridge, task_id="t",
        memory_store=fake_memory_store,
    )
    assert out["success"] is False
    assert out["aborted_reason"] == "critic_unsafe"


# ────────────────────────────────────────────────────────────────────
# 11. Executor cascade unavailable → loop continues via budget gates
# ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_executor_unavailable_eventually_stops(monkeypatch, fake_memory_store):
    """When the executor LLM cascade fails repeatedly, the orchestrator
    should burn through the 5-no-progress trigger and return a verifier
    failure (since no done payload was ever produced)."""
    _patch_cache(monkeypatch, None)
    _patch_planner(monkeypatch, _make_plan(1))
    _patch_few_shot(monkeypatch)
    _patch_verifier(monkeypatch, passed=False, honest="nothing to verify")

    async def _none(*a, **kw):  # noqa: ARG001
        return None

    monkeypatch.setattr(orch, "_executor_step", _none)
    # Reflector says continue so we don't abort early.
    _patch_reflector(monkeypatch, decision="continue")

    bridge = FakeBridge()
    out = await orch.run_task(
        "anything",
        user_id="u1", bridge=bridge, task_id="t",
        memory_store=fake_memory_store,
        soft_cap=4, hard_cap=8,
    )
    assert out["success"] is False
