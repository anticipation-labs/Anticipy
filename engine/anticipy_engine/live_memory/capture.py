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
    def __init__(self, memory: Memory, gateway=None, mode: Optional[str] = None) -> None:
        self.memory = memory
        self.gateway = gateway
        self.mode = mode or os.environ.get("ANTICIPY_MEMORY_MODE", "stub")

    def _dup(self, text: str, kind: str) -> Optional[MemoryItem]:
        n = _norm(text)
        return next((it for it in self.memory.drawer(kind).all() if _norm(it.text) == n), None)

    def capture(self, text: str, source: str = "", force: bool = False) -> Dict[str, object]:
        """keep/drop -> classify -> dedupe -> write. Returns what happened + smart_calls.
        force=True skips the gate (explicit write_memory writes are always kept)."""
        if self.mode == "live":
            # TODO(live): cheap-model gate+extraction via self.gateway; never hit in tests.
            pass
        if not force and not should_keep(text):
            return {"kept": False, "reason": "noise", "smart_calls": 0}
        kind, fields = classify(text)
        dup = self._dup(text, kind)
        if dup is not None:
            return {"kept": False, "reason": "dup", "item": dup, "kind": kind, "smart_calls": 0}
        prov = "stated" if kind in ("profile_fact", "open_loop") else (source or "capture")
        item = MemoryItem(kind=kind, text=text.strip(), people=extract_people(text),
                          fields=fields, provenance=prov,
                          status=("open" if kind == "open_loop" else "active"))
        self.memory.drawer(kind).write(item)
        return {"kept": True, "kind": kind, "item": item, "smart_calls": 0}
