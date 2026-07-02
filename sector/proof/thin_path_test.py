"""sector/proof/thin_path_test.py — the failable walking-skeleton test.

Proves the WHOLE line runs end-to-end as one thing on the mock: a real messy day goes in;
real tasks come out; the vent stays silent; a warm human check-in is produced; memory compounds.
This is the sector's own gate — it must stay green before any widening step lands.

Run:  ANTICIPY_MODEL_PROVIDER=stub ANTICIPY_HANDS_MODE=mock ANTICIPY_CHANNELS_MODE=mock \
      PYTHONPATH=engine engine/.venv/bin/python sector/proof/thin_path_test.py
"""
import asyncio
import os
import sys

os.environ.setdefault("ANTICIPY_MODEL_PROVIDER", "stub")
os.environ.setdefault("ANTICIPY_HANDS_MODE", "mock")
os.environ.setdefault("ANTICIPY_CHANNELS_MODE", "mock")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from anticipy_engine.core.control_core import ControlCore  # noqa: E402
from sector.skeleton import run_thin_path  # noqa: E402

MESSY = "grab the kids at 3, honestly I should just quit, email Sarah the budget tonight"

fails = []


async def main():
    core = ControlCore()
    await core.bus.start()
    try:
        tr = await run_thin_path(core, text=MESSY)
        print("  TRACE:", tr.summary())
        blob = " ".join(tr.tasks).lower()
        if "kid" not in blob:
            fails.append("did not catch the kids pickup")
        if "sarah" not in blob and "budget" not in blob:
            fails.append("did not catch the email-Sarah task")
        if "quit" in blob:
            fails.append("acted on the vent ('quit') — cardinal sin")
        if not tr.check_in:
            fails.append("no warm human check-in was produced")
        if not tr.ok:
            fails.append(f"line did not complete ok: {tr.summary()}")
    finally:
        await core.bus.stop()


asyncio.run(main())

if fails:
    for f in fails:
        print("FAIL:", f)
    raise SystemExit(1)
print("PASS thin_path: the whole line runs end-to-end — caught real tasks, ignored the vent, "
      "produced a warm check-in, memory compounded.")
