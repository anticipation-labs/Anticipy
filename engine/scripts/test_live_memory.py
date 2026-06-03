"""Room 7 test: the live memory brain seam holds.

Run:  PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_live_memory.py
"""
import tempfile
from pathlib import Path

from anticipy_engine.live_memory import LiveMemoryBrain
from anticipy_engine.memory import Memory
from anticipy_engine.shared.schema import CaptureEvent

mem = Memory(data_dir=Path(tempfile.mkdtemp(prefix="anticipy-lm-")))
brain = LiveMemoryBrain(mem)

# capture(): folds an event into history
ev = CaptureEvent(source="mac_mic", text="hello from the mic")
item = brain.capture(ev)
assert item.kind == "history" and item.text == ev.text
assert len(mem.history.all()) == 1

# inject(): stub returns the shape, selects nothing yet
ctx = brain.inject("what's on my plate?")
assert set(ctx) >= {"context", "profile", "open_loops", "history"}
assert ctx["stub"] is True and ctx["history"] == []

# maintain(): stub no-op
m = brain.maintain()
assert m["ran"] is False

print("PASS room 7: live memory brain seam (inject / capture / maintain)")
print("  capture ->", item.model_dump())
print("  inject keys:", sorted(ctx.keys()))
