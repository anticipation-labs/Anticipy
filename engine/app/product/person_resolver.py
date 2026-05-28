"""V7 person resolver: vague references -> Person + confidence."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from app.product.scoped_memory import KIND_ALIAS, KIND_PERSON, ScopedMemory

PRONOUN_RECENCY_SEC = 30 * 60
CONFIDENCE_FLOOR = 0.70

_PRONOUN_GENDER = {
    "she": "f", "her": "f", "hers": "f", "he": "m", "him": "m",
    "his": "m", "they": "n", "them": "n", "their": "n", "theirs": "n",
}
_NICKNAMES = {
    "mike": ["michael"], "matt": ["matthew"], "alex": ["alexander"],
    "sam": ["samuel", "samantha"], "kate": ["katherine"],
    "liz": ["elizabeth"], "bob": ["robert"], "rob": ["robert"],
    "bill": ["william"], "will": ["william"], "jim": ["james"],
    "tom": ["thomas"], "dan": ["daniel"], "chris": ["christopher"],
    "nick": ["nicholas"], "joe": ["joseph"], "tony": ["anthony"],
    "rick": ["richard"], "steve": ["stephen"], "andy": ["andrew"],
    "pete": ["peter"], "jen": ["jennifer"], "sue": ["susan"],
}


@dataclass
class Person:
    name: str
    email: str = ""
    role: str = ""
    gender: str = ""
    tags: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    last_mentioned: float = 0.0
    person_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"person_id": self.person_id or self.name,
                "name": self.name, "email": self.email, "role": self.role,
                "gender": self.gender, "tags": list(self.tags),
                "aliases": list(self.aliases),
                "last_mentioned": self.last_mentioned}


@dataclass
class Resolution:
    person: Optional[Person]
    confidence: float
    alternatives: list[Person] = field(default_factory=list)
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"person": self.person.to_dict() if self.person else None,
                "confidence": float(self.confidence),
                "alternatives": [p.to_dict() for p in self.alternatives],
                "reason": self.reason}


def _norm(s: str) -> str:
    return (s or "").strip().lower()


def _nickname_matches(ref: str, full_name: str) -> bool:
    ref = _norm(ref)
    if not ref or not full_name:
        return False
    first = _norm(full_name.split()[0])
    if not first:
        return False
    if ref == first or first in _NICKNAMES.get(ref, []):
        return True
    for nick, fulls in _NICKNAMES.items():
        if first in fulls and nick == ref:
            return True
    return False


def _person_from_dict(raw: dict[str, Any]) -> Person:
    ex = raw.get("extra") or {}
    g = lambda k: raw.get(k) or ex.get(k) or ""  # noqa: E731
    name = str(raw.get("name") or raw.get("key") or "")
    tags = g("tags")
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    return Person(
        name=name,
        email=str(g("email") or raw.get("value") or ""),
        role=str(g("role")), gender=str(g("gender")).lower(),
        tags=[str(t).lower() for t in (tags or [])],
        aliases=[str(a) for a in (g("aliases") or [])],
        last_mentioned=float(raw.get("last_mentioned")
                             or raw.get("timestamp") or 0.0),
        person_id=str(raw.get("person_id") or raw.get("item_id") or name),
    )


class PersonResolver:
    """Resolves references to Person records. Cheap to construct."""

    def __init__(self, account_id: str, device_id: str) -> None:
        self.account_id, self.device_id = account_id, device_id
        self._scope = ScopedMemory(account_id, device_id)
        self._people: list[Person] = []
        self._by_name: dict[str, Person] = {}
        self._by_email: dict[str, Person] = {}
        self._by_alias: dict[str, Person] = {}
        self._by_role: dict[str, list[Person]] = {}
        self._by_tag: dict[str, list[Person]] = {}
        self._reload()

    def _load_dossier_loader(self) -> Any:
        for mod in ("app.product.dossier_active_loader",
                    "app.product.dossier_loader"):
            try:
                m = __import__(mod, fromlist=["DossierLoader"])
                return m.DossierLoader(self.account_id, self.device_id)
            except Exception:
                continue
        return None

    def _reload(self) -> None:
        people, seen = [], set()

        def add(p: Person) -> None:
            k = _norm(p.name)
            if p.name and k not in seen:
                people.append(p)
                seen.add(k)

        loader = self._load_dossier_loader()
        if loader is not None:
            try:
                for raw in (loader.people() or []):
                    d = raw.to_dict() if hasattr(raw, "to_dict") else raw
                    if hasattr(raw, "gender_hint"):
                        d = dict(d, gender=raw.gender_hint())
                    add(_person_from_dict(d))
            except Exception:
                pass
        for item in self._scope.read(kind=KIND_PERSON, active_only=True):
            add(_person_from_dict(item))
        for item in self._scope.read(kind=KIND_ALIAS, active_only=True):
            alias = _norm(item.get("key") or "")
            target = _norm(item.get("value") or "")
            for p in people:
                if (_norm(p.name) == target and alias
                        and alias not in (_norm(a) for a in p.aliases)):
                    p.aliases.append(alias)
        self._people = people
        self._by_name, self._by_email, self._by_alias = {}, {}, {}
        self._by_role, self._by_tag = {}, {}
        for p in people:
            if _norm(p.name): self._by_name[_norm(p.name)] = p
            if _norm(p.email): self._by_email[_norm(p.email)] = p
            if _norm(p.role):
                self._by_role.setdefault(_norm(p.role), []).append(p)
            for a in p.aliases:
                if _norm(a): self._by_alias[_norm(a)] = p
            for t in p.tags:
                if _norm(t): self._by_tag.setdefault(_norm(t), []).append(p)

    def resolve(self, reference: str, context_text: str = "") -> Resolution:
        result = self._resolve_inner(reference, context_text)
        # Resolution-trace hook (M1 R3). Best-effort: never block the
        # caller on an instrumentation failure. Lazy import keeps this
        # safe if app.product.server is mid-load.
        try:
            from app.product.server import _record_resolution
            person = result.person.to_dict() if result.person else None
            _record_resolution({
                "kind": "person",
                "reference": (reference or "")[:240],
                "resolved_to": person,
                "confidence": float(result.confidence or 0.0),
                "alternatives": [p.to_dict() for p in
                                 (result.alternatives or [])][:8],
                "reason": str(result.reason or ""),
                "context_text": (context_text or "")[:240],
            })
        except Exception:
            pass
        return result

    def _resolve_inner(
        self, reference: str, context_text: str = ""
    ) -> Resolution:
        ref = _norm(reference)
        if not ref:
            return Resolution(None, 0.0, [], "empty reference")
        if "@" in ref and ref in self._by_email:
            return Resolution(self._by_email[ref], 1.0, [], "email match")
        if ref in self._by_name:
            return Resolution(self._by_name[ref], 1.0, [], "exact name match")
        if ref in _PRONOUN_GENDER:
            return self._resolve_pronoun(ref, context_text)
        if ref in self._by_alias:
            return Resolution(self._by_alias[ref], 0.95, [], "stored alias")

        role_key = re.sub(r"^the\s+", "", ref).strip()
        combined = self._dedupe(list(self._by_role.get(role_key, []))
                                + list(self._by_tag.get(role_key, [])))
        if combined:
            if len(combined) == 1:
                return Resolution(combined[0], 0.9, [],
                                  f"role match: {role_key}")
            return Resolution(
                None, 0.0, self._rank_by_recency(combined, context_text),
                f"ambiguous; need user disambiguation (role={role_key})")

        # First-name / nickname.
        hits = [p for p in self._people if _nickname_matches(ref, p.name)]
        if not hits:
            return Resolution(None, 0.0, [], "no match")
        ctx_hits = self._mentions_in_context(context_text, hits)
        if ctx_hits:
            t = ctx_hits[0]
            c = 0.95 if _norm(t.name.split()[0]) == ref else 0.9
            return Resolution(t, c, [], "name match via context")
        if len(hits) == 1:
            t = hits[0]
            c = 1.0 if _norm(t.name.split()[0]) == ref else 0.9
            r = "first-name unique match" if c == 1.0 else "nickname unique match"
            return Resolution(t, c, [], r)
        return Resolution(
            None, 0.0, self._rank_by_recency(hits, context_text),
            "ambiguous; need user disambiguation")

    def _resolve_pronoun(self, pronoun: str, ctx: str) -> Resolution:
        gender = _PRONOUN_GENDER.get(pronoun, "")
        cands = [p for p in self._people
                 if not gender or gender == "n"
                 or _norm(p.gender) == gender]
        if not cands:
            return Resolution(None, 0.0, [], "no gender-matching person")
        ctx_hits = self._mentions_in_context(ctx, cands)
        if ctx_hits:
            return Resolution(ctx_hits[0], 0.95, [],
                              "pronoun resolved via context mention")
        recent = self._recent_mentions(cands)
        if len(recent) == 1:
            return Resolution(recent[0], 0.9, [],
                              "pronoun resolved via recent mention")
        if len(recent) > 1:
            return Resolution(None, 0.0, recent[:5],
                              "ambiguous; need user disambiguation (pronoun)")
        if len(cands) == 1:
            return Resolution(cands[0], 0.85, [],
                              "pronoun resolved via unique gender candidate")
        return Resolution(None, 0.0, cands[:5],
                          "ambiguous; need user disambiguation (pronoun)")

    def _mentions_in_context(
        self, ctx_text: str, candidates: list[Person]
    ) -> list[Person]:
        if not ctx_text:
            return []
        ctx = ctx_text.lower()
        # Tier 0 = full-name hits (strongest); tier 1 = first-name only.
        hits: list[tuple[int, int, Person]] = []
        for p in candidates:
            n = _norm(p.name)
            idx = ctx.rfind(n) if n else -1
            if idx >= 0:
                hits.append((0, idx, p))
                continue
            first = _norm(p.name.split()[0]) if p.name else ""
            if first and re.search(rf"\b{re.escape(first)}\b", ctx):
                hits.append((1, ctx.rfind(first), p))
        hits.sort(key=lambda x: (x[0], -x[1]))
        return self._dedupe([p for _, _, p in hits])

    def _recent_mentions(self, candidates: list[Person]) -> list[Person]:
        cutoff = time.time() - PRONOUN_RECENCY_SEC
        active = [p for p in candidates if p.last_mentioned >= cutoff]
        active.sort(key=lambda p: p.last_mentioned, reverse=True)
        return active

    def _rank_by_recency(
        self, people: list[Person], ctx: str
    ) -> list[Person]:
        ranked = list(self._mentions_in_context(ctx, people))
        for p in sorted(people, key=lambda x: x.last_mentioned,
                        reverse=True):
            if p not in ranked:
                ranked.append(p)
        return self._dedupe(ranked)

    def _dedupe(self, people: list[Person]) -> list[Person]:
        seen, out = set(), []
        for p in people:
            k = _norm(p.name)
            if k not in seen:
                seen.add(k)
                out.append(p)
        return out

    def disambiguate(self, reference: str, user_choice: str) -> Resolution:
        ref, choice = _norm(reference), _norm(user_choice)
        if not ref or not choice:
            return Resolution(None, 0.0, [], "empty reference or choice")
        target = self._by_name.get(choice) or self._by_email.get(choice)
        if target is None:
            for p in self._people:
                pn = _norm(p.name)
                if pn.startswith(choice) or choice in pn:
                    target = p
                    break
        if target is None:
            return Resolution(None, 0.0, [], "user_choice did not match")
        try:
            self._scope.write(kind=KIND_ALIAS, key=ref, value=target.name,
                              source="person_resolver",
                              provenance="user_disambiguation",
                              extra={"learned_at": time.time()})
        except Exception:
            pass
        self._by_alias[ref] = target
        return Resolution(target, 1.0, [], "user disambiguated")
