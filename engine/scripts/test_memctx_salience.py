"""M4 gate — salience gate + tiered memory (raw buffer → durable).

Proves that on an hour of mostly-noise transcript the DURABLE store growth is BOUNDED (the
firehose of chit-chat lands in a short-lived raw buffer that auto-expires) WHILE weak-signal
real tasks are still caught (routed to the open_loops ledger, durable). Deterministic, no model.

Run:  PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_memctx_salience.py
"""
import datetime as dt
import tempfile
from pathlib import Path

from anticipy_engine.live_memory.brain import LiveMemoryBrain
from anticipy_engine.memory import Memory


def _iso(d):
    return d.isoformat()


def main():
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-salience-"))
    lm = LiveMemoryBrain(Memory(data_dir=tmp))

    tz = dt.timezone.utc
    morning = dt.datetime(2026, 6, 1, 9, 0, tzinfo=tz)      # when the hour was heard
    meta = {"observed_at": _iso(morning), "timezone": "UTC"}

    # weak-signal REAL tasks buried in the noise — must survive (durable open_loops).
    tasks = [
        "I should email the landlord about the leak this week.",
        "gotta pick up the dry cleaning tomorrow.",
        "I need to call the dentist to reschedule.",
        "remind me to send Priya the contract on Thursday.",
        "I have to renew the car registration this week.",
    ]
    # durable FACTS worth keeping (content-bearing history).
    facts = [
        "the garage code is 4432.",
        "our anniversary is June 3.",
        "the spare key is under the third planter.",
    ]
    # pure chit-chat / observation — the firehose we should NOT keep durably.
    noise = [
        "the weather is really nice today.", "ugh so tired this morning.",
        "that coffee was pretty good honestly.", "anyway whatever, moving on.",
        "traffic was kind of bad earlier.", "meh, feeling a little bored.",
        "the walk was nice and relaxing.", "lunch was decent i guess.",
        "kinda sleepy after all that.", "the sky looks great right now.",
    ]

    for t in tasks + facts:
        r = lm.capturer.capture(t, source="mp3", meta=meta)
        assert r.get("kept"), ("dropped a real line", t, r)
    # flood the buffer with 100 noise lines (10 templates x 10) — all should end up raw/expiring.
    for i in range(100):
        lm.capturer.capture(f"{noise[i % len(noise)]} ({i})", source="mp3", meta=meta)

    def active_valid(at):
        n = 0
        for drawer in (lm.memory.profile, lm.memory.open_loops, lm.memory.history, lm.memory.derived):
            for it in drawer.all():
                if it.status not in ("archived", "superseded") and it.is_valid_at(at):
                    n += 1
        return n

    d1 = morning.timestamp()
    next_day = (morning + dt.timedelta(days=1)).timestamp()   # well past the 12h raw window

    # BEFORE expiry (same morning) everything kept is live — the raw buffer is holding the noise.
    live_now = active_valid(d1)
    assert live_now >= len(tasks), (live_now, "lost real tasks at capture time")

    # run the cold sweep AT the next day: raw-buffer noise expires and is pruned.
    swept = lm.maintain_at(next_day) if hasattr(lm, "maintain_at") else lm.maintainer.sweep(at=next_day)
    assert swept["expired_raw"] >= 80, ("raw buffer did not expire the firehose", swept)

    # DURABLE growth is BOUNDED: after expiry the durable store is a small multiple of the real
    # signal, not ~108 lines. (tasks + facts = 8; allow generous headroom, must be << 108.)
    durable = active_valid(next_day)
    assert durable <= 20, (f"durable store bloated by the firehose: {durable} active items")

    # WEAK-SIGNAL RECALL held: every real task is still a durable, active open_loop.
    loop_texts = [i.text for i in lm.memory.open_loops.all() if i.status not in ("archived", "superseded")]
    for t in tasks:
        assert any(t.rstrip(".") in lt or lt in t for lt in loop_texts), (t, loop_texts)

    print(f"OK  M4 salience: durable={durable} (bounded), expired_raw={swept['expired_raw']}, "
          f"all {len(tasks)} weak-signal tasks caught")


if __name__ == "__main__":
    main()
