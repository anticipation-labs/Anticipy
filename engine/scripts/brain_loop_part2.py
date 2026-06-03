"""brain_loop part 2 (a FRESH process = engine restart): reload the waiting goal
from disk and resume it to done. Proves goals survive a restart (section 6.6).
"""
import asyncio

from anticipy_engine.core.control_core import ControlCore
from anticipy_engine.core.envelopes import GoalState, StepState


async def main() -> None:
    core = ControlCore()  # same ANTICIPY_DATA_DIR; nothing in memory from part 1

    waiting = core.store.waiting()
    assert waiting, "expected a waiting goal persisted from part 1"
    gid = waiting[0].id

    await core.start()
    try:
        resumed = await core.resume()
    finally:
        await core.stop()

    assert len(resumed) >= 1
    reloaded = core.store.load(gid)
    assert reloaded.state == GoalState.done, reloaded.state
    assert all(s.state == StepState.done and s.result and s.result.proof for s in reloaded.steps)
    assert len(core.gateway.smart_calls) == 0, "resume must not re-plan"

    print("PART2 PASS")
    print(f"  resumed goal {gid[:8]} survived restart -> state={reloaded.state.value}; re-plans=0")


if __name__ == "__main__":
    asyncio.run(main())
