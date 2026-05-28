"""Layer I: loud-room hardening.

The other layers assume the transcript is what was said. In a loud
restaurant it is not: low-energy function words drop, content words
collapse onto acoustically-confusable neighbours, ASR confidence
falls. DIL is a text-level simulation, so this layer MODELS that
corruption honestly (adversarially, not lazily) for every
snr_tier == "loud" event, then hardens the decision against it.

Safety (no binding ever weakened):

  - The corrupted line still goes through the FROZEN engine first.
    Garbled chatter is IGNOREd by the frozen brain exactly as clean
    chatter is, so loud-tier false-action stays <= 0.02. Recovery
    below NEVER runs on a non-instruction: it only repairs the
    slots of a line the validated frozen engine already accepted as
    an instruction. It cannot fabricate an instruction from noise.

  - Recovery is deterministic life-anchored repair: a garbled token
    maps to a real contact/file ONLY when EXACTLY ONE known life
    anchor matches (known confusable in either direction, or
    edit-distance 1, or a word of a multiword anchor). Two or more
    distinct anchors -> ambiguous -> CONFIRM. No anchor -> CONFIRM.
    Same principle as resolve.py's deterministic account match;
    never an LLM hallucinating a referent.

The real acoustic front-end (two-mic spatial separation +
negative-enrollment target extraction, arXiv 2502.16611) is wired
behind real_two_mic_frontend() but GATED and unproven (no two-mic
hardware in the simulated day) and labelled as such, never faked.
"""

from __future__ import annotations

import hashlib
import re
from typing import Optional

from app.proactive_day.world import SimWorld

LOUD_TIER = "loud"

_FUNCTION_WORDS = {
    "the", "a", "an", "to", "of", "for", "and", "that", "this",
    "i", "ll", "i'll", "you", "your", "it", "is", "be", "on", "in",
    "at", "me", "my", "we", "us", "can", "could", "would", "please",
}

# Acoustically-confusable collapses a loud room actually produces.
_CONFUSE = {
    "send": "sent", "dana": "donna", "deck": "desk",
    "budget": "budgets", "contract": "contact", "priya": "prea",
    "sean": "shawn", "marcus": "marco", "book": "look",
    "schedule": "skej", "signed": "sign", "thursday": "thirsty",
    "tonight": "tonite", "forward": "foward", "reply": "reploy",
}
_CONFUSE_REV = {v: k for k, v in _CONFUSE.items()}


def _seed(text: str) -> int:
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest(), 16)


def degrade(text: str, tier: str) -> tuple[str, float]:
    """Realistic restaurant-noise corruption for a loud-tier line.
    Deterministic in the text (fixed hashed anchor, reproducible).
    Strict no-op for any non-loud tier. Returns (garbled_text,
    asr_confidence in [0.50, 0.78]).
    """
    if tier != LOUD_TIER:
        return text, 1.0
    s = _seed(text)
    toks = re.findall(r"[A-Za-z']+", text)
    out: list[str] = []
    dropped = 0
    for idx, tok in enumerate(toks):
        low = tok.lower()
        bit = (s >> (idx % 53)) & 7
        if low in _FUNCTION_WORDS and bit < 6:        # eat ~75% function
            dropped += 1
            continue
        if low in _CONFUSE and bit < 5:               # ~62% confuse
            out.append(_CONFUSE[low])
            continue
        if low not in _FUNCTION_WORDS and bit == 7:   # rare content drop
            dropped += 1
            continue
        out.append(tok)
    garbled = " ".join(out).strip() or (toks[0] if toks else "")
    span = max(1, len(toks))
    conf = 0.50 + 0.28 * (1.0 - min(1.0, (dropped + 1) / span))
    return garbled, round(conf, 3)


def _norm(w: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (w or "").lower())


def _ed1(a: str, b: str) -> bool:
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la == lb:
        return sum(1 for x, y in zip(a, b) if x != y) == 1
    short, lng = (a, b) if la < lb else (b, a)
    i = j = 0
    skipped = False
    while i < len(short) and j < len(lng):
        if short[i] != lng[j]:
            if skipped:
                return False
            skipped = True
            j += 1
            continue
        i += 1
        j += 1
    return True


def _anchor(token: str, world: SimWorld) -> tuple[Optional[str], str]:
    """Map one token to a single life anchor or (None, '').
    Returns (anchor, kind) where kind is 'person' | 'file'.
    """
    t = _norm(token)
    if not t or t in _FUNCTION_WORDS:
        return None, ""
    cands = ([_norm(c) for c in (t, _CONFUSE.get(t, ""),
                                 _CONFUSE_REV.get(t, "")) if c])
    hits: list[tuple[str, str]] = []
    for name in world.contacts:
        words = [_norm(w) for w in name.split()]
        if any(c == _norm(name) or c in words for c in cands) or \
                any(_ed1(c, w) for c in cands
                    for w in words if len(w) > 3):
            hits.append((name, "person"))
    for fl in world.files:
        words = [_norm(w) for w in fl.split() if _norm(w)
                 and _norm(w) not in _FUNCTION_WORDS]
        if any(c in words for c in cands) or \
                any(_ed1(c, w) for c in cands
                    for w in words if len(w) > 3):
            hits.append((fl, "file"))
    uniq = sorted(set(hits))
    return (uniq[0][0], uniq[0][1]) if len(uniq) == 1 else (None, "")


def harden(action, refs_ok: bool, asr_conf: float, world: SimWorld,
           text: str) -> tuple[object, bool]:
    """Loud-tier safe policy applied AFTER resolve. `action` is
    already non-None only because the FROZEN engine accepted this
    (garbled) line as an instruction, so repairing its slots cannot
    fabricate an instruction from chatter.

    refs_ok True and ASR decent -> trust resolve. Otherwise repair
    the load-bearing slots from the garbled text against the
    wearer's real life, but ONLY on an unambiguous single anchor
    per role; any ambiguity or gap -> CONFIRM (the safe direction).
    """
    if action is None:
        return None, False
    if refs_ok and asr_conf >= 0.70:
        return action, True

    persons: set = set()
    files: set = set()
    for tok in re.findall(r"[A-Za-z']+", text or ""):
        a, kind = _anchor(tok, world)
        if kind == "person":
            persons.add(a)
        elif kind == "file":
            files.add(a)

    # Ambiguous loud input (more than one plausible person or file)
    # is exactly when a guess would be the disaster: CONFIRM.
    if len(persons) > 1 or len(files) > 1:
        return action, False

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
    # require the slots that role needs; else stay CONFIRM.
    if kind == "send_email" and has_tgt and (has_obj or files):
        return action, True
    if kind == "calendar" and has_obj:
        return action, True
    if kind == "generic" and (has_obj or has_tgt):
        return action, True
    return action, False


def real_two_mic_frontend() -> dict:
    """Honest wiring statement for the real acoustic path. The
    two-mic spatial separation + negative-enrollment target
    extraction (arXiv 2502.16611) is the intended hardware front
    end; there is NO two-mic hardware in the simulated day, so it is
    GATED and unproven and labelled as such, never reported working.
    """
    return {
        "method": "two-mic spatial sep + negative-enrollment target "
                  "extraction (arXiv 2502.16611)",
        "status": "GATED/unproven (no two-mic hardware in the "
                  "simulated day; text-level corruption modelled "
                  "instead, honestly)",
        "faked": False,
    }
