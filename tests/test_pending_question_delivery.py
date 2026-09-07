"""Persisted draft questions survive the nighttime deferral and become texts.

The screenshot's missing end time was an awaiting_confirm card. Restricting
the sweep to needs_user made its original failed/deferred text permanent.
These exercise transport scheduling, not interpretation of the question.
"""
from types import SimpleNamespace

import pytest

from brain import worker as W


@pytest.fixture
def delivery(monkeypatch):
    state = SimpleNamespace(jobs=[], sent=[], prompts=[], slots=[], night=False,
                            reachable=True, recorded=[], write_failed=False,
                            write_response_lost=False, send_response_lost=False)
    W._SENT_RECENTLY.clear()
    W._last_blocker.clear()
    monkeypatch.setattr(W, "ACTIVE_OWNER_REF", "owner-one")
    monkeypatch.setattr(W, "ACTIVE_OWNER_ID", "")
    monkeypatch.setattr(W, "MEETING_ARMED", False)
    monkeypatch.setattr(W, "_in_quiet_hours", lambda _: state.night)
    monkeypatch.setattr(W, "_finished_jobs", lambda query: state.jobs)
    monkeypatch.setattr(W, "asked_about_recently", lambda *a, **k: False)
    monkeypatch.setattr(W, "asks_for_goal", lambda *a, **k: 0)
    monkeypatch.setattr(W, "need_already_asked", lambda *a, **k: False)
    monkeypatch.setattr(W, "can_reach_owner_fresh", lambda _: state.reachable)
    monkeypatch.setattr(W, "reserve_uninvited_text",
                        lambda *args: (state.slots.append(args), "slot")[1])
    def post(*args, **kwargs):
        if state.write_failed:
            raise RuntimeError("storage unavailable")
        state.recorded.append((args, kwargs))
        if state.write_response_lost:
            raise TimeoutError("claim persisted but response lost")
    def read(external_id, *args, **kwargs):
        for event_args, meta in state.recorded:
            if meta.get("external_event_id") == external_id:
                return dict(meta, kind=event_args[0], text=event_args[1], id="record")
        return None
    def send(text):
        state.sent.append(text)
        return None if state.send_response_lost else True
    monkeypatch.setattr(W, "post_event", post)
    monkeypatch.setattr(W, "_event_by_external_id", read)
    state.brain = SimpleNamespace(
        owner_ref="owner-one", owner_id="",
        _voice=lambda ctx: (state.prompts.append(ctx), None)[1],
        notify_owner=send)
    yield state
    W._SENT_RECENTLY.clear()
    W._last_blocker.clear()


def question(**changes):
    return dict(id="task-one", owner_ref="owner-one", status="awaiting_confirm",
                goal="Prepare the supplier review", result="When does it end?",
                params="{}") | changes


def test_draft_waits_at_night_then_texts_once_in_daylight(delivery):
    delivery.jobs = [question()]
    delivery.night = True
    W.ask_about_stuck_jobs(delivery.brain, None)
    assert delivery.sent == delivery.prompts == delivery.slots == []
    delivery.night = False
    W.ask_about_stuck_jobs(delivery.brain, None)
    W.ask_about_stuck_jobs(delivery.brain, None)
    assert delivery.sent == ["About Prepare the supplier review: When does it end?"]
    assert len(delivery.slots) == 1
    assert delivery.prompts[0]["status"] == "awaiting_confirm"


def test_authorized_executor_question_is_a_reply_even_at_night(delivery):
    delivery.jobs = [question(status="needs_user")]
    delivery.night = True
    W.ask_about_stuck_jobs(delivery.brain, None)
    assert len(delivery.sent) == 1
    assert delivery.slots == []


def test_directly_requested_clarification_is_not_deferred_as_proactive(delivery):
    delivery.jobs = [question(params='{"_question_invited":true}')]
    delivery.night = True
    W.ask_about_stuck_jobs(delivery.brain, None)
    W.ask_about_stuck_jobs(delivery.brain, None)
    assert len(delivery.sent) == 1
    assert delivery.slots == []


def test_only_a_structural_invitation_verdict_changes_delivery_posture(delivery):
    delivery.jobs = [question(params='{"_question_invited":"yes"}')]
    delivery.night = True
    W.ask_about_stuck_jobs(delivery.brain, None)
    assert delivery.sent == []


def test_a_conversation_defers_a_proposed_question_without_dropping_it(delivery, monkeypatch):
    delivery.jobs = [question()]
    monkeypatch.setattr(W, "MEETING_ARMED", True)
    W.ask_about_stuck_jobs(delivery.brain, None)
    assert delivery.sent == delivery.prompts == []
    monkeypatch.setattr(W, "MEETING_ARMED", False)
    W.ask_about_stuck_jobs(delivery.brain, None)
    assert len(delivery.sent) == 1


def test_empty_resolved_and_foreign_questions_do_not_text(delivery):
    delivery.jobs = [question(result=""), question(status="done"),
                     question(owner_ref="someone-else")]
    W.ask_about_stuck_jobs(delivery.brain, None)
    assert delivery.sent == delivery.prompts == delivery.slots == []


def test_phone_arrival_unblocks_question_without_spending_slot_while_unreachable(delivery):
    delivery.jobs = [question()]
    delivery.reachable = False
    W.ask_about_stuck_jobs(delivery.brain, None)
    assert delivery.sent == delivery.prompts == delivery.slots == []
    delivery.reachable = True
    W.ask_about_stuck_jobs(delivery.brain, None)
    assert len(delivery.sent) == len(delivery.slots) == 1


def test_exhausted_outreach_budget_keeps_the_card_unmodified(delivery, monkeypatch):
    job = question()
    delivery.jobs = [job.copy()]
    monkeypatch.setattr(W, "reserve_uninvited_text", lambda *args: False)
    W.ask_about_stuck_jobs(delivery.brain, None)
    assert delivery.sent == delivery.prompts == delivery.recorded == []
    assert delivery.jobs == [job]


def test_lost_provider_response_never_repeats_the_message_after_restart(delivery):
    delivery.jobs = [question(status="needs_user")]
    delivery.send_response_lost = True
    W.ask_about_stuck_jobs(delivery.brain, None)
    W._SENT_RECENTLY.clear()
    W._last_blocker.clear()
    delivery.send_response_lost = False
    W.ask_about_stuck_jobs(delivery.brain, None)
    assert len(delivery.sent) == 1
    assert any(meta.get("decision") == "sms_unconfirmed" for _, meta in delivery.recorded)


def test_database_outage_prevents_unrecordable_send_then_recovers(delivery):
    delivery.jobs = [question(status="needs_user")]
    delivery.write_failed = True
    W.ask_about_stuck_jobs(delivery.brain, None)
    assert delivery.sent == []
    delivery.write_failed = False
    W.ask_about_stuck_jobs(delivery.brain, None)
    assert len(delivery.sent) == 1


def test_lost_claim_response_does_not_grant_a_second_sender_permission(delivery):
    delivery.jobs = [question(status="needs_user")]
    delivery.write_response_lost = True
    W.ask_about_stuck_jobs(delivery.brain, None)
    delivery.write_response_lost = False
    W.ask_about_stuck_jobs(delivery.brain, None)
    assert delivery.sent == []


def test_new_question_on_the_same_task_has_its_own_delivery_identity(delivery):
    delivery.jobs = [question(status="needs_user")]
    W.ask_about_stuck_jobs(delivery.brain, None)
    delivery.jobs[0]["result"] = "Which room should I use?"
    W.ask_about_stuck_jobs(delivery.brain, None)
    assert len(delivery.sent) == 2
    assert "Which room should I use?" in delivery.sent[1]
