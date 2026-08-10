"""A cancelled plan's promise dies with it.

Live, 2026-08-10: a toothbrush order was cancelled on Aug 4, but the
commitment behind it stayed "open" in memory — so six days later the clock
initiated "did you manage to get the toothbrush?" about a dead plan.
Cancelling a job, from any path, must close the matching open commitment.
"""
import json

from brain.memory import Memory


def _mem_with_commitment(what: str) -> Memory:
    mem = Memory(":memory:")
    mem.db.execute(
        "INSERT INTO nodes (type, name, created_ts, last_seen_ts, status, attrs) "
        "VALUES ('commitment', ?, 1000, 1000, 'open', ?)",
        (what, json.dumps({})))
    mem.db.commit()
    return mem


def test_close_matching_closes_the_commitment():
    mem = _mem_with_commitment("get a toothbrush")
    closed = mem.close_matching("Order toothbrush via Uber Eats to owner's "
                                "house", "cancelled")
    assert closed == ["get a toothbrush"]
    assert mem.open_loops() == []
    row = mem.db.execute(
        "SELECT status FROM nodes WHERE type='commitment'").fetchone()
    assert row[0] == "cancelled"


def test_close_matching_never_guesses_across_topics():
    mem = _mem_with_commitment("send Priya the pitch deck")
    closed = mem.close_matching("Order toothbrush via Uber Eats", "cancelled")
    assert closed == []
    assert len(mem.open_loops()) == 1


def test_clock_never_chases_a_cancelled_plan():
    """The exact 2026-08-10 shape: the toothbrush job dies, and the clock's
    later review must no longer see the promise — while a genuinely open,
    evidenced promise stays on its desk for useful follow-up."""
    from brain.anticipy_core import Anticipy

    mem = Memory(":memory:")
    cur = mem.db.execute(
        "INSERT INTO episodes(ts, text) VALUES (1000, 'me toothbrush')")
    eid = cur.lastrowid
    mem.db.execute(
        "INSERT INTO nodes (type, name, created_ts, last_seen_ts, status, attrs) "
        "VALUES ('commitment', 'get a toothbrush', 1000, 1000, 'open', ?)",
        (json.dumps({"source_episode": eid}),))
    cur = mem.db.execute(
        "INSERT INTO episodes(ts, text) VALUES "
        "(1001, 'I will send Priya the pitch deck by Friday')")
    eid2 = cur.lastrowid
    mem.db.execute(
        "INSERT INTO nodes (type, name, created_ts, last_seen_ts, status, attrs) "
        "VALUES ('commitment', 'send Priya the pitch deck', 1001, 1001, 'open', ?)",
        (json.dumps({"source_episode": eid2}),))
    mem.db.commit()

    mem.close_matching("Order toothbrush via Uber Eats to owner's house",
                       "cancelled")

    class SpyLLM:
        seen = None
        def chat(self, system, user, **kw):
            SpyLLM.seen = user
            class R:
                text = json.dumps({"initiate": False})
            return R()

    a = Anticipy(memory=mem, llm=SpyLLM(), owner_id="t")
    a.clock_tick(now=2000)
    assert SpyLLM.seen is not None
    assert "toothbrush" not in SpyLLM.seen
    assert "pitch deck" in SpyLLM.seen


def test_sms_decline_closes_the_promise(monkeypatch):
    from brain.anticipy_core import Anticipy
    from brain.conversation import Conversation
    import brain.conversation as convmod

    mem = _mem_with_commitment("get a toothbrush")
    a = Anticipy(memory=mem, llm=None)
    conv = Conversation(a, llm=None)

    job = {"id": "j1", "goal": "Order toothbrush via Uber Eats",
           "status": "awaiting_confirm", "params": "{}"}

    class R:
        ok = True
        def json(self): return job
    monkeypatch.setattr(convmod, "pb", type("PB", (), {
        "get": staticmethod(lambda *a, **k: R()),
        "patch": staticmethod(lambda *a, **k: R()),
    }))
    out = conv._cancel("j1")
    assert out == "cancelled:j1"
    assert mem.open_loops() == []
