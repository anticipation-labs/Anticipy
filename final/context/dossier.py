"""final/context/dossier.py — the per-person dossier (deliverable c).

Grafted from DEV-FINAL ``engine/app/product/dossier_active_loader.py`` (Person /
pronoun_map / do_not_touch), adapted to sit on the devin memory drawers instead of
a JSON file on disk. The profile drawer accrues person facts ("Sam Rivera is my
lawyer", "Sam Chen is my little brother") that the context engine writes; the
``PersonBook`` reads them back as typed ``Person`` records so a bare "email Sam"
either resolves to the ONE Sam or, when two people share the name, asks which —
never silently guesses the wrong person.

Why records and not flat strings: two Sams are indistinguishable as strings. A
``Person`` carries name + role + pronouns, so disambiguation is a real decision
(one match -> resolve; many -> ask the smallest clarification).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

_PRONOUN_GENDER = {
    "she": "f", "her": "f", "hers": "f", "herself": "f",
    "he": "m", "him": "m", "his": "m", "himself": "m",
    "they": "n", "them": "n", "their": "n", "theirs": "n", "themself": "n",
}

# a title we should not treat as the person's first name when disambiguating
_TITLES = {"dr", "dr.", "mr", "mr.", "mrs", "mrs.", "ms", "ms.", "prof", "prof."}


@dataclass
class Person:
    name: str
    role: str = ""
    email: str = ""
    pronouns: str = ""
    aliases: list[str] = field(default_factory=list)
    last_mentioned: float = 0.0

    def first_name(self) -> str:
        parts = [p for p in re.split(r"\s+", self.name.strip()) if p]
        for p in parts:
            if p.lower().strip(".") not in {t.strip(".") for t in _TITLES}:
                return p
        return parts[0] if parts else self.name

    def gender_hint(self) -> str:
        p = (self.pronouns or "").lower()
        if "she" in p or "her" in p:
            return "f"
        if "he" in p or "him" in p:
            return "m"
        if "they" in p or "them" in p:
            return "n"
        return ""

    def label(self) -> str:
        return f"{self.name} ({self.role})" if self.role else self.name

    def to_dict(self) -> dict:
        return {"name": self.name, "role": self.role, "email": self.email,
                "pronouns": self.pronouns, "aliases": list(self.aliases),
                "last_mentioned": float(self.last_mentioned)}


@dataclass
class DoNotTouchRule:
    pattern: str
    reason: str = ""

    def matches(self, target: str) -> bool:
        t = (target or "").strip().lower()
        p = (self.pattern or "").strip().lower()
        if not t or not p:
            return False
        if t == p or p in t or t in p:
            return True
        toks = [x for x in re.split(r"[^a-z0-9]+", p) if x]
        return bool(toks) and all(tok in t for tok in toks)


class PersonBook:
    """The per-person dossier assembled from the profile drawer's person facts."""

    def __init__(self, memory) -> None:
        self.memory = memory

    def people(self) -> list[Person]:
        out: list[Person] = []
        try:
            items = self.memory.profile.all()
        except Exception:
            return out
        for it in items:
            f = getattr(it, "fields", None) or {}
            if f.get("ctype") != "person":
                continue
            name = str(f.get("cname") or "").strip()
            if not name:
                continue
            out.append(Person(
                name=name, role=str(f.get("crole") or "").strip(),
                email=str(f.get("cemail") or "").strip(),
                pronouns=str(f.get("cpronouns") or "").strip(),
                last_mentioned=float(getattr(it, "timestamp", 0.0) or 0.0),
            ))
        return out

    def do_not_touch(self) -> list[DoNotTouchRule]:
        out: list[DoNotTouchRule] = []
        try:
            items = self.memory.profile.all()
        except Exception:
            return out
        for it in items:
            f = getattr(it, "fields", None) or {}
            if f.get("ctype") != "do_not_touch":
                continue
            pat = str(f.get("cvalue") or f.get("ckey") or "").strip()
            if pat:
                out.append(DoNotTouchRule(pattern=pat, reason=str(f.get("creason") or "")))
        return out

    def is_blocked(self, target: str) -> tuple[bool, Optional[DoNotTouchRule]]:
        for rule in self.do_not_touch():
            if rule.matches(target):
                return True, rule
        return False, None

    def pronoun_map(self) -> dict[str, str]:
        """Pronoun -> person name, biased toward the most-recently-mentioned."""
        out: dict[str, str] = {}
        people = sorted(self.people(), key=lambda p: p.last_mentioned, reverse=True)
        for pronoun, gender in _PRONOUN_GENDER.items():
            if pronoun in out:
                continue
            for person in people:
                ph = person.gender_hint()
                if not ph:
                    continue
                if gender == "n" and ph != "n":
                    continue
                if gender != "n" and ph != gender:
                    continue
                out[pronoun] = person.name
                break
        return out

    def resolve_name(self, text: str) -> tuple[Optional[Person], list[Person]]:
        """Resolve a person reference inside ``text``.

        Returns ``(person, candidates)``:
          - exactly one match  -> (that Person, [])            resolve it
          - two+ share a name  -> (None, [candidates])         ASK which one
          - no match           -> (None, [])                   leave it alone
        A full-name mention ("Sam Rivera") always wins over a bare first name.
        """
        people = self.people()
        if not people:
            return None, []
        words = set(re.findall(r"[a-z][a-z'.-]+", (text or "").lower()))
        # 1) full-name (or alias) mention is unambiguous
        for p in people:
            full = p.name.lower()
            if full and full in (text or "").lower():
                return p, []
            for a in p.aliases:
                if a and a.lower() in (text or "").lower():
                    return p, []
        # 2) first-name match; group people who share it
        by_first: dict[str, list[Person]] = {}
        for p in people:
            fn = p.first_name().lower().strip(".")
            if fn and fn in words:
                by_first.setdefault(fn, []).append(p)
        if not by_first:
            return None, []
        # pick the first-name token that actually appears; prefer a lone match
        for fn, group in by_first.items():
            if len(group) == 1:
                return group[0], []
        # every matched first name is shared -> ambiguous; return the largest group
        biggest = max(by_first.values(), key=len)
        return None, sorted(biggest, key=lambda p: p.last_mentioned, reverse=True)


__all__ = ["Person", "DoNotTouchRule", "PersonBook"]
