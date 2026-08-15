"""The 2026-08-11 live teardown, pinned.

Five behaviors were watched failing in the live end-to-end run:
1. "make it 6pm instead" on a held 8pm card released the job with a
   fabricated scope (`They said: "yes"`) while the goal stayed at 8pm — the
   correction was acknowledged in words and ignored in deed.
2. The resume after "I told you to make it 6 dammit" carried "6" into an
   OTP field and the model padded it into "666666" and submitted it.
3. "Okay let's do it." spoken after a held dinner card minted a SECOND card
   out of a leaked internal instruction instead of releasing the held plan.
4. An answered clarification ("which saturday?" → "this saturday") left no
   job behind — the plan evaporated.
5. "why is nothing happening" right after a 3-strike failure got a
   deflecting question instead of the failure's name.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import brain.anticipy_core as coremod  # noqa: E402
import brain.conversation as convmod  # noqa: E402
from brain.anticipy_core import Anticipy  # noqa: E402
from brain.conversation import Conversation, REPLY_SYSTEM  # noqa: E402
from brain.memory import Memory  # noqa: E402
from brain.orchestrator import Decision  # noqa: E402


def _conv():
    a = Anticipy(memory=Memory(":memory:"), llm=None, owner_id="t")
    return Conversation(a, llm=None)


class R:
    ok = True

    def __init__(self, payload):
        self._p = payload

    def json(self):
        return self._p


def _pb(monkeypatch, mod, job):
    patched = {}

    def get(url, **kw):
        if url.rstrip("/").endswith(job["id"]):
            return R(job)
        return R({"items": [job]})

    def patch(url, **kw):
        patched.update(kw.get("json") or {})
        return R(job)

    monkeypatch.setattr(mod, "pb", type("PB", (), {
        "get": staticmethod(get), "patch": staticmethod(patch)}))
    return patched


# ---------------------------------------------------------------- failure 1

def test_release_never_fabricates_their_words(monkeypatch):
    job = {"id": "j1", "goal": "book dinner at 8pm",
           "status": "awaiting_confirm", "params": json.dumps({})}
    patched = _pb(monkeypatch, convmod, job)
    _conv()._release("j1", None, owner_text=None)
    p = json.loads(patched["params"])
    assert 'They said: "yes"' not in p["approved_scope"]
    assert "They gave the go-ahead" in p["approved_scope"]


def test_release_with_changes_overrides_the_stale_goal_wording(monkeypatch):
    job = {"id": "j1", "goal": "book dinner for two at Bella Vista at 8pm",
           "status": "awaiting_confirm", "params": json.dumps({})}
    patched = _pb(monkeypatch, convmod, job)
    _conv()._release("j1", {"time": "6pm"}, owner_text="6pm, go ahead")
    p = json.loads(patched["params"])
    assert p["time"] == "6pm"
    assert "They changed: time: 6pm" in p["approved_scope"]
    assert "override the task wording" in p["approved_scope"]


def test_a_bare_detail_change_is_modify_never_confirm():
    low = " ".join(REPLY_SYSTEM.split()).lower()
    assert "make it 6pm instead" in low
    assert "changing something is not approving it" in low


def test_detail_verdict_downgrades_a_confirm_to_amend(monkeypatch):
    job = {"id": "j1", "goal": "book dinner at 8pm",
           "status": "awaiting_confirm", "params": json.dumps({})}
    patched = _pb(monkeypatch, convmod, job)
    c = _conv()
    monkeypatch.setattr(Conversation, "_classify", lambda self, ph, tx: {
        "intent": "confirm", "pending_id": "j1", "pending_ids": ["j1"],
        "changes": {"time": "6pm"}, "reply": "6pm it is — booking now."})
    monkeypatch.setattr(Conversation, "_about_pending",
                        lambda self, ph, tx: "detail")
    monkeypatch.setattr(Conversation, "_remember_about_owner",
                        lambda self, tx: {})
    monkeypatch.setattr(Conversation, "say", lambda self, ph, tx: None)
    out = c.on_reply("+1", "make it 6pm instead")
    assert out["intent"] == "modify"
    assert "status" not in patched or patched.get("status") != "queued"
    p = json.loads(patched["params"])
    assert p["time"] == "6pm"


def test_a_prior_amend_rides_into_the_later_release(monkeypatch):
    # The live re-verify (2026-08-12): "make it 6pm instead" amended, then a
    # separate "go ahead" released with a scope still reading 8pm — the trace
    # selected 8:00 PM. A correction must reach the authority no matter how
    # many texts later the go-ahead comes.
    job = {"id": "j1", "goal": "book dinner at 8pm",
           "status": "awaiting_confirm", "params": json.dumps({})}
    patched = _pb(monkeypatch, convmod, job)
    c = _conv()
    c._amend("j1", {"time": "6pm"}, owner_text="make it 6pm instead")
    job["params"] = patched["params"]
    c._release("j1", None, owner_text="go ahead")
    p = json.loads(patched["params"])
    assert "They changed: time: 6pm" in p["approved_scope"]
    assert "override the task wording" in p["approved_scope"]


def test_spoken_go_ahead_also_carries_prior_corrections(monkeypatch):
    a = Anticipy(memory=Memory(":memory:"), llm=None, owner_id="t")
    job = {"id": "j9", "goal": "book dinner at 8pm",
           "status": "awaiting_confirm",
           "params": json.dumps({"corrections": {"time": "6pm"}}),
           "created": "2999-01-01 00:00:00"}
    patched = _pb(monkeypatch, coremod, job)
    a.hear("Okay let's do it.")
    p = json.loads(patched["params"])
    assert "They changed: time: 6pm" in p["approved_scope"]


# ---------------------------------------------------------------- failure 2

def test_resume_drops_a_code_the_owner_never_gave(monkeypatch):
    job = {"id": "j1", "goal": "book dinner", "status": "needs_user",
           "result": "I need the 6-digit verification code",
           "params": json.dumps({"authorized": True,
                                 "approved_scope": "Task: book dinner."})}
    _pb(monkeypatch, convmod, job)
    out = _conv()._amend("j1", {"verification_code": "6"},
                         owner_text="I told you to make it 6 dammit")
    assert out is None  # nothing resumed on a fabricated code


def test_a_non_answer_amendment_never_requeues_a_parked_run(monkeypatch):
    # Live re-verify (2026-08-12): "make it 6" reached the OTP-parked job as
    # {"time": "6"} — the code was rightly dropped, but the modify still
    # requeued the run, which burned a browser attempt only to re-park on the
    # same question. An amendment that does not supply the named need is
    # noted on the job and the job stays parked.
    job = {"id": "j1", "goal": "book dinner", "status": "needs_user",
           "result": "I need the 6-digit verification code",
           "params": json.dumps({"authorized": True,
                                 "approved_scope": "Task: book dinner."})}
    patched = _pb(monkeypatch, convmod, job)
    out = _conv()._amend("j1", {"time": "6"}, owner_text="make it 6")
    assert out == "amended:j1"
    assert patched.get("status") != "queued"
    assert json.loads(patched["params"])["time"] == "6"


def test_resume_keeps_the_code_actually_texted(monkeypatch):
    job = {"id": "j1", "goal": "book dinner", "status": "needs_user",
           "result": "I need the 6-digit verification code",
           "params": json.dumps({"authorized": True,
                                 "approved_scope": "Task: book dinner."})}
    patched = _pb(monkeypatch, convmod, job)
    out = _conv()._amend("j1", {"verification_code": "742913"},
                         owner_text="742913")
    assert out == "resumed:j1"
    assert json.loads(patched["params"])["verification_code"] == "742913"


def test_non_code_changes_pass_untouched():
    kept = Conversation._drop_unquoted_codes(
        {"time": "6pm", "party_size": "3"}, "make it 6pm for 3")
    assert kept == {"time": "6pm", "party_size": "3"}


# ---------------------------------------------------------------- failure 3

def test_bare_spoken_go_ahead_releases_the_held_plan(monkeypatch):
    a = Anticipy(memory=Memory(":memory:"), llm=None, owner_id="t")
    job = {"id": "j9", "goal": "book dinner for 4 at Bella Vista",
           "status": "awaiting_confirm", "params": json.dumps({}),
           "created": "2999-01-01 00:00:00"}
    patched = _pb(monkeypatch, coremod, job)
    out = a.hear("Okay let's do it.")
    assert out["decision"].decision == "act"
    assert out["decision"].goal == "book dinner for 4 at Bella Vista"
    assert patched["status"] == "queued"
    p = json.loads(patched["params"])
    assert p["authorized"] is True
    assert 'They said: "Okay let\'s do it."' in p["approved_scope"]


def test_go_ahead_with_content_still_goes_to_triage():
    assert not Anticipy._GO_AHEAD_RE.match("Let's do Earls tomorrow at 2 PM")
    assert Anticipy._GO_AHEAD_RE.match("Okay let's do it.")
    assert Anticipy._GO_AHEAD_RE.match("sounds good")
    assert not Anticipy._GO_AHEAD_RE.match("do it for four people")


def test_instruction_shaped_memory_stays_out_of_triage_context():
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "brain", "anticipy_core.py")).read()
    assert "reply only|compact json" in src  # the recall-injection filter


# ---------------------------------------------------------------- failure 4

def test_an_asked_question_leaves_a_held_card_behind(monkeypatch):
    a = Anticipy(memory=Memory(":memory:"), llm=None, owner_id="t")
    queued = {}

    def fake_queue(goal, params, hold=False, explicit=False):
        queued.update({"goal": goal, "params": params, "hold": hold})
        return "job-ask-1"

    monkeypatch.setattr(a, "_queue_job", fake_queue)
    monkeypatch.setattr(a, "_decide", lambda *args, **kw: Decision(
        decision="ask", goal="book jazz tickets on saturday",
        reason="which saturday?", missing=["which saturday"],
        addressee="assistant", owes="owner"))
    monkeypatch.setattr(a, "notify_owner", lambda text: True)
    out = a.hear("get us jazz tickets for saturday", explicit=True)
    assert out["decision"].decision == "ask"
    assert queued["goal"] == "book jazz tickets on saturday"
    assert queued["hold"] is True
    assert queued["params"]["missing"] == "which saturday"


# ---------------------------------------------------------------- failure 5

def test_status_prompt_forbids_deflecting_questions():
    low = " ".join(REPLY_SYSTEM.split()).lower()
    assert "neither is asking them which thing is stuck" in low


def test_a_grounded_failure_answer_survives_rethinking(monkeypatch):
    c = _conv()
    monkeypatch.setattr(Conversation, "_classify", lambda self, ph, tx: {
        "intent": "chat", "pending_id": None, "pending_ids": [],
        "changes": None,
        "reply": "the bella vista booking failed 3 tries — want me to retry?"})
    monkeypatch.setattr(Conversation, "_recent_outcomes", lambda self: [
        {"goal": "book dinner at bella vista", "status": "failed",
         "outcome": "I tried this 3 times and could not get it done."}])
    monkeypatch.setattr(Conversation, "_remember_about_owner",
                        lambda self, tx: {})
    monkeypatch.setattr(Conversation, "_pending", lambda self: [])
    monkeypatch.setattr(Conversation, "_blocked", lambda self: [])
    monkeypatch.setattr(Conversation, "say", lambda self, ph, tx: None)
    thought = {"called": False}

    def no_think(self, tx, ph=""):
        thought["called"] = True
        return "what's the specific thing that's stuck?"

    monkeypatch.setattr(Conversation, "_think", no_think)
    out = c.on_reply("+1", "why is nothing happening")
    assert not thought["called"]
    assert "failed" in out["reply"]


# ------------------------------------------------- the Cactus Club failure

def test_sms_answer_lands_in_plan_facts_for_the_app_release(monkeypatch):
    # 2026-08-14 live: the brain asked "what time and how many people?", the
    # answer came by TEXT ("7pm, 3 people"), the release came by APP TAP.
    # The app rebuilds its approval from params["_workflow"] and never reads
    # params["corrections"] — so the texted answer must already live in the
    # plan FACTS, on a bumped version, by the time the tap happens. Otherwise
    # the browser walks into the reservation form with empty facts.
    from brain.workflow import Consequence, new_plan, put_in_params
    plan = new_plan(
        owner_ref="o1", lineage_key="dinner",
        goal="book dinner at Cactus Club",
        consequence=Consequence.CONSEQUENTIAL,
        source_event_id="ev1",
        authority_text="book us cactus club tonight")
    params = put_in_params({}, plan)
    job = {"id": "j1", "goal": "book dinner at Cactus Club",
           "status": "awaiting_confirm", "params": json.dumps(params)}
    patched = _pb(monkeypatch, convmod, job)
    out = _conv()._amend("j1", {"time": "7pm", "party_size": "3"},
                         owner_text="7pm, 3 people")
    assert out == "amended:j1"
    p = json.loads(patched["params"])
    facts = p["_workflow"]["facts"]
    assert facts["time"] == "7pm"
    assert facts["party_size"] == "3"
    # The answer invalidates the pre-answer version: the app can only bind
    # its approval to the plan that already carries the answer.
    assert p["_workflow"]["version"] == plan.version + 1
    assert patched["workflow_version"] == plan.version + 1
    # And the SMS release path still has its own copy to fold into scope.
    assert p["corrections"] == {"time": "7pm", "party_size": "3"}
