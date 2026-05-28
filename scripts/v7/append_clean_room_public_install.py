#!/usr/bin/env python3
"""Append a run manifest to the aggregate V7 clean-room proof file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_manifest")
    parser.add_argument(
        "--aggregate",
        default="state/v7/clean_room_public_install.json",
    )
    args = parser.parse_args()

    run_path = Path(args.run_manifest)
    aggregate_path = Path(args.aggregate)
    run = json.loads(run_path.read_text())
    if aggregate_path.exists():
        aggregate = json.loads(aggregate_path.read_text())
    else:
        aggregate = {
            "schema": "anticipy.clean_room_public_install.v7",
            "runs": [],
        }

    runs = [r for r in aggregate.get("runs", []) if r.get("run_id") != run.get("run_id")]
    runs.append(run)
    aggregate["runs"] = runs
    aggregate_path.parent.mkdir(parents=True, exist_ok=True)
    aggregate_path.write_text(json.dumps(aggregate, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"ok": True, "aggregate": str(aggregate_path), "runs": len(runs)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
