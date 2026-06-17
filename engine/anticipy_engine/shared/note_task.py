"""Reversible note-capture commands.

"Add a note to tell customers X" asks the system to create/capture a note. The
"tell customers" phrase is note content, not a binding send. This helper stays
narrow: imperative note creation only, no broad "make visible" or "I should"
captures.
"""
from __future__ import annotations

import re
from typing import Optional


_NOTE_COMMAND_RE = re.compile(
    r"^\s*(?:please\s+)?(?:add|write|make|create|leave|put)\s+"
    r"(?:a\s+|the\s+)?note\b",
    re.I,
)


def match_note_task(text: str) -> Optional[str]:
    line = re.sub(r"\s+", " ", text or "").strip()
    if not line:
        return None
    return line if _NOTE_COMMAND_RE.search(line) else None


# INTERNAL-NOTE shape (NOT a payment): "make sure the retainer NOTE is in the CRM",
# "add a note in the client file about the retainer", "log the retainer note", "put a
# note in the record". A money/obligation NOUN (retainer/invoice/balance/...) can name
# the SUBJECT of an internal note without the line ever moving money — recording a note
# ABOUT a retainer is admin, not paying one. The _MONEY_SIGNAL obligation-noun catch
# (harm.py / owner_mode) wrongly read the bare word "retainer" as money and BLOCKED the
# admin note (the lawyer seam). This detector recognizes the note shape so callers can
# treat it as a reversible internal record action, never a money wall.
#
# DELIBERATELY TIGHT — it fires ONLY when the line is built around a NOTE/record/file
# ENTRY (a note word) AND carries NO spend verb. A real payment ("pay/wire/charge the
# retainer", "chase the retainer", "deposit the retainer") has no note framing and never
# matches, so the money floor is untouched. "chase the X retainer" is a money chase
# (third-party), not a note, and correctly stays out.
_NOTE_NOUN = (
    r"(?:note|notes|memo|comment|entry|annotation|record|log|file|reminder)"
)
# A money/transaction VERB anywhere makes the line a real money move, never an internal
# note — even if it mentions a "note". This is the hard guard so the carve-out can never
# downgrade an actual payment ("pay the note off", "wire the deposit and note it").
_NOTE_MONEY_VERB = re.compile(
    r"\b(?:pay|paid|pays|paying|wire|wired|wiring|charge|charged|charging|"
    r"deposit(?:s|ed|ing)?|withdraw|venmo|zelle|cashapp|cash ?app|paypal|transfer|"
    r"transferred|transferring|reimburse|refund(?:s|ed|ing)?|invoice(?:s|d)|bill(?:s|ed|ing)?|"
    r"collect|chase|chasing|chased|settle|settling|settled)\b",
    re.I,
)
# The note must be tied to an internal STORE (CRM / client file / case file / record / system /
# ledger / chart / matter) so a bare "send a note to Sarah" (a SEND to a person) is NOT swallowed
# here, and the generic "add a note ..." capture command — which the spine already executes well as
# a write_memory goal — is left to match_note_task (NOT intercepted). This detector exists ONLY to
# keep a STORE-BOUND note ("the retainer note is in the CRM") off the MONEY wall, which is the seam.
_INTERNAL_NOTE_RE = re.compile(
    r"\b" + _NOTE_NOUN + r"\b[^.;!?]{0,60}\b(?:in|into|on|to)\s+"
    r"(?:the\s+|our\s+|my\s+|his\s+|her\s+|their\s+)?"
    r"(?:crm|client file|case file|matter file|client record|case record|matter record|"
    r"client chart|patient chart|ledger|database|client portal|case file|matter)\b",
    re.I,
)


def match_internal_note(text: str) -> Optional[str]:
    """True (returns the cleaned line) when the line is a STORE-BOUND internal note/record action
    whose subject merely MENTIONS a money/obligation word ("the retainer note is in the CRM") —
    reversible admin, not a payment. Returns None for any line carrying a spend/transaction verb (a
    real money move), and None for a generic note-capture command (that stays with match_note_task,
    which the spine executes as a write_memory goal). Used by harm.py + owner_mode to keep a
    store-bound internal note off the money wall WITHOUT weakening the money floor or rerouting the
    note-capture lines the spine already handles."""
    line = re.sub(r"\s+", " ", text or "").strip()
    if not line:
        return None
    if _NOTE_MONEY_VERB.search(line):
        return None
    return line if _INTERNAL_NOTE_RE.search(line) else None
