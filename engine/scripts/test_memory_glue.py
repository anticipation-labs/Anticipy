"""Piece 7 (integration): memory baked into the brain so it can't be skipped.

Proves on a real ControlCore (stub gateway, temp data dir): capture-before-act in
feed(), the real MemoryWorker answering read_context with injected memory (the
gate's seam), the orchestrator's memory_context hook (the plan's seam), and
write_memory on the frozen contract (proof returned). The full suite (incl.
brain_loop) proves nothing else broke.

Run:  PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_memory_glue.py
"""
import asyncio
import tempfile
from pathlib import Path

from anticipy_engine.core.control_core import ControlCore
from anticipy_engine.core.envelopes import Job


async def main():
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-glue-"))
    core = ControlCore(data_dir=tmp)
    await core.start()
    try:
        # a commitment lands in the deterministic open_loops ledger
        core.live_memory.capturer.capture("Remind me to call Sarah about the overdue invoice on Friday", source="app")
        assert any("Sarah" in l.text for l in core.memory.open_loops.all())

        # INJECT-at-gate: the real MemoryWorker answers read_context with relevant memory + proof
        r = await core.bus.submit_job(Job(intent="read_context", args={"about": "Sarah invoice"}))
        ctx = (r.output or {}).get("context", {})
        assert any("Sarah" in s for s in ctx.get("open_loops", [])), ctx
        assert r.proof and r.proof.get("open_loops", 0) >= 1

        # INJECT-at-plan: the orchestrator's memory_context hook surfaces the notes
        pctx = core.orchestrator.memory_context("Sarah invoice")
        assert "Sarah" in str(pctx), pctx

        # write_memory on the frozen contract: written + proof + routed to a drawer
        w = await core.bus.submit_job(Job(intent="write_memory", args={"text": "I prefer tea over coffee."}))
        assert w.output.get("written") and w.proof.get("memory_id") != "none", (w.output, w.proof)
        assert any("tea" in p.text for p in core.memory.profile.all())

        h = await core.bus.submit_job(Job(intent="write_memory", args={
            "text": "User declined to: send the incident summary publicly.",
            "kind": "history",
        }))
        assert h.output.get("written") and h.proof.get("kind") == "history", (h.output, h.proof)
        assert any("declined" in p.text for p in core.memory.history.all())
        assert not any("declined" in p.text for p in core.memory.open_loops.all())

        # CAPTURE-before-act through feed(): a stated fact is in memory even when triaged out (no goal)
        await core.feed("app", "My dentist is Dr. Lee, I see her on Tuesdays.")
        assert any("Lee" in p.text for p in core.memory.profile.all())
    finally:
        await core.stop()

    print("PASS piece 7: capture-before-act in feed(), real read_context inject at the gate (with proof), "
          "memory_context at the plan, write_memory on the frozen contract")


if __name__ == "__main__":
    asyncio.run(main())
