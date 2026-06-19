"""REVIEW-INFER — infer the structured task from a remembered line, for DISPLAY ONLY.

This is the inference applied to the SAFE display path (the daily review), NOT to
acting. For each inert remembered line we infer

    {task, people, due_phrase, confidence}

so the owner can SEE the unspoken task above the raw line they actually said. The raw
line stays the ground truth; the inference is metadata for the human to skim.

WHY THIS CAN NEVER FIRE (the load-bearing claim):
  - It reads ONLY the inert ``remembered_lines`` table (RememberList) and writes ONLY a
    DISTINCT cache table ``remembered_enrichment`` whose columns are
    (line_id, task, people, due_phrase, confidence, enriched_ts). There is NO due_ts /
    remind_ts / trigger / status / fired_at field — the only fields the TriggerWatcher
    and list_open_loops ever read — so nothing here can become a (delayed) action.
  - ``due_phrase`` is the literal spoken words ("by Friday", "at 3"), a STRING for the
    eye, never a parsed timestamp. ``enriched_ts`` is a cache-bookkeeping stamp (when we
    computed the row), not a time-to-fire; the trigger path does not read this table.
  - It never creates an open_loop, never calls the decider / harm-line / TriggerWatcher,
    never touches a memory drawer. It is a pure read-derive-cache loop off to the side.

ECONOMICS: enrich ONCE per line and cache the result keyed by the line id. On each pull
we enrich only the lines that have no cache row yet (and only within the recent window
the review shows), then join the cache back on. A page reload re-uses the cache and does
no work for already-enriched lines.

EXTRACTION: deterministic + conservative by default (free, CI-safe, reproducible). The
honesty rule (no-overclaim) is enforced by VENT/sarcasm detection: a vent, a wish, a
pure-narration line, or a line with no real deliverable gets confidence "low" and an
EMPTY task rather than an invented one — the raw line is still shown regardless. A cheap
model may take over behind ANTICIPY_MEMORY_MODE=live (the seam); its JSON output is
sanitized through the SAME display-only contract (any time-to-fire key it returns is
dropped on the floor).
"""
from __future__ import annotations

import json
import re
import time
from typing import Dict, List, Optional


def _extract_people(text: str) -> List[str]:
    """Reuse the capturer's people heuristic (display-only, no side effects). Imported
    lazily to avoid a capture<->review_infer import cycle (capture imports this module)."""
    from .capture import extract_people
    return extract_people(text)

# The EXACT cache columns. Note what is ABSENT and must stay absent: NO due_ts,
# remind_ts, trigger, status, fired_at, or any time-to-fire field. ``due_phrase`` is a
# human STRING ("by Friday"); ``enriched_ts`` is when we computed the row (cache age),
# never when anything is due. Adding a time-to-fire field is what would make this
# actionable, so it is structurally kept out here just as in remembered_lines.
_ENRICH_COLS = ("line_id", "task", "people", "due_phrase", "confidence", "enriched_ts")

CONF_HIGH = "high"
CONF_MED = "med"
CONF_LOW = "low"

# ---------------------------------------------------------------------------
# Vent / non-task detection (the honesty guard). Mirrors the SHAPES the proactive
# triage treats as confidently-NOT-a-task, but is a SEPARATE, self-contained copy so
# this display path never imports or perturbs the decision/trigger code. When any of
# these match we refuse to claim a task (empty task, low confidence) — acting on a vent
# is the cardinal sin, and over-claiming one in the review is the display-side echo of
# it. The raw line is shown regardless, so refusing to extract loses nothing.
# ---------------------------------------------------------------------------
_VENT = re.compile(
    r"\bi should just\b"                       # "I should just quit my job"
    # "scream" in any vent framing: gonna/going to/could/want to/wanna/just wanna scream
    r"|\bi'?(?:m| am)? ?(?:gonna|going to|could|just )?(?:wann?a|want to)? ?scream\b"
    r"|\bi'?d (?:lose|kill|die|scream|cry|murder|strangle)\b"
    r"|\b(?:kill me|shoot me|end me)\b"                       # "kill me now"
    r"|\bi (?:hate|can'?t stand|loathe|despise)\b"           # "I hate this/my job/everything"
    r"|\bi(?:'?m| am) so done\b"
    r"|\b(?:ugh|meh|eh|sigh)\b"
    # "whatever" as a dismissive interjection ("ugh whatever") — NOT the quantifier
    # "pay whatever it costs" / "whatever works for you", which is a real instruction.
    r"|\bwhatever\b(?!\s+(?:it|you|he|she|they|we|i|works?|costs?|happens?|the|amount|price|else|that|is|sounds?)\b)"
    r"|\bcan'?t wait to (?:waste|sit through|deal with)\b"
    r"|\boh (?:great|sure|wonderful|fantastic|joy)\b"        # sarcasm openers
    # "yeah right" / "oh sure" sarcasm retorts (triage's _RP_RESOLVED kills these; the
    # display guard was deaf to them, so "yeah right I'll call the dentist back at 3pm"
    # was over-claimed as a HIGH-confidence task — the sarcasm-as-task hole).
    r"|\byeah right\b|\bas if\b|(?<!make )\bsure,?\s*i'?(?:ll| will)\b"
    # sarcastic-impossible future: "I'll just magically find ten extra hours". The word
    # "magically" in a spoken personal-day line is the sarcasm tell — a real task never
    # asks the assistant to do something "magically". (Closed the cardinal-sin hole where
    # "Sure, I'll just magically find ten extra hours" rode its "I'll" into an ACT.)
    r"|\bmagically\b"
    # threat-of-destruction-of-an-object vent ("I'm going to throw my laptop") — exasperation,
    # never a handoff; no one asks an assistant to throw/smash their own hardware.
    r"|\bi'?m (?:gonna|going to) (?:throw|chuck|toss|hurl|smash|launch|yeet)\b"
    r"|\b(?:throw|chuck|hurl|smash) (?:my|this|the) (?:laptop|computer|phone|monitor|keyboard)\b"
    # death/breakdown hyperbole ("…till I drop dead", "until I collapse") and emotional-
    # breakdown verbs as the content of a line ("add 'cry in the parking lot' to my calendar").
    r"|\bdrop dead\b|\b(?:till|until) i (?:die|drop|collapse|pass out)\b"
    r"|\b(?:cry|sob|weep|bawl)\b"
    # "(officially|totally|…) lost it" = going crazy. Intensifier REQUIRED so the literal
    # "I lost it" (= misplaced an object → a real find/help task) is never swallowed.
    r"|\b(?:officially|finally|totally|completely|honestly|basically|nearly|almost) lost it\b"
    r"|\bso (?:fun|great|much fun)\b"
    # "just thinking out loud / musing / riffing" — an explicit hypothetical-aloud frame, never a
    # committed task ("just thinking out loud — send a message to the team saying I quit").
    r"|\b(?:just |merely |simply )?thinking out loud\b|\bthinking aloud\b|\bjust (?:musing|riffing|venting)\b"
    r"|\bmove to a beach\b|\bwin the lottery\b|\bquit my job\b",
    re.I,
)
# A RETRACTION / self-cancel of a just-stated task ("schedule it ... scratch that", "book it, no —
# hold off", "... we might cancel"). DISTINCT from the cart/draft BOUND "don't buy/send" (which
# is_vent_shape deliberately KEEPS as a no-purchase bound on a prep card): this lists ONLY the
# unambiguous cancel phrases, so a prep task's "don't send it" survives while a real retraction
# silences the task. Ambiguous "hold on" (filler vs cancel) is deliberately excluded.
_RETRACTION = re.compile(
    r"\b(?:never ?mind|scratch that|forget it|hold off|on second thought|"
    r"nix that|cancel that|disregard that|belay that|we might cancel|might just cancel)\b",
    re.I,
)
# A trailing self-cancelling hedge ("... probably.", "we'll see") makes it a non-plan. A
# clause-final LAUGH / JOKE tag does the SAME (this MIRRORS triage's _TRAILING_HEDGE, which
# this display guard had diverged from): a laugh-hedged commitment self-cancels into a
# joke/vent ("remind me to never agree to a 7am meeting again, lol"). Kept clause-final
# only — "lol that meeting" mid-line is not a self-cancel, and every audited breach line
# CLOSES on the laugh. Without this, infer_line() returned a non-empty task at med/high and
# press-go mapped it to a real write_memory step — a joke persisted as a task (cardinal sin).
_TRAILING_HEDGE = re.compile(
    r"\b(?:probably|maybe|perhaps|hopefully|we'?ll see|i guess|or something"
    r"|lol|lmao|lmfao|rofl|haha+|jk|just kidding|kidding)\b[\s.!…\"')]*$",
    re.I,
)
# The LAUGH/JOKE subset of the trailing hedge, clause-final. This is the joke-marker
# half of the vent FAMILY (so the durable-card / active-drawer guards — is_vent_shape —
# also catch a laugh-hedged line), kept distinct from the generic "probably/we'll see"
# hedge which is a self-cancel but not an emotional vent.
_LAUGH_HEDGE_VENT = re.compile(
    # the laugh/joke token may carry ONE trailing softener ("jk obviously", "lol man") before
    # the clause ends — an explicit short list, NOT \w+, so "kidding aside, send it" (which
    # means SERIOUSLY) is never swallowed as a joke.
    r"\b(?:lol|lmao|lmfao|rofl|haha+|jk|just kidding|kidding)\b"
    r"(?:\s+(?:obviously|though|lol|haha|guys|ha|man))?[\s.!…\"')]*$",
    re.I,
)
# Hyperbolic / destructive exasperation no assistant could (or should) run — exasperated
# venting, not a real handoff (MIRRORS triage's _DELEGATE_VENT). Two shapes: (1) a "forever"
# / "for the rest of my life" / "and never come back" tail on a schedule/vacation/time-off
# ask ("schedule a vacation for me forever") is a wish, not a bookable event; (2) a
# destructive verb over a whole/entire personal life-asset scope ("delete my whole calendar",
# "wipe my entire inbox", "burn it all down") is hyperbole. Both must yield an EMPTY task.
_HYPERBOLE = re.compile(
    r"\b(?:forever|for ?ever|for the rest of my life|for good|and never (?:come back|return)"
    r"|till the end of time|for eternity|permanently and never)\b"
    r"|\b(?:delete|wipe|erase|burn|torch|nuke|trash|scrap|blow up|set fire to)\b"
    r"[\w' ]{0,30}?\b(?:whole|entire|everything|all of|all my"
    r"|(?:my|this|the|that)\s+(?:calendar|inbox|schedule|email|account|life|day|week|"
    r"job|career|to-?do list|todos?))\b"
    r"|\bburn it all down\b",
    re.I,
)
# Pure-despair / rhetorical-hopelessness: no task, just hopelessness, which triage was
# defaulting to ASK (an unnecessary interruption — the small echo of the cardinal sin).
# Two narrow shapes: (1) the rhetorical "why does everything ... so hard / like this / even
# matter" frame; (2) a destructive verb over the speaker's LIFE / existence ("cancel my
# entire life", "ruin my life", "end it all") — deliberately NOT over calendar/inbox/schedule,
# which are real cancelable objects handled by the normal command path.
_DESPAIR = re.compile(
    r"\bwhy (?:does|do|is|are|must|can'?t|cant|would)\b[\w' ,]{0,30}?"
    r"\b(?:everything|nothing (?:ever )?works?|so hard|this hard|have to be"
    r"|even matter|matter anymore|like this|so difficult|impossible|my life)\b"
    r"|\b(?:cancel|delete|end|ruin|escape|abandon|quit) (?:my )?(?:entire |whole |damn )?life\b"
    r"|\bend it all\b|\bi give up on (?:life|everything|it all)\b",
    re.I,
)
# Retraction / countermand — the speaker calls the action OFF; not a standing task.
# NOTE: "don't forget (to)" is the OPPOSITE — a commitment to remember — so the bare
# "don't/do not" countermand is scoped to NOT precede "forget" (a negative lookahead).
_COUNTERMAND = re.compile(
    r"\b(?:don'?t|do not)\s+(?!forget\b)\w"
    r"|\b(?:never ?mind|scratch that|forget it|hold off|on second thought)\b",
    re.I,
)


def is_vent_shape(text: str) -> bool:
    """The EMOTIONAL-vent / sarcasm / joke / hyperbole shapes (the _VENT family): kill-me,
    I-hate, move-to-a-beach, I-could-scream, ugh/whatever, sarcasm openers ("yeah right"),
    a clause-final laugh/joke tag ("..., lol"), and destructive/"forever" hyperbole. This is
    the guard the owner CARD shaper and the active-drawer capture gate use, because a vent /
    joke must never become a durable card or active memory. It deliberately does NOT include
    the countermand ("don't buy"), which in an owner command is a deliberate no-purchase
    BOUND on a cart-prep card, not a retraction of a non-existent task."""
    raw = (text or "").strip()
    if not raw:
        return False
    return bool(_VENT.search(raw) or _LAUGH_HEDGE_VENT.search(raw)
                or _HYPERBOLE.search(raw) or _DESPAIR.search(raw)
                or _RETRACTION.search(raw))


def is_vent(text: str) -> bool:
    """Single source of truth for 'this line is a vent / sarcasm / joke / self-cancel /
    retraction, NOT a task'. Acting on a vent — or persisting it as a durable actionable/
    profile memory — is the cardinal sin, so every path that could create durable state from
    owner speech (the active-drawer capture gate, the remember-card persister, the press-go
    inference) gates on THIS. It is the SUPERSET of is_vent_shape: it also catches a trailing
    self-cancel hedge ("... probably.", "..., lol") and a countermand ("never mind", "forget
    it"), which are non-tasks on the inference/persist path."""
    raw = (text or "").strip()
    if not raw:
        return False
    return bool(is_vent_shape(raw) or _TRAILING_HEDGE.search(raw)
                or _COUNTERMAND.search(raw))

# A real first-person commitment / task shape. High recall is fine here — the vent guard
# above runs FIRST, and confidence downgrades anything thin. These are the everyday
# obligation phrasings (the same family the capturer's _COMMIT and the 5 prior misses use).
# RECALL FIX: an optional intensity adverb may sit between the first-person subject and the
# commit verb ("I really need to email the landlord", "I just have to call the dentist") —
# the bare lexicon was deaf to it and silently dropped the commitment. The adverb is OPTIONAL
# so the plain "I need to ..." shape is unchanged; the vent guard still runs first.
_ADV = r"(?:really|actually|just|definitely|totally|gonna|kinda|honestly|seriously)?\s*"
_COMMIT = re.compile(
    r"\bi'?ll\b|\bi will\b|\bi've got to\b|\bi gotta\b|\bgotta\b|"
    r"\bremind me\b|\bdon'?t forget\b|\bmake sure\b|\bi told\b|\bi promised\b|"
    r"\bi said i'?d\b|\bi'?m going to\b|"
    r"\bi\s+" + _ADV + r"(?:need to|have to|want to|should)\b",
    re.I,
)
# An explicit standing imperative ("Renew the domain", "Follow up with the landlord").
_IMPERATIVE_VERB = re.compile(
    r"^\s*(?:please\s+)?(send|email|call|text|book|schedule|reschedule|renew|cancel|"
    r"confirm|follow up|reply|pay|submit|finish|draft|order|pick up|drop off|review|"
    r"set up|remind|message|forward|share|sign up|register)\b",
    re.I,
)

# Due-phrase: the literal spoken time words, kept as a STRING for the eye (never parsed
# to a timestamp). Ordered so the most specific clock wins. This is the SAME vocabulary
# the capturer recognizes, but here it is shown, not grounded.
_DUE_PHRASE = re.compile(
    r"\b(by (?:end of (?:the )?day|eod|noon|midnight|tonight|tomorrow|today|"
    r"this (?:week|weekend|afternoon|evening|morning)|next (?:week|month)|"
    r"mon|tues|wednes|thurs|fri|satur|sun)(?:day)?\b[^,.;!?]*"
    r"|by \d{1,2}(?::\d{2})?\s*(?:am|pm)?\b"
    r"|at \d{1,2}(?::\d{2})?\s*(?:am|pm)?\b"
    r"|before (?:it lapses|it expires|the deadline|friday|monday|the meeting|end of \w+)\b"
    r"|tomorrow morning|tomorrow afternoon|tomorrow|tonight|this (?:week|weekend)|"
    r"next week|end of (?:the )?day|eod|by friday|by monday)\b",
    re.I,
)

# Lead-in fillers we trim off the front of a derived task imperative. The optional adverb
# (_ADV) mirrors _COMMIT so "I really need to email the landlord" trims cleanly to "Email
# the landlord" rather than leaking the adverb into the displayed task.
_LEADIN = re.compile(
    r"^(?:i'?ll|i will|i've got to|i gotta|gotta|"
    r"remind me to|don'?t forget to|make sure (?:to|i)|i should|"
    r"i'?m going to|i told \w+ i'?d|i promised \w+ i'?d|i said i'?d|"
    r"i told \w+ i would|please|"
    r"i\s+" + _ADV + r"(?:need to|have to|want to|should))\s+",
    re.I,
)
_VERB_CAP = {
    "send": "Send", "email": "Email", "call": "Call", "text": "Text", "book": "Book",
    "schedule": "Schedule", "renew": "Renew", "cancel": "Cancel", "confirm": "Confirm",
    "follow": "Follow", "reply": "Reply", "pay": "Pay", "submit": "Submit",
    "finish": "Finish", "draft": "Draft", "order": "Order", "review": "Review",
    "pick": "Pick", "drop": "Drop", "set": "Set", "remind": "", "get": "Get",
    "reschedule": "Reschedule",
}


def _imperative(text: str) -> str:
    """Turn 'I told Sam I'd send the deck' -> 'Send Sam the deck'-ish imperative.

    Conservative: strip the first-person lead-in, capitalize the leading verb, trim a
    trailing due-phrase from the task body (it is surfaced separately). Pure string work;
    if nothing reduces cleanly we fall back to a tidied version of the raw line.
    """
    t = re.sub(r"\s+", " ", (text or "").strip().rstrip(".!?"))
    body = _LEADIN.sub("", t).strip()
    if not body:
        body = t
    # drop a trailing spoken due-phrase from the task body (shown separately)
    body = _DUE_PHRASE.sub("", body).strip(" ,.;")
    body = re.sub(r"\s+", " ", body)
    if not body:
        return ""
    # capitalize the leading word so it reads as an imperative
    first, _, rest = body.partition(" ")
    cap = _VERB_CAP.get(first.lower())
    if cap == "":          # e.g. "remind" lead handled by _LEADIN already
        return body[:1].upper() + body[1:]
    if cap:
        body = (cap + (" " + rest if rest else "")).strip()
    else:
        body = body[:1].upper() + body[1:]
    return body[:120].strip()


def infer_line(text: str, people_hint: Optional[List[str]] = None) -> Dict[str, object]:
    """Infer {task, people, due_phrase, confidence} for ONE remembered line. DISPLAY-ONLY.

    Returns a plain dict with NO time-to-fire field. A vent / sarcasm / hedged / retracted
    / no-deliverable line yields task="" and confidence="low" (we do not invent a task).
    """
    raw = (text or "").strip()
    people = list(people_hint) if people_hint else _extract_people(raw)
    due_m = _DUE_PHRASE.search(raw)
    due_phrase = re.sub(r"\s+", " ", due_m.group(0)).strip(" ,.;") if due_m else None

    # Honesty guard: refuse to claim a task on a vent / sarcasm / joke / self-cancel /
    # retraction. is_vent() is the SINGLE SOURCE OF TRUTH (shared with the capture gate and
    # the owner-card shaper), so this display/inference path can never diverge from them and
    # under-guard a joke ("..., lol") or hyperbole the way the old inline check did.
    if is_vent(raw):
        return {"task": "", "people": people, "due_phrase": due_phrase,
                "confidence": CONF_LOW}

    is_commit = bool(_COMMIT.search(raw))
    is_imper = bool(_IMPERATIVE_VERB.search(raw))
    if not (is_commit or is_imper):
        # No commitment shape and no imperative -> probably narration/musing. Don't claim.
        return {"task": "", "people": people, "due_phrase": due_phrase,
                "confidence": CONF_LOW}

    task = _imperative(raw)
    if not task:
        return {"task": "", "people": people, "due_phrase": due_phrase,
                "confidence": CONF_LOW}

    # Confidence: explicit commitment/imperative + a person or a clear deliverable = high;
    # a commitment with neither a named person nor a due-phrase is med; thin is low.
    has_signal = bool(people) or bool(due_phrase)
    if (is_commit or is_imper) and has_signal:
        confidence = CONF_HIGH
    elif is_commit or is_imper:
        confidence = CONF_MED
    else:
        confidence = CONF_LOW
    return {"task": task, "people": people, "due_phrase": due_phrase,
            "confidence": confidence}


# ---------------------------------------------------------------------------
# Optional CHEAP-tier model seam (display-only). Behind ANTICIPY_MEMORY_MODE=live; NEVER
# fires in stub/CI. Its JSON output is sanitized through the SAME display-only contract:
# only {task, people, due_phrase, confidence} survive; any due_ts/remind_ts/trigger key
# the model emits is dropped on the floor here, so the model can never widen the contract.
# ---------------------------------------------------------------------------
_ALLOWED_CONF = {CONF_HIGH, CONF_MED, CONF_LOW}
_PROMPT = (
    "Infer the unspoken TASK from this remembered line, for a read-only daily review.\n"
    "Return STRICT JSON: {\"task\": short imperative or \"\", \"people\": [names], "
    "\"due_phrase\": spoken time words or null, \"confidence\": \"low\"|\"med\"|\"high\"}.\n"
    "If the line is a vent, sarcasm, a wish, or has no real deliverable, return an EMPTY "
    "task with confidence \"low\" — never invent a task. Do NOT return any date, timestamp, "
    "due_ts, or remind field; due_phrase is the literal words only.\nLine: "
)


def _sanitize_model(obj: Dict[str, object], raw: str,
                    people_hint: Optional[List[str]]) -> Dict[str, object]:
    """Force a model dict back onto the display-only contract (drops any extra keys)."""
    task = obj.get("task")
    task = (task if isinstance(task, str) else "").strip()[:120]
    ppl = obj.get("people")
    people = [str(p).strip() for p in ppl if str(p).strip()] if isinstance(ppl, list) else \
        (list(people_hint) if people_hint else _extract_people(raw))
    due = obj.get("due_phrase")
    due_phrase = due.strip()[:60] if isinstance(due, str) and due.strip() else None
    conf = obj.get("confidence")
    confidence = conf if conf in _ALLOWED_CONF else CONF_LOW
    # NOTE: due_ts / remind_ts / trigger / status / fired_at are NOT read — dropped here.
    return {"task": task, "people": people, "due_phrase": due_phrase,
            "confidence": confidence}


async def infer_line_model(gateway, text: str,
                           people_hint: Optional[List[str]] = None) -> Dict[str, object]:
    """CHEAP-tier model inference for ONE line (display-only). Falls back to the rules on
    any failure / empty output, so it can never block or break the review."""
    raw = (text or "").strip()
    try:
        out = await gateway.think(_PROMPT + raw, tier="cheap", caller="review_infer",
                                  json_mode=True, temperature=0.0, max_tokens=160)
        obj = json.loads(out) if out else {}
        if isinstance(obj, dict):
            return _sanitize_model(obj, raw, people_hint)
    except Exception:  # noqa: BLE001 — display path must never raise
        pass
    return infer_line(raw, people_hint=people_hint)


class ReviewEnricher:
    """Owns the DISTINCT, display-only ``remembered_enrichment`` cache table.

    Enriches a remembered line ONCE (keyed by its id), caches {task, people, due_phrase,
    confidence}, and joins the cache back onto pulled rows. Reuses the RememberList's
    MemoryDB connection + lock. Carries NO time-to-fire field and is on NO background
    loop — it is invoked only from the explicit read endpoint, alongside the inert pull.
    """

    def __init__(self, db) -> None:
        self.db = db
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self.db._lock:
            self.db.conn.execute(
                "CREATE TABLE IF NOT EXISTS remembered_enrichment("
                "line_id TEXT PRIMARY KEY, task TEXT, people TEXT, due_phrase TEXT, "
                "confidence TEXT, enriched_ts REAL)"
            )
            self.db.conn.commit()

    def _cached(self, line_ids: List[str]) -> Dict[str, Dict[str, object]]:
        if not line_ids:
            return {}
        out: Dict[str, Dict[str, object]] = {}
        with self.db._lock:
            qs = ",".join("?" * len(line_ids))
            rows = self.db.conn.execute(
                f"SELECT line_id, task, people, due_phrase, confidence "
                f"FROM remembered_enrichment WHERE line_id IN ({qs})",
                tuple(line_ids),
            ).fetchall()
        for r in rows:
            out[r["line_id"]] = {
                "task": r["task"] or "",
                "people": json.loads(r["people"] or "[]"),
                "due_phrase": r["due_phrase"],
                "confidence": r["confidence"] or CONF_LOW,
            }
        return out

    def _store(self, line_id: str, inferred: Dict[str, object]) -> None:
        with self.db._lock:
            self.db.conn.execute(
                f"INSERT OR REPLACE INTO remembered_enrichment({','.join(_ENRICH_COLS)}) "
                f"VALUES ({','.join('?' * len(_ENRICH_COLS))})",
                (line_id, inferred.get("task") or "",
                 json.dumps(inferred.get("people") or []),
                 inferred.get("due_phrase"),
                 inferred.get("confidence") or CONF_LOW,
                 time.time()),
            )
            self.db.conn.commit()

    def enrich_rows(self, rows: List[Dict[str, object]]) -> List[Dict[str, object]]:
        """Attach a display-only ``inferred`` dict to each remembered row, ECONOMICALLY:
        re-use the cache, compute only un-cached lines (deterministic), persist them, and
        return the rows with the inference joined on. Never raises into the caller — on any
        failure a row simply carries no ``inferred`` (the raw line still shows)."""
        ids = [str(r.get("id")) for r in rows if r.get("id")]
        try:
            cache = self._cached(ids)
        except Exception:  # noqa: BLE001
            cache = {}
        out: List[Dict[str, object]] = []
        for r in rows:
            row = dict(r)
            lid = str(r.get("id") or "")
            inferred = cache.get(lid)
            if inferred is None and lid:
                try:
                    inferred = infer_line(str(r.get("text") or ""),
                                          people_hint=r.get("people"))  # type: ignore[arg-type]
                    self._store(lid, inferred)
                except Exception:  # noqa: BLE001 — display only, never block the pull
                    inferred = None
            if inferred is not None:
                row["inferred"] = inferred
            out.append(row)
        return out

    def enrichment_count(self) -> int:
        with self.db._lock:
            r = self.db.conn.execute(
                "SELECT COUNT(*) AS n FROM remembered_enrichment").fetchone()
        return int(r["n"] if r else 0)
