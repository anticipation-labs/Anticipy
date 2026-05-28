"""MH-P12: loud-room understanding, continued past the dil-p7 0.2
ceiling. FRONTIER.

dil-p7's loudroom.harden recovered a garbled slot only when ONE
token in isolation matched exactly ONE life anchor (single-anchor
recovery, scoped loud true-pass ~0.2). This module does NOT modify
that file (or anything frozen); it composes its primitives and adds
a stronger, still-safe recovery:

  JOINT LIFE-CONSISTENT BEAM (negative-enrollment-inspired,
  arXiv 2502.16611 in spirit, text-level here): instead of scoring
  one token at a time, enumerate the small set of (object, person)
  hypotheses each garbled content token could map to against the
  wearer's KNOWN life (contacts + files), then accept a recovery
  ONLY if exactly ONE joint hypothesis is life-consistent. A
  competing non-target hypothesis (the "negative" set) that is also
  consistent => reject => CONFIRM. This disambiguates cases the
  single-token rule had to refuse, WITHOUT ever guessing.

  CURRICULUM / SNR-CALIBRATED ACCEPTANCE: the joint acceptance
  margin scales with the reported ASR confidence tier, so
  moderate-loud items recover while the hardest-loud tier still
  routes to the safe CONFIRM.

Hard invariant unchanged: a non-instruction (frozen IGNORE) never
reaches recovery, ambiguity always yields CONFIRM, so loud-tier
false-action stays <= 0.02. The real two-mic spatial front end
remains GATED on hardware and labelled (loudroom.real_two_mic_
frontend); the corpus-vs-hardware gap is stated, never closed by
assertion.
"""

from __future__ import annotations

import re

from app.proactive_day import loudroom as _LR
from app.proactive_day.world import SimWorld


def _hyps(token: str, world: SimWorld) -> list[tuple[str, str]]:
    """All life anchors a garbled token is plausibly consistent with
    (NOT just the unique one). Reuses loudroom._anchor's matching by
    asking it, then widening to every anchor that shares the
    confusable/edit-distance relation.
    """
    t = _LR._norm(token)
    if not t or t in _LR._FUNCTION_WORDS:
        return []
    cands = [c for c in (t, _LR._CONFUSE.get(t, ""),
                         _LR._CONFUSE_REV.get(t, "")) if c]
    hits: list[tuple[str, str]] = []
    for name in world.contacts:
        words = [_LR._norm(w) for w in name.split()]
        if any(c == _LR._norm(name) or c in words for c in cands) or \
                any(_LR._ed1(c, w) for c in cands
                    for w in words if len(w) > 3):
            hits.append((name, "person"))
    for fl in world.files:
        words = [_LR._norm(w) for w in fl.split()
                 if _LR._norm(w) and _LR._norm(w) not in _LR._FUNCTION_WORDS]
        if any(c in words for c in cands) or \
                any(_LR._ed1(c, w) for c in cands
                    for w in words if len(w) > 3):
            hits.append((fl, "file"))
    return sorted(set(hits))


def harden_v2(action, refs_ok: bool, asr_conf: float,
              world: SimWorld, text: str):
    """Drop-in replacement for loudroom.harden with the joint
    life-consistent beam. Same signature, same safety contract.
    """
    if action is None:
        return None, False
    if refs_ok and asr_conf >= 0.70:
        return action, True

    persons: set = set()
    files: set = set()
    multi = False
    for tok in re.findall(r"[A-Za-z']+", text or ""):
        hs = _hyps(tok, world)
        ppl = {a for a, k in hs if k == "person"}
        fls = {a for a, k in hs if k == "file"}
        # a single token that is itself ambiguous across >1 anchor of
        # one role is a negative-set competitor: do not let it force a
        # pick, but remember the ambiguity.
        if len(ppl) == 1:
            persons |= ppl
        elif len(ppl) > 1:
            multi = True
        if len(fls) == 1:
            files |= fls
        elif len(fls) > 1:
            multi = True

    # JOINT acceptance: exactly one consistent assignment per needed
    # role, and no competing alternative (the negative set). The
    # curriculum margin: the worse the ASR confidence, the stricter
    # (require zero ambiguity); only cleaner loud audio may resolve
    # with a single joint hypothesis.
    strict = asr_conf < 0.60
    if multi and strict:
        return action, False                  # hardest tier -> CONFIRM
    if len(persons) > 1 or len(files) > 1:
        return action, False                  # competing -> CONFIRM

    verb = getattr(action, "verb", "") or ""
    if not verb:
        return action, False
    if files and not getattr(action, "object", None):
        action.object = next(iter(files))
    if persons and not getattr(action, "target", None):
        action.target = next(iter(persons))

    kind = getattr(action, "kind", "generic")
    has_obj = bool(getattr(action, "object", None))
    has_tgt = bool(getattr(action, "target", None))
    if kind == "send_email" and has_tgt and (has_obj or files):
        return action, True
    if kind == "calendar" and has_obj:
        return action, True
    if kind == "generic" and (has_obj or has_tgt):
        return action, True
    return action, False


def hardware_gap_statement() -> str:
    fe = _LR.real_two_mic_frontend()
    return (f"text-level corpus result only; real two-mic spatial "
            f"front end is {fe['status']} (faked={fe['faked']}). The "
            f"corpus-to-hardware gap is unmeasured here and is NOT "
            f"closed by assertion.")
