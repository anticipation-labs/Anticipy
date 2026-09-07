"""Forgetting and completing need a contextual verdict, not shared words."""
import json
from types import SimpleNamespace

import pytest

from brain.memory import Memory


class Judge:
    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    def chat(self, system, user, **kwargs):
        self.calls.append(json.loads(user))
        return SimpleNamespace(text=json.dumps(self.reply))


def test_forgetting_one_person_does_not_delete_another():
    m = Memory()
    first = "Amira approves supplier invoices for the local manufacturing and distribution teams every week"
    second = "Simone approves supplier invoices for the local manufacturing and distribution teams every week"
    m.remember_fact(first)
    m.llm = Judge({"coverage": "outside"})
    assert m.forget_fact(second) == 0
    assert [r["fact"] for r in m.profile_facts()] == [first]
    assert len(m.llm.calls) == 1


def test_unknown_veto_match_defers_the_write_instead_of_claiming_permission():
    m = Memory()
    m.forget_fact("The private project is called Northstar")
    with pytest.raises(RuntimeError, match="veto.*unanswered"):
        m.remember_fact("I work on Northstar", source="consolidation")
    assert m.profile_facts() == []


def test_non_latin_vetoes_keep_distinct_byte_identities():
    m = Memory()
    m.forget_fact("我的名字是陈")
    m.forget_fact("我的住址在上海")
    assert m.db.execute("SELECT COUNT(*) FROM vetoed_facts").fetchone()[0] == 2


def test_completed_words_do_not_close_a_different_people_task():
    m = Memory()
    m.db.execute("INSERT INTO nodes(type,name,created_ts,last_seen_ts,status,attrs) VALUES ('commitment',?,1,1,'open','{}')",
                 ("Send the quarterly project budget update to Morgan and Casey",))
    m.db.commit()
    m.llm = Judge({"n": None, "resolution": "not_resolved"})
    assert m.close_from_speech("I sent the quarterly project budget update to Alex and Casey", completed="Sent budget update to Alex and Casey") == []
    assert len(m.open_loops()) == 1
    assert len(m.llm.calls) == 1


def test_no_model_cannot_close_a_promise_by_a_completion_verb():
    m = Memory()
    m.db.execute("INSERT INTO nodes(type,name,created_ts,last_seen_ts,status,attrs) VALUES ('commitment','send the report',1,1,'open','{}')")
    m.db.commit()
    assert m.close_from_speech("I sent the report") == []
    assert len(m.open_loops()) == 1
