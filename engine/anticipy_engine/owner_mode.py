"""Owner Action Engine intake.

This is the shared front door for the owner operating path: typed transcript,
MP3 transcript, live listening, and pay-to-try all become the same ugly stream of
observed lines. The job here is not to obey clean commands. It is to pull the
small number of actionable needles out of normal daily speech, create durable
task cards, and leave the rest as memory/noise.
"""
from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from .core.envelopes import new_id
from .live_memory.review_infer import is_vent, is_vent_shape
from .shared.invoice_draft import match_invoice_draft_ask
from .shared.note_task import match_internal_note

OwnerSource = Literal["pay_to_try", "start_listening", "mp3", "transcript", "typed", "app", "mac_mic", "pendant_phone"]
OwnerDisposition = Literal["do", "ask", "remember", "blocked"]
OwnerRoute = Literal["api", "browser", "voice_text", "memory"]


class OwnerObservedLine(BaseModel):
    line_no: int
    text: str
    # When True this line is a REAL task the model pulled out of a VENTED breath
    # ("email Sarah the budget" inside "...honestly I should just quit..."). It must
    # be CAUGHT — but it may NEVER auto-act in the heat: the spine/preview downgrade
    # any do/act disposition to ask (confirm-first), and it is never executed. This is
    # the lever that lets a vent-adjacent task be surfaced WITHOUT ever committing the
    # cardinal sin (a vent producing an act). Pure-vent clauses never become a line.
    force_ask: bool = False
    # When True the MOAT model CONFIDENTLY extracted this as a clean real task (vent=False) from
    # casual/vague speech ("I owe my mom a call" -> "call mom"; "I gotta do that email of the thing
    # next weekend"). The model is the brain; the deterministic regex triage must NOT silently VETO
    # a model-caught task into nothing. If the spine would otherwise drop it (triage too conservative
    # on loose phrasing), it is surfaced as a confirm-first ASK instead — UNLESS the deterministic
    # floor flags it a vent or money/detrimental (the only hard overrides). Never an auto-act.
    moat_task: bool = False
    # Index of the RAW transcript line this task was split from by the moat — lets the same-source
    # semantic-dedup merge sub-clauses of ONE sentence without ever merging across separate lines.
    src_idx: int = -1
    # True when the RAW source line was a money ACTION (refund/wire/pay + signal). The moat sometimes
    # TRUNCATES the money target off a fragment ("refund X back to my card" -> "refund X"), which would
    # let the fragment escape the money gate; this flag carries the raw-line money truth so the spine
    # ALWAYS blocks the fragment. Money is the hard stop — it can never be lost to truncation.
    money_src: bool = False


class OwnerTaskCard(BaseModel):
    id: str = Field(default_factory=new_id)
    source: str
    line_no: int
    source_text: str
    title: str
    disposition: OwnerDisposition
    route: OwnerRoute
    action: str
    args: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.75
    reason: str = ""
    status: str = "open"
    proof: list[dict[str, Any]] = Field(default_factory=list)
    # Execution outcome (STAGE B item 2): what the engine actually DID with this card —
    # {decision, goal_id, ask_id, goal_state}. None until an execution path runs it.
    execution: dict[str, Any] | None = None
    # Autonomy mode (packet 02) the engine assigned this card — one of autonomy.MODES, with a
    # one-line reason. Persisted onto the durable record (SEAM 2) so GET /owner/cards carries it
    # and the UI board can pick the lane/verb (the "On it — you can stop me" vs Yes/Not-now split).
    autonomy_mode: str | None = None
    autonomy_why: str | None = None


class OwnerIngestResult(BaseModel):
    source: str
    observed_lines: list[OwnerObservedLine]
    cards: list[OwnerTaskCard]
    ignored_line_count: int


_TIMEISH = re.compile(
    r"\b(today|tonight|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"this afternoon|this morning|this evening|next week|before \w+|by \w+|"
    r"at\s+\d{1,2}(:\d\d)?\s*(am|pm)?|\d{1,2}(:\d\d)?\s*(am|pm))\b",
    re.I,
)
_PICKUP = re.compile(r"\b(pick\s*up|pickup|drop\s*off|school|kids?|children|child|daycare)\b", re.I)
_REMEMBER = re.compile(
    r"\b(remind me|don't let me forget|dont let me forget|remember to|make sure i|make sure to|"
    r"i need to|need to|gotta|i have to|i should|i told .* i'?d)\b",
    re.I,
)
# C22: routing tokens must stay generic verbs/nouns — never vocabulary tuned to the
# persona bank or the directive's sample transcript (pre-games Stage B scoring).
_SEND = re.compile(r"\b(send|email|text|tell|reply|follow up|circle back|draft)\b", re.I)
# "order" gates as the SPEND-VERB shape (harm.py's money rule: "order the beakers",
# "order lunch"), never the bare noun — "the supply order", "a change order" and
# "the order email" are work vocabulary, not purchases (requested-action scope).
_ORDER_VERB = r"order (?:a|an|the|me|us|food|lunch|dinner|takeout|delivery|coffee|\d)"
# "grab" is a shopping verb ("grab me a coffee maker") but NOT in the noun "grab bar(s)" (a bathroom
# safety rail) — the bare-noun false match used to shape a descriptive context line as a browser task
# (F-011 over-catch). The negative lookahead keeps the verb, drops the product-noun.
_BROWSER = re.compile(r"\b(grab(?!\s+bars?\b)|buy|" + _ORDER_VERB + r"|purchase|checkout|cart|find|look up|research)\b", re.I)
_MONEY = re.compile(r"\b(pay|buy|" + _ORDER_VERB + r"|purchase|checkout|wire|venmo|zelle|cashapp|credit card|payment)\b", re.I)
_NO_BUY = re.compile(
    r"\b(don'?t buy|do not buy|no buying|don'?t checkout|do not checkout|"
    r"no checkout|cart only|just.*cart)\b",
    re.I,
)
_PROFILE = re.compile(
    r"\b(my name is|i am a|i'm a|i work at|i work as|i live in|i prefer|i like|i hate|"
    r"my wife|my husband|my partner|my kid|my daughter|my son|my boss|my contractor)\b",
    re.I,
)
_VENT_OR_JOKE = re.compile(
    r"\b(kill me|this is stupid|whatever|ugh|i swear|i hate this|"
    r"can'?t believe|sarcasm|lol|haha)\b",
    re.I,
)
# RECALL FALLBACK: a clause-INITIAL scheduling/contact action verb (the prompt's named set
# book/schedule/call/meet, plus the reschedule/rebook synonyms) plus an explicit time signal
# is a bare actionable line ("Book the dentist at 3pm tomorrow", "Call the plumber this
# afternoon", "Schedule the review for Monday") — these carry no "remind me"/"I need to"
# lead-in, no person-send shape, and no money/browser word, so every shape above was deaf to
# them. Clause-initial anchor (after a few spoken lead words) keeps narration out ("the
# dentist booked me for 3pm" is subject-led, never fires); the time signal (_TIMEISH) is
# REQUIRED so a bare "call the dentist" with no anchor still falls through. The verb set is
# kept tight on purpose: open phrasals like "set up ..." stay UNSHAPED so the proven spine
# keeps catching+executing them as execute_owner_task (the F17 catch path), and an anaphoric
# "Book the Tuesday morning one" still resolves through the spine's memory slot path. The
# cardinal-sin guard (is_vent_shape) has already returned above, so a hyperbolic "schedule a
# vacation for me forever" never reaches here.
_BARE_ACTION_VERB = re.compile(
    r"^(?:(?:just|please|also|then|and|so|ok|okay|now|first|hey|oh)[,\s]+)*"
    r"(book|schedule|reschedule|rebook|call|meet|block|hold|reserve|set aside)\b",
    re.I,
)
# An anaphoric booking that defers to memory context ("Book the Tuesday morning ONE with
# Marta") is resolved by the spine's slot path, not this flat regex card — let it fall
# through so the spine keeps its richer create_event resolution.
_ANAPHORIC_SLOT = re.compile(r"\bthe\s+[\w\s]{0,30}?\bone\b", re.I)
_FILLER = {
    "yeah",
    "yep",
    "ok",
    "okay",
    "uh",
    "um",
    "mhm",
    "right",
    "cool",
    "sure",
    "anyway",
    "whatever",
    "fine",
}


def _clean_line(raw: str) -> str:
    text = raw.strip()
    text = re.sub(r"^\[?\d{1,2}:\d\d(:\d\d)?\]?\s*", "", text)
    text = re.sub(r"^[A-Z][A-Za-z0-9 _-]{0,24}:\s+", "", text)
    return re.sub(r"\s+", " ", text).strip(" -\t")


# SENTENCE-SPLITTER ABBREVIATIONS (integration/recall fix): the sentence splitter breaks on
# any period+space, so "Meet Dr. Lee at 3pm" was severed at "Dr." — tearing the task ("Meet
# ... Lee") from its time ("at 3pm") and producing a stub clause and a timeless one. A period
# that belongs to a known title/abbreviation is NOT a sentence end, so it must not split. The
# set is the common spoken/written titles and time/Latin abbreviations; matched
# case-INSENSITIVELY on the token just before the period (so "dr." mid-stream is also safe).
# Multi-dot abbreviations ("a.m.", "p.m.", "e.g.", "i.e.") are protected by their own pattern
# because the internal dots would otherwise each look like a sentence break.
_ABBREVIATIONS = (
    "dr", "mr", "mrs", "ms", "prof", "st", "ave", "rd", "blvd", "apt", "dept",
    "jr", "sr", "vs", "etc", "no", "fig", "approx", "min", "hr", "hrs", "sgt",
    "lt", "gen", "col", "capt", "rev", "gov", "sen", "rep", "messrs", "mt", "ft",
)
# Dotted run-on abbreviations end in an internal-dot form ("a.m.", "p.m.", "e.g.", "i.e.",
# "a.k.a.", "u.s.", "p.s."). The internal dot is REQUIRED so a bare time token without dots
# ("3pm.") is NOT mistaken for "p.m." — that period is a genuine sentence end and may split.
_DOTTED_ABBREV = re.compile(
    r"(?:[ap]\.m|e\.g|i\.e|a\.k\.a|u\.s|p\.s)\.$", re.I
)
_SENTENCE_BOUNDARY = re.compile(
    r"(?<=[.!?])\s+", re.I
)


def _sentence_split(text: str) -> list[str]:
    """Split a run of text into sentences WITHOUT severing a known abbreviation period.

    The naive ``re.split(r"(?<=[.!?])\\s+")`` cuts after every period, so "Meet Dr. Lee at
    3pm" loses its time. This walks candidate boundaries and rejects any boundary whose
    preceding token is a known title/abbreviation (Dr/Mr/Mrs/Ms/St/...) or a dotted
    abbreviation (a.m./p.m./e.g.) — keeping the task glued to its time. Non-abbreviation
    periods still split normally so genuine multi-sentence input is still separated.
    """
    parts: list[str] = []
    start = 0
    for m in _SENTENCE_BOUNDARY.finditer(text):
        head = text[start:m.start()]
        # the token immediately before the boundary period, e.g. "Dr." -> "dr"
        prev = re.search(r"([A-Za-z]+)\.\s*$", head)
        token = prev.group(1).lower() if prev else ""
        if token in _ABBREVIATIONS or _DOTTED_ABBREV.search(head):
            continue  # not a real sentence end — keep the abbreviation glued forward
        seg = text[start:m.start()].strip()
        if seg:
            parts.append(seg)
        start = m.end()
    tail = text[start:].strip()
    if tail:
        parts.append(tail)
    return [p for p in parts if p.strip()]


# MULTI-INTENT SPLIT (integration/recall fix): a single line that bundles a SAFE action and a
# MONEY action ("email Sam the deck and venmo grandma $20") was classified as one card; the
# money interlock fired first and the whole line became a single blocked-money card — silently
# DROPPING "email Sam the deck". The fix splits such a line into independent intent clauses on
# coordinating boundaries so each clause is shaped on its own: the safe clause -> draft, the
# money clause -> blocked handback. The split is DELIBERATELY narrow (see _split_intent_clauses
# guards) — it only fires when isolating a money clause from a co-located safe action clause.
# The connectors are coordinating conjunctions ONLY ("and", "then", "and then", "also", ";").
# A bare comma is deliberately NOT a connector: it is too often a continuation/apposition of
# the SAME intent ("reply to Maya, send her the 200 we owe" is one money intent to one person,
# not a safe+money mix), and an internal comma in one clause ("pickup to 3 today, please remind
# me") must never be torn apart. The conjunction boundary is what separates genuinely distinct
# intents ("email Sam the deck AND venmo grandma $20"), so benign multi-part speech (and the
# pinned NOISY_DAY / spine-money cards) is not over-split.
_CLAUSE_CONNECTORS = re.compile(
    r"\s*(?:;|,?\s+and then\s+|,?\s+then\s+|,?\s+and also\s+|,?\s+also\s+|\s+and\s+)\s*",
    re.I,
)


def _split_intent_clauses(text: str) -> list[str]:
    """Split a co-located multi-intent line into independent clauses.

    Returns the list of clauses ONLY when splitting isolates a money clause from a non-money
    clause; otherwise returns ``[text]`` unchanged so the line stays one card. Each emitted
    clause is independently runnable: "email Sam the deck and venmo grandma $20" ->
    ["email Sam the deck", "venmo grandma $20"]. The non-money clause survives as a draft and
    the money clause is blocked on its own — never the whole line dropped because one clause is
    money. Splitting is suppressed unless BOTH a money clause and a safe action clause result.
    """
    if not _has_money_signal(text):
        return [text]
    # CARVE-OUT: a cart-prep line with an explicit no-purchase BOUND ("...put it in the cart
    # ... don't buy it") is ONE deliberate reversible command, not a money+safe mix — its
    # "buy" is a ceiling owned by the _BROWSER branch. Never sever the bound from the command.
    if _NO_BUY.search(text):
        return [text]
    raw_clauses = [c.strip(" ,.;") for c in _CLAUSE_CONNECTORS.split(text) if c and c.strip(" ,.;")]
    if len(raw_clauses) < 2:
        return [text]
    money_clauses = [c for c in raw_clauses if _has_money_signal(c)]
    safe_clauses = [c for c in raw_clauses if not _has_money_signal(c)]
    # Only split when the line genuinely mixes a money clause WITH a safe action clause AND a
    # safe clause is itself actionable (carries a send/browser/scheduling/pickup verb). A
    # trailing fragment with no verb ("and the rest") is not its own intent — keep it whole.
    if not money_clauses or not safe_clauses:
        return [text]
    if not any(_SEND.search(c) or _BROWSER.search(c) or _BARE_ACTION_VERB.search(c)
               or _PICKUP.search(c) for c in safe_clauses):
        return [text]
    return raw_clauses


def _split_transcript(text: str) -> list[OwnerObservedLine]:
    raw_parts: list[str] = []
    for raw_line in (text or "").splitlines():
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        if len(raw_line) > 220:
            raw_parts.extend(p for p in _sentence_split(raw_line) if p.strip())
        else:
            raw_parts.append(raw_line)
    if not raw_parts and text.strip():
        raw_parts = [p for p in _sentence_split(text.strip()) if p.strip()]
    observed: list[OwnerObservedLine] = []
    line_no = 0
    for raw in raw_parts:
        cleaned = _clean_line(raw)
        if not cleaned:
            continue
        # A single cleaned line may bundle a safe action and a money action — split it into
        # independent intent clauses so neither is dropped (the safe one drafts, the money one
        # blocks). Most lines return unchanged; only a co-located money+safe line is split.
        for clause in _split_intent_clauses(cleaned):
            clause = clause.strip()
            if not clause:
                continue
            line_no += 1
            observed.append(OwnerObservedLine(line_no=line_no, text=clause))
    return observed


def _is_filler(text: str) -> bool:
    words = [w.strip(".,!?;:'\"").lower() for w in text.split()]
    return len(words) <= 5 and all(w in _FILLER or not w for w in words)


# Capitalized words that are NOT names — sentence starters, adjectives, fillers, vent openers. A moat
# reframe can garble a line into "send Great great ..." (from a vent opener "Great morning, just
# great"); _person_hint must NOT invent a recipient named "Great" and draft toward a non-existent
# person (the bug-hunt's wrong_entity). Erring toward no-recipient is safe (it just won't name a person).
_NOT_A_NAME = {
    "Great", "Good", "Okay", "Ok", "Also", "Then", "And", "So", "Now", "First", "Hey", "Oh", "Sure",
    "Thanks", "Please", "Yeah", "Yes", "No", "Nope", "Maybe", "Just", "Actually", "Honestly", "Ugh",
    "The", "This", "That", "It", "Them", "Him", "Her", "Today", "Tomorrow", "Tonight", "Morning",
    "Well", "Right", "Anyway", "Whatever", "Fine", "Cool", "Wow", "Ah", "Um", "Hi", "Hello",
}


def _person_hint(text: str) -> str | None:
    m = re.search(r"\b(?:send|email|text|tell|reply to|follow up with)\s+([A-Z][a-z]+)\b", text)
    if m and m.group(1) not in _NOT_A_NAME:
        return m.group(1)
    m = re.search(r"\b([A-Z][a-z]+)\s+(?:needs|asked|is waiting|wanted)\b", text)
    return m.group(1) if (m and m.group(1) not in _NOT_A_NAME) else None


# A STRONG directed-send shape (send/email/text/draft, not the weak tell/reply) — used by the
# vent-adjacent backstop so a sarcastic "I'll tell Karen off" never qualifies.
_DIRECTED_SEND = re.compile(r"\b(send|email|text|draft)\b", re.I)


def vent_adjacent_directed_task(text: str) -> bool:
    """A CONCRETE, recipient/time-bound task embedded in a VENTED line — a directed send to a
    NAMED person ("...but remind me to send Maya the email"), or a pickup/drop-off with a time.
    Deliberately TIGHT: a pure emotional vent (no recipient, no scheduling structure) never
    matches, so promoting such a line to a confirm-first ASK (held, never an auto-act) cannot
    turn a vent into an action — the cardinal-sin floor is preserved. This is the deterministic
    backstop for when the moat fails to split a vent-prefixed line into its embedded obligation
    (the lone 'mixed' miss in the 10k cert); it only ever raises an ASK, never executes."""
    if _DIRECTED_SEND.search(text) and _person_hint(text):
        return True
    if _PICKUP.search(text) and _TIMEISH.search(text):
        return True
    return False


def _has_money_signal(text: str) -> bool:
    """True iff the line MOVES MONEY — the SINGLE SOURCE OF TRUTH for money on the spine is
    harm.py's recipient-agnostic _MONEY_SIGNAL (a currency-symbol/scale amount or a debt/
    obligation noun: owe/rent/deposit/invoice/balance/payment/...) plus its spoken _MONEY_IDIOMS
    (square up, cover the tab, chip in, settle the invoice, ...). owner_mode's own _MONEY regex
    only knows the spend VERBS, so a payment phrased as "send Priya the five hundred we owe" or
    "the deposit of 500 dollars" had no money word and slipped past the person+send branch as a
    benign message. Reusing harm.py's signal closes that. LAZY-imported to avoid any import
    cycle through the proactive package; fails CLOSED to the local verb regex on import error."""
    raw = text or ""
    try:
        from .proactive.harm import _MONEY_IDIOMS, _MONEY_SIGNAL
        if _MONEY_SIGNAL.search(raw) or re.search(_MONEY_IDIOMS, raw, re.I):
            return True
    except Exception:  # pragma: no cover - defensive; never seen in the suite
        pass
    return bool(_MONEY.search(raw))


class OwnerMode:
    """Deterministic first pass for messy owner transcript -> task cards.

    F17 (one brain): on the EXECUTING owner path the proven proactive spine
    (triage -> decider -> harm-line) is the only act/ask/silent decision-maker;
    this regex pass only SHAPES durable cards (title/route/args), pre-gates
    money-shaped browser lines as blocked, and adds silent memory. The seams
    `observe()` and `card_for_line()` exist so ControlCore can interleave the
    spine per line; `ingest()` remains the side-effect-free regex preview.
    """

    def observe(self, text: str) -> list[OwnerObservedLine]:
        """Split a messy transcript into cleaned observed lines (no decisions)."""
        return _split_transcript(text)

    def card_for_line(self, line: OwnerObservedLine, source: str) -> OwnerTaskCard | None:
        """Regex shaping for one observed line (no side effects)."""
        return self._card_for_line(line, source)

    def execution_text_for_card(self, card: OwnerTaskCard) -> str:
        """Text to send through the action spine for a shaped owner card.

        The owner card keeps the exact source text. This only removes an explicit
        no-purchase bound from cart-prep cards so the lower harm-line does not
        mistake "don't buy" for purchase intent while the card args still carry
        payment_allowed=False.
        """
        if card.action != "find_or_cart_without_purchase":
            return card.source_text
        text = _NO_BUY.sub(" ", card.source_text)
        text = re.sub(r"\s+", " ", text).strip(" ,.-")
        return text or card.source_text

    def ingest(self, text: str, source: str = "transcript", meta: dict[str, Any] | None = None) -> OwnerIngestResult:
        del meta  # reserved for clock/device context; kept out of rules for determinism.
        observed = self.observe(text)
        cards: list[OwnerTaskCard] = []
        ignored = 0
        for line in observed:
            card = self._card_for_line(line, source)
            if card is None:
                ignored += 1
            else:
                cards.append(card)
        return OwnerIngestResult(source=source, observed_lines=observed, cards=cards, ignored_line_count=ignored)

    def _card_for_line(self, line: OwnerObservedLine, source: str) -> OwnerTaskCard | None:
        text = line.text
        lowered = text.lower()
        if _is_filler(text):
            return None

        # CARDINAL-SIN GUARD (runs FIRST): a vent / sarcasm / self-cancel / retraction is NOT
        # a task and must never become a durable card — including a "remember" profile card.
        # is_vent() is the SINGLE SOURCE OF TRUTH (shared with the press-go inference and the
        # display path), so the spine agrees with them on what is a vent. It is the SUPERSET of
        # is_vent_shape: beyond the emotional-vent/sarcasm family it ALSO catches a trailing
        # self-cancel hedge ("Remind me to email the landlord, probably.") and a countermand
        # ("Remind me to book the trip. Never mind, forget it.") — the exact "Remind me that..."
        # shapes the spine was ACTING on (creating a reminder card for a self-cancelled line, a
        # Law-2 violation). The ONE carve-out: a cart/research command with an explicit
        # no-purchase BOUND ("...put it in the cart ... don't buy it") reads as a vent only via
        # is_vent()'s countermand arm, but it is a real reversible owner command — so when the
        # line is a browser/cart line with a no-buy bound, the countermand is a deliberate
        # purchase ceiling, not a retraction, and is handled by the _BROWSER branch below (with
        # payment_allowed=False). is_vent_shape (no countermand arm) still gates that line out
        # of the emotional-vent family. The raw line is captured upstream as inert memory
        # regardless; refusing to SHAPE a vent loses nothing durable.
        cart_no_purchase = bool(_BROWSER.search(text) and _NO_BUY.search(text))
        if is_vent(text) and not cart_no_purchase:
            return None
        if cart_no_purchase and is_vent_shape(text):
            return None

        if _PROFILE.search(text):
            return OwnerTaskCard(
                source=source,
                line_no=line.line_no,
                source_text=text,
                title=f"Remember: {text}",
                disposition="remember",
                route="memory",
                action="write_profile_memory",
                args={"memory_text": text},
                confidence=0.82,
                reason="stated preference, identity, or relationship fact",
            )

        # MONEY BEATS PICKUP: "drop the rent check off, $1,450" reads as a 'drop off' care chore but
        # it is a PAYMENT. Money is the hard stop and must be caught FIRST — a pickup/drop-off line
        # carrying any money signal falls through to the money interlock below (blocked), never an
        # auto-executed pickup chore (the relentless bug-hunt's worst breach: a $1,450 rent payment
        # auto-handled as a reversible drop-off). A real pickup ("grab the kids at 3") has no money.
        if (_PICKUP.search(text) and (_TIMEISH.search(text) or _REMEMBER.search(text))
                and not _has_money_signal(text)):
            return OwnerTaskCard(
                source=source,
                line_no=line.line_no,
                source_text=text,
                title="Protect pickup or drop-off timing",
                disposition="do",
                route="api",
                action="create_calendar_or_reminder",
                args={"task_text": text, "kind": "pickup_or_dropoff"},
                confidence=0.86,
                reason="care obligation plus time/reminder signal",
            )

        # MONEY INTERLOCK (hard stop, runs BEFORE the send/message + browser branches): money
        # is the one line the engine never auto-crosses (Law 3). A payment can wear a benign
        # message skin — "email Sam the rent payment of 1200 dollars", "text Priya the five
        # hundred we owe her" — and the person+send branch below would have shaped it as a
        # do/ask draft_or_confirm_message, never blocking the money. The interlock uses the
        # SAME money signal as the harm-line (harm.py's _MONEY_SIGNAL/_MONEY_IDIOMS, the spine's
        # source of truth), so a payment is always routed to the blocked money card first.
        # TWO carve-outs mirror the harm-line exactly: (1) the cart-prep "...in the cart ...
        # don't buy it" line trips the money signal on "buy" but carries payment_allowed=False
        # and is owned by the _BROWSER branch below; (2) an invoice DRAFT/REVIEW shape
        # ("Invoice the client today? No, draft it and let Jordan sanity-check the hours") is an
        # ask-first admin step, not a payment — harm.py strips the bare invoice noun for it, so
        # here it must FALL THROUGH (card_for_line -> None) to let the spine's invoice_draft ask
        # path own it. A real spend on an invoice ("pay the invoice") is not a draft shape and
        # still blocks here.
        # INTERNAL NOTE (NOT money), runs BEFORE the money interlock: "make sure the retainer NOTE
        # is in the CRM before the call", "add a note in the client file about the retainer". A
        # money/obligation word (retainer/invoice/...) names the SUBJECT of an internal record
        # entry — recording a note ABOUT a retainer is reversible admin, never a payment. The word
        # "retainer" alone tripped the money wall and blocked the lawyer's admin note (the seam).
        # match_internal_note refuses any line with a spend/transaction verb, so a real payment
        # ("pay/wire/chase the retainer") never matches here and still blocks below. Routed to a
        # non-binding internal-note prep (prepare-then-stop): the engine has no generic CRM/notes
        # arm wired yet, so this is an honest "here's the note I'd write" prep, not a money block.
        internal_note = match_internal_note(text)
        if not cart_no_purchase and internal_note is not None:
            return OwnerTaskCard(
                source=source,
                line_no=line.line_no,
                source_text=text,
                title="Prepare internal note",
                disposition="do",
                route="api",
                action="prepare_internal_note",
                args={"task_text": text, "destination": "crm_or_record", "binding": False},
                confidence=0.74,
                reason="internal note/record entry — reversible admin, not a payment",
            )
        invoice_draft_ask = match_invoice_draft_ask(text)
        if not cart_no_purchase and not invoice_draft_ask and _has_money_signal(text):
            return OwnerTaskCard(
                source=source,
                line_no=line.line_no,
                source_text=text,
                title="Block money action",
                disposition="blocked",
                route="browser",
                action="prepare_purchase_path_without_payment",
                args={"task_text": text, "payment_allowed": False},
                confidence=0.78,
                reason="money or checkout is a hard stop; prepare but do not pay",
            )

        person = _person_hint(text)
        if person and _SEND.search(text):
            return OwnerTaskCard(
                source=source,
                line_no=line.line_no,
                source_text=text,
                title=f"Prepare message for {person}",
                disposition="ask",
                route="voice_text",
                action="draft_or_confirm_message",
                args={"person": person, "task_text": text},
                confidence=0.81,
                reason="third-party communication should be confirmed before sending",
            )

        if _BROWSER.search(text):
            if _NO_BUY.search(text):
                disposition: OwnerDisposition = "do"
                action = "find_or_cart_without_purchase"
                reason = "shopping/research request explicitly blocks purchase"
            elif _MONEY.search(text):
                disposition = "blocked"
                action = "prepare_purchase_path_without_payment"
                reason = "money or checkout is a hard stop; prepare but do not pay"
            else:
                disposition = "do"
                action = "research_or_find_item"
                reason = "browser-resolvable life-admin task"
            return OwnerTaskCard(
                source=source,
                line_no=line.line_no,
                source_text=text,
                title="Resolve browser task",
                disposition=disposition,
                route="browser",
                action=action,
                args={"task_text": text, "payment_allowed": False},
                confidence=0.76,
                reason=reason,
            )

        if _MONEY.search(text):
            return OwnerTaskCard(
                source=source,
                line_no=line.line_no,
                source_text=text,
                title="Block money action",
                disposition="blocked",
                route="browser",
                action="prepare_purchase_path_without_payment",
                args={"task_text": text, "payment_allowed": False},
                confidence=0.78,
                reason="money or checkout is a hard stop; prepare but do not pay",
            )

        if _REMEMBER.search(text) and not _VENT_OR_JOKE.search(text):
            return OwnerTaskCard(
                source=source,
                line_no=line.line_no,
                source_text=text,
                title="Capture reminder or open loop",
                disposition="do",
                route="api",
                action="create_reminder_or_open_loop",
                args={"task_text": text},
                confidence=0.73,
                reason="explicit remember/commitment signal",
            )

        if "?" in text and ("can you" in lowered or "could you" in lowered) and not _VENT_OR_JOKE.search(text):
            return OwnerTaskCard(
                source=source,
                line_no=line.line_no,
                source_text=text,
                title="Clarify possible request",
                disposition="ask",
                route="voice_text",
                action="ask_clarifying_question",
                args={"task_text": text},
                confidence=0.58,
                reason="possible request but not enough structure to act",
            )

        # FALLBACK: a bare actionable line — a clause-initial scheduling/contact verb plus a
        # concrete time — that none of the shapes above caught. Routed to the same api
        # calendar/reminder action the pickup shape uses; the proven spine (triage -> decider
        # -> harm-line) still makes the real act/ask/silent call downstream. The time signal
        # is required so a vague "call the dentist" with no anchor still falls through to None.
        if (_BARE_ACTION_VERB.search(text) and _TIMEISH.search(text)
                and not _ANAPHORIC_SLOT.search(text) and not _VENT_OR_JOKE.search(text)):
            return OwnerTaskCard(
                source=source,
                line_no=line.line_no,
                source_text=text,
                title="Schedule or place a timed action",
                disposition="do",
                route="api",
                action="create_calendar_or_reminder",
                args={"task_text": text, "kind": "timed_action"},
                confidence=0.7,
                reason="clause-initial scheduling/contact verb with a concrete time",
            )

        return None
