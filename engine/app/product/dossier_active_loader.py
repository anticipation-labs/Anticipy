"""V7 dossier active loader.

Per plan section 6: loads the onboarding dossier into inference. Wraps
the frozen ``app.anticipy.memory`` without editing it. Exposes people,
preferences, do_not_touch rules, pronoun_map, recent_topics, and an
``as_context_block`` that the action planner prepends to its prompt.

Paths (priority): ``~/.anticipy/v7/dossiers/<account_id>/dossier.json``,
``~/.anticipy/v7/dossier.json``, ``~/.anticipy/dossier.json``. Test
override: ``ANTICIPY_V7_DOSSIER_ROOT``.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

_LOCK = threading.Lock()

_PRONOUN_GENDER = {
    "she": "f", "her": "f", "hers": "f", "herself": "f",
    "he": "m", "him": "m", "his": "m", "himself": "m",
    "they": "n", "them": "n", "their": "n", "theirs": "n", "themself": "n",
}

_RECENT_DAYS_DEFAULT = 7


def _safe_id(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return "default"
    return (re.sub(r"[^A-Za-z0-9._-]+", "_", s) or "default")[:128]


def _dossier_root() -> Path:
    raw = os.environ.get("ANTICIPY_V7_DOSSIER_ROOT", "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".anticipy" / "v7" / "dossiers"


def _candidate_paths(account_id: str) -> list[Path]:
    root = _dossier_root()
    cands: list[Path] = []
    if account_id:
        cands.append(root / _safe_id(account_id) / "dossier.json")
    cands.append(root / "dossier.json")
    cands.append(Path.home() / ".anticipy" / "v7" / "dossier.json")
    cands.append(Path.home() / ".anticipy" / "dossier.json")
    return cands


@dataclass
class Person:
    name: str
    role: str = ""
    email: str = ""
    pronouns: str = ""
    aliases: list[str] = field(default_factory=list)
    last_mentioned: float = 0.0
    tags: list[str] = field(default_factory=list)

    def gender_hint(self) -> str:
        p = (self.pronouns or "").lower()
        if "she" in p or "her" in p:
            return "f"
        if "he" in p or "him" in p:
            return "m"
        if "they" in p or "them" in p:
            return "n"
        return ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "role": self.role, "email": self.email,
            "pronouns": self.pronouns, "aliases": list(self.aliases),
            "last_mentioned": float(self.last_mentioned),
            "tags": list(self.tags),
        }


@dataclass
class DoNotTouchRule:
    pattern: str
    reason: str = ""
    surfaces: list[str] = field(default_factory=list)

    def matches(self, target: str) -> bool:
        t = (target or "").strip().lower()
        p = (self.pattern or "").strip().lower()
        if not t or not p:
            return False
        if t == p or p in t or t in p:
            return True
        toks = [x for x in re.split(r"[^a-z0-9]+", p) if x]
        if toks and all(tok in t for tok in toks):
            return True
        return False

    def to_dict(self) -> dict[str, Any]:
        return {"pattern": self.pattern, "reason": self.reason,
                "surfaces": list(self.surfaces)}


def _parse_person(entry: Any) -> Optional[Person]:
    if isinstance(entry, str):
        return Person(name=entry)
    if not isinstance(entry, dict):
        return None
    name = str(entry.get("name") or "").strip()
    if not name:
        return None
    aliases = entry.get("aliases") or []
    if isinstance(aliases, str):
        aliases = [aliases]
    tags = entry.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    try:
        lm = float(entry.get("last_mentioned") or 0.0)
    except Exception:
        lm = 0.0
    return Person(
        name=name, role=str(entry.get("role") or ""),
        email=str(entry.get("email") or ""),
        pronouns=str(entry.get("pronouns") or ""),
        aliases=[str(a) for a in aliases if a], last_mentioned=lm,
        tags=[str(t) for t in tags if t],
    )


class DossierLoader:
    """Cheap to construct. Loads on init, caches in memory, refresh on call."""

    def __init__(self, account_id: str, device_id: str = "") -> None:
        self.account_id = _safe_id(account_id)
        self.device_id = _safe_id(device_id) if device_id else ""
        self._raw: dict[str, Any] = {}
        self._path: Optional[Path] = None
        self._loaded_at: float = 0.0
        self.refresh()

    @property
    def loaded_path(self) -> Optional[Path]:
        return self._path

    def refresh(self) -> bool:
        """Re-read the dossier from disk. Returns True on success."""
        with _LOCK:
            for p in _candidate_paths(self.account_id):
                if p.exists() and p.is_file():
                    try:
                        raw = json.loads(p.read_text(encoding="utf-8") or "{}")
                        if isinstance(raw, dict):
                            self._raw = raw
                            self._path = p
                            self._loaded_at = time.time()
                            return True
                    except Exception:
                        continue
            self._raw = {}
            self._path = None
            self._loaded_at = time.time()
            return False

    def people(self) -> list[Person]:
        out: list[Person] = []
        raw_people = self._raw.get("people")
        if isinstance(raw_people, dict):
            for role, name in raw_people.items():
                if name:
                    out.append(Person(name=str(name), role=str(role)))
        elif isinstance(raw_people, list):
            for entry in raw_people:
                person = _parse_person(entry)
                if person is not None:
                    out.append(person)
        return out

    def preferences(self) -> dict[str, Any]:
        raw = self._raw.get("preferences")
        if isinstance(raw, dict):
            return dict(raw)
        comms = self._raw.get("comms_prefs")
        if isinstance(comms, dict):
            return dict(comms)
        return {}

    def do_not_touch(self) -> list[DoNotTouchRule]:
        raw = self._raw.get("do_not_touch")
        rules: list[DoNotTouchRule] = []
        if isinstance(raw, dict):
            for k, v in raw.items():
                rules.append(DoNotTouchRule(
                    pattern=str(k), reason=str(v or "")))
            return rules
        for item in (raw or []):
            if isinstance(item, str):
                rules.append(DoNotTouchRule(pattern=item))
                continue
            if not isinstance(item, dict):
                continue
            pattern = str(item.get("pattern") or item.get("key")
                          or item.get("target") or "").strip()
            if not pattern:
                continue
            surfaces = item.get("surfaces") or []
            if isinstance(surfaces, str):
                surfaces = [surfaces]
            rules.append(DoNotTouchRule(
                pattern=pattern, reason=str(item.get("reason") or ""),
                surfaces=[str(s) for s in surfaces if s]))
        return rules

    def is_blocked(self, target: str) -> tuple[bool, Optional[DoNotTouchRule]]:
        hit: Optional[DoNotTouchRule] = None
        for rule in self.do_not_touch():
            if rule.matches(target):
                hit = rule
                break
        # Resolution-trace hook (M1 R3). Best-effort: never block planner
        # because of an instrumentation failure. The recorder is in
        # app.product.server but resolves lazily so dossier_active_loader
        # stays loadable on its own.
        try:
            from app.product.server import _record_resolution
            _record_resolution({
                "kind": "blocked_check",
                "topic": (target or "")[:240],
                "blocked": bool(hit),
                "reason": (hit.reason if hit and hit.reason else
                           (hit.pattern if hit else "")),
                "pattern": hit.pattern if hit else "",
                "surfaces": list(hit.surfaces) if hit else [],
            })
        except Exception:
            pass
        if hit is not None:
            return True, hit
        return False, None

    def pronoun_map(self) -> dict[str, str]:
        """Pronoun to person name, biased toward most-recently-mentioned."""
        explicit = self._raw.get("pronoun_map") or {}
        if isinstance(explicit, dict) and explicit:
            return {str(k).lower(): str(v) for k, v in explicit.items()
                    if str(k).strip() and str(v).strip()}
        out: dict[str, str] = {}
        people = sorted(self.people(),
                        key=lambda p: p.last_mentioned, reverse=True)
        for pronoun, gender in _PRONOUN_GENDER.items():
            if pronoun in out:
                continue
            for person in people:
                ph = person.gender_hint()
                if not ph:
                    continue
                if gender != "n" and ph != gender:
                    continue
                if gender == "n" and ph != "n":
                    continue
                out[pronoun] = person.name
                break
        return out

    def recent_topics(
        self, n: int = 10, days: int = _RECENT_DAYS_DEFAULT
    ) -> list[str]:
        raw = self._raw.get("recent_topics") or self._raw.get("topics") or []
        cutoff = time.time() - (max(int(days), 1) * 86400)
        topics: list[tuple[float, str]] = []
        for item in (raw if isinstance(raw, list) else []):
            if isinstance(item, str) and item.strip():
                topics.append((time.time(), item.strip()))
                continue
            if not isinstance(item, dict):
                continue
            label = str(item.get("topic") or item.get("label") or "").strip()
            if not label:
                continue
            try:
                ts = float(item.get("ts") or item.get("last_mentioned") or 0.0)
            except Exception:
                ts = 0.0
            if ts and ts < cutoff:
                continue
            topics.append((ts or time.time(), label))
        topics.sort(key=lambda x: x[0], reverse=True)
        seen: set[str] = set()
        out: list[str] = []
        for _, label in topics:
            lo = label.lower()
            if lo in seen:
                continue
            seen.add(lo)
            out.append(label)
            if len(out) >= max(int(n), 1):
                break
        return out

    def as_context_block(self, max_chars: int = 2000) -> str:
        """Compact human-readable block the planner prepends to its prompt."""
        lines: list[str] = ["DOSSIER CONTEXT (active memory):"]
        people = sorted(self.people(),
                        key=lambda p: p.last_mentioned, reverse=True)
        if people:
            lines.append("People:")
            for p in people[:8]:
                bits = [p.name]
                if p.role:
                    bits.append(f"({p.role})")
                if p.email:
                    bits.append(f"<{p.email}>")
                if p.pronouns:
                    bits.append(f"pronouns={p.pronouns}")
                if p.aliases:
                    bits.append("aka " + ", ".join(p.aliases[:3]))
                lines.append("  - " + " ".join(bits))
        prons = self.pronoun_map()
        top = {k: v for k, v in prons.items()
               if k in ("she", "her", "he", "him", "they", "them")}
        if top:
            lines.append("Pronoun map: "
                         + ", ".join(f"{k}->{v}" for k, v in top.items()))
        prefs = self.preferences()
        if prefs:
            lines.append("Preferences:")
            for k, v in list(prefs.items())[:8]:
                lines.append(f"  - {k}: {str(v)[:80]}")
        dnts = self.do_not_touch()
        if dnts:
            lines.append("DO NOT TOUCH (hard rules, never act on these):")
            for rule in dnts[:6]:
                tail = f" ({rule.reason})" if rule.reason else ""
                lines.append(f"  - {rule.pattern}{tail}")
        topics = self.recent_topics(n=6)
        if topics:
            lines.append("Recent topics: " + ", ".join(topics))
        if len(lines) == 1:
            lines.append("(empty dossier; treat references as unresolved)")
        block = "\n".join(lines)
        if len(block) <= max_chars:
            return block
        return block[: max(max_chars - 3, 0)] + "..."

    def snapshot(self) -> dict[str, Any]:
        return {
            "account_id": self.account_id, "device_id": self.device_id,
            "path": str(self._path) if self._path else "",
            "loaded_at": self._loaded_at,
            "people": [p.to_dict() for p in self.people()],
            "preferences": self.preferences(),
            "do_not_touch": [r.to_dict() for r in self.do_not_touch()],
            "pronoun_map": self.pronoun_map(),
            "recent_topics": self.recent_topics(),
        }


__all__ = ["DossierLoader", "Person", "DoNotTouchRule"]
