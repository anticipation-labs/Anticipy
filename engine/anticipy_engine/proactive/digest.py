"""NF10 — the ONE daily digest (the calm one-report-a-day, anti-spam feel).

A non-urgent proactive item that exceeds the real-time interrupt budget (NF8/NF9) must NOT be
dropped and must NOT be spammed: it accumulates here and is delivered as a SINGLE end-of-day
report ("Here's what I caught today."), drawing ZERO interrupt budget. The digest holds only
already-DECIDED, PAUSED (never-executed) asks — it executes nothing, sends nothing itself, and a
DECLINED action-type never lands here (the user said no — it stays dropped, the caller's job).

Pure + deterministic: accumulate, compose one human message, deliver-once (clears). Optional JSON
persistence so an engine restart doesn't lose the day's deferred items (same pattern as the
proactive deferred/pending queues). No path (the default) = pure in-memory, no IO.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import List, Optional, Union

_HEADER = "Here's what I caught today."
_QUIET = "Quiet day — nothing else needed you."
# light cleanup so the digest reads as the user's day, not raw engine text — never machinery.
_PREFIXES = ("remind me to ", "i need to ", "i have to ", "i should ", "can you ", "could you ",
             "please ", "don't forget to ", "make sure to ")


def _humanize(text: str) -> str:
    t = " ".join((text or "").split()).strip()
    low = t.lower()
    for p in _PREFIXES:
        if low.startswith(p):
            t = t[len(p):]
            break
    return (t[:1].upper() + t[1:]) if t else t


class DigestQueue:
    def __init__(self, path: Optional[Union[str, Path]] = None) -> None:
        self._path = Path(path) if path else None
        self._items: List[dict] = []
        if self._path is not None:
            self._restore()

    def defer(self, action: str, reason: str = "", category: str = "",
              ts: Optional[float] = None) -> None:
        """Park a non-urgent, budget-suppressed ask for the daily digest. De-dupes identical
        actions so a repeated ambient line never stacks the digest."""
        action = (action or "").strip()
        if not action:
            return
        if any(it.get("action", "").strip().lower() == action.lower() for it in self._items):
            return
        self._items.append({"action": action, "reason": (reason or "").strip(),
                            "category": category or "", "ts": ts if ts is not None else time.time()})
        self._persist()

    def count(self) -> int:
        return len(self._items)

    def pending(self) -> List[dict]:
        return list(self._items)

    def build(self) -> Optional[str]:
        """Compose ONE human message from the queued items (or None if empty). Does NOT clear."""
        if not self._items:
            return None
        lines = [_HEADER]
        for it in self._items:
            lines.append("• " + _humanize(it.get("action", "")))
        return "\n".join(lines)

    def deliver(self) -> Optional[str]:
        """Build the digest and CLEAR the queue (deliver-once semantics). Returns the message,
        or None when there was nothing to say (the caller sends nothing — a quiet day stays quiet)."""
        msg = self.build()
        self._items = []
        self._persist()
        return msg

    # ---- persistence (optional; mirrors the proactive deferred/pending queues) ----
    def _persist(self) -> None:
        if self._path is None:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(self._items))
        except OSError:
            pass

    def _restore(self) -> None:
        try:
            if self._path and self._path.exists():
                data = json.loads(self._path.read_text())
                self._items = data if isinstance(data, list) else []
        except (OSError, ValueError):
            self._items = []
