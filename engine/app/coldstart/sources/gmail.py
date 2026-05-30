"""Gmail source extractor for the cold-start dossier inhale.

Returns:

    {
        "source": "gmail",
        "ok": bool,
        "top_contacts": [
            {"email": str, "name": str, "freq": int}
        ],
        "recent_threads": [
            {"subject": str, "from": str, "snippet": str, "date": str}
        ],
        "signature": str,        # best-guess of user's email signature
        "error": str,            # only when ok is False
    }

Top contacts = the 20 most-emailed addresses (across inbox + sent).
Recent threads = last 5 unique subjects pulled from the inbox.
Signature = best-effort sniff of the user's own sign-off from a sent
            row, if the extension's payload included one.

Generic + universal: this file owns NO Gmail-specific selectors. The
extension is told 'pull contacts and recent threads from gmail',
returns shaped data, we slice it. If Gmail is signed-out, ok=False
with empty lists; no crash.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from . import _bridge_protocol as _bp


GMAIL_INBOX_URL = "https://mail.google.com/mail/u/0/#inbox"
GMAIL_SENT_URL = "https://mail.google.com/mail/u/0/#sent"


_EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}")


def _normalize_email(raw: str) -> str:
    cleaned = (raw or "").strip().lower()
    m = _EMAIL_RE.search(cleaned)
    return m.group(0) if m else ""


def _is_noreply(email: str) -> bool:
    """Heuristic for non-human addresses."""
    e = (email or "").lower()
    if not e:
        return True
    bad = (
        "no-reply", "noreply", "donotreply", "do-not-reply",
        "notifications@", "notify@", "alerts@", "automated@",
        "mailer-daemon", "bounce@", "support+",
    )
    return any(b in e for b in bad)


def _top_contacts(rows: list[dict], cap: int = 20) -> list[dict]:
    """Rank addresses by raw frequency across all supplied rows."""
    if not rows:
        return []
    counts: Counter[str] = Counter()
    name_for: dict[str, str] = {}
    for r in rows:
        if not isinstance(r, dict):
            continue
        sender_raw = str(r.get("from") or r.get("sender") or "")
        recipients_raw = r.get("to") or []
        # Single from + multiple to addresses; count both directions
        # so 'people I email' shows up alongside 'people who email me'.
        candidates = [sender_raw]
        if isinstance(recipients_raw, list):
            candidates.extend(str(x) for x in recipients_raw)
        for raw in candidates:
            email = _normalize_email(raw)
            if not email:
                continue
            if _is_noreply(email):
                continue
            counts[email] += 1
            if email not in name_for:
                # Pull a display name out of the raw header if present
                # ("Sarah Lin <sarah@x.com>" → "Sarah Lin").
                stripped = re.sub(r"<[^>]+>", "", raw).strip()
                stripped = stripped.strip('"').strip("'").strip()
                if stripped and "@" not in stripped:
                    name_for[email] = stripped
    out: list[dict] = []
    for email, freq in counts.most_common(cap):
        out.append({
            "email": email,
            "name": name_for.get(email, ""),
            "freq": int(freq),
        })
    return out


def _recent_threads(rows: list[dict], cap: int = 5) -> list[dict]:
    """First N rows in payload order, deduped by subject."""
    out: list[dict] = []
    seen: set[str] = set()
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        subj = str(r.get("subject") or "").strip()
        if not subj or subj.lower() in seen:
            continue
        seen.add(subj.lower())
        out.append({
            "subject": subj[:160],
            "from": str(r.get("from") or r.get("sender") or "")[:160],
            "snippet": str(r.get("snippet") or "")[:200],
            "date": str(r.get("date") or "")[:80],
        })
        if len(out) >= cap:
            break
    return out


def _sniff_signature(sent_rows: list[dict]) -> str:
    """Pull the user's likely sign-off out of one of their sent rows.

    Looks at the last 3 lines of each sent body, picks the most-common
    short trailing block. Falls back to '' when the extension did not
    return any body content (which is the common case if it only
    returned headers).
    """
    if not sent_rows:
        return ""
    tails: Counter[str] = Counter()
    for r in sent_rows:
        body = str((r or {}).get("body") or "")
        if not body:
            continue
        lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
        if len(lines) < 2:
            continue
        tail = " ".join(lines[-3:]).strip()
        if 4 <= len(tail) <= 120:
            tails[tail] += 1
    if not tails:
        return ""
    return tails.most_common(1)[0][0]


async def extract(bridge: Any) -> dict:
    """Drive the wearer's Chrome to read Gmail inbox + sent rows.

    Calls the bridge once with a multi-surface payload. The extension
    is expected to open the inbox + sent URLs (in the Anticipy tab
    group), scrape visible rows, and return a list of dicts shaped:

        {
            "inbox": [{from, subject, snippet, date}, ...],
            "sent":  [{to, subject, body, date}, ...]
        }
    """
    payload = {
        "type": "extract_dossier_source",
        "source": "gmail",
        "urls": [GMAIL_INBOX_URL, GMAIL_SENT_URL],
        "row_cap": 80,
    }
    try:
        resp = await _bp.dispatch(bridge, payload)
    except Exception as exc:
        return {
            "source": "gmail",
            "ok": False,
            "top_contacts": [],
            "recent_threads": [],
            "signature": "",
            "error": f"dispatch raised: {type(exc).__name__}: {exc}",
        }

    if not isinstance(resp, dict) or not resp.get("ok"):
        return {
            "source": "gmail",
            "ok": False,
            "top_contacts": [],
            "recent_threads": [],
            "signature": "",
            "error": str((resp or {}).get("error") or "extension reported not ok"),
        }

    data = resp.get("data") or {}
    if not isinstance(data, dict):
        data = {}
    inbox_rows = data.get("inbox") or []
    sent_rows = data.get("sent") or []
    if not isinstance(inbox_rows, list):
        inbox_rows = []
    if not isinstance(sent_rows, list):
        sent_rows = []

    all_rows = list(inbox_rows) + list(sent_rows)
    return {
        "source": "gmail",
        "ok": True,
        "top_contacts": _top_contacts(all_rows, cap=20),
        "recent_threads": _recent_threads(inbox_rows, cap=5),
        "signature": _sniff_signature(sent_rows),
    }


__all__ = ["extract", "GMAIL_INBOX_URL", "GMAIL_SENT_URL"]
