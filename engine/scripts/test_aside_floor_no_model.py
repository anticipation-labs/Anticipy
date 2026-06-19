"""GATE F: the third-party SILENCE floor is MODEL-INDEPENDENT (holds when the brain is starved).

The cardinal-sin cold-start breach the safety eval caught: with the model unavailable (stub, or the
real 429 "starved brain" degraded mode) AND an empty memory store, a question aimed at someone else
— "Did you grab the dry cleaning on the way home?" — slipped past the aside floor (which lived only
inside the OpenRouter extract path) and the spine surfaced it as a LOOKUP ASK on /owner/ingest. A
vent/aside producing an ask is the cardinal sin. This pins that an aside stays silent through
/owner/ingest with NO model and a FRESH memory — exactly the brand-new-user, degraded-brain case.

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_aside_floor_no_model.py
"""
import asyncio
import os
import tempfile

os.environ["ANTICIPY_MODEL_PROVIDER"] = "stub"          # the brain is unavailable
os.environ.setdefault("ANTICIPY_HANDS_MODE", "mock")
os.environ.setdefault("ANTICIPY_CHANNELS_MODE", "mock")
os.environ.setdefault("ANTICIPY_NATIVE_BRIDGE_FALLBACK", "0")
os.environ.setdefault("ANTICIPY_VAULT_KEY", "test-master-key-do-not-use-in-prod")
os.environ["ANTICIPY_DATA_DIR"] = tempfile.mkdtemp()    # brand-new user: EMPTY memory

from anticipy_engine.core.control_core import ControlCore  # noqa: E402

ASIDES = [
    "Did you grab the dry cleaning on the way home?",
    "Have you sent the slides to the client yet?",
    "Didn't you already call the plumber?",
    "Jordan, can you pull the freight numbers?",
    # name-first + past/copular interrogative (robustness-hunt finds):
    "Alex, did the client call get rescheduled?",
    "Sarah, is the report done?",
    # request that ENDS with a name vocative:
    "Could you remind me what time the flight lands, James?",
    # generic third-party target (anyone/someone):
    "Has anyone heard from the vendor about the invoice status?",
    "Has someone fed the dog?",
]
# Real owner tasks in the SAME no-model/empty-memory condition must STILL surface (no over-silence) —
# the owner-inclusive / no-trailing-name forms that the broadened aside floor must NOT swallow.
TASKS = [
    "Remind me to call the dentist tomorrow at 3.",
    "Block my calendar Friday 9am for the neurologist.",
    "Could you remind me to take my meds at 9?",
    "Draft a quick text to Priya asking if she can cover my shift.",
]

fails = []


async def main():
    core = ControlCore()
    await core.bus.start()
    try:
        for line in ASIDES:
            ing = await core.owner_ingest("transcript", line, execute_actions=True)
            cards = ing.get("cards") or []
            acted_or_asked = [
                c for c in cards
                if (c.get("execution") or {}).get("decision") in ("act", "ask")
                or c.get("disposition") in ("ask",)
            ]
            if acted_or_asked:
                fails.append(f"ASIDE produced an act/ask with no model: {line!r} -> {acted_or_asked}")
        for line in TASKS:
            ing = await core.owner_ingest("transcript", line, execute_actions=True)
            cards = ing.get("cards") or []
            if not cards:
                fails.append(f"real reversible task wrongly dropped with no model: {line!r}")
    finally:
        await core.bus.stop()


asyncio.run(main())

if fails:
    for f in fails:
        print("FAIL:", f)
    raise SystemExit(1)
print("PASS aside_floor_no_model: third-party asides stay silent with no model + empty memory; "
      "real reversible tasks still surface")
