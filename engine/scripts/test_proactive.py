"""Room 8 test: proactive engine is the wired primary driver (stub).

Run:  PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_proactive.py
"""
import tempfile
from pathlib import Path

from anticipy_engine.actions import ActionLayer
from anticipy_engine.live_memory import LiveMemoryBrain
from anticipy_engine.memory import Memory
from anticipy_engine.proactive import ProactiveEngine
from anticipy_engine.shared.schema import ActionRequest

mem = Memory(data_dir=Path(tempfile.mkdtemp(prefix="anticipy-pe-")))
engine = ProactiveEngine(LiveMemoryBrain(mem), ActionLayer())

# tick(): reads the live-memory seam, proposes nothing (stub)
t1 = engine.tick()
t2 = engine.tick()
assert t1["tick"] == 1 and t2["tick"] == 2
assert t1["read_context"] is True
assert t1["proposals"] == [] and t1["stub"] is True

# it is wired to drive the action layer (gated)
res = engine.act(ActionRequest(intent="add calendar hold", risk="low", path="connector"))
assert res["decision"] == "act"

print("PASS room 8: proactive engine (primary driver, wired, stub)")
print("  tick:", t2)
print("  can drive action layer ->", res["decision"])
