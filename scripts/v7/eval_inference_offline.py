#!/usr/bin/env python3
"""Exercise the V7 structured want-inference contracts offline."""

from __future__ import annotations

import json
import time
from pathlib import Path


CONTRACTS = [
    Path("contracts/INFERENCE.md"),
    Path("contracts/WANT_SCHEMA.json"),
    Path("contracts/ACTION_SCHEMA.json"),
    Path("contracts/RISK_TIERS.md"),
    Path("contracts/ANNOTATION_GUIDE.md"),
    Path("contracts/DATA_BOOTSTRAP.md"),
]
DATASET = Path("state/inference_dataset/synthetic_wants.jsonl")
CALIBRATION = Path("state/inference_eval/calibration.json")
OUT = Path("state/inference_eval/offline_latest.json")
CHECK_DONE_OUT = Path("state/v7/inference_eval.json")


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def baseline_decision(row: dict) -> str:
    flags = row.get("flags") or {}
    if any(flags.get(key) for key in ("quoted_speech", "media_reference", "joke", "hypothetical", "third_party", "already_satisfied")):
        return "silent_decline"
    if row.get("known_surface_exists") is False and row.get("risk_tier", 0) >= 3:
        return "decline"
    if row.get("missing_slots"):
        return "ask_first"
    if row.get("risk_tier", 0) <= 1:
        return "silent_execute"
    return "execute_notify"


def main() -> int:
    missing_contracts = [str(path) for path in CONTRACTS if not path.exists()]
    rows = [json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines() if line.strip()] if DATASET.exists() else []
    correct = 0
    results = []
    for row in rows:
        predicted = baseline_decision(row)
        gold = row.get("gold_action_or_decline")
        ok = predicted == gold
        correct += int(ok)
        results.append({"id": row.get("id"), "predicted": predicted, "gold": gold, "pass": ok})
    accuracy = correct / len(rows) if rows else 0.0
    result = {
        "schema": "anticipy.v7.inference_offline_eval",
        "generated_at": utc_now(),
        "contracts_present": not missing_contracts,
        "missing_contracts": missing_contracts,
        "dataset_path": str(DATASET),
        "calibration_path": str(CALIBRATION),
        "examples": len(rows),
        "accuracy": round(accuracy, 6),
        "pass": not missing_contracts and len(rows) >= 5 and accuracy >= 0.8,
        "results": results,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    check_done = {
        "schema": "anticipy.v7.inference_eval",
        "generated_at": result["generated_at"],
        "schema_exists": not missing_contracts,
        "data_path_exists": DATASET.exists() and len(rows) >= 5,
        "eval_exercised": result["pass"],
        "offline_eval_path": str(OUT),
        "examples": len(rows),
        "accuracy": result["accuracy"],
    }
    CHECK_DONE_OUT.parent.mkdir(parents=True, exist_ok=True)
    CHECK_DONE_OUT.write_text(json.dumps(check_done, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(check_done, indent=2, sort_keys=True))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
