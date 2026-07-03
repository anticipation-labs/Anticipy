"""final/context/reconcile.py — Mem0-style ADD/UPDATE/DELETE/NOOP (deliverable b).

Grafted from DEV-FINAL ``engine/app/anticipy/memory.py:185`` (the ``reconcile``
primitive) + its ``delete_matching`` retraction path, adapted onto the devin
memory drawers.

Why a reconcile primitive and not an append log: when the wearer says "actually
never mind" the prior intent must be REMOVED, not duplicated; when they refine
("make that 8pm not 7") it must be UPDATED in place. Mem0's insight is that each
new observation resolves to exactly one of:

  ADD    genuinely new -> write it.
  UPDATE refines/corrects an existing entry -> rewrite in place.
  DELETE retracts an existing entry (a "never mind"/"forget it") -> remove it.
  NOOP   already known / nothing actionable -> do nothing.

Retraction (DELETE) is handled deterministically rather than via the model: a
"Remind me to X. Never mind." unambiguously cancels the just-stated X, so the
nevermind path uses a guaranteed delete against the open-loops drawer (mirrors the
graft's ``delete_matching``), which the eval's "handle a retraction" case proves.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Unambiguous self-cancel phrases (mirrors live_memory/review_infer._RETRACTION). A bare
# "cancel my Friday 1:1" is a real forward task, NOT a memory retraction, so it is
# deliberately excluded — only these phrases retract a prior open loop.
_RETRACTION = re.compile(
    r"\b(?:never ?mind|scratch that|forget (?:it|that|about)|nix that|cancel that|"
    r"disregard that|belay that|drop the|no need (?:to|for)|forget the)\b",
    re.I,
)

# stop tokens when reducing a retraction to its salient object noun(s)
_STOP = {
    "the", "a", "an", "that", "this", "my", "our", "your", "it", "thing", "about",
    "for", "to", "of", "on", "with", "and", "or", "just", "actually", "really",
    "please", "whole", "entire", "nevermind", "never", "mind", "forget", "scratch",
    "nix", "disregard", "belay", "drop", "need", "no", "cancel",
}


@dataclass
class ReconcileResult:
    op: str          # ADD | UPDATE | DELETE | NOOP
    reason: str = ""
    removed: int = 0


def _content_tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower())
            if len(w) > 2 and w not in _STOP}


def reconcile(memory, ctype: str, key: str, value: str, text: str) -> ReconcileResult:
    """Deterministic ADD/UPDATE/NOOP for an anchor/person/preference fact against
    the active profile drawer. Same-key-same-value -> NOOP; same-key-new-value ->
    UPDATE (supersede the old, write the new); otherwise ADD. (DELETE is the
    retraction path below.)"""
    try:
        items = memory.profile.all()
    except Exception:
        items = []
    key_l = (key or "").strip().lower()
    val_l = (value or "").strip().lower()
    superseded = 0
    for it in items:
        f = getattr(it, "fields", None) or {}
        if f.get("ctype") != ctype:
            continue
        if str(f.get("ckey") or "").strip().lower() != key_l:
            continue
        if str(f.get("cvalue") or "").strip().lower() == val_l and val_l:
            return ReconcileResult("NOOP", "already known")
        # same key, different value -> the new one supersedes the old
        try:
            memory.profile.delete(it.id)
            superseded += 1
        except Exception:
            pass
    _write_fact(memory, ctype, key, value, text)
    if superseded:
        return ReconcileResult("UPDATE", f"superseded {superseded} prior value(s)")
    return ReconcileResult("ADD", "new fact")


def _write_fact(memory, ctype: str, key: str, value: str, text: str, **extra) -> None:
    fields = {"ctype": ctype, "ckey": key, "cvalue": value, "context_fact": True}
    fields.update(extra)
    memory.profile.write_text(
        text or f"{key}: {value}", fields=fields, provenance="context",
        confidence=1.0, importance=0.7, status="active",
    )


def is_retraction(text: str) -> bool:
    return bool(_RETRACTION.search(text or ""))


def handle_retraction(memory, text: str) -> ReconcileResult:
    """DELETE arm: a detected "never mind X" removes the matching open loop(s) so a
    retracted task stops lingering as unfinished work. Matches on the salient object
    noun of the retraction (e.g. "never mind the bank thing" -> {bank}); only ever
    deletes a loop that actually shares that object token, so it can't cull unrelated
    work. Also supersedes any matching context anchor. Returns the DELETE op + count."""
    if not is_retraction(text):
        return ReconcileResult("NOOP", "not a retraction")
    # object = tokens AFTER the retraction phrase (fall back to the whole line)
    m = _RETRACTION.search(text)
    tail = text[m.end():] if m else text
    obj = _content_tokens(tail) or _content_tokens(text)
    if not obj:
        return ReconcileResult("NOOP", "no object to retract")

    removed = 0
    try:
        loops = memory.open_loops.all()
    except Exception:
        loops = []
    for it in loops:
        f = getattr(it, "fields", None) or {}
        hay = _content_tokens(
            (getattr(it, "text", "") or "") + " " + str(f.get("task") or ""))
        if obj & hay:
            try:
                if memory.open_loops.delete(it.id):
                    removed += 1
            except Exception:
                pass
    # supersede any matching context anchor too (keep memory consistent)
    try:
        for it in memory.profile.all():
            f = getattr(it, "fields", None) or {}
            if not f.get("context_fact"):
                continue
            hay = _content_tokens((getattr(it, "text", "") or "")
                                  + " " + str(f.get("cvalue") or ""))
            if obj & hay:
                memory.profile.delete(it.id)
    except Exception:
        pass
    return ReconcileResult("DELETE", f"retracted {removed} loop(s)", removed=removed)


__all__ = ["ReconcileResult", "reconcile", "handle_retraction", "is_retraction"]
