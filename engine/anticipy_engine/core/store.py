"""Goal persistence — local JSON, one file per goal.

Goals survive a restart so the orchestrator can resume long-running work (the
follow-through-over-days mechanism). Local only; default dir honors
ANTICIPY_DATA_DIR.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

from .envelopes import Goal, GoalState


def _default_base() -> Path:
    return Path(os.environ.get("ANTICIPY_DATA_DIR", ".anticipy-data")).expanduser()


class GoalStore:
    def __init__(self, data_dir: Optional[Path] = None) -> None:
        base = Path(data_dir) if data_dir else _default_base()
        self.dir = base / "goals"
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, goal_id: str) -> Path:
        return self.dir / f"{goal_id}.json"

    def save(self, goal: Goal) -> None:
        goal.touch()
        self._path(goal.id).write_text(goal.model_dump_json(indent=2))

    def load(self, goal_id: str) -> Optional[Goal]:
        p = self._path(goal_id)
        return Goal.model_validate_json(p.read_text()) if p.exists() else None

    def all(self) -> List[Goal]:
        return [Goal.model_validate_json(p.read_text()) for p in sorted(self.dir.glob("*.json"))]

    def waiting(self) -> List[Goal]:
        return [g for g in self.all() if g.state == GoalState.waiting]
