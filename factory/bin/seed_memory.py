#!/usr/bin/env python
"""Seed a fresh ANTICIPY_DATA_DIR from a persona's seed_memory.jsonl.

Usage: seed_memory.py --persona factory/personas/dev/lawyer_marcus --data <data_dir>

Each jsonl line: {"kind": "profile_fact|open_loop|history|derived", "text": "...",
                  "people": [...], "fields": {...}, "importance": 0.6, "status": "open"}
Personal data lives HERE (and only here) — never in product code.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--persona", required=True, help="persona dir containing seed_memory.jsonl")
    ap.add_argument("--data", required=True, help="target ANTICIPY_DATA_DIR (created fresh)")
    args = ap.parse_args()

    data_dir = Path(args.data).expanduser().resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    os.environ["ANTICIPY_DATA_DIR"] = str(data_dir)
    # Deterministic stub embedder for seeding; live runs can reindex().
    os.environ.setdefault("ANTICIPY_MEMORY_MODE", "stub")

    sys.path.insert(0, str(REPO / "engine"))
    from anticipy_engine.memory.store import Memory  # noqa: E402
    from anticipy_engine.shared.schema import MemoryItem  # noqa: E402

    seed_path = Path(args.persona) / "seed_memory.jsonl"
    if not seed_path.exists():
        print(f"seed_memory.py: no seed file at {seed_path}", file=sys.stderr)
        return 2

    mem = Memory(data_dir=data_dir)
    count = 0
    for raw in seed_path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw or raw.startswith("#"):
            continue
        rec = json.loads(raw)
        kind = rec.pop("kind")
        item = MemoryItem(kind=kind, text=rec.pop("text"),
                          people=rec.pop("people", []), fields=rec.pop("fields", {}),
                          **{k: v for k, v in rec.items()
                             if k in ("importance", "confidence", "status", "provenance", "timestamp")})
        mem.drawer(kind).write(item)
        count += 1
    print(json.dumps({"seeded": count, "data_dir": str(data_dir), "db": str(mem.db.path)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
