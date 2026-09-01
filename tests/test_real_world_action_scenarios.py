"""Field rehearsals for the failures reported during the long team-sync run.

The fixture is deliberately written as ordinary conversation rather than a
bag of keywords.  Meaning is supplied by scripted model verdicts; these tests
exercise the production hand-off points around that judgement: strong-model
replacement, channel delivery, and the workflow receipt floor.
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import types

import pytest

import brain.worker as worker
from brain.anticipy_core import Anticipy
from brain.memory import Memory
from brain.orchestrator import Brain, TRIAGE_SYSTEM
from brain.workflow import (
    Consequence,
    PlanState,
    WorkflowViolation,
    approve,
    claim,
    new_plan,
    succeed,
)


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "real_world_action_scenarios.json"


@pytest.fixture(scope="module")
def scenarios():
    return json.loads(FIXTURE_PATH.read_text())


class ScriptedModel:
    live = True
    model = "fixture-model"

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def chat(self, system, user, **kwargs):
        self.calls.append({"system": system, "user": user, "kwargs": kwargs})
        if not self.replies:
            raise AssertionError("the production path asked the model more times than the fixture permits")
        reply = self.replies.pop(0)
        return types.SimpleNamespace(text=json.dumps(reply))


def _prompt(case):
    context = " | ".join(case.get("context") or [])
    if not context:
        return case["utterance"]
    return f'{case["utterance"]}\n(Earlier in this conversation: {context})'


def test_field_corpus_names_every_requested_failure_family(scenarios):
    assert scenarios["schema_version"] == 1
    categories = {case["category"] for case in scenarios["conversation_cases"]}
    assert categories == {
        "correction",
        "exclusions",
        "discussion_vs_instruction",
        "hallucinated_topic",
    }
    ids = [
        case["id"]
        for group in ("conversation_cases", "delivery_cases", "browser_cases", "workflow_cases")
        for case in scenarios[group]
    ]
    assert len(ids) == len(set(ids)), "scenario ids are audit keys and must stay unique"


@pytest.mark.parametrize(
    "case_id",
    [
        "team_sync_correction",
        "dinner_exclusions_survive",
        "team_sync_discussion_is_not_an_instruction",
        "quantum_topic_invented_by_cheap_triage",
    ],
)
def test_full_context_is_rejudged_before_a_goal_can_leave_the_brain(
        scenarios, case_id):
    case = next(row for row in scenarios["conversation_cases"] if row["id"] == case_id)
    cheap = ScriptedModel([case["cheap_verdict"]])
    brain = Brain(cheap)
    strong_payload = case.get("strong_verdict")
    strong = ScriptedModel([strong_payload] if strong_payload else [])
    brain.strong = strong

    prompt = _prompt(case)
    result = brain.triage(prompt)
    expected = case["expected"]

    assert result.decision == expected["decision"]
    assert result.goal == expected.get("goal")
    if "missing" in expected:
        assert result.missing == expected["missing"]
    assert cheap.calls[0]["system"] == TRIAGE_SYSTEM
    assert cheap.calls[0]["user"] == prompt

    should_rejudge = (
        case["cheap_verdict"]["decision"] in {"act", "ask"}
        or bool(case["cheap_verdict"].get("goal"))
    )
    assert len(strong.calls) == int(should_rejudge)
    if should_rejudge:
        assert strong.calls[0]["system"] == TRIAGE_SYSTEM
        assert strong.calls[0]["user"] == prompt


def test_the_quantum_goal_is_removed_not_merely_hidden(scenarios):
    case = next(row for row in scenarios["conversation_cases"]
                if row["id"] == "quantum_topic_invented_by_cheap_triage")
    assert "quantum" not in case["utterance"].lower()
    cheap = ScriptedModel([case["cheap_verdict"]])
    strong = ScriptedModel([case["strong_verdict"]])
    brain = Brain(cheap)
    brain.strong = strong

    result = brain.triage(_prompt(case))

    assert result.decision == "ignore"
    assert result.goal is None, (
        "ignore + a goal still becomes a quiet-work card, so deleting only the action verdict is unsafe"
    )


class _Response:
    def __init__(self, payload=None):
        self.ok = True
        self.status_code = 200
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


class _DeliveryModel:
    def __init__(self):
        self.calls = 0

    def chat(self, system, user, **kwargs):
        self.calls += 1
        return types.SimpleNamespace(
            text="The team-sync dinner reservation is confirmed for 7 PM."
        )


class _TextTransport:
    def __init__(self, fails=False):
        self.sent = []
        self.attempts = 0
        self.fails = fails

    def text(self, phone, message):
        self.attempts += 1
        if self.fails:
            raise RuntimeError("SMS transport unavailable")
        self.sent.append((phone, message))
        return {"sid": "SM-FIELD-REHEARSAL"}

    def call(self, phone, message):
        return self.text(phone, message)


@pytest.fixture(autouse=True)
def _clean_worker_delivery_state():
    worker.REPORTED.clear()
    worker._SENT_RECENTLY.clear()
    worker._last_blocker.clear()
    yield
    worker.REPORTED.clear()
    worker._SENT_RECENTLY.clear()
    worker._last_blocker.clear()


@pytest.mark.parametrize(
    "case_id",
    [
        "missing_phone_uses_in_app_only",
        "verified_phone_uses_text_and_in_app_receipt",
        "text_transport_failure_still_uses_in_app",
    ],
)
def test_finished_work_names_the_channel_that_really_delivered_it(
        monkeypatch, scenarios, case_id):
    case = next(row for row in scenarios["delivery_cases"] if row["id"] == case_id)
    model = _DeliveryModel()
    transport = _TextTransport(fails=case.get("transport_fails", False))
    anticipy = Anticipy(
        memory=Memory(":memory:"),
        llm=model,
        backend_url="http://field.test",
        voice=transport,
        owner_phone=case["phone"],
        owner_id="owner-field",
    )
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    job = {
        "id": f'job-{case["id"]}',
        "goal": "arrange the team-sync dinner",
        "result": "reservation confirmed",
        "status": "done",
        "lane": "",
        "params": "{}",
        "owner": "owner-field",
        "updated": now,
    }
    feed = []

    def fake_get(url, **kwargs):
        if "/collections/events/" in url:
            return _Response({"items": []})
        return _Response({"items": [dict(job)]})

    def fake_post(url, **kwargs):
        if "/collections/events/" in url:
            feed.append(dict(kwargs.get("json") or {}))
        return _Response()

    monkeypatch.setattr(worker.pb, "get", fake_get)
    monkeypatch.setattr(worker.pb, "post", fake_post)
    monkeypatch.setattr(worker.pb, "patch", lambda *args, **kwargs: _Response())
    monkeypatch.setattr(worker, "CLOCK_QUIET_START", 25)
    monkeypatch.setattr(worker, "CLOCK_QUIET_END", 0)

    worker.report_finished_jobs(anticipy)

    delivered_feed = [row for row in feed if row.get("kind") == "anticipy_says"]
    notification_states = [
        row.get("decision")
        for row in feed
        if row.get("kind") == "notification_status"
    ]
    assert len(transport.sent) == case["expected_sms_count"]
    assert transport.attempts == case["expected_sms_attempts"]
    assert len(delivered_feed) == case["expected_feed_count"]
    assert delivered_feed[0]["decision"] == "done"
    assert notification_states == case["expected_notification_states"]
    assert model.calls == 1, "one outcome must be composed once, regardless of channel"

    # A polling sweep must not duplicate either the in-app result or an SMS
    # whose provider outcome might have been lost with the response.
    worker.report_finished_jobs(anticipy)
    assert len(transport.sent) == case["expected_sms_count"]
    assert transport.attempts == case["expected_sms_attempts"]
    assert len([row for row in feed if row.get("kind") == "anticipy_says"]) == 1


def test_no_verified_evidence_means_no_completed_state(scenarios):
    case = scenarios["workflow_cases"][0]
    now = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)
    plan = new_plan(
        owner_ref="owner-field",
        lineage_key="team-sync-dinner",
        goal=case["goal"],
        authority_text=case["goal"],
        consequence=Consequence.CONSEQUENTIAL,
        source_event_id="event-field",
        plan_id="plan-field",
        now=now,
    )
    plan = approve(
        plan,
        expected_version=plan.version,
        owner_words="Send it",
        now=now,
    )
    plan = claim(
        plan,
        expected_version=plan.version,
        actor_id="chrome-field",
        token="lease-field",
        lease_seconds=60,
        now=now,
    )

    with pytest.raises(WorkflowViolation, match="evidence"):
        succeed(
            plan,
            lease_token="lease-field",
            summary="arranged",
            evidence=(),
            verified=True,
            now=now,
        )

    assert plan.state == PlanState.RUNNING
    assert plan.receipt is None
    assert plan.job_fields()["status"] == "running"
