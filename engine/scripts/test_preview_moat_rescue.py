"""LOCK: PREVIEW == REALITY for model-caught (moat_task) tasks.

Regression for the relentless bug-hunt's biggest find: in PREVIEW (execute_actions=False, the box
unchecked), a real task the MODEL caught but the regex didn't shape was SILENTLY DROPPED — the owner
reviewing first saw FEWER tasks than the live run. The execute path rescued them; preview did not.
This pins it: a moat_task line surfaces a card in preview; a vent stays silent; money stays blocked.

Deterministic — stub model; we simulate the moat by marking every observed line moat_task=True (what
the live model would do for a clean real task), so no network is needed.
"""
import asyncio
import os
import tempfile
from pathlib import Path

os.environ.setdefault("ANTICIPY_MODEL_PROVIDER", "stub")
os.environ.setdefault("ANTICIPY_HANDS_MODE", "mock")
os.environ.setdefault("ANTICIPY_CHANNELS_MODE", "mock")

from anticipy_engine.core.control_core import ControlCore  # noqa: E402


async def _cards(core, text):
    out = await core.owner_ingest("typed", text, {"t": "1"}, execute_actions=False)  # PREVIEW
    return out["cards"]


async def main():
    d = Path(tempfile.mkdtemp())
    core = ControlCore(data_dir=d)
    await core.start()

    # Simulate the model brain: mark every observed line as a confident model-caught task
    # (moat_task=True), exactly what the live extractor does for a clean real task the regex
    # can't shape. (2026-07-02: the injection seam moved — the old second model brain
    # _expand_tasks_with_model was deleted in FIX-01 2c; under stub the else-branch now calls
    # the sync _deterministic_expand, so that is what we patch. Same lock, same assertions.)
    def _fake_expand(observed):
        for o in observed:
            o.moat_task = True
        return observed

    core._deterministic_expand = _fake_expand  # type: ignore

    fails = []

    # (1) a real model-caught task the regex doesn't shape MUST surface in preview (was DROPPED)
    real = await _cards(core, "Cancel the WeWork, we're not using it.")
    if not real:
        fails.append("preview DROPPED a real moat_task ('cancel the WeWork') — PREVIEW != REALITY")

    # (2) a vent stays SILENT even when marked moat_task (cardinal-sin floor)
    vent = await _cards(core, "honestly I'm so done with all this, I'm moving to the woods.")
    if vent:
        fails.append(f"vent surfaced a card in preview: {[c.get('disposition') for c in vent]}")

    # (3) money stays BLOCKED in preview, never a plain ask, never dropped
    money = await _cards(core, "Pay the invoice, 500 dollars.")
    if not money or money[0].get("disposition") != "blocked":
        fails.append(f"money not blocked in preview: {[(c.get('disposition')) for c in money] or 'DROPPED'}")

    await core.stop()
    if fails:
        for f in fails:
            print("FAIL:", f)
        raise SystemExit(1)
    print("PASS preview_moat_rescue: real model-caught tasks surface in preview; vents silent; money blocked")


if __name__ == "__main__":
    asyncio.run(main())
