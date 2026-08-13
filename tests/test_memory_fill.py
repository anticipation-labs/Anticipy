"""Memory answers before he is asked.

Omar, 2026-08-11, after a card grew a third question: "You're adding all these
single-question asks, and it's bogging it down. It's going to ask a billion
questions."

A missing detail is a question of LAST resort. Before any gap turns into a
text, memory gets one isolated look — the location he always books, his home
city — and whatever it plainly settles rides on the card as an assumption he
sees at the go-ahead, where a single "no, the other one" fixes it. Only what
memory cannot answer is ever asked. And every failure path must leave the gap
exactly as it was: unanswered means asked, never guessed.
"""
import json
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain.orchestrator import MEMORY_FILL_SYSTEM, fill_gaps_from_memory  # noqa: E402


class Fake:
    live = True

    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.asked = []

    def chat(self, system, user, **kw):
        self.asked.append((system, user))
        p = self.payloads.pop(0)
        text = p if isinstance(p, str) else json.dumps(p)
        return types.SimpleNamespace(text=text)


class Mem:
    def __init__(self, facts):
        self.facts = facts

    def recall(self, query, limit=8):
        return [{"fact": f} for f in self.facts]


GOAL = "Book Earls for lunch tomorrow"


def test_a_gap_memory_plainly_settles_becomes_an_answer_not_a_question():
    llm = Fake([{"answer": "Earls Ambleside in West Vancouver"}])
    mem = Mem(["he books Earls in West Vancouver (Ambleside), every time"])
    filled, remaining = fill_gaps_from_memory(
        llm, mem, GOAL, ["Which Earls location?"])
    assert filled == {"Which Earls location?": "Earls Ambleside in West Vancouver"}
    assert remaining == []


def test_a_gap_memory_cannot_answer_is_still_asked():
    llm = Fake([{"answer": None}])
    mem = Mem(["he likes window seats"])
    filled, remaining = fill_gaps_from_memory(
        llm, mem, GOAL, ["Which Earls location?"])
    assert filled == {}
    assert remaining == ["Which Earls location?"]


def test_empty_memory_asks_without_spending_a_model_call():
    llm = Fake([])
    filled, remaining = fill_gaps_from_memory(
        llm, Mem([]), GOAL, ["Which Earls location?"])
    assert filled == {}
    assert remaining == ["Which Earls location?"]
    assert llm.asked == [], "no facts, nothing to judge, no call"


def test_every_failure_leaves_the_gap_exactly_as_it_was():
    """The honesty wall: a broken filler never answers for the owner."""
    gaps = ["Which Earls location?"]
    assert fill_gaps_from_memory(None, Mem(["x"]), GOAL, gaps) == ({}, gaps)
    assert fill_gaps_from_memory(Fake(["not json"]), Mem(["x"]), GOAL, gaps) == ({}, gaps)
    assert fill_gaps_from_memory(Fake([{"answer": ""}]), Mem(["x"]), GOAL, gaps) == ({}, gaps)
    assert fill_gaps_from_memory(Fake([{"answer": "None"}]), Mem(["x"]), GOAL, gaps) == ({}, gaps)
    assert fill_gaps_from_memory(Fake([{}]), Mem(["x"]), GOAL, gaps) == ({}, gaps)

    class Dead:
        live = False

        def chat(self, *a, **k):
            raise AssertionError("must not be called when the model is offline")
    assert fill_gaps_from_memory(Dead(), Mem(["x"]), GOAL, gaps) == ({}, gaps)

    class Boom:
        live = True

        def chat(self, *a, **k):
            raise RuntimeError("network")
    assert fill_gaps_from_memory(Boom(), Mem(["x"]), GOAL, gaps) == ({}, gaps)

    class BadMem:
        def recall(self, *a, **k):
            raise RuntimeError("db locked")
    assert fill_gaps_from_memory(Fake([]), BadMem(), GOAL, gaps) == ({}, gaps)


def test_it_is_asked_in_isolation_with_the_memory_shown():
    llm = Fake([{"answer": "Earls Ambleside"}])
    mem = Mem(["he books Earls in West Vancouver"])
    fill_gaps_from_memory(llm, mem, GOAL, ["Which Earls location?"])
    system, user = llm.asked[0]
    assert system is MEMORY_FILL_SYSTEM
    assert "guess is not an answer" in " ".join(system.split()).lower().replace("a guess", "guess")
    assert "Which Earls location?" in user
    assert "he books Earls in West Vancouver" in user


def test_a_made_up_detail_is_never_ratified_by_memory():
    """An invented name in the goal must be ASKED about — a memory lookup
    quietly confirming a hallucination books the wrong thing politely."""
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "brain", "anticipy_core.py")).read()
    i = src.index("if gap and not made_up:")
    assert "fill_gaps_from_memory" in src[i:i + 300]


def test_filled_answers_reach_the_job_params_in_both_lanes():
    """What memory settled must reach the browser agent as a fact on the job,
    or the agent lands on the site as blind as before."""
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "brain", "anticipy_core.py")).read()
    assert src.count("for k, v in filled.items():") == 1          # ambient lane
    assert '_memory_filled' in src                                 # direct lane
    i = src.index('params = {"source": line, "now": self._now_line()}')
    assert "_memory_filled" in src[i:i + 500]
