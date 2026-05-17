"""Layer 3: load-bearing slot trust. Word error over a real day is
unavoidable; the honest defense is not pretending the words are
right, it is verifying the words that MATTER.

Every ASR token carries parakeet's native confidence. The
load-bearing slots are typed and extracted from the token stream:
  - the action verb (the binary do-or-don't / send-or-don't)
  - recipient / person names
  - dates / times
  - amounts / quantities
If ANY present load-bearing slot's confidence is below the trust
bar, the action does NOT fire: it returns CONFIRM, and the caller
sends EXACTLY ONE short confirmation over the existing comms path.
Only an everything-clear high-confidence candidate returns FIRE.
This is asymmetric on purpose: a missed/repeated instruction is
recoverable; acting on a misheard name or amount is not. Never
blind-fire a low-confidence load-bearing slot.
"""

from __future__ import annotations

import re

# data-driven: parakeet token confidence is ~0.9+ on clean speech and
# collapses on the fast/low-SNR ambiguous slots the corpus stresses.
# Set from the P3 measurement; a load-bearing token below this is not
# trustworthy enough to act on unconfirmed.
SLOT_CONF_BAR = 0.70

_VERBS = {"send", "forward", "email", "book", "wire", "remind", "reply",
          "add", "schedule", "move", "cancel", "call", "text", "tell",
          "transfer", "draft", "order", "share", "ping", "resend"}
_DAYS = {"monday", "tuesday", "wednesday", "thursday", "friday",
         "saturday", "sunday", "today", "tomorrow", "tonight",
         "fifteenth", "fiftieth", "morning", "afternoon", "evening"}
_NUMWORDS = {"one", "two", "three", "four", "five", "six", "seven",
             "eight", "nine", "ten", "eleven", "twelve", "fifteen",
             "fifty", "twenty", "thirty", "forty", "hundred",
             "thousand", "million", "dollars"}
_NAME_RE = re.compile(r"^[A-Z][a-z]+$")
_NUM_RE = re.compile(r"^\$?\d[\d,\.]*$")


def _norm(t: str) -> str:
    return re.sub(r"[^a-z0-9$]", "", (t or "").lower())


def extract_slots(tokens: list) -> dict:
    """Return {slot_type: [(token_text, confidence), ...]} for the
    load-bearing slots present in this utterance's token stream.
    tokens are AsrToken(text,start,end,confidence).
    """
    slots: dict[str, list] = {"verb": [], "person": [], "date": [],
                              "amount": []}
    for i, tk in enumerate(tokens):
        raw = (getattr(tk, "text", "") or "").strip()
        c = float(getattr(tk, "confidence", 0.5) or 0.0)
        n = _norm(raw)
        if not n:
            continue
        if i <= 1 and n in _VERBS:
            slots["verb"].append((raw, c))
        elif n in _VERBS and not slots["verb"]:
            slots["verb"].append((raw, c))
        if _NAME_RE.match(raw.strip(".,!?")) and n not in _DAYS:
            slots["person"].append((raw, c))
        if n in _DAYS:
            slots["date"].append((raw, c))
        if n in _NUMWORDS or _NUM_RE.match(raw.strip(".,!?")):
            slots["amount"].append((raw, c))
    return {k: v for k, v in slots.items() if v}


def slot_trust(utt) -> tuple[str, str, dict]:
    """Returns (verdict, reason, detail). verdict is FIRE or CONFIRM.
    CONFIRM whenever a present load-bearing slot is below the bar OR
    no actionable verb was confidently heard. Never FIRE on a
    low-confidence load-bearing slot (the hard invariant the P3 gate
    asserts: zero blind fires).
    """
    toks = getattr(utt, "tokens", []) or []
    slots = extract_slots(toks)

    if not slots.get("verb"):
        return ("CONFIRM", "no_confident_action_verb", slots)

    weakest = 1.0
    weak_slot = ""
    for stype, items in slots.items():
        mn = min(c for _t, c in items)
        if mn < weakest:
            weakest, weak_slot = mn, stype
    if weakest < SLOT_CONF_BAR:
        return ("CONFIRM", f"low_conf_slot:{weak_slot}={round(weakest,3)}",
                slots)
    return ("FIRE", f"all_slots_ok>= {SLOT_CONF_BAR}", slots)


def confirm_question(utt, detail: dict) -> str:
    """One short confirmation. Names the uncertain slot so the wearer
    can correct it in one reply (never a bombardment)."""
    base = (getattr(utt, "text", "") or "").strip()
    return f"Did you mean: {base[:80]!r}? (reply yes / correct it)"
