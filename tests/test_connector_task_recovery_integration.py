"""Real core/hand -> real Worker SQL -> provider adapter recovery regression.

These tests fake model decisions and vendor I/O, not lane selection, task
formation, workflow, API claims, connection storage, or API result disposal.
The successful-connection boundary is recordConnection (also used by OAuth).
This is not a real OAuth, browser, model-quality, or final-answer verification.
"""
from __future__ import annotations

import ast
import inspect
import json
import os
from pathlib import Path
import select
import shutil
import subprocess
import threading
import time
from types import SimpleNamespace

import pytest
import requests

from brain import anticipy_core as core, hands, worker
from brain.memory import Memory
from brain.orchestrator import Decision
from brain.workflow import approve, cancel, claim, from_params, put_in_params

ROOT = Path(__file__).resolve().parents[1]
GOAL = "Read my Orion notes"
TEXT = "Please read my Orion notes in the connected notes app."


class Model:
    live = True
    # What the model answers the account question with, when two accounts are
    # connected: None is "nothing said settles it", and the owner is asked.
    account = None

    def chat(self, system, user, **kwargs):
        if system == hands.HANDS_SYSTEM:
            value = {"hand": "api", "app": "fixture_notes", "effect": "read",
                     "reason": "The requested private notes are in this app."}
        elif system == hands.ACCOUNT_SYSTEM:
            value = {"account": type(self).account, "reason": "scripted"}
        elif system == hands.TOOLS_SYSTEM:
            value = {"verdict": "tool", "tool": "FIXTURE_NOTES_READ",
                     "args": {"query": "Orion"}, "effect": "read", "reason": "Reads the requested notes."}
        else:
            raise AssertionError("Unexpected model question in connector recovery fixture")
        return SimpleNamespace(text=json.dumps(value))


@pytest.fixture
def api(monkeypatch, tmp_path):
    # Never load .env or pass inherited credentials to the child process.
    node = shutil.which("node")
    assert node, "Node 24 is required for the actual Worker fixture"
    env = {key: os.environ[key] for key in ("PATH", "TMPDIR", "SYSTEMROOT") if key in os.environ}
    env.update(CLOUDFLARE_LOAD_DEV_VARS_FROM_DOT_ENV="false", WRANGLER_SEND_METRICS="false")
    errors = (tmp_path / "worker.log").open("w+")
    process = subprocess.Popen([node, "--experimental-strip-types", str(ROOT / "tests/fixtures/connector_task_api.ts")],
                               cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=errors, text=True)
    try:
        assert select.select([process.stdout], [], [], 15)[0], "Worker fixture did not start"
        line = process.stdout.readline()
        assert line, "Worker fixture failed: " + _log(errors)
        ready = json.loads(line)
        assert ready["base"].startswith("http://127.0.0.1:")
        monkeypatch.setenv("ANTICIPY_SERVICE_TOKEN", "fixture-service-token")
        monkeypatch.setenv("ANTICIPY_PB", ready["base"])
        monkeypatch.setattr(worker, "PB", ready["base"])
        monkeypatch.setattr(worker, "_api_hand_down_until", 0.0)
        original = requests.sessions.Session.request

        def local_only(session, method, url, **kwargs):
            assert url.startswith(ready["base"] + "/"), "External Python network forbidden"
            kwargs["allow_redirects"] = False
            return original(session, method, url, **kwargs)

        monkeypatch.setattr(requests.sessions.Session, "request", local_only)

        def call(method, path, body=None):
            response = requests.request(method, ready["base"] + path, json=body,
                                        headers={"X-Anticipy-Token": "fixture-service-token"}, timeout=10)
            assert response.ok, (response.status_code, response.text, _log(errors))
            return response.json()

        instances: list = []
        yield SimpleNamespace(**ready, call=call, instances=instances)
    finally:
        # THE THREAD OUTLIVES THE TEST UNLESS SOMETHING STOPS IT. Recovery runs
        # on a pool thread holding an HTTP client pointed at the server this
        # block is about to kill, and ThreadPoolExecutor joins its threads at
        # interpreter shutdown — so a leaked one turns into a hang in a later
        # test, or a connection refused from a thread nobody is watching.
        for instance in instances:
            worker.close_connection_recovery(instance, wait=True)
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        errors.close()


def _log(file):
    file.flush()
    file.seek(0)
    return file.read()[-6000:]


def form_task(api, monkeypatch, *, touches="read", about=""):
    """Form one real task from one real typed line.

    `about` names a DIFFERENT thing to read. Two identical utterances are the
    same errand and the core is right to fold them together, so a test that
    wants three tasks has to ask for three things.
    """
    text = TEXT if not about else TEXT.replace("my Orion notes", f"my {about} notes")
    goal = GOAL if not about else GOAL.replace("my Orion notes", f"my {about} notes")
    event = api.call("POST", "/api/collections/events/records", {
        "owner_ref": api.owner, "device_id": "connector-fixture", "kind": "transcript",
        "source": "typed", "text": text, "decision": ""})
    a = core.Anticipy(memory=Memory(":memory:"), llm=None, owner_ref=api.owner,
                     backend_url=api.base, owner_phone="")
    # Script triage only; the actual hear/queue/workflow path remains intact.
    monkeypatch.setattr(a, "_decide", lambda *args, **kwargs: Decision(
        decision="act", goal=goal, reason="The owner requested a read.",
        addressee="assistant", owes="owner", touches=touches, needs_confirmation=False))
    monkeypatch.setattr(hands, "_default_llm", Model)
    heard = a.hear(text, explicit=True, channel="app", capture_source="typed",
                   source_event_id=event["id"], speaker="owner", may_say=lambda *args, **kwargs: False)
    jobs = api.call("GET", "/__fixture/state")["jobs"]
    assert heard["decision"].decision == "act"
    # THIS event's task, not "the only task". Most checks here form one and the
    # distinction does not matter; the rotation check forms three and it does.
    mine = [job for job in jobs
            if json.loads(job["params"])["_workflow"]["source_event_ids"] == [event["id"]]]
    assert len(mine) == 1, f"one event produced {len(mine)} tasks"
    job = mine[0]
    params = json.loads(job["params"])
    assert params["_workflow"]["consequence"] == ("consequential" if touches == "world" else "read_only")
    assert params["source"] == text
    api.instances.append(a)
    return a, job


def owner_tick(api, a, *, wait=True):
    """One beat of the owner pump, then wait for whatever it scheduled.

    `recover_connected_read` SCHEDULES and returns — that is the whole point of
    the rewrite, and `test_the_owner_loop_never_waits_for_a_blocked_replan`
    is what holds it to that. Every other test has to wait explicitly, because
    an assertion made against a thread that has not started yet is an assertion
    about nothing, and it passes for the wrong reason.
    """
    state = getattr(a, "_connection_recovery", None)
    if state is not None:
        state.scan_at = 0.0
    worker.run_api_jobs(a)
    return worker.drain_connection_recovery(a) if wait else False


def stored_receipt(api, job_id):
    """The durable retry receipt as the DATABASE holds it, not as Python
    remembers it. The budget has to survive a restart, so the row is the only
    place worth reading it from."""
    jobs = api.call("GET", "/__fixture/state")["jobs"]
    row = next(j for j in jobs if j["id"] == job_id)
    return json.loads(row["params"]).get("_hand", {}).get("_connection_recovery")


def assert_read_ran_once(api, original):
    state = api.call("GET", "/__fixture/state")
    assert len(state["jobs"]) == 1, "Recovery must not create a second task"
    job = state["jobs"][0]
    assert job["id"] == original["id"]
    assert job["lane"] == "research", "The same task never reached API result synthesis"
    params = json.loads(job["params"])
    assert params.get("_api_evidence"), "A lane change is not evidence of a provider read"
    executed = [call for call in state["calls"] if call["method"] == "POST"]
    assert len(executed) == 1 and executed[0]["path"] == "/tools/execute/FIXTURE_NOTES_READ"
    assert params["_workflow"]["source_event_ids"] == json.loads(original["params"])["_workflow"]["source_event_ids"]
    return job


def test_fresh_task_with_connected_app_reaches_real_api_hand(api, monkeypatch):
    api.call("POST", "/__fixture/connect")
    a, job = form_task(api, monkeypatch)
    assert job["lane"] == "api"
    worker.run_api_jobs(a)
    assert_read_ran_once(api, job)


def test_preexisting_waiting_task_recovers_after_connection(api, monkeypatch):
    a, job = form_task(api, monkeypatch)
    assert job["status"] == "queued" and job["lane"] == ""
    assert hands.gather_context(json.loads(job["params"]), api.owner, api.base).browser_online is False
    api.call("POST", "/__fixture/connect")
    # This is the existing API owner-pump entry point, not a test-side lane edit.
    # It takes two beats now: the first schedules the replan and returns without
    # waiting for it, the second finds the task on the api lane and runs it.
    assert owner_tick(api, a), "the owner tick scheduled no replan"
    worker.run_api_jobs(a)
    assert_read_ran_once(api, job)


@pytest.mark.parametrize("state", ["running", "cancelled", "approved_write"])
def test_connecting_cannot_take_running_cancelled_or_approved_write(api, monkeypatch, state):
    a, job = form_task(api, monkeypatch, touches="world" if state == "approved_write" else "read")
    params = json.loads(job["params"])
    workflow = from_params(params)
    if state == "running":
        workflow = claim(workflow, expected_version=workflow.version, actor_id="fixture-browser")
    elif state == "cancelled":
        workflow = cancel(workflow, reason="Owner cancelled the fixture task")
    else:
        workflow = approve(workflow, expected_version=workflow.version, owner_words="Proceed with this fixture task")
    body = workflow.job_fields()
    if state == "running":
        body.update(claimed_by="fixture-browser", claimed_at=workflow.lease.acquired_at.isoformat())
    body["params"] = json.dumps(put_in_params(params, workflow))
    api.call("PATCH", "/api/collections/jobs/records/" + job["id"], body)
    before = api.call("GET", "/__fixture/state")["jobs"]
    api.call("POST", "/__fixture/connect")
    # Waiting matters here more than anywhere: without the drain this assertion
    # would hold because the replan had not begun, which is indistinguishable
    # from a replan that correctly refused.
    owner_tick(api, a)
    worker.run_api_jobs(a)
    after = api.call("GET", "/__fixture/state")
    assert after["jobs"] == before
    assert not [call for call in after["calls"] if call["method"] == "POST"]


def proposed_recovery(api, job):
    response = requests.get(api.base + "/api/collections/jobs/records/" + job["id"],
                            headers={"X-Anticipy-Token": "fixture-service-token"}, timeout=10)
    assert response.ok
    params = json.loads(response.json()["params"])
    assert core.job_lane(job["goal"], params, owner_ref=api.owner, backend_url=api.base, llm=Model()) == "api"
    return {"lane": "api", "params": json.dumps(params)}, {
        "X-Anticipy-Token": "fixture-service-token", "X-Anticipy-Worker": "1",
        "If-Match": response.headers["ETag"]}


@pytest.mark.parametrize("field", ["claimed_by", "claimed_at", "lane"])
def test_same_timestamp_claim_or_lane_race_rejects_recovery(api, monkeypatch, field):
    _, job = form_task(api, monkeypatch)
    api.call("POST", "/__fixture/connect")
    body, headers = proposed_recovery(api, job)
    api.call("POST", "/__fixture/race", {"field": field})
    response = requests.patch(api.base + "/api/collections/jobs/records/" + job["id"],
                              json=body, headers=headers, timeout=10)
    assert response.status_code == 412, "The atomic SQL write must lose to a new claimant/routing decision"
    state = api.call("GET", "/__fixture/state")
    assert state["jobs"][0]["params"] == job["params"]
    assert not [call for call in state["calls"] if call["method"] == "POST"]


@pytest.mark.parametrize("violation", ["missing_cas", "missing_worker", "agent", "write", "owner", "source", "version", "extra_field"])
def test_reroute_cannot_change_authority_or_bypass_caller_fences(api, monkeypatch, violation):
    _, job = form_task(api, monkeypatch)
    api.call("POST", "/__fixture/connect")
    body, headers = proposed_recovery(api, job)
    params = json.loads(body["params"])
    if violation == "missing_cas":
        headers.pop("If-Match")
    elif violation == "missing_worker":
        headers.pop("X-Anticipy-Worker")
    elif violation == "agent":
        headers["X-Anticipy-Agent-ID"] = "fixture-browser"
    elif violation == "write":
        params["_hand"]["effect"] = "write"
    elif violation == "owner":
        params["_workflow"]["owner_ref"] = "fixtureowner002"
    elif violation == "source":
        params["source"] = "Different owner instruction"
    elif violation == "version":
        params["_hand"]["plan_input"]["workflow_version"] += 1
    else:
        body["approval"] = "invented approval"
    body["params"] = json.dumps(params)
    response = requests.patch(api.base + "/api/collections/jobs/records/" + job["id"],
                              json=body, headers=headers, timeout=10)
    assert response.status_code == 403
    state = api.call("GET", "/__fixture/state")
    assert state["jobs"] == [job]
    assert not [call for call in state["calls"] if call["method"] == "POST"]


class Unavailable:
    """A model that is reachable and answers with a failure, every time."""
    live = True
    calls = 0

    def chat(self, *args, **kwargs):
        self.calls += 1
        raise RuntimeError("fixture model unavailable")


def rewind_retry(api, job_id):
    """Make the durable backoff due now, the way five real minutes would.

    It rewrites `retry_at` and nothing else. The receipt lives under `_hand`,
    which the fingerprint deliberately excludes, so a rewind cannot be mistaken
    by the implementation for a task whose facts changed.
    """
    path = api.base + "/api/collections/jobs/records/" + job_id
    token = {"X-Anticipy-Token": "fixture-service-token"}
    before = requests.get(path, headers=token, timeout=10)
    assert before.ok
    params = json.loads(before.json()["params"])
    receipt = params["_hand"]["_connection_recovery"]
    receipt["retry_at"] = 0
    after = requests.patch(path, json={"params": json.dumps(params)},
                           headers={**token, "X-Anticipy-Worker": "1",
                                    "If-Match": before.headers["ETag"]}, timeout=10)
    assert after.ok, (after.status_code, after.text)
    return receipt


def test_a_failed_replan_costs_one_attempt_and_backs_off_in_the_row(api, monkeypatch):
    """The spend is stopped by a DURABLE receipt, not by a process's memory.

    The previous design kept a per-process cache, so a restart between two owner
    ticks bought the same task another model call for free. This asserts the
    budget is where a restart can still see it.
    """
    a, job = form_task(api, monkeypatch)
    api.call("POST", "/__fixture/connect")
    model = Unavailable()
    monkeypatch.setattr(hands, "_default_llm", lambda: model)

    for _ in range(10):
        owner_tick(api, a)
    assert model.calls == 1, "ten owner ticks may buy exactly one attempt"

    receipt = stored_receipt(api, job["id"])
    assert receipt["attempts"] == 1
    assert receipt["retry_at"] > time.time(), "the backoff must outlive this process"
    state = api.call("GET", "/__fixture/state")
    assert state["jobs"][0]["lane"] == "", "a failed replan must not move the task"
    assert not [call for call in state["calls"] if call["method"] == "POST"]


def test_a_restart_inherits_the_budget_rather_than_resetting_it(api, monkeypatch):
    """A crash between the reservation and the model still costs the attempt."""
    a, job = form_task(api, monkeypatch)
    api.call("POST", "/__fixture/connect")
    model = Unavailable()
    monkeypatch.setattr(hands, "_default_llm", lambda: model)
    owner_tick(api, a)
    assert model.calls == 1
    assert stored_receipt(api, job["id"])["attempts"] == 1

    # The process dies — thread, cursor, scan clock and all — and comes back.
    worker.close_connection_recovery(a, wait=True)
    restarted = core.Anticipy(memory=Memory(":memory:"), llm=None, owner_ref=api.owner,
                              backend_url=api.base, owner_phone="")
    api.instances.append(restarted)
    for _ in range(5):
        owner_tick(api, restarted)
    assert model.calls == 1, "a restart must not buy a fresh attempt"
    assert stored_receipt(api, job["id"])["attempts"] == 1


def test_three_attempts_exhaust_the_budget_and_the_fourth_spends_nothing(api, monkeypatch):
    a, job = form_task(api, monkeypatch)
    api.call("POST", "/__fixture/connect")
    model = Unavailable()
    monkeypatch.setattr(hands, "_default_llm", lambda: model)

    for expected in (1, 2, 3):
        owner_tick(api, a)
        assert model.calls == expected
        assert stored_receipt(api, job["id"])["attempts"] == expected
        if expected < 3:
            rewind_retry(api, job["id"])

    rewind_retry(api, job["id"])
    for _ in range(5):
        owner_tick(api, a)
    assert model.calls == 3, "an exhausted task must never be planned again"
    assert stored_receipt(api, job["id"])["attempts"] == 3


def test_changed_connection_facts_start_a_fresh_budget(api, monkeypatch):
    """Three attempts are three attempts at THE SAME QUESTION.

    When what is true about the owner's connections changes, the question is a
    different one and gets its own budget — otherwise connecting the app that
    would have answered a task is worth nothing once its three are gone.
    """
    a, job = form_task(api, monkeypatch)
    api.call("POST", "/__fixture/connect")
    model = Unavailable()
    monkeypatch.setattr(hands, "_default_llm", lambda: model)
    for expected in (1, 2, 3):
        owner_tick(api, a)
        assert model.calls == expected
        rewind_retry(api, job["id"])
    exhausted = stored_receipt(api, job["id"])

    api.call("POST", "/__fixture/facts", {"writes_enabled": True})
    owner_tick(api, a)
    assert model.calls == 4, "changed connection facts are a new question"
    fresh = stored_receipt(api, job["id"])
    assert fresh["fingerprint"] != exhausted["fingerprint"]
    assert fresh["attempts"] == 1


def test_the_owner_loop_never_waits_for_a_blocked_replan(api, monkeypatch):
    """THE REASON THIS IS A THREAD AT ALL.

    The synchronous design this replaced was rejected in review because it could
    stand between the owner and an answer for as long as a model took. So: block
    the model outright, and prove the owner's own beat still turns.
    """
    a, job = form_task(api, monkeypatch)
    api.call("POST", "/__fixture/connect")
    entered, released = threading.Event(), threading.Event()

    class Blocked:
        live = True
        calls = 0

        def chat(self, *args, **kwargs):
            type(self).calls += 1
            entered.set()
            released.wait(30)
            raise RuntimeError("fixture model released")

    monkeypatch.setattr(hands, "_default_llm", Blocked)
    try:
        started = time.monotonic()
        worker.run_api_jobs(a)
        assert time.monotonic() - started < 5, "scheduling a replan must not wait for it"
        assert entered.wait(20), "the replan never reached the model"

        for _ in range(5):
            beat = time.monotonic()
            worker.run_api_jobs(a)
            assert time.monotonic() - beat < 5, "the owner beat blocked behind the model"
        assert Blocked.calls == 1, "one in-flight attempt must not be started again"
        assert not getattr(a, "_connection_recovery").future.done()
    finally:
        released.set()
        worker.drain_connection_recovery(a)

    assert api.call("GET", "/__fixture/state")["jobs"][0]["lane"] == ""


def test_a_cancellation_while_the_model_plans_loses_the_conditional_write(api, monkeypatch):
    """The owner changes their mind between the plan and the write.

    The reservation is taken before the model, so the row this attempt is about
    is fixed. If ANYTHING alters it while the model is thinking, the plan is
    thrown away rather than written over the owner's decision.
    """
    a, job = form_task(api, monkeypatch)
    api.call("POST", "/__fixture/connect")
    scripted = Model()
    cancelled = []

    class CancelsWhilePlanning:
        live = True

        def chat(self, system, user, **kwargs):
            if system == hands.HANDS_SYSTEM and not cancelled:
                path = api.base + "/api/collections/jobs/records/" + job["id"]
                token = {"X-Anticipy-Token": "fixture-service-token"}
                current = requests.get(path, headers=token, timeout=10)
                params = json.loads(current.json()["params"])
                workflow = cancel(from_params(params), reason="Owner cancelled mid-plan")
                body = workflow.job_fields()
                body["params"] = json.dumps(put_in_params(params, workflow))
                done = requests.patch(path, json=body,
                                      headers={**token, "X-Anticipy-Worker": "1",
                                               "If-Match": current.headers["ETag"]}, timeout=10)
                assert done.ok, (done.status_code, done.text)
                cancelled.append(True)
            return scripted.chat(system, user, **kwargs)

    monkeypatch.setattr(hands, "_default_llm", CancelsWhilePlanning)
    owner_tick(api, a)
    assert cancelled, "the fixture never reached the planning model"

    state = api.call("GET", "/__fixture/state")
    row = state["jobs"][0]
    assert row["lane"] == "", "a cancelled task must not be moved to the api lane"
    assert json.loads(row["params"])["_workflow"]["state"] == "cancelled"
    assert not [call for call in state["calls"] if call["method"] == "POST"], \
        "no provider read may follow a plan the write refused"


def test_a_replan_must_not_rewind_a_budget_another_process_advanced(api, monkeypatch):
    """THE CONDITIONAL WRITE, ISOLATED FROM THE FENCE BEHIND IT.

    The Worker's own reroute fence compares params-WITHOUT-`_hand` before and
    after, so any test built on a cancellation or an ordinary amendment proves
    that fence and not this code. The one thing the fence deliberately does not
    compare is `_hand` — which is where the durable retry receipt lives.

    So: a second brain process for the same owner advances the budget while this
    one is at the model. The plan in this thread's hand still carries the OLD
    receipt. Writing it back would be allowed by the Worker and would rewind the
    shared budget by one attempt, every time, forever. Only the fresh read and
    the `!= reserved_row` comparison stop it.
    """
    a, job = form_task(api, monkeypatch)
    api.call("POST", "/__fixture/connect")
    scripted = Model()
    advanced = []

    class AdvancesTheBudgetWhilePlanning:
        live = True

        def chat(self, system, user, **kwargs):
            if system == hands.HANDS_SYSTEM and not advanced:
                path = api.base + "/api/collections/jobs/records/" + job["id"]
                token = {"X-Anticipy-Token": "fixture-service-token"}
                current = requests.get(path, headers=token, timeout=10)
                params = json.loads(current.json()["params"])
                receipt = params["_hand"]["_connection_recovery"]
                assert receipt["attempts"] == 1, "this thread's own reservation"
                receipt["attempts"] = 2
                done = requests.patch(path, json={"params": json.dumps(params)},
                                      headers={**token, "X-Anticipy-Worker": "1",
                                               "If-Match": current.headers["ETag"]}, timeout=10)
                assert done.ok, (done.status_code, done.text)
                advanced.append(True)
            return scripted.chat(system, user, **kwargs)

    monkeypatch.setattr(hands, "_default_llm", AdvancesTheBudgetWhilePlanning)
    owner_tick(api, a)
    assert advanced, "the fixture never reached the planning model"

    state = api.call("GET", "/__fixture/state")
    row = state["jobs"][0]
    assert stored_receipt(api, job["id"])["attempts"] == 2, \
        "the replan wrote a stale budget over the one it never read"
    assert row["lane"] == "", "a plan made against a superseded row must not be applied"
    assert not [call for call in state["calls"] if call["method"] == "POST"]


def test_a_lost_reservation_buys_no_model_call(api, monkeypatch):
    """The reservation is what authorises the spend, and it comes first.

    A second writer taking the row between the read and the reservation must
    cost nothing: no model, no provider, no lane change. The reservation is the
    only thing standing between a contended row and an unbounded bill.
    """
    a, job = form_task(api, monkeypatch)
    api.call("POST", "/__fixture/connect")
    model = Unavailable()
    monkeypatch.setattr(hands, "_default_llm", lambda: model)

    # The next UPDATE on jobs is the reservation; this makes it lose.
    api.call("POST", "/__fixture/race", {"field": "claimed_by"})
    owner_tick(api, a)

    assert model.calls == 0, "a replan that could not reserve must not reach a model"
    state = api.call("GET", "/__fixture/state")
    assert state["jobs"][0]["lane"] == ""
    assert stored_receipt(api, job["id"]) is None, "a lost reservation records no attempt"
    assert not [call for call in state["calls"] if call["method"] == "POST"]


def test_shutdown_stops_the_recovery_thread_rather_than_leaking_it(api, monkeypatch):
    """close_connection_recovery must actually end the thread, not just intend to."""
    a, job = form_task(api, monkeypatch)
    api.call("POST", "/__fixture/connect")
    entered, released = threading.Event(), threading.Event()

    class Blocked:
        live = True

        def chat(self, *args, **kwargs):
            entered.set()
            released.wait(30)
            raise RuntimeError("fixture model released")

    monkeypatch.setattr(hands, "_default_llm", Blocked)
    worker.run_api_jobs(a)
    assert entered.wait(20), "the replan never reached the model"

    state = a._connection_recovery
    worker.close_connection_recovery(a)
    assert state.stop.is_set(), "the thread was never told to stop"

    released.set()
    assert state.future.result(timeout=30) is not None
    worker.close_connection_recovery(a, wait=True)
    assert not any(t.name.startswith("connection-read-recovery") and t.is_alive()
                   for t in threading.enumerate()), "the recovery thread outlived shutdown"

    # Safe twice, because a shutdown path that cannot be re-entered is a
    # shutdown path that turns an ordinary error into a second one.
    worker.close_connection_recovery(a, wait=True)


def test_the_process_entry_point_closes_recovery_on_the_way_out():
    """THE WIRING ITSELF, READ OUT OF THE SOURCE.

    Production runs this module as `python -m brain.worker`, so the
    `if __name__ == "__main__"` block is the process entry point and the only
    place a shutdown can reach the pool: ThreadPoolExecutor joins its threads
    before atexit handlers run. A behavioural test cannot see whether that
    wiring exists, so this reads the real file, the way the iOS gates read
    theirs. It goes red if somebody calls `main()` bare again.
    """
    tree = ast.parse(Path(inspect.getsourcefile(worker)).read_text())
    guards = [node for node in tree.body if isinstance(node, ast.If)
              and ast.unparse(node.test) == "__name__ == '__main__'"]
    assert len(guards) == 1, "brain.worker has no single module entry point"
    tries = [node for node in guards[0].body if isinstance(node, ast.Try)]
    assert tries, "the entry point calls main() with no shutdown path at all"
    closing = [ast.unparse(node) for node in ast.walk(tries[0])
               if isinstance(node, ast.Call)
               and getattr(node.func, "id", "") == "close_connection_recovery"]
    assert any("ACTIVE_ANTICIPY" in call for call in closing), \
        "the entry point never closes the live owner's recovery thread"
    assert any(isinstance(node, ast.Call) and getattr(node.func, "id", "") == "main"
               for node in ast.walk(tries[0].body[0])), "main() is not what is being guarded"
    assert tries[0].finalbody, "a shutdown in `except` is a shutdown a clean exit skips"


def test_an_api_hand_outage_does_not_also_stop_replanning(api, monkeypatch):
    """Replanning is not execution, and the backoff belongs to execution.

    `_api_hand_down_until` is the five-minute hold that stops this process
    hammering a /hands/api/run that just failed. Recovery neither claims nor
    runs anything — it decides that a task which has been waiting on a browser
    can now take the api lane. Behind the hold, one door failing froze every
    replan for five minutes, so a task waiting on an app the owner had JUST
    connected sat there with nothing to say why.
    """
    a, job = form_task(api, monkeypatch)
    api.call("POST", "/__fixture/connect")
    monkeypatch.setattr(worker, "_api_hand_down_until", time.time() + 300)

    assert owner_tick(api, a), "the replan was skipped while the api hand was held down"
    assert api.call("GET", "/__fixture/state")["jobs"][0]["lane"] == "api", \
        "the task was never replanned onto the api lane"
    # ...and the hold is still doing its own job: nothing was claimed or run.
    state = api.call("GET", "/__fixture/state")
    assert not [call for call in state["calls"] if call["method"] == "POST"]
    assert not state["jobs"][0]["claimed_by"]

    # Once the hold lifts, the same pump executes it.
    monkeypatch.setattr(worker, "_api_hand_down_until", 0.0)
    worker.run_api_jobs(a)
    assert_read_ran_once(api, job)


def test_one_unrecoverable_task_cannot_starve_the_ones_behind_it(api, monkeypatch):
    """THE CURSOR, AND WHY IT IS A KEYSET AND NOT A `LIMIT 1`.

    The list filter selects queued read-only tasks on the browser lane; whether
    a task is CLAIMED is checked afterwards, on the row itself. So a claimed
    task keeps matching the list forever. A scan that always took the first
    match would hand back the same unrecoverable row on every tick and nothing
    behind it would ever be looked at — the owner connects an app and the task
    that was waiting for it never moves, with nothing anywhere saying why.

    Three tasks, the first one permanently ineligible. Both of the others must
    be replanned. This does not separately exercise the >25-task case; it
    exercises the rotation and the wrap that case depends on.
    """
    formed = [form_task(api, monkeypatch, about=about)
              for about in ("Orion", "Lyra", "Vega")]
    a = formed[-1][0]
    api.call("POST", "/__fixture/connect")
    # The scan orders by id, and ids are minted, not sequential — so the row a
    # naive `LIMIT 1` would keep returning is the lexicographically smallest.
    # That is the one to make unrecoverable.
    tasks = sorted((job for _, job in formed), key=lambda job: job["id"])
    blocked, rest = tasks[0], tasks[1:]

    # The first task is claimed by a browser agent: it still matches the list
    # query, and the row read will always refuse it.
    path = api.base + "/api/collections/jobs/records/" + blocked["id"]
    token = {"X-Anticipy-Token": "fixture-service-token"}
    current = requests.get(path, headers=token, timeout=10)
    patched = requests.patch(path, json={"claimed_by": "fixture-browser",
                                         "claimed_at": "2026-09-11T00:00:00Z"},
                             headers={**token, "X-Anticipy-Worker": "1",
                                      "If-Match": current.headers["ETag"]}, timeout=10)
    assert patched.ok, (patched.status_code, patched.text)

    for _ in range(8):
        owner_tick(api, a)

    lanes = {job["id"]: job["lane"] for job in api.call("GET", "/__fixture/state")["jobs"]}
    assert lanes[blocked["id"]] == "", "a claimed task was replanned"
    for job in rest:
        # "api" means replanned and waiting; "research" means the same pump then
        # ran it and filed the result. Either is proof it was reached at all,
        # which is the only thing this check is about.
        assert lanes[job["id"]] in ("api", "research"), \
            f"task {job['id']} was starved behind an unrecoverable one"


@pytest.mark.parametrize("mode", ["http403", "tool403"])
def test_a_scope_403_on_one_tool_does_not_declare_the_account_dead(api, monkeypatch, mode):
    """ACTIVE is not "every tool runs", and one refused tool is not a dead credential.

    The catalog the planner reads is the vendor's GLOBAL list for the toolkit,
    so a tool the account's granted scopes do not cover is still an allow-list
    entry. Its 403 — as an HTTP status or as a 2xx body carrying status 403 —
    used to flip the whole connection to needs_reconnect: Settings said
    "needs reconnect", the weekly nudge asked for a reconnect that changed
    nothing, and the brain's inventory dropped the app. The Worker now reads
    the vendor's account status after the refusal, and ACTIVE leaves the row.
    """
    api.call("POST", "/__fixture/connect")
    a, job = form_task(api, monkeypatch)
    assert job["lane"] == "api"
    api.call("POST", "/__fixture/deny", {"mode": mode})
    worker.run_api_jobs(a)
    state = api.call("GET", "/__fixture/state")
    row = next(j for j in state["jobs"] if j["id"] == job["id"])
    executed = [c for c in state["calls"] if c["method"] == "POST"]
    assert len(executed) == 1, "exactly one vendor execute was attempted"
    assert [c for c in state["calls"] if c["path"] == "/connected_accounts"], \
        "the Worker must read the vendor's account status before deciding the credential died"
    assert state["connections"][0]["status"] == "connected", \
        f"one refused tool ({mode}) flipped the connection to {state['connections'][0]['status']!r}"
    note = json.loads(row["params"])["_hand"]
    assert note["outcome"]["credential"] == "alive"
    assert row["lane"] == "", "the step still hands back to the browser"
    assert "still connected" in row["result"] and "reconnect" not in row["result"], row["result"]


def test_a_vendor_that_says_expired_still_flips_the_connection(api, monkeypatch):
    """THE CONTROL: a real expiry, in the vendor's own enum, still marks the row."""
    api.call("POST", "/__fixture/connect")
    a, job = form_task(api, monkeypatch)
    api.call("POST", "/__fixture/deny", {"mode": "http403", "status": "EXPIRED"})
    worker.run_api_jobs(a)
    state = api.call("GET", "/__fixture/state")
    assert state["connections"][0]["status"] == "needs_reconnect"
    row = next(j for j in state["jobs"] if j["id"] == job["id"])
    assert json.loads(row["params"])["_hand"]["outcome"]["credential"] == "dead"
    assert "reconnect" in row["result"]


def test_workflow_bookkeeping_does_not_mint_a_fresh_budget(api, monkeypatch):
    """A handback rewrites `_workflow` (state, reason, updated_at, attempts); the
    question is the same. Measured 2026-09-12: the fingerprint hashed the whole
    `_workflow`, so every api->browser bounce started a new three-attempt
    budget and an ambiguous task was re-planned six times before the attempt
    cap failed it. Identity fields count; bookkeeping does not.
    """
    a, job = form_task(api, monkeypatch)
    api.call("POST", "/__fixture/connect")
    model = Unavailable()
    monkeypatch.setattr(hands, "_default_llm", lambda: model)
    owner_tick(api, a)
    assert model.calls == 1
    assert stored_receipt(api, job["id"])["attempts"] == 1

    # What a Worker handback does to the row's workflow envelope, and nothing
    # more: the plan, its version, goal, scope and consequence are untouched.
    path = api.base + "/api/collections/jobs/records/" + job["id"]
    token = {"X-Anticipy-Token": "fixture-service-token"}
    current = requests.get(path, headers=token, timeout=10)
    params = json.loads(current.json()["params"])
    params["_workflow"]["reason"] = "handed back once"
    params["_workflow"]["updated_at"] = "2026-09-12T00:00:01+00:00"
    params["_hand"]["_connection_recovery"]["retry_at"] = 0     # the backoff is due
    done = requests.patch(path, json={"params": json.dumps(params)},
                          headers={**token, "X-Anticipy-Worker": "1", "If-Match": current.headers["ETag"]}, timeout=10)
    assert done.ok, (done.status_code, done.text)

    owner_tick(api, a)
    receipt = stored_receipt(api, job["id"])
    assert receipt["attempts"] == 2, "the same question continues its budget"
    assert model.calls == 2

    # And the CONTROL: identity DOES change the question.
    current = requests.get(path, headers=token, timeout=10)
    params = json.loads(current.json()["params"])
    params["_workflow"]["reason"] = "handed back twice"
    params["_hand"]["_connection_recovery"]["retry_at"] = 0
    done = requests.patch(path, json={"params": json.dumps(params)},
                          headers={**token, "X-Anticipy-Worker": "1", "If-Match": current.headers["ETag"]}, timeout=10)
    assert done.ok
    owner_tick(api, a)
    assert stored_receipt(api, job["id"])["attempts"] == 3
    owner_tick(api, a)
    assert model.calls == 3, "three attempts, and the fourth spends nothing"


def test_two_accounts_and_nothing_said_parks_the_task_for_the_owner_on_the_api_lane(api, monkeypatch):
    """Report 3 and 5: work and personal connected, "read my notes", nothing
    said about which. Until 2026-09-12 the row was handed to the BROWSER lane
    (which runs in whatever account Chrome is signed into) and, with Chrome
    closed, bounced api->browser->api until the attempt cap failed it after
    six model calls, the owner never asked. Now it parks on the api lane with
    the owner's own labels in the question, after one planning pass.
    """
    api.call("POST", "/__fixture/connect", {"alias": "personal", "account": "fixture-account-personal"})
    api.call("POST", "/__fixture/connect", {"alias": "work", "account": "fixture-account-work"})
    monkeypatch.setattr(Model, "account", None)
    a, job = form_task(api, monkeypatch)
    assert job["lane"] == "api"
    assert json.loads(job["params"])["_hand"]["alias"] == "", "nothing said: no account chosen for him"
    worker.run_api_jobs(a)
    state = api.call("GET", "/__fixture/state")
    row = next(j for j in state["jobs"] if j["id"] == job["id"])
    assert row["status"] == "needs_user", f"the owner was not asked: {row['status']!r} {row['result']!r}"
    assert row["lane"] == "api", "the question must not sit on the browser lane"
    assert "personal" in row["result"] and "work" in row["result"], row["result"]
    assert not [c for c in state["calls"] if c["method"] == "POST"], "no vendor read may run against a guessed account"
    # And it stays parked: the owner pump does not re-plan a row that is waiting on him.
    owner_tick(api, a)
    assert api.call("GET", "/__fixture/state")["jobs"][0]["status"] == "needs_user"


def test_a_named_account_runs_the_read_against_that_account(api, monkeypatch):
    api.call("POST", "/__fixture/connect", {"alias": "personal", "account": "fixture-account-personal"})
    api.call("POST", "/__fixture/connect", {"alias": "work", "account": "fixture-account-work"})
    monkeypatch.setattr(Model, "account", "work")
    a, job = form_task(api, monkeypatch)
    assert json.loads(job["params"])["_hand"]["alias"] == "work"
    worker.run_api_jobs(a)
    state = api.call("GET", "/__fixture/state")
    executed = [c for c in state["calls"] if c["method"] == "POST"]
    assert len(executed) == 1 and executed[0]["body"]["connected_account_id"] == "fixture-account-work"
    row = next(j for j in state["jobs"] if j["id"] == job["id"])
    assert row["lane"] == "research" and json.loads(row["params"]).get("_api_evidence")
