"""Live memory contract test: capture, inject, maintain, infer, self-check.

Run:  PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_live_memory.py
"""
import tempfile
from pathlib import Path

from anticipy_engine.live_memory import LiveMemoryBrain
from anticipy_engine.memory import Memory
from anticipy_engine.shared.schema import CaptureEvent


tmp = Path(tempfile.mkdtemp(prefix="anticipy-lm-"))
mem = Memory(data_dir=tmp)
brain = LiveMemoryBrain(mem)

# capture(): useful speech is routed into the right drawer; pure filler is dropped.
loop = brain.capture(CaptureEvent(
    source="mac_mic",
    text="Remind me to call Sarah about the overdue invoice tomorrow",
))
assert loop["kept"] is True and loop["kind"] == "open_loop", loop
assert loop["item"].fields["task"].startswith("Remind me"), loop["item"].fields
assert brain.capture(CaptureEvent(source="mac_mic", text="uh"))["kept"] is False

profile = brain.capture(CaptureEvent(source="mac_mic", text="I work at Anticipy"))
assert profile["kept"] is True and profile["kind"] == "profile_fact", profile
profile_new = brain.capture(CaptureEvent(source="mac_mic", text="I work at NewCo now"))
assert profile_new["kept"] is True and profile_new["kind"] == "profile_fact", profile_new

# Direct writes simulate memory arriving from multiple product doors.
hist1 = mem.history.write_text("Sarah and I reviewed the invoice packet", people=["Sarah"])
hist2 = mem.history.write_text("Sarah and I reviewed the invoice packet", people=["Sarah"])
mem.history.write_text("Sarah asked about invoice timing again", people=["Sarah"])
mem.history.write_text("Sarah mentioned the invoice follow-up one more time", people=["Sarah"])

# inject(): retrieval is real, not a stub, and every open loop is always surfaced.
ctx = brain.inject("Sarah invoice")
assert ctx["stub"] is False, ctx
assert loop["item"].id in {i.id for i in ctx["open_loops"]}, ctx["open_loops"]
assert hist1.id in {i.id for i in ctx["history"]}, ctx["history"]
assert "[open_loop]" in ctx["text"] and "Sarah" in ctx["text"], ctx["text"]

# maintain(): cold cleanup supersedes changed profile facts and consolidates dup history.
maint = brain.maintain()
assert maint["ran"] is True, maint
assert maint["superseded"] >= 1, maint
assert maint["consolidated"] >= 1, maint
assert mem.profile.get(profile["item"].id).status == "superseded"
assert mem.history.get(hist2.id).status != mem.history.get(hist1.id).status

# infer(): repeated episodes become derived context, never promoted to stated facts.
inf = brain.infer()
assert inf["ran"] is True and inf["created"] >= 1, inf
derived = mem.derived.all()
assert any(d.fields.get("signal") == "person:sarah" for d in derived), [d.model_dump() for d in derived]
assert all(d.provenance == "inferred" and d.confidence < 1.0 for d in derived), derived

# inject_checked(): self-check proves the injected context is complete and recalls expected memory.
checked = brain.inject_checked("Sarah invoice")
check = checked["self_check"]
assert check["hit"] is True and check["complete"] is True, check
surviving_invoice = next(
    h for h in mem.history.all()
    if h.text == "Sarah and I reviewed the invoice packet" and h.status not in ("archived", "superseded")
)
explicit = brain.recall_check("Sarah invoice", checked, expected_ids=[loop["item"].id, surviving_invoice.id])
assert explicit["hit"] is True, explicit

print("PASS live_memory: real capture/inject/maintain/infer/self-check contract")
