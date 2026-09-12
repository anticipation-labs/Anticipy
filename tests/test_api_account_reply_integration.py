"""Owner reply -> existing API task -> selected connected account, offline.

Uses the real conversation, hand planner, Worker router and SQL. Only model
judgments and vendor I/O are scripted by the imported loopback fixture.
"""
import json
from types import SimpleNamespace

import pytest

from brain import hands, worker, server_work
from brain.conversation import Conversation, REPLY_SYSTEM
from brain.workflow import cancel, from_params, put_in_params
from test_connector_task_recovery_integration import api, form_task, Model


ANSWER = "Use my work account"


def parked(api, monkeypatch):
    api.call("POST", "/__fixture/connect", {"alias": "personal", "account": "fixture-account-personal"})
    api.call("POST", "/__fixture/connect", {"alias": "work", "account": "fixture-account-work"})
    monkeypatch.setattr(Model, "account", None)
    owner, job = form_task(api, monkeypatch)
    worker.run_api_jobs(owner)
    row = api.call("GET", "/__fixture/state")["jobs"][0]
    assert row["status"] == "needs_user" and row["lane"] == "api"
    return owner, row


class ReplyModel(Model):
    account = "work"

    def __init__(self, job, *, intent="answer", account="work", effect="read", before_plan=None):
        self.job, self.intent, self.account = job, intent, account
        self.effect, self.before_plan = effect, before_plan
        self.planning_prompts = []

    def chat(self, system, user, **kwargs):
        if system == REPLY_SYSTEM:
            value = {"intent": self.intent, "pending_id": self.job["id"],
                     "changes": {"account": "work"} if self.intent == "answer" else None,
                     "reply": "Ready."}
        elif system == Conversation.REMEMBER_SYSTEM:
            value = {"facts": {}}
        elif system == Conversation.ANSWER_SYSTEM:
            value = {"verdict": "answered", "changes": {"account": "work"}, "remaining_question": ""}
        elif system in (server_work.PLAN_SYSTEM, server_work.COMPOSE_SYSTEM, server_work.VERIFY_SYSTEM):
            evidence = json.loads(user)["task_record"]["_api_evidence"]
            assert evidence["vendor_log_id"] == "fixture-read-receipt"
            assert "Friday" in evidence["content"]
            if system == server_work.COMPOSE_SYSTEM:
                return SimpleNamespace(text="Your Orion note says the review is on Friday.")
            value = {"verdict": "compose" if system == server_work.PLAN_SYSTEM else "satisfied",
                     "reason": "The returned note directly supports the answer."}
        elif system in (hands.HANDS_SYSTEM, hands.ACCOUNT_SYSTEM, hands.TOOLS_SYSTEM):
            self.planning_prompts.append((system, user))
            if system == hands.HANDS_SYSTEM:
                if self.before_plan:
                    callback, self.before_plan = self.before_plan, None
                    callback()
                value = {"hand": "api", "app": "fixture_notes", "effect": self.effect,
                         "reason": "Owner selected the account for the existing read."}
            elif system == hands.ACCOUNT_SYSTEM:
                value = {"account": self.account, "reason": "Owner's reply settles the account."}
            else:
                return super().chat(system, user, **kwargs)
        else:
            return super().chat(system, user, **kwargs)
        return SimpleNamespace(text=json.dumps(value))


def answer_in_app(api, owner, row, model, *, question=None):
    conversation = Conversation(owner, llm=model)
    event = api.call("POST", "/api/collections/events/records", {
        "owner_ref": api.owner, "device_id": "connector-fixture", "kind": "app_reply",
        "source": "typed", "text": ANSWER, "decision": ""})
    context = {"reply_to_job_id": row["id"], "workflow_version": row["workflow_version"],
               "question": row["result"] if question is None else question, "goal": row["goal"]}
    with conversation.from_event(event), conversation.reply_in_app():
        reply = conversation.on_reply("fixture-app-thread", ANSWER, context)
    return reply


@pytest.mark.parametrize("intent", ["answer", "confirm"])
def test_account_answer_replans_same_task_and_runs_selected_account(api, monkeypatch, intent):
    owner, row = parked(api, monkeypatch)
    model = ReplyModel(row, intent=intent)
    answer = answer_in_app(api, owner, row, model)
    assert answer["acted"] and not answer["acted"].startswith("failed"), answer
    queued = api.call("GET", "/__fixture/state")["jobs"][0]
    params = json.loads(queued["params"])
    assert queued["id"] == row["id"] and queued["lane"] == "api"
    assert params["_hand"]["alias"] == "work"
    assert params["_hand"]["plan_input"]["workflow_version"] == queued["workflow_version"]
    assert model.planning_prompts and all(ANSWER in prompt for _, prompt in model.planning_prompts)
    assert all(row["result"] in prompt or json.dumps(row["result"])[1:-1] in prompt
               for _, prompt in model.planning_prompts)
    worker.run_api_jobs(owner)
    state = api.call("GET", "/__fixture/state")
    assert len(state["jobs"]) == 1
    final = state["jobs"][0]
    assert final["lane"] == "research" and final["status"] == "queued"
    assert json.loads(final["params"])["_api_evidence"]["vendor_log_id"] == "fixture-read-receipt"
    calls = [call for call in state["calls"] if call["method"] == "POST"]
    assert len(calls) == 1 and calls[0]["body"]["connected_account_id"] == "fixture-account-work"
    owner.llm = model
    worker.run_research_jobs(owner)
    done = api.call("GET", "/__fixture/state")["jobs"][0]
    assert done["status"] == "done" and "Friday" in done["result"]
    receipt = json.loads(done["receipt"])
    assert receipt["verified"] is True and receipt["effect_key"] == done["effect_key"]
    assert receipt["evidence"] and receipt["evidence"][0].startswith("text-sha256:")


def test_removed_selected_account_does_not_default_to_remaining_account(api, monkeypatch):
    owner, row = parked(api, monkeypatch)
    api.call("POST", "/__fixture/disconnect", {"account": "fixture-account-work"})
    model = ReplyModel(row)
    answer = answer_in_app(api, owner, row, model)
    state = api.call("GET", "/__fixture/state")
    assert state["jobs"][0]["status"] == "needs_user", answer
    assert not [call for call in state["calls"] if call["method"] == "POST"]


def test_previous_named_account_survives_a_different_hold_reason(api, monkeypatch):
    owner, row = parked(api, monkeypatch)
    params = json.loads(row["params"])
    params["_hand"]["alias"] = "work"
    params["_hand"]["outcome"]["reason"] = "read_scope_review"
    row = api.call("PATCH", "/api/collections/jobs/records/" + row["id"],
                   {"params": json.dumps(params)})
    api.call("POST", "/__fixture/disconnect", {"account": "fixture-account-work"})
    answer_in_app(api, owner, row, ReplyModel(row))
    state = api.call("GET", "/__fixture/state")
    assert state["jobs"][0]["status"] == "needs_user"
    assert json.loads(state["jobs"][0]["params"])["_hand"]["alias"] == "work"
    assert not [call for call in state["calls"] if call["method"] == "POST"]


def test_replan_receives_previous_selected_account_as_context(api, monkeypatch):
    owner, row = parked(api, monkeypatch)
    params = json.loads(row["params"])
    params["_hand"]["alias"] = "work"
    params["_hand"]["outcome"]["reason"] = "read_scope_review"
    row = api.call("PATCH", "/api/collections/jobs/records/" + row["id"],
                   {"params": json.dumps(params)})
    model = ReplyModel(row)
    answer = answer_in_app(api, owner, row, model)
    assert answer["acted"] and not answer["acted"].startswith("failed")
    assert model.planning_prompts
    assert all('"previous_account_alias": "work"' in prompt for _, prompt in model.planning_prompts)


def test_stale_selected_account_plan_can_recover_through_a_second_owner_reply(api, monkeypatch):
    owner, row = parked(api, monkeypatch)
    answer = answer_in_app(api, owner, row, ReplyModel(row))
    assert answer["acted"] and not answer["acted"].startswith("failed"), answer
    queued = api.call("GET", "/api/collections/jobs/records/" + row["id"])
    params = json.loads(queued["params"])
    params["_hand"]["plan_input"]["workflow_version"] = 0
    api.call("PATCH", "/api/collections/jobs/records/" + row["id"], {"params": json.dumps(params)})
    worker.run_api_jobs(owner)
    state = api.call("GET", "/__fixture/state")
    held = state["jobs"][0]
    note = json.loads(held["params"])["_hand"]
    assert held["status"] == "needs_user" and held["lane"] == "api"
    assert note["alias"] == "work" and note["outcome"]["reason"] == "plan_stale"
    assert note["tool"] == "" and note["args"] is None and note["plan_input"] is None
    assert not held["receipt"] and not held["lease_token"]
    assert not [call for call in state["calls"] if call["method"] == "POST"]
    answer = answer_in_app(api, owner, held, ReplyModel(held))
    assert answer["acted"] and not answer["acted"].startswith("failed"), answer
    worker.run_api_jobs(owner)
    state = api.call("GET", "/__fixture/state")
    final = state["jobs"][0]
    assert final["id"] == row["id"] and final["lane"] == "research"
    assert json.loads(final["params"])["_api_evidence"]["vendor_log_id"] == "fixture-read-receipt"
    calls = [call for call in state["calls"] if call["method"] == "POST"]
    assert len(calls) == 1 and calls[0]["body"]["connected_account_id"] == "fixture-account-work"


@pytest.mark.parametrize("when", ["during_planning", "after_queue", "cancel_after_disconnect"])
def test_disconnect_after_context_read_cannot_move_named_account_work_to_browser(api, monkeypatch, when):
    owner, row = parked(api, monkeypatch)

    def disconnect():
        api.call("POST", "/__fixture/disconnect", {"account": "fixture-account-work"})

    model = ReplyModel(row, before_plan=disconnect if when == "during_planning" else None)
    answer = answer_in_app(api, owner, row, model)
    assert answer["acted"] and not answer["acted"].startswith("failed"), answer
    if when in ("after_queue", "cancel_after_disconnect"):
        disconnect()
    if when == "cancel_after_disconnect":
        current = api.call("GET", "/api/collections/jobs/records/" + row["id"])
        params = json.loads(current["params"])
        plan = cancel(from_params(params), reason="Owner stopped the disconnected task")
        fields = plan.job_fields()
        fields["params"] = json.dumps(put_in_params(params, plan))
        api.call("PATCH", "/api/collections/jobs/records/" + row["id"], fields)
    worker.run_api_jobs(owner)
    state = api.call("GET", "/__fixture/state")
    final = state["jobs"][0]
    assert final["status"] == ("cancelled" if when == "cancel_after_disconnect" else "needs_user")
    assert final["lane"] == "api"
    assert json.loads(final["params"])["_hand"]["alias"] == "work"
    assert final["receipt"] == "" and not final["lease_token"]
    if when == "cancel_after_disconnect":
        assert not final["approval"]
    assert not [call for call in state["calls"] if call["method"] == "POST"]


@pytest.mark.parametrize("mode", ["exception", "unknown", "success"])
def test_account_choice_logs_never_echo_private_model_or_account_data(mode, capsys):
    sentinel = "private_account_sentinel_20260912"
    labels = (sentinel, "personal") if mode == "success" else ("work", "personal")
    context = hands.HandContext(connections=tuple(
        hands.ConnectedApp("fixture_notes", alias=label, status="connected") for label in labels))

    class AccountModel:
        live = True

        def chat(self, system, user, **kwargs):
            if mode == "exception":
                raise RuntimeError(sentinel)
            return SimpleNamespace(text=json.dumps({"account": sentinel, "reason": sentinel}))

    verdict = hands.choose_account(
        hands.HandVerdict(hands.HAND_API, "read", "fixture_notes", hands.EFFECT_READ),
        "Read my notes", context, llm=AccountModel())
    assert verdict.alias == (sentinel if mode == "success" else "")
    captured = capsys.readouterr()
    assert sentinel not in captured.out + captured.err


@pytest.mark.parametrize("learned", [{}, {"account": "work"}])
def test_legacy_requeue_entry_replans_with_conditional_write(api, monkeypatch, learned):
    owner, row = parked(api, monkeypatch)
    row = api.call("GET", "/api/collections/jobs/records/" + row["id"])
    conversation = Conversation(owner, llm=ReplyModel(row))
    assert conversation._requeue(row, learned=learned, owner_text=ANSWER) == row["id"]
    worker.run_api_jobs(owner)
    state = api.call("GET", "/__fixture/state")
    assert state["jobs"][0]["lane"] == "research"
    calls = [call for call in state["calls"] if call["method"] == "POST"]
    assert len(calls) == 1 and calls[0]["body"]["connected_account_id"] == "fixture-account-work"


@pytest.mark.parametrize("fault", ["inventory", "model", "owner_changed"])
def test_unavailable_or_changed_owner_context_keeps_api_task_parked(api, monkeypatch, fault):
    owner, row = parked(api, monkeypatch)

    def interrupt():
        if fault == "model":
            raise RuntimeError("Synthetic model unavailable")
        if fault == "owner_changed":
            owner.owner_ref = "differentowner1"

    model = ReplyModel(row, before_plan=interrupt)
    if fault == "inventory":
        monkeypatch.setattr(hands, "read_connections", lambda *args, **kwargs: None)
    answer_in_app(api, owner, row, model)
    state = api.call("GET", "/__fixture/state")
    assert state["jobs"][0]["status"] == "needs_user"
    assert state["jobs"][0]["lane"] == "api"
    assert not [call for call in state["calls"] if call["method"] == "POST"]


@pytest.mark.parametrize("account,effect", [(None, "read"), ("invented", "read"), ("work", "write")])
def test_unknown_account_or_changed_effect_cannot_release_api_reply(api, monkeypatch, account, effect):
    owner, row = parked(api, monkeypatch)
    answer = answer_in_app(api, owner, row, ReplyModel(row, account=account, effect=effect))
    worker.run_api_jobs(owner)
    state = api.call("GET", "/__fixture/state")
    assert state["jobs"][0]["status"] == "needs_user", answer
    assert state["jobs"][0]["lane"] == "api"
    assert not [call for call in state["calls"] if call["method"] == "POST"]


def test_cancellation_during_account_replan_wins_conditional_write(api, monkeypatch):
    owner, row = parked(api, monkeypatch)

    def stop():
        current = api.call("GET", "/__fixture/state")["jobs"][0]
        params = json.loads(current["params"])
        plan = cancel(from_params(params), reason="Owner cancelled during account choice")
        fields = plan.job_fields()
        fields["params"] = json.dumps(put_in_params(params, plan))
        api.call("PATCH", "/api/collections/jobs/records/" + row["id"], fields)

    model = ReplyModel(row, before_plan=stop)
    answer = answer_in_app(api, owner, row, model)
    state = api.call("GET", "/__fixture/state")
    assert model.before_plan is None, "Never reached the replanning boundary"
    assert answer["acted"].startswith("failed"), answer
    assert state["jobs"][0]["status"] == "cancelled"
    assert not state["jobs"][0]["approval"]
    assert not [call for call in state["calls"] if call["method"] == "POST"]


@pytest.mark.parametrize("intent,question", [("decline", None), ("answer", "stale question")])
def test_declined_or_stale_answer_never_replans(api, monkeypatch, intent, question):
    owner, row = parked(api, monkeypatch)
    model = ReplyModel(row, intent=intent)
    answer_in_app(api, owner, row, model, question=question)
    state = api.call("GET", "/__fixture/state")
    assert not model.planning_prompts
    assert state["jobs"][0]["status"] == ("cancelled" if intent == "decline" else "needs_user")
    assert not [call for call in state["calls"] if call["method"] == "POST"]
