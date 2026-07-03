"""final/context/engine.py — the ONE context-engine facade (learns-you, no keys).

Ties the four Phase-3 deliverables together behind a single object the live intake
holds as ``core.context``:

  (a) reference resolution   reference_resolver.resolve_reference  (memory-anchored)
  (b) reconcile ADD/UPDATE/DELETE/NOOP + retraction   reconcile.*
  (c) per-person dossier     dossier.PersonBook  (two Sams -> disambiguate/ask)
  (d) never-re-ask ledger    never_re_ask.NeverReAskLedger

Two seams into ``control_core._owner_ingest_inner``:

  observe(text)             — run FIRST, before the brain. Captures the wearer's
                              stated anchors/people/preferences into memory (the
                              pipeline drops pure facts as "ignore", so they'd be
                              lost otherwise) and applies retractions (DELETE the
                              matching open loop on "never mind X").
  resolve_observed(lines)   — run after the transcript-scoped intent resolve. For
                              each task line, resolve vague references from memory,
                              disambiguate a person, and fill any slot we already
                              know — rewriting the line so the card the wearer sees
                              carries the concrete value instead of re-asking.

Everything is best-effort and fail-safe: a memory hiccup logs and no-ops; it never
breaks intake, and an empty context leaves the line byte-identical.
"""

from __future__ import annotations

import re

from . import reconcile
from .dossier import PersonBook
from .never_re_ask import NeverReAskLedger
from .reference_resolver import resolve_reference

# ---- fact-capture patterns (deterministic; only fire on clear statements) ---------
# "<Name> is my <role>"  -> a person record   ("Sam Rivera is my lawyer")
_NAME_IS_MY = re.compile(r"^\s*([\w.'-]+(?:\s+[\w.'-]+){0,2})\s+is\s+my\s+([\w ]{2,40}?)\s*$", re.I)
# "my <role> is <value>" -> a person keyed by role  ("my dentist is Dr. Lee on King St")
_MY_ROLE_IS = re.compile(r"^\s*my\s+([\w ]{2,24}?)\s+is\s+(.{2,80}?)\s*$", re.I)
# "I always/usually get/order/have <X>" -> the "usual" anchor
_USUAL_CAP = re.compile(
    r"\bI\s+(?:always|usually|normally|typically|generally)\s+"
    r"(?:get|order|have|drink|grab|do|go\s+for)\s+(.{2,80}?)\s*$", re.I)
# "from <place>" (a short continuation fragment) -> the "usual place" anchor
_FROM_PLACE = re.compile(r"^\s*from\s+(.{3,60}?)\s*$", re.I)
# "I'm allergic to <X>" -> an allergy fact
_ALLERGIC = re.compile(r"\b(?:i'?m|i am)?\s*allergic\s+to\s+(.{2,60}?)\s*$", re.I)
# "I live at <X>" -> the address anchor
_LIVE_AT = re.compile(r"\bI\s+live\s+at\s+(.{3,80}?)\s*$", re.I)

# roles that are really a category, not a person's name — keep them as anchors too
_ROLE_LIKE = {"dentist", "doctor", "lawyer", "accountant", "landlord", "barber",
              "mechanic", "vet", "pharmacy", "manager", "boss", "gym", "bank"}


def _fragments(text: str) -> list[str]:
    parts: list[str] = []
    for line in (text or "").splitlines():
        for frag in re.split(r"(?<=[.!?])\s+", line):
            frag = frag.strip()
            if frag:
                parts.append(frag)
    return parts or ([text.strip()] if (text or "").strip() else [])


class ContextEngine:
    """The learns-you facade. Holds no state beyond the memory drawers it reads/writes."""

    def __init__(self, memory, gateway=None) -> None:
        self.memory = memory
        self.gateway = gateway
        self.people = PersonBook(memory)
        self.ledger = NeverReAskLedger(memory)

    # ---- seam 1: before the brain ------------------------------------------------
    def observe(self, text: str) -> dict:
        """Capture stated facts + apply retractions. Returns a small trace."""
        out = {"captured": [], "retraction": None}
        try:
            retr = reconcile.handle_retraction(self.memory, text)
            if retr.op != "NOOP":
                out["retraction"] = {"op": retr.op, "removed": retr.removed, "reason": retr.reason}
        except Exception:
            pass
        # A pure retraction shouldn't also be mined for facts.
        if out["retraction"] is not None:
            return out
        try:
            out["captured"] = self._capture_facts(text)
        except Exception:
            pass
        return out

    def _capture_facts(self, text: str) -> list[dict]:
        captured: list[dict] = []
        for frag in _fragments(text):
            m = _NAME_IS_MY.match(frag)
            if m:
                name, role = m.group(1).strip(), m.group(2).strip()
                # skip "<pronoun> is my ..." / non-name subjects
                if name.lower() in {"he", "she", "they", "it", "this", "that"}:
                    continue
                self._add_person(name, role, frag)
                captured.append({"person": name, "role": role})
                continue
            m = _MY_ROLE_IS.match(frag)
            if m:
                role, value = m.group(1).strip(), m.group(2).strip()
                self._add_person(value, role, frag)
                reconcile.reconcile(self.memory, "anchor", role.lower(), value, frag)
                captured.append({"anchor": role, "value": value})
                continue
            m = _USUAL_CAP.search(frag)
            if m:
                reconcile.reconcile(self.memory, "anchor", "usual", m.group(1).strip(), frag)
                captured.append({"anchor": "usual", "value": m.group(1).strip()})
                continue
            m = _FROM_PLACE.match(frag)
            if m:
                reconcile.reconcile(self.memory, "anchor", "usual place", m.group(1).strip(), frag)
                captured.append({"anchor": "usual place", "value": m.group(1).strip()})
                continue
            m = _ALLERGIC.search(frag)
            if m:
                reconcile.reconcile(self.memory, "allergy", "allergy", m.group(1).strip(),
                                    f"allergic to {m.group(1).strip()}")
                captured.append({"allergy": m.group(1).strip()})
                continue
            m = _LIVE_AT.search(frag)
            if m:
                reconcile.reconcile(self.memory, "address", "address", m.group(1).strip(),
                                    f"lives at {m.group(1).strip()}")
                captured.append({"address": m.group(1).strip()})
                continue
        return captured

    def _add_person(self, name: str, role: str, text: str) -> None:
        pronouns = ""
        low = text.lower()
        if re.search(r"\b(?:brother|father|son|husband|uncle|nephew|grandpa|he|him)\b", low):
            pronouns = "he/him"
        elif re.search(r"\b(?:sister|mother|mom|daughter|wife|aunt|niece|grandma|she|her)\b", low):
            pronouns = "she/her"
        self.memory.profile.write_text(
            text,
            fields={"ctype": "person", "cname": name, "crole": role,
                    "cpronouns": pronouns, "context_fact": True},
            provenance="context", confidence=1.0, importance=0.7, status="active",
        )

    # ---- seam 2: after the transcript-scoped resolve -----------------------------
    def resolve_observed(self, observed):
        """Rewrite each task line with what we already know (references, people, slots)."""
        for line in observed:
            try:
                self._resolve_line(line)
            except Exception:
                continue
        return observed

    def _resolve_line(self, line) -> None:
        text = getattr(line, "text", "") or ""
        if not text.strip():
            return
        low = text.lower()
        additions: list[str] = []

        # (a) memory-anchored reference resolution ("my usual" -> the oat latte)
        rr = resolve_reference(self.memory, text, gateway=self.gateway)
        if rr.resolved and rr.value and rr.value.lower() not in low:
            additions.append(rr.value)

        # (c) per-person disambiguation (two Sams -> ask which; one -> qualify)
        person, candidates = self.people.resolve_name(text)
        if candidates:
            first = candidates[0].first_name()
            names = ", ".join(p.label() for p in candidates[:3])
            additions.append(f"which one — {first}? ({names})")
        elif person is not None and person.name.lower() not in low:
            additions.append(person.label())

        # (d) never-re-ask: fill any slot named by role that we already know
        joined = " ".join(additions).lower()
        for hit in self.ledger.known_slots_in(text):
            if hit.value.lower() not in low and hit.value.lower() not in joined:
                additions.append(f"{hit.slot}: {hit.value}")

        if additions:
            line.text = text.rstrip(" .") + " — " + "; ".join(additions)


__all__ = ["ContextEngine"]
