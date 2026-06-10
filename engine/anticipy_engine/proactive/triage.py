"""Room 1 — the triage gate (the bouncer; cheap, first, the cost spine).

Drops the bulk of ambient events that aren't actionable BEFORE any smart model runs.
Tuned for HIGH RECALL: a dropped real event is unrecoverable; a passed junk event is
killed cheaply at the harm-line — so when unsure, PASS. Deterministic by default (zero
model calls, CI-safe + free); a cheap-model tiebreak for genuinely ambiguous events is
behind the flag and NEVER fires in stub. General signals only (no site/test-specific
branches). Recipe + sources: notes/proactive_room1.md.

The gate classifies by SPEECH-ACT SHAPE, not bag-of-words (lap 20260610T062952Z):
an action word counts only where it can be a command — clause-initial imperative
("Order a new charger"), a commitment/request pattern ("I'll...", "can you..."),
a task idiom ("put that on my calendar", "get the answers over to Sam", "someone
needs to chase..."). The same word in noun position is narration, not a task
("Pipeline review.", "Forecast draft: ...", "Lab report draft is at 60%") — passing
those was the dominant false-action source. The confident negatives (retractions,
conditional vents, trailing hedges, already-handled, vocative asides to a present
third party) are the shapes a person uses when there is explicitly NOTHING to do;
they are checked before positive cues, like the hedge rule, because acting (or even
asking) on them is the product's cardinal sin while capture still remembers the line.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Optional, Tuple

# Actionable VERBS / task intents — general task language. These no longer match
# "anywhere in the line": they count only clause-initial (imperative) or inside an
# intent/idiom pattern below. Kept as the canonical vocabulary.
_ACTION: Tuple[str, ...] = (
    "add", "find", "create", "make",
    "send", "book", "schedule", "reschedule", "email", "remind", "call", "text",
    "set up", "draft", "meet", "reply", "wire", "pay", "transfer", "buy", "order",
    "cancel", "delete", "move", "follow up", "forward", "share", "invite", "rsvp",
    "reserve", "sign up", "subscribe", "renew", "submit", "post", "message", "ping",
    "book a", "look up", "search", "research", "compare", "confirm", "register", "purchase",
    "prepare", "compose", "outline", "write up", "put together", "publish", "unsubscribe",
    "deactivate", "enroll", "donate", "withdraw", "deposit", "log in", "sign in", "look into",
    "gather", "review", "wipe", "tweet", "announce",
    "captcha", "grab", "snag", "pull up", "check out", "checkout", "log on", "tell",
)
# Commitment / request / imperative patterns — intent even without a listed verb.
_INTENT: Tuple[str, ...] = (
    r"\bi'?ll\b", r"\bi will\b", r"\bi need to\b", r"\bi have to\b", r"\bi should\b",
    r"\bi want to\b", r"\bi'?m going to\b", r"\bremind me\b", r"\bdon'?t forget\b",
    r"\bmake sure\b", r"\bcan you\b", r"\bcould you\b", r"\bwould you\b",
    # "let's see/hope/be/not/say/face/pretend" are idiomatic musing, not a plan
    r"\blet'?s\b(?!\s+(?:see|hope|be|not|say|face|pretend))",
    r"\bwe need to\b", r"\bgotta\b", r"\bneed to\b", r"\bhave to\b",
    # day names need their own boundary: "by month end" must NOT match via "mon" (it is
    # someone else's demand-narration far more often than a first-person commitment)
    r"\bby (?:(?:mon|tues?|wednes|thurs?|fri|satur|sun)(?:day)?\b|tomorrow\b|tonight\b|"
    r"next\b|end of\b|noon\b|eod\b)",
    r"\bdue\b", r"\boverdue\b",   # deadlines imply a task (general signal)
    # spoken/colloquial: SEPARABLE phrasal verbs (words may sit between the verb + particle)
    r"\bsign\b[\w' ]{0,12}\bup\b", r"\bset\b[\w' ]{0,10}\bup\b", r"\bfill\b[\w' ]{0,10}\b(in|out)\b",
    r"\blog ?in(to)?\b", r"\bsign ?in(to)?\b", r"\bsign on\b", r"\blogin\b",
    r"\bget (past|through|into)\b", r"\btake care of\b", r"\bdeal with\b", r"\bsort out\b",
)
# Pure-noise: fillers / greetings / acks. Exact-match (whole utterance) -> drop.
_FILLER = {
    "um", "uh", "ok", "okay", "thanks", "thank you", "hey", "hi", "hello", "yeah",
    "yep", "nope", "no", "cool", "nice", "lol", "hmm", "right", "sure", "yo", "sup",
    "mm", "mhm", "ok thanks", "okay thanks", "thanks!", "got it", "sounds good",
}
# Hedge-NONSPECIFIC lines ("someday", "at some point") are vents/non-commitments, not tasks —
# a place this gate is confidently negative despite positive cues ("I should ... someday").
# Acting (or asking) on a vent is the product's cardinal sin; capture still remembers the line,
# so dropping it here loses nothing durable. A concrete time anchor cancels the hedge:
# "eventually we need to confirm the venue by Friday" stays actionable.
_HEDGE = re.compile(
    r"\b(?:someday|some day|eventually|at some point|one of these days|one day|sooner or later|"
    r"when i get (?:a chance|around to it))\b", re.I)
_TIME_ANCHOR = re.compile(
    r"\b(?:today|tonight|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"next week|this week|this weekend|by \w+|at \d{1,2}(?::\d\d)?\s*(?:am|pm)?|"
    r"in an? (?:hour|day|week)|in \d+ (?:minutes?|hours?|days?|weeks?)|"
    r"end of (?:the )?day|eod|noon)\b", re.I)
_CONTEXT_ONLY = re.compile(
    r"\b(i|we)\s+(?:was|were|am|are|have been|had been)\s+"
    r"(?:looking at|looking for|browsing|viewing|checking out|considering|shopping for)\b",
    re.I,
)

# ---------- confident negatives (checked BEFORE positive cues) ----------
# Retraction / countermand: the speaker explicitly calls OFF an action ("Hold it...
# don't send anything", "Park it, do not pay", "keep it as a draft"). The most common
# real-world shape is a money/send command immediately self-retracted; an assistant that
# asks anyway is noise. NOTE: "don't forget" is a commitment, not a countermand.
_COUNTERMAND = re.compile(
    r"\b(?:don'?t|do not|won'?t|never)\s+(?:send|pay|buy|order|book|wire|transfer|venmo|"
    r"zelle|text|email|call|submit|post|share|schedule|do)\b"
    r"|\bhold\s+(?:it|on|off|up|that thought)\b"
    # "forget it/that" countermands only clause-initially ("Forget it, I'll go myself");
    # "before I forget it" is the opposite — a reason to capture
    r"|\bpark\s+(?:it|that)\b|\bscratch that\b|\bnever ?mind\b"
    r"|(?:^|[.;!?—-]\s*|,\s*)forget\s+(?:it|that)\b"
    r"|\bleave\s+(?:it|that)\b|\bleave\s+the\s+\w+\s+to\s+(?:her|him|them|me)\b"
    r"|\bkeep\s+(?:it|that|this)\s+(?:as\s+)?a\s+draft\b|\bon second thought\b"
    r"|\bdon'?t\s+need\s+to\s+do\s+anything\b",
    re.I)
# Conditional / counterfactual vents: "If <X> I will simply <absurd>", "I'd lose my
# mind", "Oh sure, I'll just clone myself", "Maybe I'll frame it", "I should just quit".
# First-person futures inside a conditional or sarcastic frame are feelings, not plans.
_CONDITIONAL_VENT = re.compile(
    r"^(?:ugh,?\s+|ha\.?\s+|oh,?\s+)?if\b.{0,100}\bi(?:'ll| will|'d| would| have to| gotta)\b"
    r"|\bi(?:'d| would)\b(?!\s+(?:like|love|rather|prefer|want))"
    r"|^(?:oh,?\s+)?maybe i\b"
    r"|\boh,?\s+sure\b"
    r"|\bi should just\b",
    re.I)
# Deferral / self-handled scheduling of one's own attention ("I'll deal with that
# later", "I will look at it Sunday", "need to check with her mom", "keep an eye on") —
# the person is parking it or consulting another human; nothing for the assistant yet.
_DEFERRAL = re.compile(
    r"\bi(?:'ll| will)\s+(?:deal with|get to|handle|look at|think about|figure out)\s+"
    r"(?:it|that|this|them)\b"
    r"|\bdeal with (?:that|it|this) later\b|\bkeep an eye on\b"
    r"|\b(?:need to|i'?ll|i will|gotta|should)\s+check with\b",
    re.I)
# Already handled / handled by someone else ("already in the group chat", "she handled
# ours", "he can grab Jonah today, one less thing") — the loop is closed; stay silent.
_ALREADY_HANDLED = re.compile(
    r"\balready\s+(?:handled|done|sent|booked|ordered|paid|sorted|covered|in the)\b"
    r"|\bone less thing\b"
    r"|\b(?:he|she|they)\s+(?:handled|covered|grabbed|took care of|can grab|can handle|"
    r"can take|has it|have it)\b"
    r"|\b(?:he|she|they)'?s\s+(?:doing|handling|bundling|covering|got)\b",
    re.I)
# Trailing hedge: an utterance that ENDS on "probably / hopefully / eh / we'll see"
# self-cancels the commitment ("I'll read it on the bike. Probably.").
_TRAILING_HEDGE = re.compile(
    r"\b(?:probably|maybe|perhaps|hopefully|eh|meh|we'?ll see|i guess|or something)\b"
    r"[\s.!…\"']*$",
    re.I)

# ---------- task idioms (positive even without a clause-initial verb) ----------
# "put/get/goes/stick/block/need ... on|in|to my/the calendar" — THE canonical spoken
# calendar command ("That goes on the calendar now", "I need that on my calendar").
_CAL_PUT = re.compile(
    r"\b(?:put|puts|putting|get|gets|getting|go|goes|going|add|adds|adding|make|makes|"
    r"stick|sticks|throw|throws|block|blocks|blocking|need|needs|needed|drop|drops|"
    r"fix|fixes|update|updates|change|changes|correct|corrects|move|moves)\b"
    r"[^.;!?]{0,60}\b(?:on|in|into|onto|to)\s+(?:my|the|his|her|our)\s+calendar\b",
    re.I)
# "block <time> to <time>" — calendar hold phrased as a time range ("block 9 to noon",
# "block Monday 8 to 9").
_CAL_BLOCK = re.compile(
    r"\bblock\b[^.;!?]{0,40}?\b(?:\d{1,2}(?::\d{2})?\s*(?:am|pm)?|noon|midnight)\s*"
    r"(?:to|until|till|through|-|–)\s*(?:\d{1,2}(?::\d{2})?\s*(?:am|pm)?|noon|midnight)\b",
    re.I)
# "put/add ... in the cart" — spoken cart add.
_CART_PUT = re.compile(
    r"\b(?:put|add|stick|throw|toss|drop)\b[^.;!?]{0,60}"
    r"\b(?:in|into|to)\s+(?:my\s+|the\s+)?(?:cart|basket|bag)\b",
    re.I)
# Causative get: "get the inspection scheduled", "get those answers over to Sam" —
# an imperative that delegates the doing.
_CAUSATIVE_GET = re.compile(
    r"\b(?:get|gets)\b[^.;!?]{0,60}\b(?:scheduled|booked|sent|drafted|confirmed|done|"
    r"ordered|fixed|signed|filed|submitted|over to)\b",
    re.I)
# Delegation: "someone should/needs to <do X>", "have someone <do X>" — a task whose
# owner is unassigned is exactly what an assistant exists to pick up (ask-first).
_DELEGATE = re.compile(
    r"\b(?:have|get|ask|tell)\s+someone\b"
    r"|\bsomeone\s+(?:should|needs?\s+to|has\s+to|please)\b",
    re.I)
# "deadline" counts only with first-person skin in the game; "the paralegal flagged the filing
# deadline is Thursday" is narration the memory keeps, not a command.
_DEADLINE = re.compile(r"\bdeadline\b", re.I)
_FIRST_PERSON = re.compile(r"\b(?:i|we|my|our|me)\b", re.I)

# ---------- clause-initial imperative machinery ----------
_CLAUSE_SEP = re.compile(r"[.;!?:\n…]+|\s+[-–—]+\s+")
_WORDS_RE = re.compile(r"[A-Za-z][A-Za-z'\-]*|\d[\w:]*")
# words that may precede the verb in a spoken imperative ("Just wire the vendor...", "ok so
# first book the table")
_SKIP_LEAD = {
    "just", "please", "also", "then", "and", "so", "ok", "okay", "now", "first",
    "hey", "oh", "go", "gotta", "really", "honestly", "seriously", "definitely",
    "sure", "actually", "yes", "yeah", "ugh", "fine", "again", "quick", "quickly",
}
# two-word phrasal imperatives
_PHRASAL_IMP = {
    ("set", "up"), ("sign", "up"), ("look", "up"), ("look", "into"), ("check", "out"),
    ("write", "up"), ("put", "together"), ("read", "up"), ("pull", "up"), ("follow", "up"),
}
# verbs that open a bare imperative on their own ("Order a new charger.")
_STRONG_IMP = {
    "add", "find", "create", "make", "send", "schedule", "reschedule", "remind", "buy",
    "wire", "pay", "cancel", "delete", "move", "forward", "invite", "reserve", "renew",
    "submit", "confirm", "register", "purchase", "prepare", "compose", "publish",
    "unsubscribe", "deactivate", "enroll", "donate", "withdraw", "gather", "wipe",
    "tweet", "announce", "reply", "meet", "follow", "subscribe", "ping", "rsvp",
    "research", "update",
}
# verbs that double as everyday NOUNS ("call block", "lunch order", "pipeline review",
# "forecast draft") — imperative only with an object-ish next word ("call him",
# "order a charger", "review the doc", "text Mom").
_NOUN_PRONE_IMP = {
    "call", "text", "order", "review", "draft", "outline", "message", "post", "email",
    "deposit", "transfer", "search", "grab", "snag", "share", "book", "tell",
}
_OBJ_NEXT = {
    "a", "an", "the", "my", "our", "your", "his", "her", "their", "this", "that",
    "these", "those", "some", "more", "me", "him", "them", "us", "it", "mom", "dad",
    "everyone", "one", "two",
}
# words that can open a sentence and must never be mistaken for a vocative name
_NOT_A_NAME = (
    {"the", "a", "an", "i", "it", "we", "he", "she", "they", "that", "this", "there",
     "my", "our", "your", "his", "her", "their", "what", "who", "why", "how", "when",
     "where", "can", "could", "would", "will", "don", "do", "let", "lets", "maybe",
     "morning", "evening", "afternoon", "today", "tomorrow", "tonight", "monday",
     "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "january",
     "february", "march", "april", "may", "june", "july", "august", "september",
     "october", "november", "december", "note", "status", "new", "update", "reminder",
     "mrs", "mr", "ms", "dr", "if", "but", "after", "before", "everyone", "someone",
     "nothing", "everything", "wait", "hold", "stop", "remember"}
    | _FILLER | _SKIP_LEAD | _STRONG_IMP | _NOUN_PRONE_IMP
)


@dataclass
class TriageConfig:
    action_cues: Tuple[str, ...] = _ACTION
    intent_patterns: Tuple[str, ...] = _INTENT
    min_tokens: int = 2          # 0/1-token utterances are noise


class Triage:
    """The bouncer. `actionable(text)` decides survive-vs-drop with NO smart model in stub."""

    def __init__(self, gateway=None, config: Optional[TriageConfig] = None, mode: Optional[str] = None) -> None:
        self.gateway = gateway
        self.cfg = config or TriageConfig()
        self.mode = mode or os.environ.get("ANTICIPY_MEMORY_MODE", "stub")
        self._intent_re = [re.compile(p) for p in self.cfg.intent_patterns]
        self.smart_calls = 0

    # ---- positive shapes ----

    def _positive(self, t: str, raw: str) -> bool:
        if any(r.search(t) for r in self._intent_re):
            return True
        if _CAL_PUT.search(t) or _CAL_BLOCK.search(t) or _CART_PUT.search(t):
            return True
        if _CAUSATIVE_GET.search(t) or _DELEGATE.search(t):
            return True
        if _DEADLINE.search(t) and _FIRST_PERSON.search(t):
            return True
        return self._imperative(raw)

    @staticmethod
    def _imperative(raw: str) -> bool:
        """A clause that OPENS with an action verb is a command; the same verb later in
        the clause is usually a noun or narration ('I love sending postcards')."""
        for clause in _CLAUSE_SEP.split(raw):
            words_raw = _WORDS_RE.findall(clause)
            if len(words_raw) < 3:   # "Call block." / "Bed." — too short to be a command
                continue
            words = [w.lower() for w in words_raw]
            i = 0
            while i < len(words) and words[i] in _SKIP_LEAD:
                i += 1
            if i >= len(words):
                continue
            w = words[i]
            nxt_raw = words_raw[i + 1] if i + 1 < len(words_raw) else ""
            nxt = nxt_raw.lower()
            if (w, nxt) in _PHRASAL_IMP:
                return True
            if w in _STRONG_IMP:
                return True
            if w in _NOUN_PRONE_IMP and (
                nxt in _OBJ_NEXT or nxt_raw[:1].isupper() or nxt[:1].isdigit()
            ):
                return True
        return False

    @staticmethod
    def _vocative_aside(raw: str) -> bool:
        """'Jordan can you pull the freight numbers' / 'Casey just wire grandma...' — the
        speaker is addressing a PRESENT third party by name; the request is theirs, not
        the assistant's. Fires only on Name-initial lines with a direct-request shape;
        name-as-subject narration ('the professor moved office hours...') does not fire."""
        words_raw = _WORDS_RE.findall(raw)
        if len(words_raw) < 3:
            return False
        first = words_raw[0]
        if not re.fullmatch(r"[A-Z][a-z]+", first) or first.lower() in _NOT_A_NAME:
            return False
        if re.search(r"\b(?:can|could|would|will)\s+you\b", raw, re.I):
            return True
        j = 1
        while j < len(words_raw) and words_raw[j].lower() in {"just", "please"}:
            j += 1
        if j < len(words_raw):
            w, nxt = words_raw[j].lower(), (words_raw[j + 1].lower() if j + 1 < len(words_raw) else "")
            if w in _STRONG_IMP or (w, nxt) in _PHRASAL_IMP or w in _NOUN_PRONE_IMP and nxt in _OBJ_NEXT:
                return True
        return False

    # ---- the gate ----

    def actionable(self, text: str) -> bool:
        """True -> survives to the harm-line; False -> dropped (no smart model touched in stub)."""
        raw = (text or "").strip()
        t = raw.lower().rstrip(".!?")
        if not t or t in _FILLER:
            return False
        if len(re.findall(r"[a-z0-9']+", t)) < self.cfg.min_tokens:
            return False
        # confident negatives — each is a shape that explicitly means "nothing to do";
        # checked BEFORE positive cues (like the hedge rule, ledger gate-S3)
        if _COUNTERMAND.search(t):
            return False
        if _ALREADY_HANDLED.search(t):
            return False
        if _DEFERRAL.search(t):
            return False
        if _CONDITIONAL_VENT.search(t):
            return False
        if _TRAILING_HEDGE.search(t):
            return False
        if _HEDGE.search(t) and not _TIME_ANCHOR.search(t):
            return False   # hedged non-commitment (a vent shape)
        if self._vocative_aside(raw):
            return False
        if self._positive(t, raw):
            return True
        if _CONTEXT_ONLY.search(t):
            return False
        # ambiguous: no positive signal, not obvious filler. Stub -> drop (deterministic, free).
        # Live -> a cheap-model tiebreak MAY rescue it (bias: pass when in doubt). Never in CI.
        if self.mode == "live" and self.gateway is not None:
            return self._tiebreak(text)
        return False

    def _tiebreak(self, text: str) -> bool:  # pragma: no cover (live-only; never in the free suite)
        try:
            from ..core.gateway import CHEAP
            import asyncio
            prompt = ("Is the user's utterance an actionable task/request/commitment (something an "
                      "assistant could act on), vs ambient chatter/observation? Answer yes or no only.\n"
                      f"Utterance: {text}")
            raw = (asyncio.get_event_loop().run_until_complete(
                self.gateway.think(prompt, tier=CHEAP, caller="triage")) or "").lower()
            self.smart_calls += 1
            return "yes" in raw and "no" not in raw.split()  # bias handled by the harm-line downstream
        except Exception:
            return True  # fail OPEN (high recall): on any tiebreak error, pass it down
