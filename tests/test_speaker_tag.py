"""The voice verdict rides into triage — and its absence changes nothing.

Brief 09: the phone tags each line "owner" / "other" / nothing. These tests
pin the plumbing (tag -> triage prompt) and the honesty wall (garbage or
missing tag == exactly today's behaviour).
"""
import json
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain.anticipy_core import Anticipy  # noqa: E402


class ScriptedLLM:
    live = True

    def __init__(self, response):
        self.response = response
        self.triage_prompts = []

    def chat(self, system, user, **kw):
        if '"decision"' in (system or ""):
            self.triage_prompts.append(user)
            return types.SimpleNamespace(text=json.dumps(self.response))
        return types.SimpleNamespace(text="okay")


def _anticipy(response):
    mem = types.SimpleNamespace(
        ingest=lambda *a, **k: {"commitment_id": None},
        recall=lambda *a, **k: [],
        open_loops=lambda: [],
        close_from_speech=lambda *a, **k: [])
    llm = ScriptedLLM(response)
    a = Anticipy(memory=mem, llm=llm, backend_url="http://127.0.0.1:1")
    a._queue_job = lambda *args, **kw: "job1"
    a._pending_jobs = lambda: []
    a.notify_owner = lambda m, channel="sms": {"ok": True}
    return a, llm


IGNORE = {"decision": "ignore", "goal": None, "addressee": "person",
          "reason": "friend's promise"}


def test_an_owner_tag_reaches_the_model():
    a, llm = _anticipy(IGNORE)
    a.hear("I'll look into the flights tomorrow", speaker="owner")
    assert "spoken by the OWNER himself" in llm.triage_prompts[0]


def test_an_other_tag_reaches_the_model_with_the_rule():
    a, llm = _anticipy(IGNORE)
    a.hear("I'll get into it", speaker="other")
    p = llm.triage_prompts[0]
    assert "NOT the owner" in p and "never the owner's own" in p


def test_no_tag_means_no_voice_check_line():
    a, llm = _anticipy(IGNORE)
    a.hear("I'll get into it")
    assert "Voice check" not in llm.triage_prompts[0]


def test_garbage_tags_are_no_tag():
    a, llm = _anticipy(IGNORE)
    a.hear("I'll get into it", speaker="speaker_3")
    a.hear("I'll get into it", speaker="unknown")
    assert all("Voice check" not in p for p in llm.triage_prompts)


def test_old_callers_without_the_kwarg_still_work():
    a, llm = _anticipy(IGNORE)
    out = a.hear("I'll get into it", context=["earlier line"])
    assert out["decision"].decision == "ignore"


ASK_SELF = {"decision": "ask", "goal": None, "addressee": "self",
            "reason": "mumbling through a plan"}
ASK_ASSIST = {"decision": "ask", "goal": None, "addressee": "assistant",
              "reason": "asked her directly"}


def test_self_talk_questions_are_never_texted():
    a, llm = _anticipy(ASK_SELF)
    texts = []
    a.notify_owner = lambda m, channel="sms": texts.append(m) or {"ok": True}
    out = a.hear("when do you wanna go here for")
    assert texts == [], texts
    assert out["anticipy_says"] is None


def test_a_direct_question_still_gets_asked():
    a, llm = _anticipy(ASK_ASSIST)
    texts = []
    a.notify_owner = lambda m, channel="sms": texts.append(m) or {"ok": True}
    a.hear("hey should I do the park location or downtown?")
    assert len(texts) == 1, texts
