"""M2 gate — capture-time ADD/UPDATE/DELETE reconciliation.

Proves that a contradicting stated fact UPDATEs the world at WRITE time (not only in the
cold sweep): re-ingest "I work at X" then "I work at Y" -> exactly ONE active employer fact
(Y), X superseded WITH a trail (superseded_by), and the retrieval/ContextPack never surfaces
the stale X. Coexisting facts (preferences) are left alone. Deterministic, zero model calls.

Run:  PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_memctx_reconcile.py
"""
import tempfile
from pathlib import Path

from anticipy_engine.live_memory.brain import LiveMemoryBrain
from anticipy_engine.memory import Memory


def main():
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-recon-"))
    mem = Memory(data_dir=tmp)
    lm = LiveMemoryBrain(mem)

    # Coexisting preference (control): must NOT be superseded by anything below.
    lm.capturer.capture("I prefer tea over coffee.", source="app")

    # ADD then UPDATE the single-valued 'employer' subject.
    r1 = lm.capturer.capture("I work at OldCo Inc.", source="app")
    r2 = lm.capturer.capture("Actually I work at NewCo Labs now.", source="app")
    assert r1["kept"] and r2["kept"], (r1, r2)
    # the UPDATE superseded the older employer fact at write time
    assert r2.get("superseded", 0) >= 1, r2

    facts = mem.profile.all()
    active_employer = [f for f in facts if "work at" in f.text.lower() and f.status == "active"]
    superseded = [f for f in facts if f.status == "superseded"]
    assert len(active_employer) == 1, [f.text for f in active_employer]
    assert "NewCo" in active_employer[0].text, active_employer[0].text
    # TRAIL preserved (not deleted), points at the winner.
    assert superseded and "OldCo" in superseded[0].text, [f.text for f in superseded]
    assert (superseded[0].fields or {}).get("superseded_by") == active_employer[0].id, superseded[0].fields

    # preference untouched (coexists)
    assert any("tea" in f.text.lower() and f.status == "active" for f in facts)

    # THE STALE FACT NEVER SURFACES: the one ContextPack builder must show NewCo, never OldCo.
    pack = lm.build_context("where do I work", purpose="decide")
    blob = " ".join(pack.profile + [pack.text])
    assert "NewCo" in blob and "OldCo" not in blob, blob

    print("OK  M2 reconcile: contradiction resolves at write -> one active fact, trail kept, stale never surfaced")


if __name__ == "__main__":
    main()
