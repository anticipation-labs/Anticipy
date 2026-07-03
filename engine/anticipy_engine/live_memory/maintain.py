"""MAINTAIN — the COLD batched sweep (idle / sleep-time consolidation, NOT per event).

Letta-style idle consolidation: rare + amortized, so a bigger model is fine here later; the
stub is deterministic rules (zero model calls, no fabricated text). Five jobs, all
deterministic-safe:
  - RECONCILE (generalized supersede): when a newer profile fact states a DIFFERENT value for
    the SAME single-valued attribute, mark the older one `superseded` (timestamped) —
    contradictions resolve toward the newest stated value. This widens the old narrow rule
    (employer / name / location only) to ANY single-valued "my <attr> is <value>" fact
    (my dentist / my gym / my doctor / my number ...). Multi-valued or preference facts have no
    attr=value shape, never match, and safely coexist. Same-value repeats are NOT a
    contradiction (left for CONSOLIDATE).
  - CONSOLIDATE / SUMMARIZE: cluster NEAR-duplicate episodes (token-Jaccard, not just exact) into
    one durable item — keep the newest, archive the rest, bump importance, and annotate the
    cluster size on the survivor (a deterministic summary: the survivor now stands for N
    occurrences). Re-dedupes across sources.
  - DECAY: archive old, low-importance history so stale clutter falls away.
  - EXPIRE RAW: prune the low-salience raw buffer once its short validity window passes (and any
    near-zero-salience raw line left past its buffer age), so the firehose can never accrete.
Never touched here: the open_loops ledger (commitments are deterministic; they close via explicit
state changes, never decay/consolidation) and vents (a vent never becomes — or steers — durable
memory: vent-shaped items are skipped by supersede and can never be a consolidation survivor).
"""
from __future__ import annotations

import os
import re
from typing import Dict, List, Optional, Tuple

from ..memory.store import Memory
from ..shared.schema import MemoryItem, now_ts
from .review_infer import is_vent_shape
from .salience import RAW_BUFFER_HOURS, score as salience_score

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^a-z0-9 ]+")
# a tiny stop set so near-dup clustering keys on content words, not filler.
_STOP = frozenset(
    "a an the to of in on at for and or but so is are was were be been being have has had "
    "i my me we our us you your it this that these those with about just really".split())


def _norm(s: str) -> str:
    return _WS.sub(" ", (s or "").strip().lower())


def _subject(text: str) -> Optional[str]:
    """Precise subject key for supersede — only facts that genuinely replace each
    other (employer/name/location). Preferences/roles return None (they coexist).

    KEPT for back-compat: capture._reconcile imports this for the WRITE-time reconcile. The COLD
    sweep uses the broader `_single_valued()` below (attribute + value), so the hot path stays
    exactly as before while idle consolidation reconciles ANY contradicting single-valued fact."""
    t = text.lower()
    if re.search(r"work (at|for)", t):
        return "employer"
    if "name is" in t:
        return "name"
    if "live in" in t or "lives in" in t:
        return "location"
    return None


# GENERALIZED single-valued reconcile (M6). Each pattern yields (attr_key, raw_value). Two active
# profile facts that share an attr_key but state DIFFERENT values contradict -> the older is
# superseded. The fixed-attr patterns preserve the old employer/name/location keys; the generic
# possessive pattern extends the rule to any "my <attr> is/are <value>" fact.
_VALUE_PATTERNS: List[Tuple[re.Pattern, Optional[str]]] = [
    (re.compile(r"\bwork(?:s)?\s+(?:at|for)\s+(.+)$", re.I), "employer"),
    (re.compile(r"\b(?:i|we)\s+live(?:s)?\s+in\s+(.+)$", re.I), "location"),
    (re.compile(r"\blives?\s+in\s+(.+)$", re.I), "location"),
    (re.compile(r"\b(?:my\s+)?name\s+is\s+(.+)$", re.I), "name"),
    # generic possessive single-valued attribute: "my <attr> is/are <value>".
    (re.compile(r"\bmy\s+([a-z][a-z ]*?)\s+(?:is|are)\s+(.+)$", re.I), None),
]


def _single_valued(text: str) -> Optional[Tuple[str, str]]:
    """(attr_key, normalized_value) for a single-valued profile fact, else None. attr_key groups
    contradictions; value decides whether two facts on that attribute actually differ."""
    t = (text or "").strip()
    if not t:
        return None
    for pat, fixed_attr in _VALUE_PATTERNS:
        m = pat.search(t)
        if not m:
            continue
        if fixed_attr is not None:
            return fixed_attr, _norm(m.group(1))
        attr, val = _norm(m.group(1)), _norm(m.group(2))
        # guard: an empty or over-long "attr" isn't a real single-valued key (avoid over-grouping).
        if not attr or len(attr.split()) > 4:
            return None
        return attr, val
    return None


def _tokens(text: str) -> frozenset:
    words = _PUNCT.sub(" ", _norm(text)).split()
    return frozenset(w for w in words if w not in _STOP)


def _jaccard(a: frozenset, b: frozenset) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / float(len(a | b))


# near-dup threshold for CONSOLIDATE clustering (token Jaccard). High enough that only genuinely
# redundant episodes collapse; distinct episodes stay separate.
_NEAR_DUP = 0.8


class Maintainer:
    def __init__(self, memory: Memory, gateway=None, mode: Optional[str] = None,
                 stale_days: float = 30.0) -> None:
        self.memory = memory
        self.gateway = gateway
        self.mode = mode or os.environ.get("ANTICIPY_MEMORY_MODE", "stub")
        self.stale_days = stale_days

    def _supersede(self) -> int:
        facts = [f for f in self.memory.profile.all()
                 if f.status not in ("superseded", "archived")]
        groups: Dict[str, List[MemoryItem]] = {}
        for f in facts:
            # a vent never steers durable memory; only single-valued facts reconcile.
            if is_vent_shape(f.text):
                continue
            sv = _single_valued(f.text)
            if sv:
                groups.setdefault(sv[0], []).append(f)
        n = 0
        for group in groups.values():
            if len(group) <= 1:
                continue
            group.sort(key=lambda f: f.timestamp)          # oldest -> newest
            newest = group[-1]
            newest_val = _single_valued(newest.text)[1]
            for old in group[:-1]:                          # keep the newest active
                if _single_valued(old.text)[1] == newest_val:
                    continue                                # same value = duplicate, not a contradiction
                old.status = "superseded"
                old.fields = {**(old.fields or {}), "superseded_by": newest.id}
                self.memory.profile.update(old)             # stamps updated_at
                n += 1
        return n

    def _consolidate(self) -> int:
        # exclude the RAW buffer (that firehose is handled by _expire_raw, never consolidated).
        items = [h for h in self.memory.history.all()
                 if h.status not in ("archived", "superseded")
                 and (h.fields or {}).get("tier") != "raw"]
        items.sort(key=lambda x: x.timestamp)               # oldest -> newest
        clusters: List[Dict[str, object]] = []
        for h in items:
            toks = _tokens(h.text)
            placed = False
            for cl in clusters:
                if _norm(h.text) == cl["key"] or _jaccard(toks, cl["tokens"]) >= _NEAR_DUP:
                    cl["members"].append(h)
                    cl["canonical"] = h                     # newest seen becomes the survivor
                    placed = True
                    break
            if not placed:
                clusters.append({"key": _norm(h.text), "tokens": toks,
                                 "members": [h], "canonical": h})
        n = 0
        for cl in clusters:
            members: List[MemoryItem] = cl["members"]        # type: ignore[assignment]
            if len(members) <= 1:
                continue
            canonical: MemoryItem = cl["canonical"]          # type: ignore[assignment]
            if is_vent_shape(canonical.text):
                continue                                    # never make a vent the durable survivor
            archived_ids: List[str] = []
            for m in members:
                if m.id == canonical.id:
                    continue
                m.status = "archived"
                self.memory.history.update(m)
                archived_ids.append(m.id)
                n += 1
            # SUMMARIZE (deterministic): the survivor now stands for the whole cluster. We annotate
            # the cluster size instead of fabricating a summary sentence (zero model, no hallucination).
            canonical.importance = min(1.0, canonical.importance + 0.1)   # repetition => more durable
            canonical.fields = {**(canonical.fields or {}),
                                "consolidated_count": len(members),
                                "consolidated_of": archived_ids}
            self.memory.history.update(canonical)
        return n

    def _decay(self) -> int:
        now = now_ts()
        cutoff = self.stale_days * 86400.0
        n = 0
        for h in self.memory.history.all():
            if h.status not in ("archived", "superseded") and (now - h.timestamp) > cutoff and h.importance < 0.5:
                h.status = "archived"
                self.memory.history.update(h)
                n += 1
        return n

    def _expire_raw(self, at: Optional[float] = None) -> int:
        """TIERED MEMORY (M4): prune the raw buffer. A low-salience episodic line was written
        with tier="raw" and a short validity window (M3 valid_to); once it is no longer valid it
        is archived, so the firehose can never bloat the durable store. Retrieval already hides
        it (is_valid_at) the instant it expires; this physically clears it in the cold sweep. As a
        belt-and-suspenders, a near-zero-salience raw line left past its buffer age is pruned even
        if it somehow carries a wide validity window."""
        moment = now_ts() if at is None else at
        floor = 0.05
        n = 0
        for h in self.memory.history.all():
            if h.status in ("archived", "superseded"):
                continue
            if (h.fields or {}).get("tier") != "raw":
                continue
            expired = not h.is_valid_at(moment)
            stale = ((moment - h.timestamp) > (RAW_BUFFER_HOURS * 3600.0)
                     and salience_score(h.text, "history", h.people) <= floor)
            if expired or stale:
                h.status = "archived"
                self.memory.history.update(h)
                n += 1
        return n

    def sweep(self, at: Optional[float] = None) -> Dict[str, object]:
        if self.mode == "live":
            pass  # TODO(live): a bigger model can do richer reflection here; rare + amortized.
        superseded = self._supersede()
        consolidated = self._consolidate()
        archived = self._decay()
        expired_raw = self._expire_raw(at=at)
        return {"ran": True, "superseded": superseded, "consolidated": consolidated,
                "archived": archived, "expired_raw": expired_raw, "smart_calls": 0}
