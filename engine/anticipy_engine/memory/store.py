"""Local-only memory stores (read/write stubs).

One JSON file per store under the data dir. The three stores are kept separate
on disk and in the API; nothing here merges them or reasons over them — that's a
later chunk. Default data dir is ``.anticipy-data/`` (repo-local, gitignored),
overridable with ``ANTICIPY_DATA_DIR``.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List, Optional

from ..shared.schema import MemoryItem, MemoryKind


def _default_data_dir() -> Path:
    return Path(os.environ.get("ANTICIPY_DATA_DIR", ".anticipy-data")).expanduser()


class MemoryStore:
    """A single store. Holds only items of its ``kind``."""

    def __init__(self, name: str, kind: MemoryKind, data_dir: Path) -> None:
        self.name = name
        self.kind = kind
        data_dir.mkdir(parents=True, exist_ok=True)
        self.path = data_dir / f"{name}.json"
        if not self.path.exists():
            self._persist([])

    # ---- read ----
    def all(self) -> List[MemoryItem]:
        raw = json.loads(self.path.read_text() or "[]")
        return [MemoryItem(**r) for r in raw]

    def get(self, item_id: str) -> Optional[MemoryItem]:
        return next((i for i in self.all() if i.id == item_id), None)

    # ---- write ----
    def write(self, item: MemoryItem) -> MemoryItem:
        item.kind = self.kind  # stores stamp their own kind; never cross-contaminate
        items = self.all()
        items.append(item)
        self._persist([i.model_dump() for i in items])
        return item

    def write_text(self, text: str, people: Optional[List[str]] = None) -> MemoryItem:
        return self.write(MemoryItem(kind=self.kind, text=text, people=people or []))

    def clear(self) -> None:
        self._persist([])

    def _persist(self, rows: list) -> None:
        self.path.write_text(json.dumps(rows, indent=2))


class Memory:
    """Facade over the three separate stores."""

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        base = Path(data_dir) if data_dir else _default_data_dir()
        self.profile = MemoryStore("profile", "profile_fact", base)
        self.open_loops = MemoryStore("open_loops", "open_loop", base)
        self.history = MemoryStore("history", "history", base)
        self.data_dir = base
