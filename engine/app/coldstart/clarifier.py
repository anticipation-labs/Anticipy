"""Cold-start dossier → SMS clarification generator.

After the 90s inhale finishes, we know roughly who the user is. We
need to confirm the 2-3 most-uncertain facts in a single SMS so the
dossier locks before the wearer's first action. Per
``planning/00-handoff/ARCHITECTURE.md`` section 7 step 7:

    "I know you work at X, your boss is Y, your big project is Z.
     Did I get it right?"

Hard rules pulled from owner directives in MEMORY.md:

* NEVER use em-dashes. Use periods, commas, parens. (Already a
  blocking rule, enforced again in this file's renderer.)
* Output MUST fit in one SMS segment so the wearer answers fast.
  GSM-7 single-segment cap is 160 chars; we keep ourselves a 5-char
  margin (155 chars) so a leading 'Anticipy: ' prefix added by the
  Twilio relay does not split the message.
* Three facts max. More than three reads like an interrogation.

What this module DOES NOT do:

* It does not call SMS. The orchestrator owns sending. This file is
  pure: dossier dict in, SMS body string out.
* It does not call any LLM. The dossier already has structured
  fields; we read them deterministically. The owner has been burned
  by 'agent reported success' patterns; a deterministic clarifier
  cannot lie.
"""

from __future__ import annotations

from typing import Any


SMS_BODY_MAX = 155  # 160 GSM-7 minus 5 chars of broker prefix headroom


# Replace em-dashes / en-dashes with periods. Keep this list narrow;
# do NOT touch other unicode punctuation the user may legitimately
# type back in confirmations.
_BANNED_CHARS = ("—", "–")  # em dash, en dash


def _strip_em_dashes(s: str) -> str:
    out = s
    for ch in _BANNED_CHARS:
        out = out.replace(ch, ".")
    return out


def _first(items: Any) -> str:
    """First non-empty string in a list, or ''."""
    if not isinstance(items, list):
        return ""
    for x in items:
        s = str(x or "").strip()
        if s:
            return s
    return ""


def _top_contact_name(gmail: dict) -> str:
    contacts = (gmail or {}).get("top_contacts") or []
    if not isinstance(contacts, list) or not contacts:
        return ""
    top = contacts[0] if isinstance(contacts[0], dict) else {}
    return str(top.get("name") or top.get("email") or "").strip()


def _recurring_attendee(calendar: dict) -> str:
    """Best guess at 'your boss' = someone in your most-frequent recurring."""
    recurring = (calendar or {}).get("recurring_meetings") or []
    if not isinstance(recurring, list):
        return ""
    for r in recurring:
        if not isinstance(r, dict):
            continue
        atts = r.get("attendees") or []
        if isinstance(atts, list) and atts:
            return str(atts[0]).strip()
    return ""


def _company(linkedin: dict) -> str:
    prof = (linkedin or {}).get("profile") or {}
    return str(prof.get("company") or "").strip()


def _job_title(linkedin: dict) -> str:
    prof = (linkedin or {}).get("profile") or {}
    return str(prof.get("job_title") or prof.get("headline") or "").strip()


def _project(drive: dict) -> str:
    """Best guess at 'big project' = most-recent drive project name."""
    names = (drive or {}).get("project_names") or []
    name = _first(names)
    if name:
        return name
    # Fall back to first recent doc title head
    docs = (drive or {}).get("recent_docs") or []
    if isinstance(docs, list) and docs:
        first = docs[0]
        if isinstance(first, dict):
            return str(first.get("title") or "").strip()
    return ""


def _select_three_facts(dossier: dict) -> list[tuple[str, str]]:
    """Pick 3 facts to confirm, in priority order.

    Returns a list of (label, value) tuples. Empty values are skipped
    so a sparse dossier (e.g. LinkedIn signed out) does not produce
    'I see you work at .' nonsense.

    Priority: company (most-impactful), boss, big project. Falls back
    to top contact + job title if those slots are empty.
    """
    linkedin = dossier.get("linkedin") or {}
    calendar = dossier.get("calendar") or {}
    drive = dossier.get("drive") or {}
    gmail = dossier.get("gmail") or {}

    candidates: list[tuple[str, str]] = []

    company = _company(linkedin)
    if company:
        candidates.append(("work at", company))

    boss = _recurring_attendee(calendar)
    if boss:
        candidates.append(("meet with", boss))

    project = _project(drive)
    if project:
        candidates.append(("are working on", project))

    # Fallback fillers if any priority slot was empty.
    if len(candidates) < 3:
        title = _job_title(linkedin)
        if title and not any(v == title for _, v in candidates):
            candidates.append(("work as", title))

    if len(candidates) < 3:
        top = _top_contact_name(gmail)
        if top and not any(v == top for _, v in candidates):
            candidates.append(("email a lot with", top))

    return candidates[:3]


def _format_fact(label: str, value: str) -> str:
    """One natural-language fragment: 'work at Acme'."""
    return f"{label} {value}"


def _join_facts(facts: list[tuple[str, str]]) -> str:
    """Join facts with commas + final 'and'. Plain English, no em-dashes."""
    parts = [_format_fact(lbl, val) for lbl, val in facts]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return f"{parts[0]}, {parts[1]}, and {parts[2]}"


def _truncate_for_sms(body: str, cap: int = SMS_BODY_MAX) -> str:
    """If body is too long, cut at a word boundary and end clean.

    We try to keep the trailing 'Got it right?' question because the
    wearer needs an explicit prompt to reply.
    """
    if len(body) <= cap:
        return body
    tail = " Got it right?"
    if len(tail) >= cap:
        # Degenerate cap; just hard-truncate.
        return body[:cap].rstrip()
    head_cap = cap - len(tail)
    # If the head already ends with a period, keep it; else trim
    # at the last space before head_cap.
    head = body[:head_cap]
    last_space = head.rfind(" ")
    if last_space > head_cap - 30:  # only trim if word is mid-cut
        head = head[:last_space].rstrip(",. ")
    if not head.endswith("."):
        head = head.rstrip() + "."
    return (head + tail).strip()


def build_clarification_sms(dossier: dict) -> str:
    """Generate the one-SMS clarification body from the merged dossier.

    Returns an empty string when there is literally nothing to
    confirm (no LinkedIn, no calendar, no drive, no gmail data) so
    the orchestrator can choose to fall back to "tell me about your
    day" instead of sending a blank SMS.
    """
    if not isinstance(dossier, dict):
        return ""

    facts = _select_three_facts(dossier)
    if not facts:
        return ""

    joined = _join_facts(facts)
    if not joined:
        return ""

    body = f"Hey. I see you {joined}. Got it right? Reply YES, NO, or EDIT."
    body = _strip_em_dashes(body)
    body = _truncate_for_sms(body, cap=SMS_BODY_MAX)
    body = _strip_em_dashes(body)
    return body


__all__ = ["build_clarification_sms", "SMS_BODY_MAX"]
