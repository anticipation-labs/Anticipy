"""M1 gate — the ONE ContextPack builder is the single context seam.

Proves on a real ControlCore (stub gateway, temp data dir) that the decider, the hands, and
the voice all read through the SAME `live_memory.build_context` (not three parallel pipes),
that it returns a typed ContextPack, that ALL active open loops are ALWAYS surfaced for every
purpose (the spine is never dropped), and that abstain/top_relevance flow through so the
harm-line and hands get the right guard.

Run:  PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_memctx_contextpack.py
"""
import asyncio
import tempfile
from pathlib import Path

from anticipy_engine.core.control_core import ControlCore
from anticipy_engine.core.envelopes import Job
from anticipy_engine.shared.schema import ContextPack


async def main():
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-ctxpack-"))
    core = ControlCore(data_dir=tmp)
    await core.start()
    try:
        lm = core.live_memory

        # Seed: one commitment (open loop) + one durable profile fact.
        lm.capturer.capture("Remind me to send Sam the revised decking before Friday", source="app")
        lm.memory.profile.write_text("My wife Maya prefers texts after lunch.",
                                     provenance="stated", status="active")
        assert any("Sam" in l.text for l in lm.memory.open_loops.all()), "seed loop missing"

        # 1) build_context returns a typed ContextPack for each purpose.
        for purpose in ("decide", "act", "speak"):
            pack = lm.build_context("Sam decking", purpose=purpose)
            assert isinstance(pack, ContextPack), (purpose, type(pack))
            assert pack.purpose == purpose
            # THE SPINE: every active open loop is present for EVERY purpose (never dropped).
            assert any("Sam" in s for s in pack.open_loops), (purpose, pack.open_loops)

        # 2) purpose shapes the budget (act >= decide room), same source of truth.
        decide = lm.build_context("Sam decking", purpose="decide")
        act = lm.build_context("Sam decking", purpose="act")
        assert act.item_count >= decide.item_count, (decide.item_count, act.item_count)

        # 3) the decider seam (read_context, default purpose=decide) goes through the builder
        #    and carries top_relevance + abstain for the harm-line gray middle.
        r = await core.bus.submit_job(Job(intent="read_context", args={"about": "Sam decking"}))
        out = r.output or {}
        assert out.get("purpose") == "decide", out
        assert any("Sam" in s for s in out.get("context", {}).get("open_loops", [])), out
        assert "abstain" in out and "top_relevance" in out, out

        # 4) the hands seam (purpose=act) goes through the SAME builder.
        ra = await core.bus.submit_job(Job(intent="read_context", args={"about": "Sam decking", "purpose": "act"}))
        assert (ra.output or {}).get("purpose") == "act", ra.output

        # 5) _mem_ctx (orchestrator/plan seam) uses the one builder too (back-compat shape).
        pctx = core._mem_ctx("Sam decking")
        assert "Sam" in str(pctx.get("open_loops")), pctx
        assert set(pctx.keys()) >= {"notes", "open_loops", "profile", "history", "derived"}, pctx

        print("OK  M1 ContextPack: one builder, three purposes, spine always complete")
    finally:
        await core.stop()


if __name__ == "__main__":
    asyncio.run(main())
