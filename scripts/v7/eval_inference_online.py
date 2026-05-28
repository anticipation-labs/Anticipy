#!/usr/bin/env python3
"""Summarize online inference receipts from current stranger runs."""

from __future__ import annotations

import json
import time
from pathlib import Path


ROOT = Path("state/strangers")
OUT = Path("state/inference_eval/online_latest.json")


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def main() -> int:
    rows = []
    for verdict_path in sorted(ROOT.glob("*/verdict.json")):
        verdict = read_json(verdict_path)
        trace = read_json(verdict_path.parent / "trace.json")
        rows.append({
            "stranger_id": verdict_path.parent.name,
            "pass": verdict.get("pass") is True,
            "verb_category": verdict.get("verb_category"),
            "hard_category": verdict.get("hard_category"),
            "changed_surfaces": (trace.get("diff") or {}).get("changed_surfaces") or [],
            "surface_receipts_present": trace.get("surface_receipts_present") is True,
        })
    result = {
        "schema": "anticipy.v7.inference_online_eval",
        "generated_at": utc_now(),
        "stranger_runs": len(rows),
        "passing_runs": sum(1 for row in rows if row["pass"]),
        "rows": rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
