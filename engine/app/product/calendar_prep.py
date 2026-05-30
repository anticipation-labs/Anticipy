"""Calendar auto-prep: pull together everything the user needs for
the meeting that is about to start.

The user says "prep for the 3pm with Sarah" (or, more often, says
nothing and the always-on engine notices a meeting starting in the
next 30 minutes) and the engine silently assembles a one-page brief:

  - the calendar event itself: title, start, attendees, agenda
  - the last email thread with the primary attendee (via Gmail)
  - related Drive docs that mention the attendee's name
  - any past Anticipy notes about the attendee from the active dossier
  - 3 talking points the LLM extracts from the above
  - open questions the LLM thinks the user should raise

The brief is markdown. It is delivered to the user through the same
notification surface as the rest of Anticipy: a local-notify banner
plus an entry in the recent-fires log so the popover can display it.

Hard constraints (from CLAUDE.md and planning/00-handoff):

  - NO hardcoded per-app recipes. The walker JS is the SAME generic
    row-extraction the coldstart inhale uses; the LLM interprets.
  - NO service APIs. We never call the Google Calendar API or the
    Gmail API. We drive the user's real Chrome via the existing
    loopback bridge on 127.0.0.1:7777 and Chrome CDP at :9222.
  - NO em-dashes anywhere in code or LLM prompts.
  - DeepSeek V4 Flash via the platform_adapter (OpenRouter broker),
    with the system prompt above 1000 chars so prompt caching engages.
  - Background scheduler runs on startup; scans every 5 min for
    meetings in the next 30 min window; auto-fires the prep brief
    once per meeting (dedup by event id).

Module surface used by server.py:

    from app.product.calendar_prep import (
        find_upcoming_meeting,
        pull_meeting_context,
        compose_brief,
        Meeting,
        start_scheduler,
        prep_meeting,
    )
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

_logger = logging.getLogger("anticipy.product.calendar_prep")


# ---------------------------------------------------------------------------
# Public dataclasses
# ---------------------------------------------------------------------------
@dataclass
class Meeting:
    """A single calendar event the prep flow targets.

    ``event_id`` is the dedup key for the scheduler so a meeting is
    not auto-prepped more than once. ``start_ts`` and ``end_ts`` are
    Unix epoch seconds when known; ``attendee_emails`` is best-effort
    from the row label, which Google Calendar formats as
    ``title, attendees, time``. The brief composer treats every field
    as optional and degrades gracefully if a field is empty.
    """

    event_id: str
    title: str = ""
    start_ts: float = 0.0
    end_ts: float = 0.0
    raw_label: str = ""
    attendee_emails: list[str] = field(default_factory=list)
    attendee_names: list[str] = field(default_factory=list)
    when_text: str = ""
    description_hint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "title": self.title,
            "start_ts": self.start_ts,
            "end_ts": self.end_ts,
            "raw_label": self.raw_label,
            "attendee_emails": list(self.attendee_emails),
            "attendee_names": list(self.attendee_names),
            "when_text": self.when_text,
            "description_hint": self.description_hint,
            "minutes_until_start": self.minutes_until_start(),
        }

    def minutes_until_start(self) -> float:
        if not self.start_ts:
            return 0.0
        return round((self.start_ts - time.time()) / 60.0, 2)

    def primary_attendee(self) -> str:
        for email in self.attendee_emails:
            if email and email.strip():
                return email.strip()
        for name in self.attendee_names:
            if name and name.strip():
                return name.strip()
        return ""


# ---------------------------------------------------------------------------
# Scheduler state (module level so the status endpoint can read it)
# ---------------------------------------------------------------------------
@dataclass
class SchedulerState:
    state: str = "idle"  # idle | running | stopped
    started_at: float = 0.0
    last_scan_at: float = 0.0
    scans_completed: int = 0
    briefs_fired: int = 0
    last_brief_meeting_id: str = ""
    last_brief_at: float = 0.0
    last_error: str = ""
    fired_event_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "started_at": self.started_at,
            "last_scan_at": self.last_scan_at,
            "scans_completed": self.scans_completed,
            "briefs_fired": self.briefs_fired,
            "last_brief_meeting_id": self.last_brief_meeting_id,
            "last_brief_at": self.last_brief_at,
            "last_error": self.last_error,
            "fired_event_ids": list(self.fired_event_ids[-20:]),
        }


_STATE = SchedulerState()
_STATE_LOCK = threading.Lock()
_THREAD: Optional[threading.Thread] = None
_STOP_EVENT = threading.Event()


def scheduler_state() -> dict[str, Any]:
    with _STATE_LOCK:
        return _STATE.to_dict()


def _record_brief_fired(meeting_id: str) -> None:
    with _STATE_LOCK:
        _STATE.briefs_fired += 1
        _STATE.last_brief_meeting_id = meeting_id
        _STATE.last_brief_at = time.time()
        if meeting_id and meeting_id not in _STATE.fired_event_ids:
            _STATE.fired_event_ids.append(meeting_id)


def _record_scan() -> None:
    with _STATE_LOCK:
        _STATE.scans_completed += 1
        _STATE.last_scan_at = time.time()


def _record_scheduler_error(msg: str) -> None:
    with _STATE_LOCK:
        _STATE.last_error = (msg or "")[:240]


# ---------------------------------------------------------------------------
# CDP walker access
# ---------------------------------------------------------------------------
def _walker():
    """Return a fresh CDPWalker. Bridge readiness is the caller's check.

    Imported lazily so calendar_prep stays importable even when the
    coldstart package is mid-edit. The walker exposes the SAME generic
    row extraction the coldstart inhale uses; we re-bind here to keep
    one source of truth for CDP plumbing.
    """
    from app.coldstart.cdp_walker import CDPWalker
    return CDPWalker()


_EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.[a-z]{2,}", re.I)
_NAME_RE = re.compile(r"\b([A-Z][a-zA-Z'\-]+(?:\s+[A-Z][a-zA-Z'\-]+)+)\b")


def _parse_attendees(raw: str) -> tuple[list[str], list[str]]:
    """Extract emails + names from a calendar row label.

    Google Calendar surfaces event aria-labels as one human-readable
    string ("Sync with Sarah Chen at 3pm, sarah@example.com"). We
    pull emails by regex and proper-noun pairs by capitalisation
    heuristic, then de-dupe.
    """
    emails: list[str] = []
    for hit in _EMAIL_RE.findall(raw or ""):
        e = hit.lower().strip()
        if e and e not in emails:
            emails.append(e)
    names: list[str] = []
    for hit in _NAME_RE.findall(raw or ""):
        nm = " ".join(hit.split())
        if nm and nm not in names:
            names.append(nm)
    return emails[:8], names[:8]


def _parse_event_when(raw: str) -> tuple[str, float, float]:
    """Best-effort timestamp extraction from a Google Calendar row.

    The aria-label format is locale dependent ("3pm to 4pm", "15:00 to
    16:00", "Tuesday, May 29, 2026 at 3pm"). We pull whichever clock
    fragment looks like a time and convert it against today's date in
    the user's local tz. Returns (when_text, start_ts, end_ts) where
    timestamps may be 0 if parsing fails. We never fabricate a time.
    """
    s = (raw or "").strip()
    # Pull a clock-shaped substring. Prefer "3pm to 4pm" / "15:00".
    clock = re.search(
        r"\b(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\b", s, re.I)
    when_text = ""
    start_ts = 0.0
    end_ts = 0.0
    if clock:
        when_text = clock.group(1).strip()
        # Try to convert to a real timestamp anchored to today.
        try:
            now = time.localtime()
            h, m = _parse_clock_to_h_m(when_text)
            if h is not None:
                tm = time.struct_time((
                    now.tm_year, now.tm_mon, now.tm_mday, h, m, 0,
                    now.tm_wday, now.tm_yday, now.tm_isdst,
                ))
                start_ts = float(time.mktime(tm))
                # If the parsed time is more than 30 min in the past,
                # assume it is tomorrow (people prep for upcoming, not
                # past, meetings).
                if start_ts < (time.time() - 1800):
                    start_ts += 86400.0
                end_ts = start_ts + 3600.0
        except Exception:
            pass
    return when_text, start_ts, end_ts


def _parse_clock_to_h_m(text: str) -> tuple[Optional[int], int]:
    """Convert "3pm", "3:30pm", "15:00" to (hour, minute)."""
    if not text:
        return None, 0
    t = text.strip().lower()
    is_pm = t.endswith("pm")
    is_am = t.endswith("am")
    if is_pm or is_am:
        t = t[:-2].strip()
    if ":" in t:
        parts = t.split(":", 1)
        try:
            h = int(parts[0])
            m = int(parts[1])
        except Exception:
            return None, 0
    else:
        try:
            h = int(t)
            m = 0
        except Exception:
            return None, 0
    if is_pm and h < 12:
        h += 12
    if is_am and h == 12:
        h = 0
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None, 0
    return h, m


# ---------------------------------------------------------------------------
# find_upcoming_meeting
# ---------------------------------------------------------------------------
def find_upcoming_meeting(within_minutes: int = 30,
                          *,
                          walker_obj: Any = None,
                          ) -> Optional[Meeting]:
    """Read Google Calendar via CDP and return the next meeting that
    starts within ``within_minutes`` from now.

    Returns None when:
      - the CDP bridge is not ready
      - there is no agenda row whose parsed start time falls in the
        next ``within_minutes`` minutes
      - parsing fails entirely (we do not invent meetings)

    ``walker_obj`` exists for tests; production callers pass nothing
    and we construct a fresh CDPWalker that auto-closes its tab.
    """
    walker = walker_obj if walker_obj is not None else _walker()
    own_walker = walker_obj is None
    try:
        if hasattr(walker, "bridge_ready") and not walker.bridge_ready():
            _logger.info("find_upcoming_meeting: bridge not ready")
            return None
        # Resolve the calendar URL from the user config. URL CHOICES
        # live in ~/.anticipy/inhale_sources.json, not in source code.
        cal_url = ""
        try:
            from app.coldstart import sources as _inhale_sources
            for s in _inhale_sources.load_enabled():
                if "calendar" in str(s.get("id") or "").lower():
                    cal_url = str(s.get("url") or "")
                    break
        except Exception as exc:
            _logger.warning(
                "find_upcoming_meeting: load_enabled failed: %s", exc)
        if not cal_url:
            _logger.info(
                "find_upcoming_meeting: no calendar source enabled in "
                "inhale_sources.json")
            return None
        try:
            rows = walker.walk_calendar(
                url=cal_url, per_tab_budget_s=12.0)
        except Exception as exc:
            _logger.warning(
                "find_upcoming_meeting: walk_calendar failed: %s", exc)
            return None
        if not rows:
            return None
        now_s = time.time()
        horizon_s = now_s + max(1, int(within_minutes)) * 60.0
        candidates: list[tuple[float, Meeting]] = []
        for idx, row in enumerate(rows):
            label = (row.extra.get("title")
                     or row.text or "").strip()
            if not label or len(label) < 4:
                continue
            when_text, start_ts, end_ts = _parse_event_when(label)
            emails, names = _parse_attendees(label)
            # Build a stable id from the row content so the scheduler
            # never re-fires the same brief.
            digest = re.sub(r"\s+", " ", label.lower())[:160]
            event_id = f"evt:{abs(hash(digest)):016x}"
            meeting = Meeting(
                event_id=event_id,
                title=label.split(",")[0][:140],
                start_ts=start_ts,
                end_ts=end_ts,
                raw_label=label[:400],
                attendee_emails=emails,
                attendee_names=names,
                when_text=when_text,
                description_hint=label[:400],
            )
            # Keep meetings whose start falls within the horizon.
            if start_ts and now_s <= start_ts <= horizon_s:
                candidates.append((start_ts, meeting))
            # Also keep the first row regardless of time parsing, so
            # explicit /api/calendar/prep calls can target "the next
            # one" even when time parse fails. They are returned only
            # if there are no time-anchored candidates.
            elif not candidates and idx == 0:
                candidates.append((horizon_s + 1.0, meeting))
        if not candidates:
            return None
        candidates.sort(key=lambda x: x[0])
        return candidates[0][1]
    finally:
        if own_walker:
            try:
                walker.close_all()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# pull_meeting_context: emails + drive docs + dossier notes
# ---------------------------------------------------------------------------
def _walk_gmail_for_attendee(walker: Any,
                              query: str,
                              max_rows: int = 12) -> list[dict]:
    """Open Gmail with a ?#search/<query> URL and pull the row labels.

    Reuses the generic _GMAIL_COLLECT_JS row extractor that the
    coldstart walker already exposes. The walker does not have a
    public search method, so we open a tab to the search URL and
    re-use _scroll_and_collect directly.
    """
    try:
        import urllib.parse
        from app.coldstart.cdp_walker import _cdp_eval_on_target
    except Exception as exc:
        _logger.warning("gmail walk import failed: %s", exc)
        return []
    if not query.strip():
        return []
    qenc = urllib.parse.quote(query.strip())
    search_url = f"https://mail.google.com/mail/u/0/#search/{qenc}"
    tid = walker._open_anticipy_tab(search_url)
    if not tid:
        return []
    ready_js = (
        "(()=>{const rows=document.querySelectorAll('"
        "[role=\\\"row\\\"],tr.zA');return rows&&rows.length>0;})()"
    )
    try:
        walker._wait_for_dom_ready(tid, probe_js=ready_js,
                                    timeout_s=8.0)
        raw = walker._scroll_and_collect(
            tid, walker._GMAIL_COLLECT_JS,
            scroll_pages=2, settle_s=0.5)
    except Exception as exc:
        _logger.warning("gmail walk failed for %s: %s", query, exc)
        raw = []
    out: list[dict] = []
    for row in raw[:max_rows]:
        out.append({
            "sender": str(row.get("sender") or "")[:160],
            "subject": str(row.get("subject") or "")[:200],
            "date": str(row.get("date") or "")[:60],
            "snippet": str(row.get("snippet") or "")[:240],
            "text": str(row.get("text") or "")[:300],
        })
    return out


def _walk_drive_for_attendee(walker: Any,
                              query: str,
                              max_rows: int = 8) -> list[dict]:
    """Search Drive by the attendee's name. Returns recent doc titles.

    Uses Drive's search URL pattern. Generic row extraction reused
    from the coldstart walker.
    """
    try:
        import urllib.parse
        from app.coldstart.cdp_walker import _cdp_eval_on_target
    except Exception as exc:
        _logger.warning("drive walk import failed: %s", exc)
        return []
    if not query.strip():
        return []
    qenc = urllib.parse.quote(query.strip())
    search_url = (
        f"https://drive.google.com/drive/u/0/search?q={qenc}"
    )
    tid = walker._open_anticipy_tab(search_url)
    if not tid:
        return []
    ready_js = (
        "(()=>{return document.querySelectorAll('[role=\\\"row\\\"]')"
        ".length>0||document.querySelectorAll('[data-id]').length>0;})()"
    )
    try:
        walker._wait_for_dom_ready(tid, probe_js=ready_js, timeout_s=8.0)
        raw = walker._scroll_and_collect(
            tid, walker._DRIVE_COLLECT_JS,
            scroll_pages=1, settle_s=0.4)
    except Exception as exc:
        _logger.warning("drive walk failed for %s: %s", query, exc)
        raw = []
    out: list[dict] = []
    for row in raw[:max_rows]:
        title = str(row.get("title") or "")[:200]
        if not title:
            continue
        out.append({"title": title, "text": str(row.get("text") or "")[:240]})
    return out


def _attendee_query(meeting: Meeting,
                    attendee_email: str = "") -> tuple[str, str]:
    """Decide which person to search for in Gmail/Drive.

    Caller can override with ``attendee_email`` (typed by the user via
    POST /api/calendar/prep). Otherwise we prefer the first email on
    the event, falling back to the first proper name. Returns the
    (search_query, label) pair the prompt and walker both use.
    """
    if attendee_email and "@" in attendee_email:
        return attendee_email, attendee_email
    primary = meeting.primary_attendee()
    if "@" in primary:
        return primary, primary
    if primary:
        return primary, primary
    # No attendee anywhere; fall back to the title.
    label = meeting.title or meeting.raw_label
    return label, label


def _dossier_notes_for(label: str, max_chars: int = 600) -> list[str]:
    """Read the active dossier and return any people/projects whose
    name or email matches the attendee label.

    Reads ~/.anticipy/v7/dossiers/<account>/dossier.json directly so
    calendar_prep stays self-contained. Returns a small list of human
    readable strings; the brief composer appends them to its prompt.
    """
    notes: list[str] = []
    if not label:
        return notes
    try:
        from app.product.dossier_active_loader import DossierLoader
    except Exception:
        return notes
    try:
        loader = DossierLoader("anticipy-user")
    except Exception:
        return notes
    needle = label.lower()
    for person in loader.people():
        candidates = [person.name.lower(), (person.email or "").lower()]
        candidates.extend(a.lower() for a in person.aliases)
        if any(needle in c or c in needle for c in candidates if c):
            bits = [person.name]
            if person.role:
                bits.append(f"({person.role})")
            if person.email:
                bits.append(f"<{person.email}>")
            notes.append(" ".join(bits)[:max_chars // 2])
    try:
        raw_projects = loader._raw.get("projects") or []
        if isinstance(raw_projects, list):
            for proj in raw_projects:
                if not isinstance(proj, dict):
                    continue
                related = proj.get("related_people") or []
                if isinstance(related, list) and any(
                    needle in str(r).lower() for r in related
                ):
                    notes.append(
                        f"project: {proj.get('name','')}"
                        f" ({proj.get('why','')})"[:max_chars // 2])
    except Exception:
        pass
    return notes[:8]


def pull_meeting_context(meeting: Meeting,
                          *,
                          attendee_email: str = "",
                          walker_obj: Any = None,
                          ) -> dict[str, Any]:
    """Assemble the full prep context for one meeting.

    Returns a dict with keys:
      - ``meeting`` (the dict form of the Meeting)
      - ``search_label`` (the query we used for Gmail/Drive)
      - ``emails`` (list of recent Gmail rows that match)
      - ``drive_docs`` (list of Drive doc titles)
      - ``dossier_notes`` (list of strings from the active dossier)
      - ``warnings`` (anything skipped)

    Tolerant of a missing CDP bridge: returns the meeting + dossier
    notes even when the live walkers cannot run.
    """
    walker = walker_obj if walker_obj is not None else _walker()
    own_walker = walker_obj is None
    warnings: list[str] = []
    search_q, label = _attendee_query(meeting, attendee_email)
    emails: list[dict] = []
    drive_docs: list[dict] = []
    try:
        if hasattr(walker, "bridge_ready") and not walker.bridge_ready():
            warnings.append("bridge_not_ready_skipping_live_walks")
        else:
            try:
                emails = _walk_gmail_for_attendee(walker, search_q,
                                                    max_rows=10)
            except Exception as exc:
                warnings.append(f"gmail_walk:{type(exc).__name__}:{exc}")
            try:
                drive_docs = _walk_drive_for_attendee(walker, search_q,
                                                       max_rows=6)
            except Exception as exc:
                warnings.append(f"drive_walk:{type(exc).__name__}:{exc}")
    finally:
        if own_walker:
            try:
                walker.close_all()
            except Exception:
                pass
    dossier_notes = _dossier_notes_for(label)
    return {
        "meeting": meeting.to_dict(),
        "search_label": label,
        "emails": emails,
        "drive_docs": drive_docs,
        "dossier_notes": dossier_notes,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# compose_brief: LLM call (DeepSeek V4 Flash, prompt-cached)
# ---------------------------------------------------------------------------
# This system prompt is the cache anchor. It is sent verbatim for every
# brief, so the broker can serve it as a warm cache hit on the second
# call onward (platform_adapter.model_call auto-attaches
# cache_control:ephemeral when the system block crosses 1000 chars).
# Keep above the floor so caching engages. NO em-dashes.
BRIEF_SYSTEM_PROMPT = (
    "You are Anticipy's calendar prep brief writer. The user is about "
    "to walk into a meeting. The engine has already silently pulled "
    "together everything visible from their open Chrome surfaces: the "
    "Google Calendar event itself, the latest Gmail rows matching the "
    "primary attendee, recent Drive document titles that mention the "
    "attendee, and any past Anticipy dossier notes about that person. "
    "Your job is to compress all of that into a one-page markdown "
    "brief the user will skim in under 30 seconds.\n\n"
    "INPUT shape. The user message is a JSON object with these "
    "fields:\n"
    "  meeting: {title, when_text, attendee_emails, attendee_names, "
    "raw_label, minutes_until_start}\n"
    "  search_label: the string used to search Gmail and Drive\n"
    "  emails: [{sender, subject, date, snippet, text}]\n"
    "  drive_docs: [{title}]\n"
    "  dossier_notes: [str]\n\n"
    "OUTPUT shape. Return MARKDOWN ONLY, no JSON, no code fences, no "
    "preamble. Follow this exact heading structure so the popover can "
    "parse it deterministically:\n\n"
    "## Brief: {meeting title}\n"
    "When: {when_text} ({minutes_until_start} min from now)\n"
    "Who: {attendee names or emails, comma separated}\n\n"
    "### Recent context\n"
    "- one line per relevant email or recent activity, newest first, "
    "max 5 bullets\n"
    "- if there are no emails, write: no recent email thread found\n\n"
    "### Related docs\n"
    "- one line per Drive doc title, max 3 bullets\n"
    "- if there are no docs, omit this section entirely\n\n"
    "### Talking points\n"
    "1. concrete talking point grounded in the recent context\n"
    "2. another concrete talking point\n"
    "3. one more if there is enough material; otherwise stop at 2\n\n"
    "### Open questions\n"
    "- open question the user should raise, grounded in the input\n"
    "- another if the data supports it\n\n"
    "RULES.\n"
    "1. Be specific. Cite the actual subject lines and doc titles. Do "
    "NOT invent facts that are not present in the input.\n"
    "2. If the input is sparse, the brief is sparse. An empty Recent "
    "context line is honest and more useful than a hallucinated one.\n"
    "3. Never use em dashes. Use commas, periods, or parentheses.\n"
    "4. Talking points are imperative or noun phrases the user can "
    "lead with, not 'you could ask about...'. Example good: "
    "'Update on the Q3 roadmap sync results'. Example bad: "
    "'You could discuss the roadmap'.\n"
    "5. Open questions are real questions ending with '?'. They are "
    "not the user's to-do list.\n"
    "6. Keep the whole brief under 350 words.\n"
    "7. Markdown only. No JSON. No code fences.\n"
)


def compose_brief(context: dict[str, Any],
                  *,
                  timeout_s: float = 25.0,
                  max_tokens: int = 700) -> str:
    """Send the assembled context to DeepSeek V4 Flash and return the
    markdown brief.

    Falls back to a deterministic skeleton when the LLM is unreachable
    so the caller always gets a usable brief; the skeleton clearly
    labels itself "(offline summary)" so the user can tell.
    """
    payload = json.dumps(context, ensure_ascii=False, default=str)[:6000]
    try:
        from app.anticipy import platform_adapter
    except Exception as exc:
        _logger.warning("compose_brief: platform_adapter import: %s", exc)
        return _fallback_brief(context, reason=f"adapter_import:{exc}")
    try:
        result = platform_adapter.model_call(
            BRIEF_SYSTEM_PROMPT,
            payload,
            max_tokens=max_tokens,
            temperature=0.2,
            json_mode=False,
            timeout_s=timeout_s,
        )
    except Exception as exc:
        _logger.warning("compose_brief: model_call: %s", exc)
        return _fallback_brief(context, reason=f"model_call:{exc}")
    if not result.ok or not (result.content or "").strip():
        return _fallback_brief(
            context,
            reason=f"llm_empty:{result.error or 'no content'}",
        )
    text = result.content.strip()
    # Defensive: strip a stray code fence if the model wraps in ```.
    if text.startswith("```"):
        text = text.strip("`")
        first_nl = text.find("\n")
        if first_nl != -1:
            text = text[first_nl + 1:].strip()
        if text.endswith("```"):
            text = text[: -3].strip()
    # Hard belt and suspenders: scrub any em dashes the model emitted.
    text = text.replace("—", ", ").replace("–", ", ")
    return text


def _fallback_brief(context: dict[str, Any],
                    *,
                    reason: str = "") -> str:
    """Build a deterministic skeleton from the raw input so the caller
    always gets a brief even when the LLM is unreachable.

    Labelled clearly so the user can tell it is a degraded path. Keeps
    every literal string the user supplied so the brief is real and
    verifiable on inspection.
    """
    meeting = context.get("meeting") or {}
    emails = context.get("emails") or []
    drive_docs = context.get("drive_docs") or []
    dossier = context.get("dossier_notes") or []
    title = str(meeting.get("title") or "Untitled meeting")
    when = str(meeting.get("when_text") or "")
    mins = meeting.get("minutes_until_start")
    when_str = f"{when} ({mins} min from now)" if when else (
        f"in {mins} min" if isinstance(mins, (int, float)) and mins else "")
    who = ", ".join(
        list(meeting.get("attendee_names") or [])[:4]
        + list(meeting.get("attendee_emails") or [])[:4]
    )
    lines = [f"## Brief: {title} (offline summary)"]
    if when_str:
        lines.append(f"When: {when_str}")
    if who:
        lines.append(f"Who: {who}")
    lines.append("")
    lines.append("### Recent context")
    if emails:
        for em in emails[:5]:
            subj = str(em.get("subject") or "")[:80]
            sender = str(em.get("sender") or "")[:60]
            date = str(em.get("date") or "")[:30]
            lines.append(
                f"- {subj or '(no subject)'} from {sender} ({date})")
    else:
        lines.append("- no recent email thread found")
    if drive_docs:
        lines.append("")
        lines.append("### Related docs")
        for d in drive_docs[:3]:
            lines.append(f"- {str(d.get('title') or '')[:120]}")
    if dossier:
        lines.append("")
        lines.append("### Dossier notes")
        for note in dossier[:3]:
            lines.append(f"- {str(note)[:140]}")
    lines.append("")
    lines.append("### Talking points")
    lines.append("1. Confirm the meeting agenda and goals up front.")
    lines.append("2. Surface the most recent email thread topic above.")
    lines.append("")
    lines.append("### Open questions")
    lines.append("- What is the desired outcome of this conversation?")
    if reason:
        lines.append("")
        lines.append(f"_(reason: {reason})_")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# prep_meeting: one-shot orchestrator (used by both endpoints)
# ---------------------------------------------------------------------------
@dataclass
class PrepResult:
    ok: bool
    meeting: Optional[Meeting]
    brief: str
    context: dict[str, Any]
    delivered: list[dict] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "meeting": self.meeting.to_dict() if self.meeting else None,
            "brief": self.brief,
            "context": self.context,
            "delivered": list(self.delivered),
            "error": self.error,
        }


def prep_meeting(meeting: Optional[Meeting] = None,
                 *,
                 attendee_email: str = "",
                 deliver: bool = False) -> PrepResult:
    """End to end prep: pull context, compose brief, optionally deliver.

    Always returns a PrepResult; never raises. ``deliver=True`` fires
    the brief through ``deliver_brief`` (channel router). Callers that
    only want the brief text (the POST /api/calendar/prep endpoint)
    pass ``deliver=False`` and inspect ``result.brief`` directly.
    """
    if meeting is None:
        return PrepResult(
            ok=False, meeting=None, brief="",
            context={}, error="no meeting provided",
        )
    try:
        context = pull_meeting_context(
            meeting, attendee_email=attendee_email)
    except Exception as exc:
        context = {
            "meeting": meeting.to_dict(),
            "search_label": "",
            "emails": [],
            "drive_docs": [],
            "dossier_notes": [],
            "warnings": [f"pull_meeting_context_unhandled:{exc}"],
        }
    brief = compose_brief(context)
    delivered: list[dict] = []
    if deliver:
        try:
            delivered = deliver_brief(meeting, brief)
        except Exception as exc:
            delivered.append({"ok": False, "channel": "deliver",
                              "error": f"{type(exc).__name__}: {exc}"})
    return PrepResult(
        ok=True,
        meeting=meeting,
        brief=brief,
        context=context,
        delivered=delivered,
    )


# ---------------------------------------------------------------------------
# deliver_brief: notify_user channel router
# ---------------------------------------------------------------------------
def _brief_summary_for_notification(meeting: Meeting, brief: str) -> str:
    """Squeeze the markdown brief into a single notification line.

    macOS notification banners cap somewhere around 200 chars and we
    want the title line plus a teaser. Pull the first non-heading,
    non-empty bullet from the brief and prepend the meeting title.
    """
    title = meeting.title or "Upcoming meeting"
    teaser = ""
    for raw in (brief or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            continue
        if line.startswith("```"):
            continue
        # First bullet or paragraph wins.
        teaser = line.lstrip("-*0123456789. ").strip()
        if teaser:
            break
    summary = f"Brief ready: {title}"
    if teaser:
        summary += f". {teaser[:140]}"
    return summary[:220]


def deliver_brief(meeting: Meeting, brief: str) -> list[dict]:
    """Push the brief through the channel router.

    Returns a list of per-channel result dicts. The default route is:

      1. macOS local notification banner (always best-effort)
      2. append to the trivia recent-fires queue so the popover renders
         it in the same scrolling activity feed it already shows

    SMS and other escalations are intentionally NOT used here: a brief
    is FYI material, not a critical alert. The user opens the popover
    to read the full markdown.
    """
    results: list[dict] = []
    summary = _brief_summary_for_notification(meeting, brief)
    # 1. macOS banner via the proactive notifier
    try:
        import asyncio
        from app.proactive.notifier import local_notify
        result = asyncio.run(
            local_notify(
                f"Anticipy: prep for {meeting.title or 'next meeting'}",
                summary,
            )
        )
        results.append({
            "channel": "local_notify",
            "ok": bool(result.get("ok")),
            "detail": result,
        })
    except Exception as exc:
        results.append({
            "channel": "local_notify",
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
        })
    # 2. popover activity feed via the trivia recent-fires queue
    try:
        from app.trivia import deliver as _trivia_deliver
        entry = {
            "answer": summary,
            "source": "calendar_prep",
            "lane": "prep",
            "topic": meeting.title,
            "score": None,
            "elapsed_ms": None,
        }
        try:
            _trivia_deliver.deliver(
                f"prep brief: {meeting.title}",
                entry,
                trigger_result={"source": "calendar_prep",
                                "event_id": meeting.event_id},
            )
            results.append({"channel": "popover_feed", "ok": True})
        except Exception as exc:
            results.append({
                "channel": "popover_feed",
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
            })
    except Exception as exc:
        results.append({
            "channel": "popover_feed",
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
        })
    # Persist the brief to disk so the popover can fetch the full
    # markdown by event_id. Best-effort; never raises.
    try:
        _persist_brief(meeting, brief)
        results.append({"channel": "disk_cache", "ok": True})
    except Exception as exc:
        results.append({"channel": "disk_cache", "ok": False,
                        "error": f"{type(exc).__name__}: {exc}"})
    return results


_BRIEFS_DIR = Path.home() / ".anticipy" / "v7" / "calendar_briefs"


def _persist_brief(meeting: Meeting, brief: str) -> Path:
    """Write the brief markdown to disk so the popover can fetch it
    later by event_id.
    """
    _BRIEFS_DIR.mkdir(parents=True, exist_ok=True)
    safe_id = re.sub(r"[^A-Za-z0-9._-]+", "_", meeting.event_id or "default")
    out = _BRIEFS_DIR / f"{safe_id[:64]}.md"
    out.write_text(brief or "", encoding="utf-8")
    return out


def read_persisted_brief(event_id: str) -> Optional[str]:
    """Read back a previously persisted brief by event_id."""
    if not event_id:
        return None
    safe_id = re.sub(r"[^A-Za-z0-9._-]+", "_", event_id)
    path = _BRIEFS_DIR / f"{safe_id[:64]}.md"
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Background scheduler
# ---------------------------------------------------------------------------
def _scheduler_loop(within_minutes: int,
                    scan_interval_s: float,
                    stop_event: threading.Event) -> None:
    """Body of the background thread: scan every scan_interval_s, fire
    a brief once per detected upcoming meeting.

    Dedup is in-process: ``_STATE.fired_event_ids`` keeps the last 20
    event ids we have already prepped for, so a meeting in the next 30
    min is briefed at most once even though we scan every 5 min.
    """
    _logger.info(
        "calendar_prep scheduler: started within=%d scan_every=%.1fs",
        within_minutes, scan_interval_s)
    while not stop_event.is_set():
        try:
            meeting = find_upcoming_meeting(within_minutes=within_minutes)
            _record_scan()
            if meeting is not None:
                already = False
                with _STATE_LOCK:
                    if meeting.event_id in _STATE.fired_event_ids:
                        already = True
                if not already:
                    _logger.info(
                        "calendar_prep scheduler: prepping %s "
                        "(start in %.1f min)",
                        meeting.title,
                        meeting.minutes_until_start())
                    try:
                        prep_meeting(meeting, deliver=True)
                        _record_brief_fired(meeting.event_id)
                    except Exception as exc:
                        _record_scheduler_error(
                            f"prep_meeting: {type(exc).__name__}: {exc}")
        except Exception as exc:
            _record_scheduler_error(
                f"scan: {type(exc).__name__}: {exc}")
        # Sleep in small chunks so stop_event can interrupt quickly.
        deadline = time.time() + max(5.0, scan_interval_s)
        while not stop_event.is_set() and time.time() < deadline:
            time.sleep(1.0)
    with _STATE_LOCK:
        _STATE.state = "stopped"
    _logger.info("calendar_prep scheduler: stopped")


def start_scheduler(within_minutes: int = 30,
                     scan_interval_s: float = 300.0) -> dict[str, Any]:
    """Kick off the background scan loop. Idempotent.

    Returns the current scheduler state. If a scheduler is already
    running this is a no-op and the snapshot's ``state`` stays
    ``running``.
    """
    global _THREAD
    # ANTICIPY_QUIET=1 short-circuits the loop spawn so the engine
    # never auto-opens Calendar / Gmail / Drive tabs. Defence-in-depth
    # for the startup-hook gate: this same function is reachable via
    # the /api/calendar/prep/scheduler/start route. Audit:
    # planning/00-handoff/TAB_OPEN_AUDIT.md.
    try:
        from app.config import _quiet_mode_enabled
    except Exception:
        _quiet_mode_enabled = lambda: False  # noqa: E731
    if _quiet_mode_enabled():
        _logger.info("quiet_mode_skipped path=calendar_prep_start_scheduler")
        print(
            "[anticipy.calendar_prep] quiet_mode_skipped "
            "path=calendar_prep_start_scheduler",
            flush=True,
        )
        return scheduler_state() | {"quiet_mode_skipped": True}
    with _STATE_LOCK:
        if _STATE.state == "running" and _THREAD is not None \
                and _THREAD.is_alive():
            return _STATE.to_dict() | {"already_running": True}
        _STATE.state = "running"
        _STATE.started_at = time.time()
        _STATE.last_error = ""
    _STOP_EVENT.clear()
    t = threading.Thread(
        target=_scheduler_loop,
        args=(int(within_minutes), float(scan_interval_s), _STOP_EVENT),
        name="anticipy.calendar_prep.scheduler",
        daemon=True,
    )
    t.start()
    _THREAD = t
    return scheduler_state()


def stop_scheduler() -> dict[str, Any]:
    """Ask the scheduler thread to exit at its next loop check.

    Returns the state snapshot. Test-only entry; production keeps the
    scheduler running for the engine's lifetime.
    """
    _STOP_EVENT.set()
    with _STATE_LOCK:
        if _STATE.state == "running":
            _STATE.state = "stopped"
    return scheduler_state()


__all__ = [
    "Meeting",
    "PrepResult",
    "SchedulerState",
    "BRIEF_SYSTEM_PROMPT",
    "find_upcoming_meeting",
    "pull_meeting_context",
    "compose_brief",
    "prep_meeting",
    "deliver_brief",
    "read_persisted_brief",
    "start_scheduler",
    "stop_scheduler",
    "scheduler_state",
]
