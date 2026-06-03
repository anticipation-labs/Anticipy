"""Piece 6 (engine) test: glass-box + scorecard + ControlCore wiring.

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_glassbox_scorecard.py
"""
import asyncio
import tempfile
from pathlib import Path

from anticipy_engine.core.control_core import ControlCore
from anticipy_engine.core.glassbox import GlassBox
from anticipy_engine.core.scorecard import Scorecard


def test_units():
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-gb-"))
    gb = GlassBox(tmp / "glassbox.jsonl")
    gb.log("event", {"text": "hello"})
    gb.log("decision", {"decision": "do_and_notify", "text": "hello"})
    assert len(gb.entries()) == 2
    sums = gb.summaries()
    assert any(s["kind"] == "decision" and "do_and_notify" in s["summary"] for s in sums)

    sc = Scorecard(tmp / "scorecard.jsonl")
    sc.record_decision("do_and_notify", "ev1")
    sc.record_goal("g1", "success", 0.04)
    r = sc.readout()
    assert r["decisions"]["do_and_notify"] == 1 and r["goal_outcomes"]["success"] == 1
    assert r["total_model_cost"] == 0.04
    print("  units: glassbox summaries + scorecard readout OK")


async def test_control_core():
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-core-"))
    core = ControlCore(data_dir=tmp)
    await core.start()
    try:
        out = await core.feed("mac_mic", "I'll send Sarah the Q3 deck on Friday and book us lunch.")
    finally:
        await core.stop()
    assert out["decision"] == "do_and_notify" and out["goal_id"]

    kinds = {e["kind"] for e in core.glassbox.entries()}
    for required in ("event", "decision", "job", "result", "goal_done"):
        assert required in kinds, f"glass-box missing {required}: {kinds}"

    ro = core.scorecard.readout()
    assert ro["decisions"].get("do_and_notify") == 1
    assert ro["goal_outcomes"].get("success") == 1
    assert ro["total_model_cost"] > 0
    print("  control core: glass-box trail =", sorted(kinds))
    print("  scorecard readout:", ro)


async def main():
    test_units()
    await test_control_core()
    print("PASS piece 6 (engine): glass-box + scorecard + control core")


if __name__ == "__main__":
    asyncio.run(main())
