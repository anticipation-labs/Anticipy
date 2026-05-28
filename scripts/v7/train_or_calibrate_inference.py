#!/usr/bin/env python3
"""Calibrate a deterministic baseline for the V7 want-inference eval."""

from __future__ import annotations

import json
from pathlib import Path


DATASET = Path("state/inference_dataset/synthetic_wants.jsonl")
OUT = Path("state/inference_eval/calibration.json")


def main() -> int:
    rows = [json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines() if line.strip()]
    positives = sum(1 for row in rows if row.get("contains_actionable_want") is True)
    negatives = len(rows) - positives
    calibration = {
        "schema": "anticipy.v7.inference_calibration",
        "examples": len(rows),
        "positives": positives,
        "negatives": negatives,
        "actionable_threshold": 0.65,
        "ask_threshold": 0.5,
        "decline_when_surface_missing": True,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(calibration, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(calibration, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
