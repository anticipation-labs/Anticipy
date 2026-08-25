"""Wiring the link answer to a record id.

The whole mechanism is POSITIONAL — the model answers with a number and the
worker turns that number into an id by counting. An off-by-one here links
every line to the wrong parent and produces no symptom anyone would notice:
no crash, no error, no empty screen, just quietly wrong conversations. I
nearly shipped exactly that by filtering blank candidates in the layer that
renders them while the caller kept an unfiltered list, so the tests that
matter most here are about alignment.
"""
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import brain.worker as W  # noqa: E402
from brain.anticipy_core import Anticipy  # noqa: E402

C = [("id-a", "first thing"), ("id-b", "second thing"), ("id-c", "third thing")]


# --------------------------------------------------------- index -> id

def test_the_index_is_one_based_into_the_list_as_given():
    assert W.resolve_link(1, "me", C) == "id-a"
    assert W.resolve_link(2, "me", C) == "id-b"
    assert W.resolve_link(3, "me", C) == "id-c"


def test_zero_is_stored_as_a_self_link():
    """"Starts something new" is an ANSWER and must be written down. If it
    were left blank it would be indistinguishable from "never asked", and
    the scoring could not tell a correct new-thread call from a silence."""
    assert W.resolve_link(0, "me", C) == "me"


def test_no_answer_writes_nothing():
    assert W.resolve_link(None, "me", C) is None


def test_out_of_range_writes_nothing():
    for bad in (4, 99, -1):
        assert W.resolve_link(bad, "me", C) is None


def test_no_candidates_means_no_link_even_for_zero():
    """With nothing shown, a 0 is not a judgement about anything."""
    assert W.resolve_link(0, "me", []) is None
    assert W.resolve_link(1, "me", []) is None


# ------------------------------------------------- candidates and ids

def test_blanks_are_dropped_where_ids_and_texts_leave_together(monkeypatch):
    """The alignment bug, pinned. If a blank were dropped further down, the
    text at index 2 would no longer be the id at index 2."""
    rows = [
        {"id": "1", "text": "alpha",  "created": "2026-08-05 10:00:00.000Z"},
        {"id": "2", "text": "   ",    "created": "2026-08-05 10:00:01.000Z"},
        {"id": "3", "text": "bravo",  "created": "2026-08-05 10:00:02.000Z"},
        {"id": "",  "text": "no id",  "created": "2026-08-05 10:00:03.000Z"},
        {"id": "5", "text": "charlie", "created": "2026-08-05 10:00:04.000Z"},
    ]
    monkeypatch.setattr(W.pb, "get", lambda *a, **k: types.SimpleNamespace(
        raise_for_status=lambda: None, json=lambda: {"items": rows}))
    got = W.link_candidates()
    assert got == [("1", "alpha"), ("3", "bravo"), ("5", "charlie")]
    # And the mapping still lands on the right row.
    assert W.resolve_link(2, "me", got) == "3"


def test_candidates_come_back_in_speech_order_not_delivery_order(monkeypatch):
    """A flushed backlog must be numbered the way he SAID it.

    The rows are given in the order PocketBase actually returns them — newest
    delivered first, because the query sorts by "-created" — and that order
    is deliberately the REVERSE of speech order. An earlier version of this
    test happened to list them already-sorted, so deleting the sort entirely
    still passed. Caught by mutation testing; the data now makes the sort do
    real work.
    """
    said_first = {"id": "said_first", "text": "morning line",
                  "created": "2026-08-05 12:00:01.000Z",
                  "capture_started_at": "2026-08-05 09:00:00.000Z"}
    said_second = {"id": "said_second", "text": "later line",
                   "created": "2026-08-05 12:00:05.000Z",
                   "capture_started_at": "2026-08-05 11:00:00.000Z"}
    rows = [said_second, said_first]          # delivery order, newest first
    monkeypatch.setattr(W.pb, "get", lambda *a, **k: types.SimpleNamespace(
        raise_for_status=lambda: None, json=lambda: {"items": list(rows)}))
    assert [i for i, _ in W.link_candidates()] == ["said_first", "said_second"]


def test_unstamped_rows_still_come_back_in_arrival_order(monkeypatch):
    """The old-build case. No capture stamps anywhere means arrival order,
    which is exactly what happened before any of this existed."""
    rows = [
        {"id": "c", "text": "third", "created": "2026-08-05 10:00:03.000Z"},
        {"id": "a", "text": "first", "created": "2026-08-05 10:00:01.000Z"},
        {"id": "b", "text": "second", "created": "2026-08-05 10:00:02.000Z"},
    ]
    monkeypatch.setattr(W.pb, "get", lambda *a, **k: types.SimpleNamespace(
        raise_for_status=lambda: None, json=lambda: {"items": rows}))
    assert [i for i, _ in W.link_candidates()] == ["a", "b", "c"]


def test_a_backend_failure_asks_no_question_rather_than_crashing(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("pb down")
    monkeypatch.setattr(W.pb, "get", boom)
    assert W.link_candidates() == []


def test_the_window_is_bounded(monkeypatch):
    rows = [{"id": f"i{n}", "text": f"line {n}",
             "created": f"2026-08-05 10:00:{n:02d}.000Z"} for n in range(60)]
    monkeypatch.setattr(W.pb, "get", lambda *a, **k: types.SimpleNamespace(
        raise_for_status=lambda: None, json=lambda: {"items": rows}))
    got = W.link_candidates()
    assert len(got) == W.LINK_WINDOW
    assert got[-1][0] == "i59", "must keep the most RECENT lines, not the oldest"


def test_a_failed_patch_never_raises(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("nope")
    monkeypatch.setattr(W.pb, "patch", boom)
    W.record_link("a", "b")          # must not raise: the line already ran


def test_links_are_off_by_default():
    """The verdict costs prompt tokens on every heard line. Until scoring
    says it earns them, asking is opt-in."""
    assert W.LINKS_ON is False


# -------------------------------------------- the prompt the model sees

class Recorder:
    live = True

    def __init__(self):
        self.prompts, self.kwargs = [], []

    def chat(self, system, user, **kw):
        if '"decision"' in (system or ""):
            self.prompts.append(user)
        return types.SimpleNamespace(
            text='{"decision":"ignore","goal":null,"reason":"x","continues":2}')


def build(llm):
    mem = types.SimpleNamespace(
        ingest=lambda *a, **k: {"commitment_id": None},
        recall=lambda *a, **k: [], open_loops=lambda: [],
        close_from_speech=lambda *a, **k: [])
    a = Anticipy(memory=mem, llm=llm, backend_url="http://127.0.0.1:1")
    a._queue_job = lambda *a_, **k: "job1"
    a._pending_jobs = lambda: []
    a._same_pending = lambda goal, **_k: None
    a._refines_pending = lambda goal, **_k: None
    a.notify_owner = lambda m, channel="sms": {"ok": 1}
    return a


def test_candidates_are_numbered_from_one_in_the_order_given():
    llm = Recorder()
    build(llm).hear("what about tomorrow",
                    link_candidates=["alpha", "bravo", "charlie"])
    p = llm.prompts[-1]
    assert "[1] alpha" in p and "[2] bravo" in p and "[3] charlie" in p


def test_a_blank_candidate_still_occupies_its_number():
    """Proof the renderer does not silently renumber. If it dropped the
    blank, charlie would become [2] while the caller still calls it 3."""
    llm = Recorder()
    build(llm).hear("so what about the table for tomorrow night",
                    link_candidates=["alpha", "   ", "charlie"])
    p = llm.prompts[-1]
    assert "[1] alpha" in p and "[3] charlie" in p


def test_no_candidates_means_the_question_is_never_asked():
    llm = Recorder()
    build(llm).hear("so what about the table for tomorrow night")
    assert "continues" not in llm.prompts[-1]
    assert "Recent lines" not in llm.prompts[-1]


def test_the_verdict_survives_onto_the_decision():
    llm = Recorder()
    out = build(llm).hear("so what about the table for tomorrow night",
                          link_candidates=["alpha", "bravo", "charlie"])
    assert out["decision"].continues == 2


def test_an_answer_with_no_candidates_shown_is_discarded():
    """The model answered 2 regardless; with nothing shown it means nothing."""
    llm = Recorder()
    out = build(llm).hear("so what about the table for tomorrow night")
    assert out["decision"].continues is None
