"""A promise kept by one process must close in the next one.

memory.resolve() was reachable from exactly one place: review_loops(), which
walks self.loops — a plain in-RAM list with no load path, rebuilt EMPTY on
every process start. The other closer, close_from_speech, needs the owner to
say out loud that he finished it.

So: he says "book dinner at Cactus tomorrow", a commitment row lands in
memory.db and a held card on his desk. The worker is redeployed (or evicted by
the supervisor). He approves, the extension books the table, the job goes done
— and the new process has no idea which promise that job was keeping. The
commitment stays status='open' forever, so clock_tick keeps selecting it, with
his own quote attached, and composes "just confirming our dinner!" about a
table that was reserved days ago.

Fix: the job row carries the commitment it is keeping, so any process can read
it back. Matched on that id and nothing else — a fuzzy match on goal wording
would close the wrong promise, and there is no undoing that.
"""
import json

from brain.anticipy_core import Anticipy
from brain.memory import Memory


def _memory_with_commitment(what="book dinner at Cactus tomorrow"):
    mem = Memory(":memory:")
    cur = mem.db.execute(
        "INSERT INTO episodes(ts, text) VALUES (1000, 'book dinner at Cactus')")
    eid = cur.lastrowid
    cur = mem.db.execute(
        "INSERT INTO nodes (type, name, created_ts, last_seen_ts, status, attrs) "
        "VALUES ('commitment', ?, 1000, 1000, 'open', ?)",
        (what, json.dumps({"source_episode": eid})))
    mem.db.commit()
    return mem, cur.lastrowid


def _pb_returning(monkeypatch, items, posts=None):
    import brain.anticipy_core as C

    class FakePB:
        @staticmethod
        def get(url, params=None, timeout=10):
            class Response:
                ok = True

                @staticmethod
                def json():
                    return {"items": items}
            return Response()

        @staticmethod
        def post(url, json=None, timeout=10):
            if posts is not None:
                posts.append(json)

            class Response:
                @staticmethod
                def raise_for_status():
                    return None

                @staticmethod
                def json():
                    return {"id": "job1", "status": "awaiting_confirm"}
            return Response()
    monkeypatch.setattr(C, "pb", FakePB)


def test_the_card_records_which_promise_it_is_keeping(monkeypatch):
    posts = []
    _pb_returning(monkeypatch, [], posts)
    mem, cid = _memory_with_commitment()
    a = Anticipy(memory=mem, llm=None, owner_id="t")
    monkeypatch.setattr(a, "_open_card_in_lineage", lambda _l: None)
    a._queue_job("Book dinner at Cactus tomorrow at 7 PM",
                 a._keeping({"source": "book dinner at Cactus"}, cid),
                 hold=True)
    assert json.loads(posts[-1]["params"])["commitment_id"] == cid


def test_a_job_finished_after_a_restart_closes_its_commitment(monkeypatch):
    mem, cid = _memory_with_commitment()
    done = {"id": "job1", "status": "done",
            "goal": "Book dinner at Cactus tomorrow at 7 PM",
            "params": json.dumps({"source": "book dinner at Cactus",
                                  "commitment_id": cid})}
    _pb_returning(monkeypatch, [done])
    # The process that queued it is gone: this one has never heard of it.
    fresh = Anticipy(memory=mem, llm=None, owner_id="t")
    assert fresh.loops == []
    assert [l["id"] for l in mem.open_loops()] == [cid]

    fresh.review_loops()
    assert mem.open_loops() == [], \
        "the clock must never chase a dinner that was already booked"
    row = mem.db.execute(
        "SELECT status FROM nodes WHERE id=?", (cid,)).fetchone()
    assert row[0] == "done"


def test_a_cancelled_job_closes_its_commitment_as_cancelled(monkeypatch):
    mem, cid = _memory_with_commitment()
    killed = {"id": "job1", "status": "cancelled",
              "goal": "Book dinner at Cactus tomorrow at 7 PM",
              "params": json.dumps({"commitment_id": cid})}
    _pb_returning(monkeypatch, [killed])
    Anticipy(memory=mem, llm=None, owner_id="t").review_loops()
    row = mem.db.execute(
        "SELECT status FROM nodes WHERE id=?", (cid,)).fetchone()
    assert row[0] == "cancelled"


def test_somebody_else_s_finished_job_never_closes_this_promise(monkeypatch):
    """Only the recorded id counts. A job that names no commitment, or names
    another one, leaves this promise exactly where it was."""
    mem, cid = _memory_with_commitment()
    strangers = [
        {"id": "job2", "status": "done",
         "goal": "Book dinner at Cactus tomorrow",   # same words, no id
         "params": json.dumps({"source": "book dinner at Cactus"})},
        {"id": "job3", "status": "done", "goal": "Order running shoes",
         "params": json.dumps({"commitment_id": cid + 999})},
    ]
    _pb_returning(monkeypatch, strangers)
    Anticipy(memory=mem, llm=None, owner_id="t").review_loops()
    assert [l["id"] for l in mem.open_loops()] == [cid]


def test_the_sweep_does_not_ask_the_backend_on_every_poll(monkeypatch):
    """review_loops() runs every worker tick (POLL_SECONDS = 2) and this sweep
    only ever catches up on another process's work, so it is rate-limited —
    otherwise one genuinely open promise means a backend query every 2s
    forever."""
    mem, cid = _memory_with_commitment()
    calls = []
    import brain.anticipy_core as C

    class CountingPB:
        @staticmethod
        def get(url, params=None, timeout=10):
            calls.append(url)

            class Response:
                ok = True

                @staticmethod
                def json():
                    return {"items": []}
            return Response()
    monkeypatch.setattr(C, "pb", CountingPB)
    a = Anticipy(memory=mem, llm=None, owner_id="t")
    a.review_loops()
    assert len(calls) == 1
    a.review_loops()
    a.review_loops()
    assert len(calls) == 1
    a._last_loop_sweep -= a.LOOP_SWEEP_SECONDS + 1
    a.review_loops()
    assert len(calls) == 2
