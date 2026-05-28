#!/usr/bin/env python3
"""Audit V6 runtime cost projection from stranger cost receipts."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


STATE = Path("state")
CEILING_PER_TASK = 0.002
TASKS_PER_YEAR = 100_000


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def extract_cost(data: Any) -> float | None:
    if not isinstance(data, dict):
        return None
    if not isinstance(data.get("calls"), list):
        return None
    for key in ("total_usd", "cost_usd", "runtime_cost_usd"):
        value = data.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    calls = data.get("calls")
    if isinstance(calls, list):
        total = 0.0
        seen = False
        for row in calls:
            if isinstance(row, dict) and isinstance(row.get("cost_usd"), (int, float)):
                total += float(row["cost_usd"])
                seen = True
        if seen:
            return total
    return None


def main() -> int:
    costs: list[float] = []
    for path in sorted((STATE / "strangers").glob("*/cost_breakdown.json"), key=lambda p: p.stat().st_mtime)[-20:]:
        cost = extract_cost(read_json(path))
        if cost is not None:
            costs.append(cost)
    if not costs:
        result = {
            "verdict": "no_data",
            "reason": "no stranger cost_breakdown.json files with runtime cost",
            "ceiling_per_task_usd": CEILING_PER_TASK,
        }
        code = 2
    else:
        per_task = sum(costs) / len(costs)
        projected = per_task * TASKS_PER_YEAR
        result = {
            "verdict": "pass" if per_task <= CEILING_PER_TASK else "fail",
            "sample_count": len(costs),
            "per_task_usd": round(per_task, 8),
            "projected_yearly_per_user_usd": round(projected, 2),
            "ceiling_yearly_usd": CEILING_PER_TASK * TASKS_PER_YEAR,
        }
        code = 0 if result["verdict"] == "pass" else 1
        if code == 1:
            out_dir = STATE / "cost-overruns"
            out_dir.mkdir(parents=True, exist_ok=True)
            ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
            (out_dir / f"{ts}.md").write_text(json.dumps(result, indent=2), encoding="utf-8")
    STATE.mkdir(exist_ok=True)
    (STATE / "last_v6_cost_audit.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
