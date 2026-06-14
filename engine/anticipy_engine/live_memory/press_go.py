"""PRESS-GO — the default-deny owner approval mapper for the remembered list.

The owner skims the inert remembered list (each line carries a DISPLAY-ONLY inferred
{task, people, due_phrase, confidence}). When the owner presses go on a specific line,
``ControlCore.approve_remembered`` enriches that line (reusing the SAME review inference),
maps the inferred task to ONE closed intent, and gates on a tiny WHITELIST of provably
safe, reversible intents. This module owns the pure, additive mapper + gate; it touches
no decision/trigger/harm code.

THE DEFAULT-DENY CORE (why this is not money-detection whack-a-mole):
  WHITELIST is a frozenset of exactly the reversible intents that can ALSO be independently
  read back live (create_event = a calendar hold, read back via ListEvents; write_memory =
  a standing note, re-read from the local memory store). An intent EXECUTES only if it is
  explicitly IN the set: ``if intent in WHITELIST: execute else: handback``. There is no
  keyword/money test to defeat — an unrecognized, ambiguous, or money/send/message intent
  simply is not in the set, so it CANNOT execute. Money phrased as "send a payment" lands in
  the non-whitelist branch precisely because no money intent is in the set; it is handed back
  to the owner, never approvable into execution. This is the structural fix for the earlier
  reverted version where money phrased as a send reached an executable approval path.

  send_email_draft is reversible (a Gmail DRAFT is never sent) but is NOT in the auto-execute
  set: api_hand has no wired, verified Gmail drafts-READ tool, so a live draft write cannot
  produce a real read-back receipt — it would fail closed to needs_human, and auto-executing
  it would make the "executes with a read-back receipt" claim false for it. So a draft is a
  prepared-HANDBACK: the mapper surfaces the exact draft the owner would create, but returns
  NO executable step, so the owner is shown the draft to create and creates it himself. When
  a verified drafts-read tool is wired (api_hand READ_BACK), it can be re-admitted here.

THE MAPPER is deterministic and conservative. It produces a single pre-built Step for a
whitelisted intent, or falls through to NON-WHITELIST (handback). It NEVER emits a multi
-step or free-text plan, so the orchestrator's planner cannot widen a create_event into a
browser write — the caller drives the ONE pre-built step it returns and asserts that
step's intent is in WHITELIST before any execution.

The whitelist DECISION is keyed off the inferred shape; grounding a concrete event time
reads the RAW spoken line (the due_phrase the review shows is a lossy human string), so a
calendar hold only forms when an explicit clock time is present — never invented.
"""
from __future__ import annotations

import datetime as dt
import re
from typing import Dict, List, Optional, Tuple

from ..core.envelopes import Risk, Step

# The audited AUTO-EXECUTE surface: exactly the reversible intents that can ALSO be
# independently READ BACK live (the receipt is the only currency — Law 4). An intent may
# only auto-execute on press-go if (a) it is reversible AND (b) api_hand has a wired,
# verified read-back tool to re-observe the artifact. Today that is:
#   create_event  -> GoogleCalendar.ListEvents read-back (wired, verified)
#   write_memory  -> a LOCAL note re-read from the memory store (no external tool needed)
# send_email_draft was REMOVED from this set: it is reversible (a Gmail DRAFT never sends),
# but api_hand.READ_BACK["send_email_draft"] is None — no Gmail drafts-read tool is wired
# yet — so a live draft write CANNOT produce a real read-back receipt and would fail closed
# to needs_human. Auto-executing it would make the "executes with read-back" claim false for
# it. Until a verified drafts-read tool is wired (api_hand READ_BACK), a draft is a
# prepared-HANDBACK: the owner is shown the draft to create, and creates it himself. Adding
# send_email/message/browser-write here would reopen the reverted send hole — keep this a
# single audited constant. Default-deny is structural: only an intent IN this set executes.
WHITELIST = frozenset({"create_event", "write_memory"})

# Words that signal an ACTUAL binding send / message / money / browser-write. Any of these
# in the inferred task DENIES the whitelist mappings outright (belt-and-suspenders; the
# set-membership gate already denies any non-set intent). An ambiguous "send" can never
# become a draft and then look approved.
#
# WIDENED (Apollo wave 4) so this belt can never be NARROWER than harm.py's send/money
# vocabulary — the class of bug where a money-idiom ("square up the dinner tab"), a soft-send
# ("email the resignation"), or a send GERUND ("schedule sending the deck") slipped past this
# narrower belt and got mapped into the WHITELIST. We OR IN harm's own money signal /
# idioms / soft-send patterns plus the -ing gerund forms of the send/pay verbs, so a line
# that harm.py would call money/send is also denied here at the shape layer. (The real,
# structural fix is the harm-line gate in ``_harm_refuses`` below, run on the RAW line before
# ANY whitelisted Step is returned; this widening is the second, redundant belt.)
_BINDING_SEND = re.compile(
    r"\b(send|sent|sending|pay|paid|pays|paying|payment|venmo|zelle|wire|wired|wiring|"
    r"transfer|transferring|invoice|invoicing|charge|charging|deposit|depositing|refund|"
    r"slack|message|messaged|messaging|text|texted|texting|dm|post|posting|tweet|tweeting|"
    r"publish|publishing|submit|submitted|submitting|email|emailing|emailed|"
    r"buy|bought|buying|purchase|purchasing|order(?:ed|ing)?|checkout|check out)\b",
    re.I,
)
# Harm.py's own send/money vocabulary, OR'd in so this belt is never narrower than the
# harm-line. Imported as raw pattern strings (compiled here) to keep this module additive
# and pin the two vocabularies together: if harm.py widens money/idioms/soft-send, this
# belt widens with it. Used alongside _BINDING_SEND in the binding test.
from ..proactive.harm import _MONEY_IDIOMS as _HARM_MONEY_IDIOMS  # noqa: E402
from ..proactive.harm import _MONEY_SIGNAL as _HARM_MONEY_SIGNAL  # noqa: E402
from ..proactive.harm import _SOFT_SEND as _HARM_SOFT_SEND  # noqa: E402

# The DETRIMENTAL harm categories that must NEVER be approvable into a press-go execution.
# These are the clearly-detrimental / binding categories from harm.HarmLine — money, any
# binding/casual send, destroy, public-post, sign-up, auth-wall, invoice. NOT included:
# the reversible-safe categories (calendar_hold, note, draft, cart, reservation, research,
# calendar, calendar_event, doc) and the ``unclassified`` fail-safe-ask bucket (a raw
# calendar line that press-go DOES recognize by shape can read ``unclassified`` from the
# harm-line, which must still be allowed to ground a reversible hold — refusing on it would
# wrongly kill the legitimate calendar/note mappings). The gate is keyed off the harm
# CATEGORY, not the broad ``detrimental`` flag, precisely so a fail-safe-ask on a genuinely
# reversible shape does not block it.
_HARM_REFUSE_CATEGORIES = frozenset({
    "money", "binding_send", "casual_send", "destroy", "public",
    "signup", "auth_wall", "invoice_draft",
})

# A self-directed reminder shape, read off the RAW line: "remind me to X", "remember to X",
# "don't forget to X", "note that X". No external party, no send -> a standing note.
_NOTE_RAW = re.compile(
    r"\b(remind me to|remember to|note (?:to self|that)|don'?t forget to|"
    r"make a note|jot (?:down|a note)|log that)\b", re.I)

# Calendar shape word in the inferred task (a meeting/event/appointment kind of thing).
# Grounding to a concrete datetime is REQUIRED and read off the RAW line.
_CALENDAR_SHAPE = re.compile(
    r"\b(meeting|meet|event|appointment|appt|call|sync|standup|stand-up|interview|"
    r"lunch|dinner|coffee|review|1:1|one[- ]on[- ]one|schedule|book)\b", re.I)

# An explicit draft request: an explicit draft verb in the inferred task. "send" alone is
# NOT here (actual-send is non-whitelisted). A draft is reversible (never sent) but is NOT
# auto-executable yet (no wired drafts-read tool -> no live read-back receipt), so a draft
# verb produces a prepared-HANDBACK that SHOWS the owner the draft to create, not a step.
_DRAFT_SHAPE = re.compile(r"\b(draft|drafting|write up|compose)\b", re.I)

# Concrete clock + day grounding, read off the RAW spoken line. Requires BOTH an explicit
# clock time AND a day anchor (relative day or weekday); a vague "soon"/"this week" does
# NOT ground and the calendar mapping falls through to handback (never invent a time).
_CLOCK = re.compile(r"\b(?:at|by|@)?\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", re.I)
_CLOCK_BARE = re.compile(r"\b(?:at|@)\s*(\d{1,2})(?::(\d{2}))?\b", re.I)
_REL_DAY = {"today": 0, "tonight": 0, "tomorrow": 1}
_WEEKDAYS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
             "friday": 4, "saturday": 5, "sunday": 6,
             "mon": 0, "tue": 1, "tues": 1, "wed": 2, "thu": 3, "thurs": 3,
             "fri": 4, "sat": 5, "sun": 6}


def _ground_datetime(raw: str,
                     now: Optional[dt.datetime] = None,
                     tz: Optional[dt.tzinfo] = None) -> Optional[Tuple[str, str]]:
    """Ground the RAW spoken line to a concrete (start_iso, end_iso) 1-hour window, or None.

    Conservative: requires an explicit clock time AND a day anchor. Returns None
    (-> handback) when no concrete clock time can be grounded — never invents one,
    and never crashes on a malformed clock (an out-of-range minute like '2:99' is
    rejected the same as a missing time, exactly like ``duetime._hm``).

    TIMEZONE: the grounding clock is ``now``; pass the OWNER's tz-aware now (built from
    the onboarded timezone) so the produced start/end ISO carry the owner's offset, not
    the server's. ``tz`` is the owner's tzinfo: if given (and ``now`` was server-local),
    ``now`` is converted into it first, so the resulting wall-clock day + offset are the
    owner's. When neither is supplied, falls back to the server-local clock as before.
    """
    text = (raw or "").lower()
    if now is None:
        now = dt.datetime.now(tz) if tz is not None else dt.datetime.now().astimezone()
    elif tz is not None and now.tzinfo is not tz:
        # caller passed a clock but a distinct owner zone: re-anchor to the owner zone so
        # the wall-clock day boundaries (and offset) are the owner's, not the server's.
        now = now.astimezone(tz)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=tz) if tz is not None else now.astimezone()

    # day anchor
    day_offset: Optional[int] = None
    for word, off in _REL_DAY.items():
        if re.search(rf"\b{word}\b", text):
            day_offset = off
            break
    if day_offset is None:
        for word, wd in _WEEKDAYS.items():
            if re.search(rf"\b{word}\b", text):
                ahead = (wd - now.weekday()) % 7
                day_offset = ahead or 7  # next occurrence of that weekday
                break
    if day_offset is None:
        return None

    # clock time — an am/pm clock wins; else an explicit "at N" reads as afternoon if < 8.
    hour: Optional[int] = None
    minute = 0
    m = _CLOCK.search(text)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2) or 0)
        ampm = (m.group(3) or "").lower()
        if ampm == "pm" and hour < 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0
    else:
        mb = _CLOCK_BARE.search(text)
        if mb:
            hour = int(mb.group(1))
            minute = int(mb.group(2) or 0)
            if hour < 8:
                hour += 12  # bare "at 3" on a calendar reads as afternoon
        elif "tonight" in text:
            hour = 19
    # Validate the parsed clock BEFORE building the datetime — a malformed minute (e.g.
    # "2:99") or hour must hand back gracefully, never crash dt.replace(). Same bounds as
    # duetime._hm (0<=minute<=59, 0<=hour<=23). Returning None routes to a handback.
    if hour is None or not (0 <= hour <= 23) or not (0 <= minute <= 59):
        return None

    base = (now + dt.timedelta(days=day_offset)).replace(
        hour=hour, minute=minute, second=0, microsecond=0)
    end = base + dt.timedelta(hours=1)
    return base.isoformat(timespec="seconds"), end.isoformat(timespec="seconds")


# A HARD binding send / money vocabulary — actual send/pay/wire verbs and money signals,
# but deliberately WITHOUT the pure soft-send MEDIUM words (email/message/text/reply/ping).
# A soft-send medium word is the legitimate medium of a reversible DRAFT ("draft the email
# to Priya"), exactly as harm.py treats _SOFT_SEND as benign when a _DRAFT_FRAME is present.
# This is used by the DRAFT branch so widening _BINDING_SEND to cover soft-send (for the
# note/calendar branches) does not wrongly flip a genuine draft into the generic handback.
_HARD_BINDING = re.compile(
    r"\b(send|sent|sending|pay|paid|pays|paying|payment|venmo|zelle|wire|wired|wiring|"
    r"transfer|transferring|invoice|invoicing|charge|charging|deposit|depositing|refund|"
    r"slack|post|posting|tweet|tweeting|publish|publishing|submit|submitted|submitting|"
    r"buy|bought|buying|purchase|purchasing|order(?:ed|ing)?|checkout|check out)\b",
    re.I,
)


def _binding_line(low: str, raw_low: str) -> bool:
    """True iff EITHER the inferred task OR the raw line carries a binding send / money /
    message shape — using BOTH the local widened ``_BINDING_SEND`` belt AND harm.py's own
    money-signal / money-idiom / soft-send vocabulary. This guarantees the press-go belt is
    never NARROWER than the harm-line's send/money detector."""
    for hay in (low, raw_low):
        if not hay:
            continue
        if (_BINDING_SEND.search(hay)
                or _HARM_MONEY_SIGNAL.search(hay)
                or re.search(_HARM_MONEY_IDIOMS, hay, re.I)
                or _HARM_SOFT_SEND.search(hay)):
            return True
    return False


def _hard_binding_line(low: str, raw_low: str) -> bool:
    """True iff EITHER the inferred task OR the raw line carries a HARD binding send / money
    shape (actual send/pay/wire verbs + money signals/idioms), EXCLUDING the pure soft-send
    medium words. Used only by the DRAFT branch: a draft of an email/message is reversible
    (it is never sent), so a soft-send medium word must not deny the draft handback — but a
    real send/pay verb or a money signal still does."""
    for hay in (low, raw_low):
        if not hay:
            continue
        if (_HARD_BINDING.search(hay)
                or _HARM_MONEY_SIGNAL.search(hay)
                or re.search(_HARM_MONEY_IDIOMS, hay, re.I)):
            return True
    return False


def _harm_refuses(raw_line: str) -> Optional[str]:
    """THE structural fix: run the deterministic harm-line + the vent guard on the RAW spoken
    line BEFORE any whitelisted Step is returned. Returns a non-empty REASON string when the
    whitelist mapping MUST be refused (handback), else None.

    Refuse when:
      * ``review_infer.is_vent(raw_line)`` is True — a vent/sarcasm/joke/retraction is the
        cardinal sin to act on (e.g. "Remind me to scream at 3pm" once is_vent widens, plus
        every vent is_vent already catches: "I could scream", "ugh", "kill me", "..., lol"); OR
      * ``harm.HarmLine().assess(raw_line, {}).category`` is a clearly-detrimental / binding
        category (money / binding_send / casual_send / destroy / public / signup / auth_wall /
        invoice_draft). This makes press-go structurally UNABLE to out-loose the harm-line:
        any line the harm-line would stop as money/send/destroy/etc. can no longer be mapped
        into the WHITELIST, regardless of how the press-go shape regexes classify it.

    Keyed off the harm CATEGORY, not the broad ``detrimental`` flag, so a genuine reversible
    shape that the harm-line conservatively reads as ``unclassified`` (fail-safe ask) is NOT
    blocked here — the press-go shape mapper still grounds it. Imports are local to keep this
    additive and avoid any import cycle at module load."""
    raw = (raw_line or "").strip()
    if not raw:
        return None
    try:
        from .review_infer import is_vent
        if is_vent(raw):
            return "raw line reads as a vent / sarcasm / joke / retraction — never act on a vent"
    except Exception:  # noqa: BLE001 — never let a guard import failure open the gate
        pass
    try:
        from ..proactive.harm import HarmLine
        verdict = HarmLine().assess(raw, {})
        if verdict.category in _HARM_REFUSE_CATEGORIES:
            return (f"harm-line stops this as {verdict.category!r} "
                    f"(detrimental / binding) — cannot map into the safe whitelist")
    except Exception:  # noqa: BLE001 — a guard failure must FAIL CLOSED, not open
        return "harm-line could not confirm this line is safe — handing back"
    return None


def map_inferred_to_step(inferred: Dict[str, object], raw_text: str = "",
                         now: Optional[dt.datetime] = None,
                         tz: Optional[dt.tzinfo] = None) -> Dict[str, object]:
    """Map a display-only inferred task to ONE intent + a pre-built Step, or handback.

    ``inferred`` is the review's display-only {task, people, due_phrase, confidence}.
    ``raw_text`` is the spoken line, used ONLY to ground a concrete event datetime (the
    due_phrase the review shows is a lossy human string). ``now``/``tz`` carry the OWNER's
    clock + timezone so a grounded calendar hold's start/end ISO carry the owner's offset
    (not the server's); both are forwarded to ``_ground_datetime``. The whitelist DECISION
    is keyed off the inferred shape; an ambiguous or binding/send/money/message shape returns
    step=None so the gate hands it back. Never produces more than a single whitelisted step.

    Returns a dict:
      whitelisted -> {"intent", "step": Step, "would_do": <human description>}
      otherwise   -> {"intent": None, "step": None, "would_do": <human description>,
                      "non_whitelist_reason": <why>}
    """
    task = str(inferred.get("task") or "").strip()
    people = [str(p) for p in (inferred.get("people") or []) if str(p).strip()]

    if not task:
        # vent / narration — the caller stops before here, but stay safe.
        return {"intent": None, "step": None, "would_do": "",
                "non_whitelist_reason": "no confident inferred task"}

    low = task.lower()
    raw_low = (raw_text or "").lower()
    binding = _binding_line(low, raw_low)

    # STRUCTURAL HARM-LINE GATE (Apollo wave 4): before ANY whitelisted mapping, run the
    # deterministic harm-line + vent guard on the RAW spoken line. If the harm-line stops it
    # as money/send/destroy/signup/auth_wall/public/invoice, OR it reads as a vent, REFUSE
    # the whitelist mapping outright and hand it back. This makes press-go structurally
    # unable to out-loose the harm-line: a money idiom ("square up the dinner tab"), a send
    # gerund ("schedule sending the deck"), or a soft-send ("email the resignation") that the
    # shape regexes might otherwise route into write_memory/create_event is denied here.
    harm_reason = _harm_refuses(raw_text)
    if harm_reason is not None:
        return {"intent": None, "step": None, "would_do": f"Do: {task}",
                "non_whitelist_reason": harm_reason}

    # NOTE shape FIRST (self-directed reminder, no external party). Read off the RAW line
    # because the review strips the "remind me to" lead-in out of the task. A note never
    # sends, so a binding-send word still DENIES it (e.g. "remind me to pay" -> handback).
    if _NOTE_RAW.search(raw_low) and not binding:
        note_text = task
        step = Step(intent="write_memory",
                    args={"kind": "open_loop", "text": note_text, "approved": True},
                    risk=Risk.low)
        return {"intent": "write_memory", "step": step,
                "would_do": f"Save a standing note: {note_text!r}"}

    # CALENDAR shape — REQUIRES a concrete grounded datetime from the RAW line, else handback.
    if _CALENDAR_SHAPE.search(low) and not binding:
        window = _ground_datetime(raw_text, now=now, tz=tz)
        if window is not None:
            start_iso, end_iso = window
            summary = task[:120]
            step = Step(intent="create_event",
                        args={"summary": summary,
                              "start_datetime": start_iso,
                              "end_datetime": end_iso,
                              "approved": True},
                        risk=Risk.needs_confirm)  # a calendar WRITE -> exercises the owner_approved gate
            return {"intent": "create_event", "step": step,
                    "would_do": f"Hold a calendar event {summary!r} {start_iso} - {end_iso}"}
        # a calendar-word task with no groundable concrete time -> handback (don't invent)
        return {"intent": None, "step": None,
                "would_do": f"Schedule: {task}",
                "non_whitelist_reason": "calendar task without a concrete grounded time"}

    # DRAFT shape — an explicit draft verb + a recipient, and NOT a binding-send word.
    # A draft is reversible (a Gmail DRAFT is never sent), but it is NOT auto-executable:
    # api_hand has no wired Gmail drafts-READ tool, so a live draft write cannot produce a
    # real read-back receipt. Rather than auto-execute into a needs_human dead-end (and falsely
    # claim a read-backed execution), we PREPARE a handback: surface the exact draft the owner
    # would create — but return NO step, so the owner is shown the draft to create and creates
    # it himself. (Re-admit to the whitelist + emit a step once a drafts-read tool is wired.)
    if _DRAFT_SHAPE.search(low) and people and not _hard_binding_line(low, raw_low):
        recipient = people[0]
        return {"intent": None, "step": None,
                "would_do": f"Create a Gmail DRAFT to {recipient} (never sent): {task!r}",
                "non_whitelist_reason": ("a Gmail draft can be prepared, but Anticipy cannot "
                                         "yet independently verify the saved draft "
                                         "(no drafts read-back wired) — shown for you to "
                                         "create yourself")}

    # Everything else (actual send, message/Slack, money/binding, browser-write, ambiguous)
    # is NON-WHITELISTED — return no step so the gate hands it back.
    reason = "binding send / message / money / ambiguous — not a provably-safe reversible intent"
    return {"intent": None, "step": None, "would_do": f"Do: {task}",
            "non_whitelist_reason": reason}


def _norm_summary(text: str) -> str:
    """Normalize a human action summary for content-equality (case/whitespace/punct fold)."""
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def action_content_key(intent: object, step) -> Optional[str]:
    """A stable CONTENT key for a whitelisted action: intent + normalized summary +
    grounded start. Two remembered lines that map to the SAME real action (same intent,
    same event summary, same grounded start time) share this key, so press-go can dedupe
    on the ACTION the owner is about to take — not on the line_id. This is the
    idempotency fix: the same task captured twice yields ONE real calendar hold.

    Returns None for a non-whitelisted/None step (those never execute, so never dedupe).
    The key is keyed off the EXACT args the executable Step carries:
      create_event -> intent | normalized(summary) | start_datetime
      write_memory -> intent | normalized(text)
    """
    if step is None or not intent:
        return None
    args = getattr(step, "args", {}) or {}
    if intent == "create_event":
        return "|".join((
            "create_event",
            _norm_summary(args.get("summary")),
            str(args.get("start_datetime") or "").strip(),
        ))
    if intent == "write_memory":
        return "|".join((
            "write_memory",
            _norm_summary(args.get("text")),
        ))
    # Any other (non-auto-executed) intent: key off intent + normalized args repr.
    return "|".join((str(intent), _norm_summary(repr(sorted(args.items())))))
