"""Room 6 test — the frontend-facing API (decisions flow brain -> app -> back).

The SwiftUI app's "needs you" surface and approve/deny resolve REAL paused goals through these
ControlCore methods (exposed over HTTP as /pending and /resolve). Asserts: a detrimental event
PAUSES and APPEARS in pending_asks(); approve RESUMES the exact paused goal to done and clears
it from the surface; deny drops a goal + writes the decline; the glass-box carries the full trail.

ControlCore with default MOCK hands (send_email -> ApiHand mock); deterministic.
Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_frontend_api.py
"""
import asyncio
import tempfile
from pathlib import Path

from anticipy_engine.core.control_core import ControlCore
from anticipy_engine.core.envelopes import GoalState


async def main():
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-fe-"))
    core = ControlCore(data_dir=tmp)
    fails = []
    await core.start()
    try:
        # (1) detrimental event -> PAUSE -> appears on the "needs you" surface
        out = await core.feed("app", "Email the investor the signed contract.")
        if not (out["decision"] == "ask" and out["ask_id"]):
            fails.append(f"detrimental should pause + register an ask: {out}")
        pend = core.pending_asks()
        if not any(p["ask_id"] == out["ask_id"] and "investor" in p["action"] for p in pend):
            fails.append(f"paused ask must appear in pending_asks(): {pend}")

        # (2) APPROVE (app tap) -> the REAL paused goal resumes to done; cleared from the surface
        r = await core.resolve(out["ask_id"], approved=True)
        resumed = core.store.load(out["goal_id"])
        if not (r.get("approved") and resumed.state == GoalState.done):
            fails.append(f"approve must resume the exact paused goal to done: r={r} state={resumed.state}")
        if any(p["ask_id"] == out["ask_id"] for p in core.pending_asks()):
            fails.append("approved ask should be cleared from the surface")

        # (3) DENY (app tap) -> goal dropped + decline written (Room 5 feed)
        out2 = await core.feed("app", "Delete the production database.")
        r2 = await core.resolve(out2["ask_id"], approved=False)
        if not (r2.get("approved") is False and core.store.load(out2["goal_id"]).state == GoalState.failed):
            fails.append(f"deny must drop the goal: r2={r2}")

        # (4) the glass-box carries the full trail (what the app's feed renders)
        kinds = {e["kind"] for e in core.glassbox.entries()}
        need = {"decision", "ask_sent", "ask_approved", "ask_declined", "goal_done"}
        if not need <= kinds:
            fails.append(f"glass-box trail missing {need - kinds}; has {sorted(kinds)}")
    finally:
        await core.stop()

    print("==== ROOM 6 — FRONTEND API (brain -> app -> back) ====")
    print(f"  (1) detrimental -> paused + on the 'needs you' surface (pending_asks)")
    print(f"  (2) approve -> resumed goal state={core.store.load(out['goal_id']).state.value}; cleared from surface")
    print(f"  (3) deny -> goal dropped + decline written")
    print(f"  (4) glass-box trail kinds present: decision/ask_sent/ask_approved/ask_declined/goal_done")
    if fails:
        print("==== FAIL ===="); [print("   -", f) for f in fails]; raise SystemExit(1)
    print("==== PASS ====")


if __name__ == "__main__":
    asyncio.run(main())
