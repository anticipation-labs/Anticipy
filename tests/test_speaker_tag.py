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


def test_a_named_person_reaches_the_model_by_name():
    a, llm = _anticipy(IGNORE)
    a.hear("I'll grab the tickets", speaker="other:Sarah")
    p = llm.triage_prompts[0]
    assert "Sarah" in p and "not him" in p


def test_a_bare_voice_id_is_NO_VERDICT_not_someone_else():
    """AMENDED 2026-08-06, on production evidence.

    This test used to require that "other:v2" reach the model as "NOT the
    owner". That was wrong, and it cost him real work.

    The roster emits `other:<id>` in two opposite situations that look
    identical on the wire: a CONFIDENT match to someone it knows, and a brand
    new voice it has never heard and has just filed. VoiceRoster carries a
    `confident` flag distinguishing them and throws it away before sending.

    Measured on 200 real tagged lines: 195 distinct identities, 97% of them
    seen exactly once, the owner recognised twice. He has never enrolled, so
    there is no voiceprint to match against and every utterance becomes a new
    stranger. Both of the "I have to email Priya" lines she ignored were
    tagged other:v210 and other:v215 — and the triage prompt rightly treats a
    first-person commitment from someone who is NOT the owner as that
    person's promise. His own to-dos were being handed to a stranger.

    Failing to recognise a voice is not the same as recognising a different
    one. A bare auto-generated id is no verdict.
    """
    a, llm = _anticipy(IGNORE)
    a.hear("I'll grab the tickets", speaker="other:v2")
    p = llm.triage_prompts[0]
    assert "Voice check" not in p, "an unplaced voice must not speak for him"
    assert "v2" not in p


def test_a_NAMED_other_is_still_real_evidence():
    """The half that must keep working: she knows who this is."""
    a, llm = _anticipy(IGNORE)
    a.hear("I'll grab the tickets", speaker="other:Sarah")
    p = llm.triage_prompts[0]
    assert "NOT the owner" in p or "Sarah" in p


def test_unknown_from_the_roster_is_no_verdict():
    a, llm = _anticipy(IGNORE)
    a.hear("I'll grab the tickets", speaker="unknown")
    assert "Voice check" not in llm.triage_prompts[0]
