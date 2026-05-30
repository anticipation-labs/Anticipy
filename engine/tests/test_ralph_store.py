"""Unit tests for the Ralph loop SQLite persistence layer.

Phase P4-1 gate. Covers create/get/update/cost-cap/retry-schedule/steps
plus stats rollups. No external services; all tests run against a
tmp_path SQLite file.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.ralph import CostCapExceeded, Goal, GoalStep, RalphStore  # noqa: E402


@pytest.fixture
def store(tmp_path: Path) -> RalphStore:
    db = tmp_path / "ralph.db"
    s = RalphStore(db_path=db)
    yield s
    s.close()


def test_create_goal_returns_id(store: RalphStore) -> None:
    goal_id = store.create_goal(
        user_id="u1",
        goal_text="draft email to ada@example.com",
        origin="inject",
    )
    assert isinstance(goal_id, str)
    assert goal_id.startswith("g_")
    assert len(goal_id) > len("g_")


def test_get_goal_returns_record_or_none(store: RalphStore) -> None:
    assert store.get_goal("nope") is None
    goal_id = store.create_goal(
        user_id="u1",
        goal_text="navigate to gmail",
        origin="asr",
        surface="web",
        channel_payload={"hint": "draft only"},
    )
    g = store.get_goal(goal_id)
    assert isinstance(g, Goal)
    assert g.goal_id == goal_id
    assert g.user_id == "u1"
    assert g.goal_text == "navigate to gmail"
    assert g.origin == "asr"
    assert g.status == "pending"
    assert g.cost_usd == 0.0
    assert g.cost_cap_usd == 0.05
    assert g.consecutive_failures == 0
    assert g.next_attempt_at is None
    assert g.surface == "web"
    assert g.channel_payload_dict() == {"hint": "draft only"}
    assert g.final_artifact_path is None
    assert g.created_at <= g.updated_at


def test_update_status_persists(store: RalphStore) -> None:
    goal_id = store.create_goal(user_id="u1", goal_text="x")
    before = store.get_goal(goal_id)
    assert before is not None and before.status == "pending"

    # Force updated_at to tick forward (we store integer unix seconds).
    time.sleep(1.05)
    store.update_goal_status(
        goal_id,
        "running",
        consecutive_failures=2,
        final_artifact_path="/tmp/shot.png",
    )
    after = store.get_goal(goal_id)
    assert after is not None
    assert after.status == "running"
    assert after.consecutive_failures == 2
    assert after.final_artifact_path == "/tmp/shot.png"
    assert after.updated_at >= before.updated_at

    # Bogus status rejected.
    with pytest.raises(ValueError):
        store.update_goal_status(goal_id, "WAT")

    # Bogus column rejected.
    with pytest.raises(ValueError):
        store.update_goal_status(goal_id, "running", goal_text="hijack")

    # Missing goal raises KeyError.
    with pytest.raises(KeyError):
        store.update_goal_status("missing", "running")


def test_bump_cost_under_cap(store: RalphStore) -> None:
    goal_id = store.create_goal(
        user_id="u1", goal_text="x", cost_cap_usd=0.05
    )
    new_cost = store.bump_cost(goal_id, 0.01)
    assert new_cost == pytest.approx(0.01)
    new_cost = store.bump_cost(goal_id, 0.02)
    assert new_cost == pytest.approx(0.03)
    g = store.get_goal(goal_id)
    assert g is not None
    assert g.cost_usd == pytest.approx(0.03)


def test_bump_cost_over_cap_raises(store: RalphStore) -> None:
    goal_id = store.create_goal(
        user_id="u1", goal_text="x", cost_cap_usd=0.01
    )
    # First bump fits under the cap.
    store.bump_cost(goal_id, 0.006)
    # Second bump tips over.
    with pytest.raises(CostCapExceeded) as exc:
        store.bump_cost(goal_id, 0.01)
    assert exc.value.goal_id == goal_id
    assert exc.value.cost_cap_usd == pytest.approx(0.01)
    assert exc.value.cost_usd == pytest.approx(0.016)
    # The increment is still recorded so callers can see the actual spend.
    g = store.get_goal(goal_id)
    assert g is not None
    assert g.cost_usd == pytest.approx(0.016)

    # Negative bumps rejected.
    with pytest.raises(ValueError):
        store.bump_cost(goal_id, -0.01)

    # Missing goal raises KeyError.
    with pytest.raises(KeyError):
        store.bump_cost("nope", 0.001)


def test_schedule_retry_sets_next_attempt(store: RalphStore) -> None:
    goal_id = store.create_goal(user_id="u1", goal_text="x")
    target_ts = int(time.time()) + 300
    store.schedule_retry(goal_id, target_ts)
    g = store.get_goal(goal_id)
    assert g is not None
    assert g.status == "wait_retry"
    assert g.next_attempt_at == target_ts


def test_due_for_retry_filters_by_time(store: RalphStore) -> None:
    now = int(time.time())
    ready_id = store.create_goal(user_id="u1", goal_text="ready")
    not_ready_id = store.create_goal(user_id="u1", goal_text="not yet")
    other_status_id = store.create_goal(user_id="u1", goal_text="running")

    store.schedule_retry(ready_id, now - 60)  # past, due
    store.schedule_retry(not_ready_id, now + 3600)  # future, not due
    # Goal scheduled in the past but with a different status must not appear.
    store.schedule_retry(other_status_id, now - 30)
    store.update_goal_status(other_status_id, "running")

    due = store.due_for_retry(limit=10)
    due_ids = [g.goal_id for g in due]
    assert ready_id in due_ids
    assert not_ready_id not in due_ids
    assert other_status_id not in due_ids

    # Add a second ready goal a bit later in time; both should appear in time order.
    ready2 = store.create_goal(user_id="u1", goal_text="ready2")
    store.schedule_retry(ready2, now - 30)
    due = store.due_for_retry(limit=10)
    due_ids = [g.goal_id for g in due]
    assert due_ids.index(ready_id) < due_ids.index(ready2)


def test_add_step_links_to_goal(store: RalphStore) -> None:
    goal_id = store.create_goal(user_id="u1", goal_text="x")
    s1 = store.add_step(
        goal_id,
        "navigate",
        action_payload={"url": "https://mail.google.com/"},
        pre_state_hash="abc123",
    )
    s2 = store.add_step(
        goal_id,
        "click",
        action_payload={"selector": "div[gh=cm]"},
        pre_state_hash="def456",
    )
    assert s1.startswith("s_") and s2.startswith("s_") and s1 != s2

    steps = store.goal_steps(goal_id)
    assert len(steps) == 2
    assert steps[0].step_index == 0
    assert steps[1].step_index == 1
    assert steps[0].action == "navigate"
    assert steps[0].action_payload_dict() == {"url": "https://mail.google.com/"}
    assert steps[0].pre_state_hash == "abc123"
    assert steps[0].result is None  # not yet completed
    assert steps[0].cost_usd == 0.0
    assert steps[0].retry_count == 0
    assert steps[0].started_at > 0
    assert steps[0].ended_at is None

    # Step against unknown goal raises.
    with pytest.raises(KeyError):
        store.add_step("nope", "navigate")


def test_complete_step_records_result(store: RalphStore) -> None:
    goal_id = store.create_goal(user_id="u1", goal_text="x")
    step_id = store.add_step(
        goal_id, "type", action_payload={"text": "hello"}, pre_state_hash="pre"
    )
    store.complete_step(
        step_id,
        post_state_hash="post",
        result="fail",
        failure_class="element_missing",
        failure_detail="compose button not found",
        cost_usd=0.0008,
        duration_ms=1234,
    )
    steps = store.goal_steps(goal_id)
    assert len(steps) == 1
    s = steps[0]
    assert isinstance(s, GoalStep)
    assert s.result == "fail"
    assert s.failure_class == "element_missing"
    assert s.failure_detail == "compose button not found"
    assert s.post_state_hash == "post"
    assert s.cost_usd == pytest.approx(0.0008)
    assert s.duration_ms == 1234
    assert s.ended_at is not None and s.ended_at >= s.started_at

    # Invalid result rejected.
    with pytest.raises(ValueError):
        store.complete_step(step_id, "post", "WAT")

    # Missing step raises KeyError.
    with pytest.raises(KeyError):
        store.complete_step("missing", "post", "pass")


def test_goal_steps_returns_ordered_by_index(store: RalphStore) -> None:
    goal_id = store.create_goal(user_id="u1", goal_text="x")
    ids: list[str] = []
    for i in range(5):
        ids.append(store.add_step(goal_id, f"a{i}"))
    steps = store.goal_steps(goal_id)
    assert [s.step_index for s in steps] == [0, 1, 2, 3, 4]
    assert [s.step_id for s in steps] == ids


def test_stats_counts_by_status(store: RalphStore) -> None:
    # Empty store baseline.
    s0 = store.stats()
    assert s0["total_goals"] == 0
    assert s0["by_status"] == {}
    assert s0["cost_last_24h_usd"] == 0.0
    assert s0["cost_today_usd"] == 0.0
    assert s0["cost_month_usd"] == 0.0

    # Two pending + one done + one wait_retry.
    g1 = store.create_goal(user_id="u1", goal_text="a")
    g2 = store.create_goal(user_id="u1", goal_text="b")
    g3 = store.create_goal(user_id="u1", goal_text="c")
    g4 = store.create_goal(user_id="u1", goal_text="d")
    store.bump_cost(g1, 0.01)
    store.bump_cost(g3, 0.02)
    store.update_goal_status(g3, "done")
    store.schedule_retry(g4, int(time.time()) + 60)

    s1 = store.stats()
    assert s1["total_goals"] == 4
    assert s1["by_status"]["pending"] == 2
    assert s1["by_status"]["done"] == 1
    assert s1["by_status"]["wait_retry"] == 1
    # Cost totals roll up across all goals updated in the window.
    assert s1["cost_last_24h_usd"] == pytest.approx(0.03)
    assert s1["cost_today_usd"] == pytest.approx(0.03)
    assert s1["cost_month_usd"] == pytest.approx(0.03)


def test_thread_safety_basic(store: RalphStore) -> None:
    """Many threads inserting goals must not corrupt or collide on ids."""
    import threading

    ids: list[str] = []
    errors: list[BaseException] = []
    lock = threading.Lock()

    def worker(n: int) -> None:
        try:
            for _ in range(n):
                gid = store.create_goal(user_id="u1", goal_text="x")
                with lock:
                    ids.append(gid)
        except BaseException as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(10,)) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert len(ids) == 50
    assert len(set(ids)) == 50  # all unique
    stats = store.stats()
    assert stats["by_status"]["pending"] == 50
