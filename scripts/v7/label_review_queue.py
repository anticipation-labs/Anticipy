#!/usr/bin/env python3
"""Build a human review queue from inference examples."""

from __future__ import annotations

import json
from pathlib import Path


DATASET = Path("state/inference_dataset/synthetic_wants.jsonl")
OUT = Path("state/inference_dataset/review_queue.jsonl")


def main() -> int:
    rows = []
    for line in DATASET.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        needs_review = item.get("risk_tier", 0) >= 3 or item.get("gold_action_or_decline") == "decline"
        if needs_review:
            rows.append({
                "id": item["id"],
                "text": item["text"],
                "risk_tier": item["risk_tier"],
                "gold_action_or_decline": item["gold_action_or_decline"],
                "review_reason": "high_risk_or_decline_boundary",
            })
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    print(json.dumps({"ok": True, "path": str(OUT), "review_items": len(rows)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
