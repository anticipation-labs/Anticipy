"""The jobs row and the plan inside it must spell the goal the same way.

workflow_guard.pb.js compares them character for character:

    String(embedded.goal||"") !== String(rowValue("goal","") || "")
        -> reject("job fields disagree with the embedded workflow")

_queue_job wrote the row column straight from the triage model's string —
orchestrator.py never strips it and job_fields() does not carry goal at all —
while new_plan() stored goal.strip() inside the plan. So a model reply of
{"goal": "Book dinner at Earls tomorrow at 7 \\n"} 409'd on the POST,
raise_for_status raised, the bare `except: return None` swallowed it, and
_queue_job handed back None.

By then hear() had ALREADY texted him asking about the card. He answered yes
to a card that was never created, and his yes found nothing to release.
"""
import json

from brain.anticipy_core import Anticipy
from brain.memory import Memory
from brain.workflow import Consequence, new_plan, put_in_params

PADDED = "Book dinner at Earls tomorrow at 7 PM for 2 \n"


def _core(monkeypatch, posts, patches):
    a = Anticipy(memory=Memory(":memory:"), llm=None, owner_id="t")
    monkeypatch.setattr(a, "_open_card_in_lineage", lambda _l: None)
    import brain.anticipy_core as C

    class FakePB:
        @staticmethod
        def get(url, params=None, timeout=10):
            class Response:
                ok = True

                @staticmethod
                def json():
                    return {"items": []}
            return Response()

        @staticmethod
        def post(url, json=None, timeout=10):
            posts.append(json)

            class Response:
                @staticmethod
                def raise_for_status():
                    return None

                @staticmethod
                def json():
                    return {"id": "job1", "status": "awaiting_confirm"}
            return Response()

        @staticmethod
        def patch(url, json=None, timeout=10):
            patches.append(json)

            class Response:
                ok = True
            return Response()
    monkeypatch.setattr(C, "pb", FakePB)
    return a


def _embedded_goal(fields):
    return json.loads(fields["params"])["_workflow"]["goal"]


def test_a_padded_goal_still_posts_a_row_the_guard_accepts(monkeypatch):
    posts, patches = [], []
    a = _core(monkeypatch, posts, patches)
    assert a._queue_job(PADDED, {"source": "dinner at Earls"},
                        hold=True) == "job1"
    body = posts[-1]
    assert body["goal"] == _embedded_goal(body), \
        "the row column and the embedded plan must agree exactly"
    assert body["goal"] == PADDED.strip()


def test_a_padded_correction_still_amends_a_row_the_guard_accepts(monkeypatch):
    posts, patches = [], []
    a = _core(monkeypatch, posts, patches)
    original = "Book dinner at Earls tomorrow"
    plan = new_plan(owner_ref="t", lineage_key="lin1", goal=original,
                    consequence=Consequence.CONSEQUENTIAL, source_event_id="e1")
    current = {"id": "job1", "goal": original, "status": "awaiting_confirm",
               "params": json.dumps(put_in_params({"source": original}, plan))}
    a._merge_into("job1", current, PADDED, {"source": "make it 7 for two"})
    fields = patches[-1]
    assert fields["goal"] == PADDED.strip()
    assert fields["goal"] == _embedded_goal(fields)
