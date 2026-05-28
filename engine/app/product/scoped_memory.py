"""Account/device scoped product memory (V7 canonical wrapper).

The frozen `app.anticipy.memory` uses a static USER_ID and is not
account/device scoped. Per plan section 6, every memory item must carry
account_id, device_id, source, timestamp, confidence, kind, active,
provenance. This module is the WRITE/READ surface for product flows.

Storage: ~/.anticipy/v7/memory/<account_id>/<device_id>/memory.jsonl
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

_LOCK = threading.Lock()

KIND_PERSON = "person"
KIND_PREFERENCE = "preference"
KIND_ALIAS = "alias"
KIND_DO_NOT_TOUCH = "do_not_touch"
KIND_RECIPE = "recipe"
KIND_ACTION_OUTCOME = "action_outcome"
KIND_FACT = "fact"
KIND_LATENT_INTENT = "latent_intent"

CONFIDENCE_RESOLVE_FLOOR = 0.70

_PRONOUN_GENDER = {
    "she": "f", "her": "f", "hers": "f",
    "he": "m", "him": "m", "his": "m",
    "they": "n", "them": "n", "their": "n", "theirs": "n",
}


def _root() -> Path:
    raw = os.environ.get("ANTICIPY_V7_MEMORY_ROOT", "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".anticipy" / "v7" / "memory"


def _safe_id(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return "unknown"
    return (re.sub(r"[^A-Za-z0-9._-]+", "_", s) or "unknown")[:128]


@dataclass
class MemoryItem:
    item_id: str
    account_id: str
    device_id: str
    kind: str
    key: str
    value: str
    source: str
    provenance: str
    timestamp: float
    confidence: float = 1.0
    active: bool = True
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "account_id": self.account_id,
            "device_id": self.device_id,
            "kind": self.kind,
            "key": self.key,
            "value": self.value,
            "source": self.source,
            "provenance": self.provenance,
            "timestamp": self.timestamp,
            "confidence": float(self.confidence),
            "active": bool(self.active),
            "extra": dict(self.extra or {}),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "MemoryItem":
        return cls(
            item_id=str(d.get("item_id") or ""),
            account_id=str(d.get("account_id") or ""),
            device_id=str(d.get("device_id") or ""),
            kind=str(d.get("kind") or ""),
            key=str(d.get("key") or ""),
            value=str(d.get("value") or ""),
            source=str(d.get("source") or "unknown"),
            provenance=str(d.get("provenance") or "unknown"),
            timestamp=float(d.get("timestamp") or 0.0),
            confidence=float(d.get("confidence") or 1.0),
            active=bool(d.get("active", True)),
            extra=dict(d.get("extra") or {}),
        )


class ScopedMemory:
    """Account/device scoped product memory. Cheap to construct."""

    def __init__(self, account_id: str, device_id: str) -> None:
        self.account_id = _safe_id(account_id)
        self.device_id = _safe_id(device_id)
        self._dir = _root() / self.account_id / self.device_id
        self._path = self._dir / "memory.jsonl"

    @property
    def path(self) -> Path:
        return self._path

    @property
    def dir(self) -> Path:
        return self._dir

    def _ensure_dir(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)

    def _read_all(self) -> list[MemoryItem]:
        if not self._path.exists():
            return []
        out: list[MemoryItem] = []
        try:
            for line in self._path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(MemoryItem.from_dict(json.loads(line)))
                except Exception:
                    continue
        except Exception:
            return []
        return out

    def _write_all(self, items: list[MemoryItem]) -> None:
        self._ensure_dir()
        tmp = self._path.with_suffix(".jsonl.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            for it in items:
                fh.write(json.dumps(it.to_dict(), ensure_ascii=False) + "\n")
        os.replace(tmp, self._path)

    def _append(self, item: MemoryItem) -> None:
        self._ensure_dir()
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(item.to_dict(), ensure_ascii=False) + "\n")

    def write(
        self,
        *,
        kind: str,
        key: str,
        value: str,
        source: str = "product_runtime",
        provenance: str = "direct_write",
        confidence: float = 1.0,
        extra: Optional[dict[str, Any]] = None,
        dedupe: bool = True,
    ) -> MemoryItem:
        """Write a memory item; dedupe replaces prior active item with
        the same (kind, key)."""
        item = MemoryItem(
            item_id=f"v7-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}",
            account_id=self.account_id,
            device_id=self.device_id,
            kind=str(kind),
            key=str(key)[:200],
            value=str(value),
            source=str(source),
            provenance=str(provenance),
            timestamp=time.time(),
            confidence=float(confidence),
            active=True,
            extra=dict(extra or {}),
        )
        with _LOCK:
            if dedupe:
                items = self._read_all()
                changed = False
                for existing in items:
                    if (
                        existing.active
                        and existing.kind == item.kind
                        and existing.key.lower() == item.key.lower()
                    ):
                        existing.active = False
                        changed = True
                if changed:
                    items.append(item)
                    self._write_all(items)
                else:
                    self._append(item)
            else:
                self._append(item)
        return item

    def read(
        self,
        *,
        kind: Optional[str] = None,
        active_only: bool = True,
        key: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        with _LOCK:
            items = self._read_all()
        out: list[dict[str, Any]] = []
        for it in items:
            if active_only and not it.active:
                continue
            if kind and it.kind != kind:
                continue
            if key and it.key.lower() != key.lower():
                continue
            out.append(it.to_dict())
        return out

    def resolve_person(self, hint: str) -> Optional[dict[str, Any]]:
        """Most recent active person whose name/value/alias matches."""
        h = (hint or "").strip().lower()
        if not h:
            return None
        with _LOCK:
            items = self._read_all()
        # Person direct match.
        hits = [
            it for it in items
            if it.active and it.kind == KIND_PERSON
            and (h == it.key.lower() or h in it.value.lower())
        ]
        if hits:
            hits.sort(key=lambda x: (x.confidence, x.timestamp), reverse=True)
            return hits[0].to_dict()
        # Alias -> person.
        for it in items:
            if not it.active or it.kind != KIND_ALIAS or h != it.key.lower():
                continue
            target = (it.value or "").strip().lower()
            for p in items:
                if (p.active and p.kind == KIND_PERSON
                        and p.key.lower() == target):
                    return p.to_dict()
        return None

    def resolve_alias(
        self, alias: str, *, context_people: Optional[list[str]] = None
    ) -> Optional[dict[str, Any]]:
        """Resolve stored alias or pronoun. Returns None when ambiguous
        so the caller ASKs rather than guesses."""
        a = (alias or "").strip().lower()
        if not a:
            return None
        with _LOCK:
            items = self._read_all()
        # Stored alias wins.
        for it in items:
            if not it.active or it.kind != KIND_ALIAS or a != it.key.lower():
                continue
            target = (it.value or "").strip().lower()
            for p in items:
                if (p.active and p.kind == KIND_PERSON
                        and p.key.lower() == target):
                    return p.to_dict()
        # Pronoun handling.
        gender = _PRONOUN_GENDER.get(a)
        if not gender:
            return None
        ctx = {n.strip().lower() for n in (context_people or []) if n}
        candidates: list[MemoryItem] = []
        for it in items:
            if not it.active or it.kind != KIND_PERSON:
                continue
            pg = str((it.extra or {}).get("gender") or "").strip().lower()
            if gender != "n" and pg and pg != gender:
                continue
            if ctx and it.key.lower() not in ctx:
                continue
            candidates.append(it)
        if len(candidates) == 1:
            return candidates[0].to_dict()
        return None

    def is_do_not_touch(self, surface_or_recipient: str) -> bool:
        needle = (surface_or_recipient or "").strip().lower()
        if not needle:
            return False
        with _LOCK:
            items = self._read_all()
        for it in items:
            if not it.active or it.kind != KIND_DO_NOT_TOUCH:
                continue
            k, v = it.key.lower(), it.value.lower()
            if (
                needle == k or needle == v
                or needle in k or needle in v
                or k in needle or v in needle
            ):
                return True
        return False

    def record_recipe(
        self,
        *,
        name: str,
        steps: list[dict[str, Any]],
        surfaces: Optional[list[str]] = None,
        source: str = "learned",
    ) -> MemoryItem:
        extra = {"steps": list(steps or []),
                 "surfaces": list(surfaces or [])}
        return self.write(
            kind=KIND_RECIPE, key=name,
            value=json.dumps(extra, ensure_ascii=False),
            source=source, provenance="recipe_save", extra=extra,
        )

    def recall_recipe(self, name: str) -> Optional[dict[str, Any]]:
        n = (name or "").strip().lower()
        if not n:
            return None
        with _LOCK:
            items = self._read_all()
        hits = [it for it in items if it.active
                and it.kind == KIND_RECIPE and it.key.lower() == n]
        if not hits:
            return None
        hits.sort(key=lambda x: x.timestamp, reverse=True)
        return hits[0].to_dict()

    def record_action_outcome(
        self,
        *,
        action_id: str,
        status: str,
        surface: str,
        notes: str = "",
        provenance: str = "action_engine",
    ) -> MemoryItem:
        return self.write(
            kind=KIND_ACTION_OUTCOME, key=str(action_id), value=str(status),
            source="action_dispatcher", provenance=provenance,
            extra={"surface": str(surface), "notes": str(notes)},
            dedupe=False,
        )

    def diag(self) -> dict[str, Any]:
        with _LOCK:
            items = self._read_all()
        per_kind: dict[str, int] = {}
        active = 0
        for it in items:
            per_kind[it.kind] = per_kind.get(it.kind, 0) + 1
            if it.active:
                active += 1
        return {
            "account_id": self.account_id,
            "device_id": self.device_id,
            "path": str(self._path),
            "exists": self._path.exists(),
            "total_items": len(items),
            "active_items": active,
            "per_kind": per_kind,
        }
