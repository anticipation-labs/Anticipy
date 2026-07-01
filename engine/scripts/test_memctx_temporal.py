"""M3 gate — bi-temporal validity (valid_from/valid_to, event_time vs ingest_time).

Proves an ephemeral, day-scoped fact expires: "school moved pickup to 3 TODAY" said on DAY 1
is NOT surfaced by the ContextPack on DAY 2 — while a durable fact ("I work at NewCo Labs")
and a NON-day-scoped loop said the same day ARE still surfaced. Retrieval filters by validity
at the moment of the read (`as_of`). Deterministic, zero model calls.

Run:  PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_memctx_temporal.py
"""
import datetime as dt
import tempfile
from pathlib import Path

from anticipy_engine.live_memory.brain import LiveMemoryBrain
from anticipy_engine.memory import Memory


def _iso(d: dt.datetime) -> str:
    return d.isoformat()


def main():
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-temporal-"))
    lm = LiveMemoryBrain(Memory(data_dir=tmp))

    tz = dt.timezone.utc
    day1 = dt.datetime(2026, 6, 1, 9, 0, tzinfo=tz)   # when the words were said
    day2 = dt.datetime(2026, 6, 2, 9, 0, tzinfo=tz)   # the next day (the read moment)
    meta1 = {"observed_at": _iso(day1), "timezone": "UTC"}

    # DAY 1 captures (all heard on day 1):
    eph = lm.capturer.capture("school moved pickup to 3 today, remind me before I forget.",
                              source="app", meta=meta1)
    durable = lm.capturer.capture("I work at NewCo Labs.", source="app", meta=meta1)
    persistent_loop = lm.capturer.capture("remind me to send Sam the revised decking on Friday.",
                                          source="app", meta=meta1)
    assert eph["kept"] and durable["kept"] and persistent_loop["kept"], (eph, durable, persistent_loop)

    # the ephemeral fact carries a valid_to at end of DAY 1; the durable one does not.
    assert eph["item"].valid_to is not None, eph["item"]
    assert durable["item"].valid_to is None, durable["item"]
    # event_time is the utterance clock, not ingest time.
    assert abs(eph["item"].event_time - day1.timestamp()) < 2, eph["item"].event_time

    d1 = day1.timestamp()
    d2 = day2.timestamp()

    # SAME DAY (day1): the ephemeral pickup fact IS surfaced.
    pack_d1 = lm.build_context("pickup", purpose="decide", as_of=d1)
    blob_d1 = " ".join(pack_d1.open_loops + pack_d1.profile + pack_d1.history + [pack_d1.text])
    assert "pickup" in blob_d1.lower(), blob_d1

    # NEXT DAY (day2): the ephemeral pickup fact is GONE (expired) ...
    pack_d2 = lm.build_context("pickup", purpose="decide", as_of=d2)
    blob_d2 = " ".join(pack_d2.open_loops + pack_d2.profile + pack_d2.history + [pack_d2.text])
    assert "pickup" not in blob_d2.lower(), f"stale ephemeral surfaced next day: {blob_d2}"

    # ... but the durable fact and the Friday (non-day-scoped) loop still surface on day2.
    where = lm.build_context("where do I work", purpose="decide", as_of=d2)
    assert any("NewCo" in t for t in where.profile + [where.text]), where.profile
    sam = lm.build_context("Sam decking", purpose="act", as_of=d2)
    sam_blob = " ".join(sam.open_loops + [sam.text])
    assert "decking" in sam_blob.lower(), sam_blob

    print("OK  M3 temporal: 'pickup to 3 today' NOT surfaced next day; durable fact + dated loop still are")


if __name__ == "__main__":
    main()
