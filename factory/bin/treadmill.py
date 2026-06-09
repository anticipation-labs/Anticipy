#!/usr/bin/env python
"""Dead-lap detector. Halts the loop and writes ESCALATION.md when the Factory grinds.

Triggers (any):
  a) treadmill_count >= K consecutive laps with no metric movement and no gate closure
  b) the same intended_metric attempted >= T times in a row with no movement
  c) spend_since_movement > week_budget/2

On trigger: write factory/ESCALATION.md (STATUS: OPEN), touch factory/.halt, exit 2.
The loop refuses to run while an OPEN escalation exists; the foreman resolves it by
re-aiming TARGET.md and archiving the escalation.
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RATCHET = REPO / "logs/factory/RATCHET.json"
SB = REPO / "logs/factory/product_scoreboard.csv"
ESC = REPO / "factory/ESCALATION.md"
HALT = REPO / "factory/.halt"


def conf(key: str, default: str) -> str:
    if os.environ.get(key):
        return os.environ[key]
    for line in (REPO / "factory/config/factory.conf").read_text().splitlines():
        line = line.strip()
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1]
    return default


def main() -> int:
    k = int(conf("TREADMILL_K", "5"))
    same_tries = int(conf("TREADMILL_SAME_METRIC_TRIES", "3"))
    ratchet = json.loads(RATCHET.read_text()) if RATCHET.exists() else {}
    budget = json.loads((REPO / "factory/config/budget.json").read_text())
    count = int(ratchet.get("treadmill_count", 0))
    spend_since = float(ratchet.get("spend_since_movement", 0.0))

    rows = []
    if SB.exists():
        with SB.open() as f:
            rows = list(csv.DictReader(f))
    tail = rows[-max(k, same_tries):]

    trigger = None
    if count >= k:
        trigger = f"{count} consecutive laps with no metric movement and no gate closure (K={k})"
    elif len(tail) >= same_tries:
        metrics = [r.get("intended_metric", "") for r in tail[-same_tries:]]
        moved = [r.get("metric_moved", "none") for r in tail[-same_tries:]]
        if len(set(metrics)) == 1 and metrics[0] and all(m == "none" for m in moved):
            trigger = f"same intended_metric '{metrics[0]}' attempted {same_tries}x with no movement"
    if trigger is None and spend_since > float(budget.get("week_usd", 200)) / 2:
        trigger = f"${spend_since:.2f} spent since last movement (> half the weekly envelope)"

    if trigger is None:
        print(json.dumps({"treadmill": "ok", "count": count}))
        return 0

    lap_lines = "\n".join(
        f"- {r['lap']}: intended={r.get('intended_metric','')} moved={r.get('metric_moved','')} "
        f"kept={r.get('kept','')} notes={r.get('notes','')[:120]}"
        for r in tail)
    ESC.write_text(f"""# ESCALATION {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}        STATUS: OPEN

trigger: {trigger}
treadmill_count: {count}
spend_since_last_movement_usd: {spend_since:.2f}

recent laps:
{lap_lines}

What the foreman must do:
1. Read the recent lap dirs under logs/factory/laps/ and the per-persona breakdowns
   in logs/factory/runs/<lap>/.
2. Diagnose the bottleneck (write it here under 'bottleneck_hypothesis:').
3. Pick a strategy change and re-aim by editing factory/TARGET.md (bump the version).
   Lowering a threshold honestly (with rationale) is allowed; silently shrinking the
   goal is not.
4. Set STATUS: RESOLVED above, move this file to logs/factory/ESCALATIONS/, rm factory/.halt.

bottleneck_hypothesis: (foreman fills in)
options: (foreman fills in)
""", encoding="utf-8")
    HALT.touch()
    print(json.dumps({"treadmill": "HALT", "trigger": trigger, "escalation": str(ESC)}))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
