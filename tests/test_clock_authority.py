"""Time may surface an owner-authored task; it may never invent one."""
import json

from brain.anticipy_core import Anticipy


class Memory:
    def __init__(self, source):
        self.source = source

    def open_loops(self):
        return [{"id": 7, "what": "dentist appointment", "source": self.source,
                 "ts": 1000}]


class LLM:
    owner_zone = "America/Vancouver"

    def chat(self, *_args, **_kwargs):
        class R:
            text = json.dumps({
                "initiate": True,
                "say": "Your dentist appointment is Friday at 3 PM.",
                "goal": "confirm appointment details",
                "loop_ids": [7],
            })
        return R()


def _run(source):
    a = Anticipy(memory=Memory(source), llm=LLM(), owner_phone=None)
    queued = []
    a._queue_job = lambda goal, params, hold=False: queued.append(
        (goal, params, hold)) or "job"
    out = a.clock_tick(now=2000)
    return out, queued


def test_a_remembered_fact_can_be_reminded_but_never_becomes_a_job():
    out, queued = _run("Remember that my dentist appointment is Friday at 3 PM.")
    assert out["say"] == "Your dentist appointment is Friday at 3 PM."
    assert out["goal"] is None
    assert queued == []


def test_an_owner_authored_obligation_can_still_be_prepared_safely():
    out, queued = _run("I need to confirm my dentist appointment by Friday.")
    assert out["goal"] == "confirm appointment details"
    assert queued and queued[0][0] == "confirm appointment details"
    assert queued[0][2] is True, "consequential clock work remains approval-held"
