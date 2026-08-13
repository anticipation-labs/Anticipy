#!/usr/bin/env python3
"""Stress the real temporal memory with a large ambient transcript history."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import resource
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from brain.memory import Memory


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=100_000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="anticipy-memory-scale-") as folder:
        db_path = Path(folder) / "memory.sqlite3"
        memory = Memory(db_path)
        memory.ingest("project lighthouse gate code is 4417", ts=1.0)
        for index in range(args.count):
            memory.ingest(
                f"ambient filler sentence {index} about ordinary daily context",
                ts=2.0 + index,
            )
        memory.ingest("project lighthouse launch room is cedar", ts=args.count + 3.0)

        recall_started = time.perf_counter()
        recalled = memory.recall("what is the project lighthouse gate code", limit=8)
        recall_seconds = time.perf_counter() - recall_started
        blob = " ".join(str(item) for item in recalled).lower()
        if "4417" not in blob:
            raise SystemExit("FAIL: the oldest exact fact disappeared behind ambient noise")

        native_peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        peak_bytes = native_peak if sys.platform == "darwin" else native_peak * 1024
        report = {
            "ok": True,
            "ambient_episodes": args.count,
            "stored_episodes": args.count + 2,
            "oldest_fact_recalled": True,
            "recall_seconds": round(recall_seconds, 4),
            "total_seconds": round(time.perf_counter() - started, 2),
            "database_bytes": db_path.stat().st_size,
            "peak_rss_bytes": peak_bytes,
        }
    encoded = json.dumps(report, sort_keys=True)
    print(encoded)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
