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

# ---- standing-preference patterns (durable constraints, NOT one-off tasks) ---------
# A standing preference is a persistent rule about how to schedule/act for the wearer
# ("I only take meetings in the morning", "never book me anything before 9am",
# "I prefer afternoon calls"). The decision pipeline drops these as an IGNORED open
# loop, so without capturing them here the profile stays empty and the constraint is
# lost — then a later "set up a call with Dana" neither honors nor asks the time.
# These are deliberately narrow so they never swallow an ordinary task or a "usual"
# anchor (verbs here are disjoint from _USUAL_CAP's get/order/have/... set).
_PREF_ONLY = re.compile(r"\bi\s+only\s+(.{3,80}?)\s*[.!]?\s*$", re.I)
_PREF_NEVER = re.compile(
    r"\bnever\s+((?:book|schedule|call|ring|meet|put|set|plan|slot)\b.{0,72}?)\s*[.!]?\s*$", re.I)
_PREF_PREFER = re.compile(
    r"\bi\s+(?:prefer|only\s+want|would\s+rather)\s+(.{3,80}?)\s*[.!]?\s*$", re.I)
_PREF_NO = re.compile(
    r"^\s*no\s+((?:meetings?|calls?|bookings?|appointments?)\b.{0,72}?)\s*[.!]?\s*$", re.I)
_PREF_ALWAYS = re.compile(
    r"\bi\s+always\s+((?:take|keep|start|end|book|schedule|meet)\b.{0,72}?)\s*[.!]?\s*$", re.I)
_PREF_PATTERNS = (_PREF_ONLY, _PREF_NEVER, _PREF_PREFER, _PREF_NO, _PREF_ALWAYS)

# does a preference concern SCHEDULING/time? (so we know to echo it on a scheduling card)
_SCHED_SIGNAL = re.compile(
    r"\b(?:meetings?|calls?|appointments?|bookings?|schedule|sync|"
    r"morning|afternoon|evening|noon|midday|o'?clock|before|after|earlier|later|"
    r"mon(?:day)?|tue(?:sday)?|wed(?:nesday)?|thu(?:rsday)?|fri(?:day)?|"
    r"sat(?:urday)?|sun(?:day)?|weekday|weekend|\d{1,2}\s*(?::\d{2})?\s*(?:am|pm))\b", re.I)

# a scheduling/booking task line — the place a standing time preference must be applied
_SCHED_LINE = re.compile(
    r"\b(?:set\s+up|schedule|book|arrange|plan|organi[sz]e|line\s+up)\b"
    r".*\b(?:call|meeting|meet|appointment|appt|sync|1:1|catch\s*up|chat|interview|session)\b"
    r"|\b(?:meeting|appointment|appt|1:1|sync)\b"
    r"|\bcall\s+with\b", re.I)

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
            pref = self._preference_from(frag)
            if pref is not None:
                value, is_sched = pref
                if self._add_preference(value, frag, is_sched):
                    captured.append({"preference": value, "scheduling": is_sched})
                continue
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

    # ---- standing preferences (durable rules; surfaced at schedule time) ----------
    @staticmethod
    def _preference_from(frag: str):
        """(value, is_scheduling) if ``frag`` states a standing preference, else None.
        The value is the whole statement so the constraint (e.g. 'morning', '9am') is
        preserved verbatim for the card echo."""
        f = (frag or "").strip()
        for rx in _PREF_PATTERNS:
            if rx.search(f):
                return f.rstrip(" ."), bool(_SCHED_SIGNAL.search(f))
        return None

    def _add_preference(self, value: str, text: str, scheduling: bool) -> bool:
        """Persist a standing preference as a DURABLE profile fact (not a fireable open
        loop). Coexists with other constraints; exact repeats NOOP. Returns True if
        newly written."""
        val_l = (value or "").strip().lower()
        if not val_l:
            return False
        try:
            for it in self.memory.profile.all():
                f = getattr(it, "fields", None) or {}
                if f.get("ctype") == "preference" \
                        and str(f.get("cvalue") or "").strip().lower() == val_l:
                    return False  # already known -> NOOP
        except Exception:
            pass
        self.memory.profile.write_text(
            text or value,
            fields={"ctype": "preference", "ckey": "scheduling" if scheduling else "general",
                    "cvalue": value, "cscheduling": bool(scheduling), "context_fact": True},
            provenance="context", confidence=1.0, importance=0.7, status="active",
        )
        return True

    def _scheduling_prefs(self) -> list[str]:
        """The stored standing preferences that concern scheduling/time (most recent
        first), for echoing onto a scheduling card."""
        out: list[str] = []
        try:
            items = self.memory.profile.all()
        except Exception:
            return out
        for it in items:
            f = getattr(it, "fields", None) or {}
            if f.get("ctype") != "preference" or not f.get("cscheduling"):
                continue
            val = str(f.get("cvalue") or getattr(it, "text", "") or "").strip()
            if val and val not in out:
                out.append(val)
        return out[:2]

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

        # (e) standing scheduling preference: a scheduling/booking task must honor a
        #     stored time rule ("mornings only / nothing before 9am"). Echo the stored
        #     constraint onto the card so the wearer sees it applied instead of ignored.
        if _SCHED_LINE.search(text):
            running = low + " " + " ".join(additions).lower()
            for pref in self._scheduling_prefs():
                if pref.lower() not in running:
                    additions.append(pref)
                    running += " " + pref.lower()

        if additions:
            line.text = text.rstrip(" .") + " — " + "; ".join(additions)


__all__ = ["ContextEngine"]
