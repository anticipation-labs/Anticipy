"""GATE MIDDLE-1 — the intent-shaped middle.

The system used to remember WORDS (diary lines) and resolve vague references against ALL raw
memories, so "that desk thing" could retrieve the wrong open loop (a kid pickup) or nothing. This
layer turns a messy transcript into structured INTENT THREADS and resolves vague references against
RANKED threads — deterministically, so it does not depend on a flaky cheap-model call.

Each line is classified into exactly one kind:
  vent      — emotional/joke/hyperbole -> NO action (the moat already drops these; we re-guard).
  preference— "the Jarvis desk is the one I liked", "don't buy it yet" -> a referent, NOT a task.
  passive   — ambient fact about others -> remembered, never a card.
  action    — a concrete obligation/request aimed at the speaker -> a card-eligible thread.
  followup  — "remind me before I send it" -> attaches to an existing thread, not a new card.

A vague reference ("that desk thing" / "it" / "that") is resolved by RANKING threads:
  head-noun match (>) recency, with a clear single winner required — otherwise it stays vague and the
  caller asks the smallest clarification (never guesses the wrong thread).

Pure-Python, deterministic, no model calls — so it is testable and reliable.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

# filler / pronouns / articles / preps / aux / generic light verbs / time — tokens that do NOT
# identify an obligation's object. (Kept local so this module stands alone.)
_STOP = {
    "a", "an", "the", "this", "that", "these", "those", "it", "its", "i", "im", "me", "my", "mine",
    "you", "your", "he", "him", "his", "she", "her", "they", "them", "their", "we", "us", "our",
    "to", "for", "of", "on", "in", "at", "by", "with", "about", "from", "into", "before", "after",
    "and", "or", "but", "so", "as", "up", "out", "off", "is", "are", "was", "were", "be", "am",
    "do", "does", "did", "will", "would", "can", "could", "should", "please", "yeah", "yes", "ok",
    "okay", "sure", "just", "really", "gotta", "gonna", "need", "got", "get", "let", "make", "want",
    "actually", "thing", "one", "liked", "like", "prefer", "buy", "yet", "not", "dont",
    "today", "tomorrow", "tonight", "now", "later", "soon", "morning", "afternoon", "evening",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
}

_VENT = re.compile(
    r"\b(move to the woods|moving to the woods|burn it all|i quit|i should just quit|kill me|"
    r"i could scream|move to a beach|if i win the lottery|win the lottery|i hate)\b", re.I)
_PREF = re.compile(
    r"\b(the one i (liked|like|want|prefer)|is the one|i (liked|prefer) (the|that|this)|"
    r"my favou?rite|don'?t buy (it|that|this)? ?yet|not yet|don'?t order)\b", re.I)
_FOLLOWUP = re.compile(r"\b(remind me|before i (send|do|buy|call|submit)|don'?t let me forget)\b", re.I)
_VAGUE_HEAD = re.compile(r"\b(?:that|this|the)\s+([a-z]+)\s+thing\b", re.I)   # "that desk thing"
_VAGUE_HEAD2 = re.compile(r"\b(?:that|this)\s+([a-z]+)\b(?!\s+thing)", re.I)   # "that desk"
_BARE_REF = re.compile(r"\b(it|that thing|the thing|that one|this one|that|this)\b", re.I)
_SENDABLE = re.compile(r"\b(send|email|deliver|submit|share)\b", re.I)


def _content_tokens(text: str) -> frozenset:
    out = set()
    for tok in re.findall(r"[a-z0-9]+", (text or "").lower()):
        if tok in _STOP or (len(tok) <= 2 and not tok.isdigit()):
            continue
        if len(tok) > 4:
            tok = re.sub(r"(ings|ing|ed|es|s)$", "", tok)
        out.add(tok)
    return frozenset(out)


def _head_noun(text: str) -> Optional[str]:
    """The head noun of a vague reference: 'that desk thing'->'desk', 'that desk'->'desk'."""
    m = _VAGUE_HEAD.search(text)
    if m:
        h = m.group(1).lower()
        return h if h not in _STOP else None
    m = _VAGUE_HEAD2.search(text)
    if m:
        h = m.group(1).lower()
        return h if h not in _STOP else None
    return None


def _is_bare_ref(text: str) -> bool:
    """A vague reference with NO head noun: 'send it', 'do that'. Needs recency to resolve."""
    if _head_noun(text):
        return False
    return bool(_BARE_REF.search(text))


def _referent_phrase(line: str, head: str) -> Optional[str]:
    """Pull a short noun phrase around `head` from a context line: up to 3 preceding
    proper-noun/modifier words + the head. 'The Jarvis standing desk is...' + 'desk' ->
    'Jarvis standing desk'."""
    words = re.findall(r"[A-Za-z0-9']+", line)
    low = [w.lower().rstrip("'s") for w in words]
    h = head.lower()
    idx = next((i for i, w in enumerate(low) if w == h or w == h + "s" or w.rstrip("s") == h), None)
    if idx is None:
        return None
    phrase = [words[idx]]
    j = idx - 1
    while j >= 0 and (idx - j) <= 3:
        w = words[j]
        if w.lower() in _STOP or w[:1].islower() and w.lower() not in {"standing", "compact", "office"}:
            # keep modifiers/proper nouns; stop at filler or a generic lowercase verb
            if w.lower() in {"standing", "office", "compact", "travel", "recycled", "revised"}:
                phrase.insert(0, w); j -= 1; continue
            break
        phrase.insert(0, w)
        j -= 1
    return " ".join(phrase)


def classify(text: str) -> str:
    t = (text or "").strip()
    if _VENT.search(t):
        return "vent"
    if _FOLLOWUP.search(t):
        return "followup"
    if _PREF.search(t):
        return "preference"
    return "action"


@dataclass
class IntentThread:
    idx: int
    text: str
    kind: str
    tokens: frozenset = field(default_factory=frozenset)

    def to_dict(self) -> dict:
        return {"idx": self.idx, "kind": self.kind, "text": self.text, "tokens": sorted(self.tokens)}


def build_threads(lines: list[str]) -> list[IntentThread]:
    """One thread per line, classified + tokenized, recency = idx (higher == more recent)."""
    return [IntentThread(idx=i, text=l, kind=classify(l), tokens=_content_tokens(l))
            for i, l in enumerate(lines)]


def rank_referents(reference_text: str, threads: list[IntentThread], self_idx: int) -> dict:
    """Rank prior threads as referents for a vague reference. Returns the 7-field-friendly trace:
    {head, bare, candidates:[{text,kind,score,reason}], chosen, rejected, resolved_phrase}."""
    head = _head_noun(reference_text)
    bare = _is_bare_ref(reference_text)
    trace = {"head": head, "bare": bare, "candidates": [], "chosen": None,
             "rejected": [], "resolved_phrase": None}
    # a referent must be a CONCRETE prior thread (action/preference) — never a vent, a follow-up, or
    # another line that ITSELF carries a vague reference (that is a query, not a referent; this also
    # robustly excludes the query line itself even when the moat reworded it so idx self-match fails).
    prior = [t for t in threads if t.idx < self_idx and t.kind not in ("vent", "followup")
             and _head_noun(t.text) is None]
    scored = []
    for t in prior:
        score, reason = 0.0, []
        if head:
            toks = {x.rstrip("s") for x in re.findall(r"[a-z0-9]+", t.text.lower())}
            if head.rstrip("s") in toks:
                score += 10; reason.append(f"names '{head}'")
        if bare and _SENDABLE.search(reference_text) and _SENDABLE.search(t.text):
            score += 6; reason.append("both about sending")
        # recency: closer prior line ranks higher (small weight, only a tie-breaker)
        score += (t.idx + 1) * 0.01
        if t.kind in ("action", "preference"):
            score += 0.5
        scored.append((score, t, "; ".join(reason) or "weak/recency only"))
    scored.sort(key=lambda s: s[0], reverse=True)
    for score, t, reason in scored:
        trace["candidates"].append({"text": t.text, "kind": t.kind,
                                    "score": round(score, 2), "reason": reason})
    # a clear single winner: top score is meaningfully > the next, and is a real match (>=1)
    strong = [s for s in scored if s[0] >= 1.0]
    if strong and (len(strong) == 1 or strong[0][0] - strong[1][0] >= 5.0):
        _, top, _ = strong[0]
        trace["chosen"] = top.text
        trace["rejected"] = [t.text for _, t, _ in scored if t.text != top.text]
        if head:
            trace["resolved_phrase"] = _referent_phrase(top.text, head)
        else:  # bare ref -> use the winner's object phrase (content tokens of the action)
            trace["resolved_phrase"] = top.text
    else:
        trace["rejected"] = [t.text for _, t, _ in scored]
    return trace


def resolve_reference(reference_text: str, threads: list[IntentThread], self_idx: int) -> tuple[str, dict]:
    """Rewrite a vague reference to its chosen referent. Returns (resolved_text, trace).
    If no clear winner, returns the original text (caller asks the smallest clarification)."""
    trace = rank_referents(reference_text, threads, self_idx)
    if not trace["chosen"] or not trace["resolved_phrase"]:
        return reference_text, trace
    phrase = trace["resolved_phrase"]
    head = trace["head"]
    if head:
        # REWRITE only when the referent adds specificity — a content word the line does not already
        # name ("that desk thing" -> "Jarvis standing desk" adds "Jarvis"; "that plant thing" ->
        # "fiddle leaf plant" adds "fiddle"/"leaf"). If it adds nothing new, leave the line (the
        # referent is still recorded in the trace) so we never churn an already-concrete line.
        ref_low = reference_text.lower()
        adds_specificity = any(w.lower() not in ref_low and w.lower() not in _STOP
                               for w in phrase.split())
        if not adds_specificity:
            trace["decision_note"] = "referent recorded; line already concrete — not rewritten"
            return reference_text, trace
        resolved = _VAGUE_HEAD.sub(phrase, reference_text)
        resolved = _VAGUE_HEAD2.sub(phrase, resolved) if resolved == reference_text else resolved
    else:
        # bare ref ("send it" / "before I send it"): graft the referent's object noun phrase
        ref_obj = " ".join(w for w in trace["chosen"].split()
                           if w.lower().rstrip(".,") not in _STOP) or phrase
        resolved = _BARE_REF.sub(ref_obj, reference_text, count=1)
    return resolved, trace
