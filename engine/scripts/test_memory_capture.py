"""Piece 2 (unit): memory CAPTURE — keep/drop gate + extraction + dedupe + routing.

(Distinct from the chunk-1 room-2 test_capture.py, which tests the mic->intake
input seam.) Replays a noisy stream and asserts the noise is dropped, commitments
land in the exact open_loops ledger (with fields + people), stated facts land in
profile, episodes land in history, an exact repeat is deduped, and it costs
nothing in stub mode (zero model calls — the Capturer is built with no gateway).

Run:  PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_memory_capture.py
"""
import tempfile
from pathlib import Path

from anticipy_engine.live_memory.brain import LiveMemoryBrain
from anticipy_engine.live_memory.capture import Capturer
from anticipy_engine.memory import Memory
from anticipy_engine.shared.schema import CaptureEvent

STREAM = [
    ("um", "noise"),
    ("ok thanks", "noise"),
    ("hey", "noise"),
    ("yeah sure", "noise"),
    ("I'll call Sarah about the invoice tomorrow", "open_loop"),
    ("Remind me to pay rent on Friday", "open_loop"),
    ("My name is Omar and I'm a founder", "profile_fact"),
    ("I work at Anticipy", "profile_fact"),
    ("We talked about the new ergonomic chair design for a while", "history"),
    ("I'll call Sarah about the invoice tomorrow", "dup"),   # exact repeat
]


def main():
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-cap-"))
    m = Memory(data_dir=tmp)
    cap = Capturer(m)                       # NO gateway -> stub rules only -> free
    assert cap.gateway is None

    kept, dropped = 0, 0
    for text, expect in STREAM:
        r = cap.capture(text)
        assert r["smart_calls"] == 0, r     # hot path is cheap: zero model calls
        if expect == "noise":
            assert r["kept"] is False and r["reason"] == "noise", (text, r)
            dropped += 1
        elif expect == "dup":
            assert r["kept"] is False and r["reason"] == "dup", (text, r)
            dropped += 1
        else:
            assert r["kept"] is True and r["kind"] == expect, (text, r)
            kept += 1

    # routed to the right drawers, correct counts
    assert len(m.open_loops.all()) == 2 and len(m.profile.all()) == 2 and len(m.history.all()) == 1
    assert kept == 5 and dropped == 5

    # open_loops is EXACT: commitment text stored verbatim, with fields + state
    loops = {i.text: i for i in m.open_loops.all()}
    sarah = loops["I'll call Sarah about the invoice tomorrow"]
    assert sarah.status == "open" and sarah.fields.get("task") == sarah.text
    assert sarah.fields.get("due") == "tomorrow" and "Sarah" in sarah.people
    rent = loops["Remind me to pay rent on Friday"]
    assert rent.fields.get("due") == "Friday"

    # stated facts carry provenance=stated, confidence 1.0
    pf = m.profile.all()[0]
    assert pf.provenance == "stated" and pf.confidence == 1.0

    # the seam works end-to-end via LiveMemoryBrain on a CaptureEvent
    lmb = LiveMemoryBrain(Memory(data_dir=Path(tempfile.mkdtemp(prefix="anticipy-cap2-"))))
    res = lmb.capture(CaptureEvent(source="mac_mic", text="I need to email the landlord about the lease tonight"))
    assert res["kept"] and res["kind"] == "open_loop" and "landlord" in res["item"].people
    assert lmb.capture(CaptureEvent(source="mac_mic", text="uh"))["kept"] is False

    print("PASS piece 2: capture gate drops noise (5/5), routes commitments->open_loops "
          "(exact+fields+people), facts->profile, episodes->history, dedupes, zero model calls")


if __name__ == "__main__":
    main()
