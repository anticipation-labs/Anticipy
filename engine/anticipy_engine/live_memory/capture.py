"""CAPTURE — the hot write path: keep/drop gate -> extract -> dedupe -> route.

A cheap keep/drop gate kills the ~99% noise; survivors are classified into a
drawer (commitment -> open_loops, stated fact/preference -> profile, else episodic
-> history), people are pulled out, near-duplicates are skipped. Gate + extraction
are RULES/deterministic by default (TEST mode = zero model calls, free + cheap on
purpose); a cheap model takes over behind ANTICIPY_MEMORY_MODE=live (the seam).
The "what to keep" judgment lives here, deliberately cheap.
"""
from __future__ import annotations

import os
import re
from typing import Dict, List, Optional, Tuple

from ..memory.store import Memory
from ..shared.schema import MemoryItem
from .duetime import REMIND_LEAD_S, anchor_from_meta, parse_due
from .remember import RememberList
from .review_infer import ReviewEnricher, is_vent_shape

_FILLER = {"um", "uh", "ok", "okay", "yeah", "yep", "yup", "nope", "no", "yes", "thanks",
           "thank", "hi", "hey", "hello", "bye", "cool", "nice", "sure", "right", "mhm",
           "hmm", "lol", "haha", "k", "kk", "fine", "great"}
_COMMIT = re.compile(
    r"\b(i'?ll|i will|i need to|i have to|i've got to|gotta|remind me|don'?t forget|"
    r"make sure|i should|schedule|book|call|email|text|send|pay|finish|submit|"
    r"follow up|reply|pick up|drop off|renew|cancel|confirm)\b", re.I)
_TIME = re.compile(
    r"\b(today|tonight|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"next week|this week|this weekend|by \w+|at \d{1,2}(:\d\d)?\s*(am|pm)?|"
    r"in an? (hour|day|week)|end of (the )?day|eod|noon)\b", re.I)
_PROFILE = re.compile(
    r"\b(my name is|i am (a|an)|i'?m (a|an)|i work (at|as|for)|i live in|i prefer|i like|"
    r"i love|i hate|i use|i'?m allergic|my (mom|dad|mother|father|wife|husband|partner|boss|"
    r"landlord|sister|brother|son|daughter|manager|doctor|dentist|friend|colleague))\b", re.I)
_REL = {"mom", "dad", "mother", "father", "wife", "husband", "partner", "boss", "landlord",
        "sister", "brother", "son", "daughter", "manager", "doctor", "dentist", "friend",
        "colleague", "accountant", "lawyer", "neighbor"}
_NOT_NAME = {"I", "I'll", "I'm", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
             "Saturday", "Sunday", "Today", "Tomorrow", "Tonight", "January", "February",
             "March", "April", "May", "June", "July", "August", "September", "October",
             "November", "December"}


def should_keep(text: str) -> bool:
    """The keep/drop gate: drop empty/short pure-filler; keep anything with signal."""
    t = (text or "").strip()
    if len(t) < 4:
        return False
    words = [w.strip(".,!?;:'\"").lower() for w in t.split()]
    if len(words) <= 3 and all(w in _FILLER or not w for w in words):
        return False
    return True


def should_remember(text: str) -> bool:
    """The GENEROUS gate for the inert remember-list (separate from should_keep).

    Over-capture is HARMLESS here because the remember-list is pull-only and can never
    fire, so this is biased to high recall: keep anything that is not pure empty/filler.
    Critically this is LOOSER than should_keep — it has no effect on any drawer, classify,
    dedupe, or decision path; it only decides what lands in the inert remembered table.
    """
    t = (text or "").strip()
    if len(t) < 2:
        return False
    words = [w.strip(".,!?;:'\"").lower() for w in t.split()]
    # drop ONLY a 1-2 word pure-filler grunt ("um", "ok thanks"); keep everything else.
    if len(words) <= 2 and all(w in _FILLER or not w for w in words):
        return False
    return True


def classify(text: str) -> Tuple[str, Dict[str, object]]:
    """Route a kept utterance to a drawer (rules; cheap model in live mode)."""
    if _COMMIT.search(text):
        fields: Dict[str, object] = {"task": text.strip()}
        m = _TIME.search(text)
        if m:
            fields["due"] = m.group(0)
        return "open_loop", fields
    if _PROFILE.search(text):
        return "profile_fact", {}
    return "history", {}


def extract_people(text: str) -> List[str]:
    out: List[str] = []
    toks = text.split()
    for i, raw in enumerate(toks):
        w = raw.strip(".,!?;:'\"")
        if i > 0 and re.fullmatch(r"[A-Z][a-z]+", w) and w not in _NOT_NAME:
            out.append(w)
    for w in re.findall(r"[a-z]+", text.lower()):
        if w in _REL:
            out.append(w)
    return list(dict.fromkeys(out))


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


class Capturer:
    def __init__(self, memory: Memory, gateway=None, mode: Optional[str] = None,
                 remember: Optional[RememberList] = None) -> None:
        self.memory = memory
        self.gateway = gateway
        self.mode = mode or os.environ.get("ANTICIPY_MEMORY_MODE", "stub")
        # The inert, pull-only remember-list (the SAFE half of the inference core).
        # It is a SEPARATE table — never a drawer, never an open_loop, no due/remind/
        # trigger fields — so nothing it holds can ever fire an action or an interrupt.
        # Constructed here so both capture call sites (feed + owner_ingest) write to it
        # through the single capture chokepoint with no control_core change.
        self.remember = remember if remember is not None else RememberList(memory.db)
        # DISPLAY-ONLY review enrichment cache (a DISTINCT table from remembered_lines;
        # no due/remind/trigger field, on no background loop). Surfaces the inferred
        # {task, people, due_phrase, confidence} above the raw line in the daily review.
        self.review_enricher = ReviewEnricher(memory.db)

    def _remember_side_write(self, text: str, source: str,
                             people: List[str], meta: Optional[Dict[str, object]]) -> None:
        """Fire-and-forget parallel write into the inert remember-list.

        GENEROUS (should_remember) and fully isolated: any failure is swallowed so it can
        NEVER alter the capture decision dict (kept/kind/reason/smart_calls) or raise into
        the always-listening / act/ask path. Returns nothing into the decision flow.
        """
        try:
            if should_remember(text):
                self.remember.remember(text, source=source, meta=meta, people=people)
        except Exception:  # noqa: BLE001 — the remember-write must never disturb capture
            pass

    def _dup(self, text: str, kind: str) -> Optional[MemoryItem]:
        n = _norm(text)
        return next((it for it in self.memory.drawer(kind).all() if _norm(it.text) == n), None)

    def capture(self, text: str, source: str = "", force: bool = False,
                meta: Optional[Dict[str, object]] = None) -> Dict[str, object]:
        """keep/drop -> classify -> dedupe -> write. Returns what happened + smart_calls.
        force=True skips the gate (explicit write_memory writes are always kept).
        meta carries the utterance clock (observed_at/timezone) for due-time grounding."""
        if self.mode == "live":
            # TODO(live): cheap-model gate+extraction via self.gateway; never hit in tests.
            pass
        # ADDITIVE parallel write to the INERT remember-list — generous + isolated.
        # Runs BEFORE the keep/drop gate so over-capture is high-recall, but it is a
        # side effect only: it never feeds the returned decision dict and never raises
        # into the act/ask/trigger path. The existing classify/dedupe/drawer.write path
        # below is left byte-for-byte unchanged.
        self._remember_side_write(text, source=source, people=extract_people(text), meta=meta)
        if not force and not should_keep(text):
            return {"kept": False, "reason": "noise", "smart_calls": 0}
        kind, fields = classify(text)
        # CARDINAL-SIN GUARD: a vent / sarcasm must NEVER land in a durable ACTIVE drawer
        # (an active profile fact or an open open_loop). classify() routes on _PROFILE
        # ("i hate", "i like") and _COMMIT ("i should"), so "I hate this", "I could scream",
        # "I should just move to a beach" would otherwise persist as active memory — the
        # cardinal-sin echo the Apollo audit caught. We gate on the _VENT-family SHAPE only
        # (not the countermand), so a genuine task carrying "don't" ("I need to tell them I
        # don't want to renew") still persists. The inert remember-list write above already
        # preserved the raw line (pull-only, can never fire), so a vent stays inert, never
        # durable+active — no context is lost.
        if kind in ("profile_fact", "open_loop") and is_vent_shape(text):
            return {"kept": False, "reason": "vent", "smart_calls": 0}
        if kind == "open_loop":
            # ground the spoken due-time to the utterance's own clock, never engine time
            due_dt = parse_due(text, anchor_from_meta(meta))
            if due_dt is not None:
                fields["due_ts"] = due_dt.timestamp()
                fields["remind_ts"] = due_dt.timestamp() - REMIND_LEAD_S
        dup = self._dup(text, kind)
        if dup is not None:
            return {"kept": False, "reason": "dup", "item": dup, "kind": kind, "smart_calls": 0}
        prov = "stated" if kind in ("profile_fact", "open_loop") else (source or "capture")
        item = MemoryItem(kind=kind, text=text.strip(), people=extract_people(text),
                          fields=fields, provenance=prov,
                          status=("open" if kind == "open_loop" else "active"))
        self.memory.drawer(kind).write(item)
        return {"kept": True, "kind": kind, "item": item, "smart_calls": 0}
