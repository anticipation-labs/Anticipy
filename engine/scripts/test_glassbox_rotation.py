"""glassbox.jsonl is a true BYTE-capped log — it rotates (keeps recent) instead of growing
unbounded, honors the byte cap regardless of KEEP_LINES, and NEVER crashes the engine's log path
(even on a malformed env value). The 21GB runaway that filled the disk can't recur.

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_glassbox_rotation.py
"""
import os
import tempfile
from pathlib import Path

from anticipy_engine.core.glassbox import GlassBox


def _fresh(d, name="glassbox.jsonl"):
    return GlassBox(Path(d) / name)


def main():
    # 1) basic rotation: keep recent, drop head, stay bounded; newest survives (tail, not head)
    os.environ["ANTICIPY_GLASSBOX_MAX_BYTES"] = "3000"
    os.environ["ANTICIPY_GLASSBOX_KEEP_LINES"] = "25"
    with tempfile.TemporaryDirectory() as d:
        gb = _fresh(d); p = Path(d) / "glassbox.jsonl"
        for i in range(2000):
            gb.log("event", {"text": f"line {i} " + "x" * 50})
        assert p.stat().st_size <= 3000, p.stat().st_size
        ents = gb.entries()
        assert ents[-1]["data"]["text"].startswith("line 1999"), ents[-1]
        assert gb.tail(5) and gb.summaries(5)

    # 2) malformed env value must NOT crash logging (falls back to defaults) — the critical fix
    os.environ["ANTICIPY_GLASSBOX_MAX_BYTES"] = "notanint"
    os.environ["ANTICIPY_GLASSBOX_KEEP_LINES"] = "also-bad"
    with tempfile.TemporaryDirectory() as d:
        gb = _fresh(d)
        for i in range(50):
            gb.log("event", {"text": f"y{i}"})   # must not raise
        assert len(gb.entries()) == 50

    # 3) KEEP_LINES=0 must NOT mean "keep everything" (clamped >=1) -> still byte-bounded
    os.environ["ANTICIPY_GLASSBOX_MAX_BYTES"] = "2000"
    os.environ["ANTICIPY_GLASSBOX_KEEP_LINES"] = "0"
    with tempfile.TemporaryDirectory() as d:
        gb = _fresh(d); p = Path(d) / "glassbox.jsonl"
        for i in range(1000):
            gb.log("event", {"text": f"z{i} " + "x" * 50})
        assert p.stat().st_size <= 2100, f"KEEP_LINES=0 must not defeat the cap: {p.stat().st_size}"

    # 4) a huge KEEP_LINES must still honor the BYTE cap (not KEEP_LINES x line-size)
    os.environ["ANTICIPY_GLASSBOX_MAX_BYTES"] = "2000"
    os.environ["ANTICIPY_GLASSBOX_KEEP_LINES"] = "100000"
    with tempfile.TemporaryDirectory() as d:
        gb = _fresh(d); p = Path(d) / "glassbox.jsonl"
        for i in range(1000):
            gb.log("event", {"text": f"w{i} " + "x" * 50})
        assert p.stat().st_size <= 2100, f"byte cap must hold despite huge KEEP_LINES: {p.stat().st_size}"

    # 5) under the DEFAULT cap (8MB) a small log is untouched
    os.environ.pop("ANTICIPY_GLASSBOX_MAX_BYTES", None)
    os.environ.pop("ANTICIPY_GLASSBOX_KEEP_LINES", None)
    with tempfile.TemporaryDirectory() as d:
        gb = _fresh(d)
        for i in range(5):
            gb.log("event", {"text": f"x{i}"})
        assert len(gb.entries()) == 5

    print("PASS: glassbox.jsonl is a true byte-capped log — bounded under any KEEP_LINES, "
          "survives a malformed env value, keeps recent, defaults untouched")


if __name__ == "__main__":
    main()
