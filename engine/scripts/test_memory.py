"""Room 6 test: three separate memory stores, read/write, local only.

Uses an isolated temp data dir so it's repeatable and pollutes nothing.

Run:  PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_memory.py
"""
import tempfile
from pathlib import Path

from anticipy_engine.memory import Memory

tmp = Path(tempfile.mkdtemp(prefix="anticipy-mem-"))
mem = Memory(data_dir=tmp)

# write a scrap to history, read it back (the hello-loop's memory hop)
scrap = mem.history.write_text("engine heard: hello from the mic")
back = mem.history.get(scrap.id)
assert back is not None and back.text == scrap.text
assert back.kind == "history"

# stores are SEPARATE: a history write must not appear in profile/open_loops
assert len(mem.history.all()) == 1
assert mem.profile.all() == []
assert mem.open_loops.all() == []

# each store stamps its own kind
fact = mem.profile.write_text("name is Omar")
loop = mem.open_loops.write_text("reply to landlord")
assert fact.kind == "profile_fact" and loop.kind == "open_loop"

# separate files on disk (local only)
files = sorted(p.name for p in tmp.glob("*.json"))
assert files == ["history.json", "open_loops.json", "profile.json"], files

print("PASS room 6: memory (three separate stores)")
print("  data dir:", tmp)
print("  files:", files)
print("  history readback:", back.model_dump())
