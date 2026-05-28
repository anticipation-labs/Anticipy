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


def words_with_conf(text: str, tokens: list) -> list[tuple]:
    """parakeet emits SUBWORD tokens (R, ep, ly, ...) with a clean
    detokenized `text`. Reconstruct WORD-level (word, confidence) by
    walking subword tokens in order and accumulating their normalized
    characters until they cover the next text word; the word's
    confidence is the MIN of its subword confidences (a word is only
    as trustworthy as its weakest piece). Deterministic, robust to
    punctuation and casing. The original word (with case) is kept so
    name detection still works.
    """
    words = re.findall(r"[A-Za-z0-9$']+", text or "")
    out: list[tuple] = []
    ti = 0
    n_tok = len(tokens)
    for w in words:
        target = _norm(w)
        if not target:
            continue
        buf = ""
        mn = 1.0
        consumed = 0
        while ti < n_tok and len(buf) < len(target):
            tk = tokens[ti]
            piece = _norm(getattr(tk, "text", "") or "")
            ti += 1
            if not piece:
                continue
            buf += piece
            mn = min(mn, float(getattr(tk, "confidence", 0.5) or 0.0))
            consumed += 1
        if consumed == 0:
            out.append((w, 0.5))           # no aligned tokens -> uncertain
        else:
            out.append((w, round(mn, 4)))
    return out


def extract_slots(text: str, tokens: list) -> dict:
    """Load-bearing slots from RECONSTRUCTED words (verb / person /
    date / amount), each carrying its weakest-subword confidence.
    """
    wc = words_with_conf(text, tokens)
    slots: dict[str, list] = {"verb": [], "person": [], "date": [],
                              "amount": []}
    for i, (w, c) in enumerate(wc):
        n = _norm(w)
        if not n:
            continue
        if n in _VERBS and (i <= 2 or not slots["verb"]):
            slots["verb"].append((w, c))
        if _NAME_RE.match(w.strip(".,!?")) and n not in _DAYS and i > 0:
            slots["person"].append((w, c))
        if n in _DAYS:
            slots["date"].append((w, c))
        if n in _NUMWORDS or _NUM_RE.match(w.strip(".,!?")):
            slots["amount"].append((w, c))
    return {k: v for k, v in slots.items() if v}


def slot_trust(utt, secondary=None, ultra=False) -> tuple[str, str, dict]:
    """Returns (verdict, reason, detail). verdict is FIRE or CONFIRM.
    CONFIRM whenever a present load-bearing slot is below the bar OR
    no actionable verb was confidently heard. Never FIRE on a
    low-confidence load-bearing slot (the hard invariant the P3 gate
    asserts: zero blind fires).
    """
    toks = getattr(utt, "tokens", []) or []
    text = getattr(utt, "text", "") or ""
    slots = extract_slots(text, toks)

    if not slots.get("verb"):
        return ("CONFIRM", "no_confident_action_verb", slots)

    # Corrected option (b), narrow scope. The mandatory confirm
    # fires ONLY when BOTH hold:
    #  (1) the action is in the FROZEN engine's existing ultra-high
    #      class (ultra_high or money, the 3-hour-rule carve-out
    #      class) -- passed in as `ultra`, read via the existing
    #      comms.classify_criticality seam, NOT redefined here; AND
    #  (2) a load-bearing slot is uncertain: parakeet's own min
    #      confidence below the bar OR not corroborated by the
    #      independent second ASR.
    # Normal / high-but-not-ultra actions are NEVER gated here even
    # with a name/date/amount; they proceed and the frozen engine
    # applies its own rules. Binding guarantee: zero blind-fire on an
    # ultra-high action with an uncertain load-bearing slot.
    # not ultra-high -> never gated here; the frozen engine decides.
    if not ultra:
        return ("FIRE", "proceed(non_ultra)", slots)

    # ULTRA-HIGH: it may FIRE only if its load-bearing CONTENT is
    # present, parakeet-confident, AND strongly corroborated by the
    # independent ASR. An ultra-high action with NO identifiable
    # content slot (the who/what/how-much was destroyed into garbage
    # that no longer classifies as a name/amount/date) is the most
    # dangerous case (wire money to ???; send the contract to ???) ->
    # uncertain by definition -> CONFIRM. This guarantees the binding:
    # zero blind-fire on an ultra-high action with an uncertain
    # load-bearing slot. Over-confirming a CLEAN-but-uncorroborated
    # ultra-high action is the accepted, honestly-reported cost of
    # scoped option (b); normal/high true-pass is untouched.
    content = {st: slots[st] for st in ("person", "amount", "date")
               if st in slots}
    if not content:
        return ("CONFIRM",
                "ultra_high+uncertain_slot:no_content_slot(destroyed)", slots)

    s2w: set = set()
    s2 = ""
    if isinstance(secondary, str):
        s2 = re.sub(r"\s+", " ",
                    " " + re.sub(r"[^a-z0-9 ]", " ", secondary.lower()) + " ")
        s2w = set(s2.split())
    for stype, items in content.items():
        mn = min(c for _t, c in items)
        if mn < SLOT_CONF_BAR:
            return ("CONFIRM",
                    f"ultra_high+uncertain_slot:low_conf:{stype}="
                    f"{round(mn, 3)}", slots)
        for w, _c in items:
            if not (s2w and _corroborated(w, s2, s2w)):
                return ("CONFIRM",
                        f"ultra_high+uncertain_slot:uncorroborated:"
                        f"{stype}:{w!r}", slots)
    return ("FIRE", "ultra_high+content_confident_corroborated", slots)


_NUM_EQUIV = {
    "0": "zero", "1": "one", "2": "two", "3": "three", "4": "four",
    "5": "five", "6": "six", "7": "seven", "8": "eight", "9": "nine",
    "10": "ten", "15": "fifteen", "20": "twenty", "50": "fifty",
}


def _corroborated(word: str, s2: str, s2w: set) -> bool:
    """The independent ASR corroborates this slot word if a
    PHONETICALLY close word appears in the second transcript. Exact
    match is too strict: proper names are out-of-vocabulary and
    spelled differently by an independent char-CTC model even when
    BOTH heard the name correctly ('Dana' vs 'dane'), which falsely
    flagged every clean name (measured). Fuzzy similarity tolerates
    that spelling variance (clean name -> a close word exists ->
    corroborated) while a genuinely corrupted slot (parakeet's
    confident wrong/hallucinated word vs the other model's unrelated
    output) has NO close word -> not corroborated. Digit/number-word
    equivalence is handled exactly so clean amounts are not flagged."""
    import difflib

    n = _norm(word)
    if not n:
        return True
    cands = {n}
    if n in _NUM_EQUIV:
        cands.add(_NUM_EQUIV[n])
    for k, v in _NUM_EQUIV.items():
        if n == v:
            cands.add(k)
    for c in cands:
        if c in s2w or f" {c} " in s2:
            return True
    # phonetic/fuzzy: any second-model word similar enough to the
    # parakeet slot word (ratio tuned from the measured clean-name vs
    # corrupted-slot separation).
    best = 0.0
    for w2 in s2w:
        if abs(len(w2) - len(n)) > 4:
            continue
        r = difflib.SequenceMatcher(None, n, w2).ratio()
        if r > best:
            best = r
    # STRONG corroboration required. This is only ever applied to
    # ULTRA-HIGH actions (normal/high are never gated), so a strict
    # bar can only add safe confirmations on ultra-high and cannot
    # harm normal-risk true-pass. A genuinely corrupted slot will not
    # reach a strong independent-model match; a clean one will.
    return best >= 0.80


def confirm_question(utt, detail: dict) -> str:
    """One short confirmation. Names the uncertain slot so the wearer
    can correct it in one reply (never a bombardment)."""
    base = (getattr(utt, "text", "") or "").strip()
    return f"Did you mean: {base[:80]!r}? (reply yes / correct it)"
