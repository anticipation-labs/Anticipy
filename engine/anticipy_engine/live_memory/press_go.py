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
_BINDING_SEND = re.compile(
    r"\b(send|sent|pay|paid|pays|payment|venmo|zelle|wire|wired|transfer|"
    r"invoice|charge|deposit|refund|"
    r"slack|message|messaged|text|texted|dm|post|tweet|publish|submit|submitted|"
    r"buy|bought|purchase|order(?:ed)?|checkout|check out)\b",
    re.I,
)

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
                     now: Optional[dt.datetime] = None) -> Optional[Tuple[str, str]]:
    """Ground the RAW spoken line to a concrete (start_iso, end_iso) 1-hour window, or None.

    Conservative: requires an explicit clock time AND a day anchor. Returns None
    (-> handback) when no concrete clock time can be grounded — never invents one.
    """
    text = (raw or "").lower()
    now = now or dt.datetime.now().astimezone()

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
    if hour is None or not (0 <= hour <= 23):
        return None

    base = (now + dt.timedelta(days=day_offset)).replace(
        hour=hour, minute=minute, second=0, microsecond=0)
    end = base + dt.timedelta(hours=1)
    return base.isoformat(timespec="seconds"), end.isoformat(timespec="seconds")


def map_inferred_to_step(inferred: Dict[str, object], raw_text: str = "",
                         now: Optional[dt.datetime] = None) -> Dict[str, object]:
    """Map a display-only inferred task to ONE intent + a pre-built Step, or handback.

    ``inferred`` is the review's display-only {task, people, due_phrase, confidence}.
    ``raw_text`` is the spoken line, used ONLY to ground a concrete event datetime (the
    due_phrase the review shows is a lossy human string). The whitelist DECISION is keyed
    off the inferred shape; an ambiguous or binding/send/money/message shape returns
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
    binding = bool(_BINDING_SEND.search(low) or _BINDING_SEND.search(raw_low))

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
        window = _ground_datetime(raw_text, now=now)
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
    if _DRAFT_SHAPE.search(low) and people and not binding:
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
