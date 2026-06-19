"""GATE F: a RETRACTED task is silenced; a prep-task BOUND ("don't send/buy") is preserved.

The generalization sweep found the engine acting/asking on tasks the owner explicitly took back —
"schedule the meeting... no actually hold off", "confirm the reservation... scratch that, we might
cancel". Acting on a retracted task is a trust+cardinal failure. Fix: a NARROW _RETRACTION detector
(unambiguous cancel phrases only — never/scratch that/forget it/hold off/on second thought/nix-cancel-
disregard-belay that/we might cancel) folded into is_vent_shape. It deliberately EXCLUDES the bare
"don't buy/send" countermand, which is a no-purchase BOUND on a draft/cart-prep task, not a retraction —
so "draft an email but don't send it" still surfaces. Stub model + empty memory (the floor must hold
model-independently).

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_retraction_silenced.py
"""
import os
import asyncio
import tempfile

os.environ["ANTICIPY_MODEL_PROVIDER"] = "stub"
os.environ.setdefault("ANTICIPY_HANDS_MODE", "mock")
os.environ.setdefault("ANTICIPY_CHANNELS_MODE", "mock")
os.environ.setdefault("ANTICIPY_NATIVE_BRIDGE_FALLBACK", "0")
os.environ.setdefault("ANTICIPY_VAULT_KEY", "test-master-key-do-not-use-in-prod")
os.environ["ANTICIPY_DATA_DIR"] = tempfile.mkdtemp()

from anticipy_engine.core.control_core import ControlCore  # noqa: E402
from anticipy_engine.live_memory.review_infer import is_vent_shape  # noqa: E402

# Retraction phrase detection (unit-level, deterministic):
RETRACT_SHAPES = [
    "schedule it for Tuesday, scratch that",
    "book the flight, on second thought forget it",
    "set the reminder, never mind",
    "hold off on the reservation",
    "confirm it, we might cancel",
]
# These are BOUNDS on prep tasks, NOT retractions — must NOT be treated as vents:
BOUND_SHAPES = [
    "draft an email to Sarah but don't send it",
    "put diapers in the cart, don't check out",
    "build the cart but don't buy yet",
]

fails = []
for t in RETRACT_SHAPES:
    if not is_vent_shape(t):
        fails.append(f"retraction NOT detected by is_vent_shape: {t!r}")
for t in BOUND_SHAPES:
    if is_vent_shape(t):
        fails.append(f"prep-task BOUND wrongly treated as vent/retraction: {t!r}")


async def main():
    core = ControlCore()
    await core.bus.start()
    try:
        # End-to-end: a retracted task must not act/ask; a real task must still surface.
        for t in [
            "schedule a meeting with the whole team for next Tuesday... no actually hold off on that",
            "confirm the restaurant reservation for eight people tomorrow... scratch that, we might cancel",
        ]:
            cards = (await core.owner_ingest("transcript", t, execute_actions=True)).get("cards") or []
            leaked = [c for c in cards if (c.get("execution") or {}).get("decision") in ("act", "ask")
                      or c.get("disposition") == "ask"]
            if leaked:
                fails.append(f"retracted task acted/asked: {t!r}")
        for t in ["remind me to call the dentist tomorrow at 3", "block off Friday morning for the review"]:
            if not ((await core.owner_ingest("transcript", t, execute_actions=True)).get("cards") or []):
                fails.append(f"real task dropped: {t!r}")
    finally:
        await core.bus.stop()


asyncio.run(main())

if fails:
    for f in fails:
        print("FAIL:", f)
    raise SystemExit(1)
print("PASS retraction_silenced: retractions silenced, prep-task bounds + real tasks preserved")
