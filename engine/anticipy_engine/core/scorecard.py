"""The scorecard — health, from day one.

Records, per proactive decision and per goal: what was decided, the outcome, the
model cost, and timing. Provides a simple readout (counts and rates) so quality
is measured, not guessed. Local JSONL.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from .envelopes import now_ts


class Scorecard:
    def __init__(self, path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)

    def _append(self, row: dict) -> None:
        with self.path.open("a") as fh:
            fh.write(json.dumps(row) + "\n")

    def record_decision(self, decision: str, event_id: str, reason: str = "") -> None:
        self._append({"ts": now_ts(), "kind": "decision", "decision": decision, "event_id": event_id})

    def record_goal(self, goal_id: str, outcome: str, cost: float) -> None:
        self._append({"ts": now_ts(), "kind": "goal", "goal_id": goal_id, "outcome": outcome, "cost": cost})

    def rows(self) -> list:
        return [json.loads(ln) for ln in self.path.read_text().splitlines() if ln.strip()]

    def readout(self) -> dict:
        rows = self.rows()
        decisions = Counter(r["decision"] for r in rows if r["kind"] == "decision")
        outcomes = Counter(r["outcome"] for r in rows if r["kind"] == "goal")
        total_cost = round(sum(r.get("cost", 0.0) for r in rows if r["kind"] == "goal"), 6)
        goals = outcomes.total() if hasattr(outcomes, "total") else sum(outcomes.values())
        return {
            "decisions": dict(decisions),
            "goal_outcomes": dict(outcomes),
            "goals": goals,
            "total_model_cost": total_cost,
        }
