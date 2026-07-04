"""S6 — the email verification-code tool (reusable, service-agnostic).

Part of the autonomous-capability build: signing up for a service almost always ends in
"we emailed you a code — enter it to continue." This reads the **latest** verification
code sent by a given service from Gmail and extracts the code. It is a general TOOL, not a
site-specific script: you pass a ``service`` (a name, domain, or signup URL) and it finds
the most recent matching message and pulls the code out.

Two layers, cleanly separated so the reusable core is testable with zero network and zero
real login (which S6 must never perform):
  * The **pure core** — :func:`extract_code`, :func:`match_service`,
    :func:`latest_code_for_service` — operates on already-fetched message dicts. Regex-first
    with an optional injected ``llm_extract`` fallback for oddly-worded mails ("regex/LLM").
  * The **live adapter** — :class:`GmailReader` — a thin Gmail REST client (messages.list +
    messages.get) with an injectable HTTP layer, used only when a real access token is
    supplied. Tests drive the core with fixtures and the adapter with a fake HTTP.

Design note (safety): reading a code the AGENT's own signup just triggered is the intended
use. This is distinct from the recovery ladder's MFA rule ("never read the *user's*
personal 2FA codes") — a distinction the caller enforces by choosing the inbox/service.
"""
from __future__ import annotations

import base64
import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Sequence

from ..core.env import load_local_env

__all__ = [
    "VerificationEmail",
    "CodeHit",
    "GmailReader",
    "extract_code",
    "match_service",
    "latest_code_for_service",
    "read_verification_code",
    "from_env",
]


@dataclass(frozen=True)
class VerificationEmail:
    """A fetched message reduced to what code-extraction needs."""

    id: str = ""
    from_addr: str = ""
    subject: str = ""
    snippet: str = ""
    body: str = ""
    internal_ts: int = 0    # ms since epoch (Gmail internalDate) — for "latest"

    @property
    def haystack(self) -> str:
        return "\n".join((self.subject, self.snippet, self.body))


@dataclass(frozen=True)
class CodeHit:
    """A code found in a matching message."""

    code: str
    email: VerificationEmail
    matched_on: str = ""    # which token matched the service


# ── code extraction (regex-first, optional LLM fallback) ──────────────────────
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")

# Verification-context keyword; the code is the first digit-bearing token in the window
# AFTER it (so "one-time passcode 9KJ4T2" yields 9KJ4T2, not the word "passcode").
_KEYWORD = re.compile(
    r"(?:verification|confirmation|security|one[\s-]*time|1[\s-]*time|access|login|"
    r"sign[\s-]*in|authenticat\w*|passcode|pass\s*code|otp|pin|code|verify)",
    re.I,
)
_TOKEN = re.compile(r"(?<![A-Za-z0-9])([A-Z0-9]{4,8})(?![A-Za-z0-9])")
_LABEL_WINDOW = 48
# Google-style "G-123456".
_GOOGLE = re.compile(r"\bG-(\d{6})\b")
# "... is 123456" / "code: 123456".
_IS_CODE = re.compile(r"(?:is|:)\s*(?<![A-Za-z0-9])(\d{4,8})(?![A-Za-z0-9])", re.I)
# A bare 6-digit block (last resort).
_STANDALONE6 = re.compile(r"(?<![A-Za-z0-9._+/-])(\d{6})(?![A-Za-z0-9._+/-])")
# Reject obvious non-codes.
_YEAR = re.compile(r"^(?:19|20)\d{2}$")


def _plain(text: str) -> str:
    return _WS.sub(" ", _TAG.sub(" ", text or "")).strip()


def _looks_like_code(s: str) -> bool:
    if not s or not (4 <= len(s) <= 8):
        return False
    if not any(c.isdigit() for c in s):
        return False            # pure-alpha capture (e.g. "SECURE") is not a code
    if len(s) == 4 and _YEAR.match(s):
        return False            # a bare year is not a 4-digit code
    return True


def extract_code(text: str, subject: str = "",
                 llm_extract: Optional[Callable[[str], Optional[str]]] = None) -> Optional[str]:
    """Extract a verification code from an email body (+optional subject).

    Order of confidence: Google ``G-######`` → a labeled code near a verify keyword →
    ``"is 123456"`` → a bare 6-digit block. Codes must contain a digit and not be a bare
    year. If regex finds nothing and an ``llm_extract`` callable is supplied, it is asked
    last ("regex/LLM"). Returns the code string or ``None``.
    """
    blob = _plain(f"{subject}\n{text}")

    g = _GOOGLE.search(blob)
    if g:
        return g.group(1)

    for km in _KEYWORD.finditer(blob):
        window = blob[km.end():km.end() + _LABEL_WINDOW]
        for tm in _TOKEN.finditer(window):
            if _looks_like_code(tm.group(1)):
                return tm.group(1)

    m = _IS_CODE.search(blob)
    if m and _looks_like_code(m.group(1)):
        return m.group(1)

    m = _STANDALONE6.search(blob)
    if m:
        return m.group(1)

    if llm_extract is not None:
        try:
            got = llm_extract(blob)
        except Exception:
            got = None
        if got and _looks_like_code(str(got).strip()):
            return str(got).strip()
    return None


# ── service matching ──────────────────────────────────────────────────────────
def service_tokens(service: str) -> set[str]:
    """Normalize a service name / domain / signup URL to match tokens.

    "https://railway.app/signup" → {"railway.app", "railway"}; "Railway" → {"railway"};
    "noreply@railway.app" → {"railway.app", "railway"}.
    """
    s = (service or "").strip().lower()
    if not s:
        return set()
    m = re.search(r"https?://([^/]+)", s)
    host = m.group(1) if m else s
    host = host.split("@")[-1]                 # drop any local-part
    host = re.sub(r"^www\.", "", host).strip("/ ")
    toks: set[str] = set()
    if host:
        toks.add(host)
        label = host.split(".")[0] if "." in host else host
        if label:
            toks.add(label)
    if not m and "." not in s and "@" not in s and "/" not in s:
        toks.add(s)                            # a bare brand name
    return {t for t in toks if t}


def match_service(email: VerificationEmail, service: str) -> str:
    """Return the token that matched (from address preferred), or "" if none did."""
    toks = service_tokens(service)
    if not toks:
        return ""
    frm = (email.from_addr or "").lower()
    for t in toks:
        if t in frm:
            return t
    hay = email.haystack.lower()
    for t in toks:
        if t in hay:
            return t
    return ""


def latest_code_for_service(
    emails: Sequence[VerificationEmail], service: str, *,
    llm_extract: Optional[Callable[[str], Optional[str]]] = None,
) -> Optional[CodeHit]:
    """Newest message that both matches ``service`` and contains a code → its CodeHit."""
    candidates: list[tuple[int, VerificationEmail, str]] = []
    for e in emails or []:
        tok = match_service(e, service)
        if not tok:
            continue
        candidates.append((e.internal_ts, e, tok))
    for _ts, e, tok in sorted(candidates, key=lambda x: x[0], reverse=True):
        code = extract_code(e.body or e.snippet, e.subject, llm_extract=llm_extract)
        if code:
            return CodeHit(code=code, email=e, matched_on=tok)
    return None


# ── the live Gmail adapter (used only with a real token) ──────────────────────
_GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1/users"


def _requests_http(method: str, url: str, *, headers: Any = None, params: Any = None,
                   timeout: float = 30) -> Any:
    import requests  # noqa: WPS433 (lazy: importing this module never requires requests)
    return requests.request(method, url, headers=headers, params=params, timeout=timeout)


def _b64url(data: str) -> str:
    if not data:
        return ""
    pad = "=" * (-len(data) % 4)
    try:
        return base64.urlsafe_b64decode(data + pad).decode("utf-8", "replace")
    except Exception:
        return ""


def _header(headers: list, name: str) -> str:
    for h in headers or []:
        if str(h.get("name", "")).lower() == name.lower():
            return str(h.get("value", ""))
    return ""


def _walk_body(payload: dict) -> str:
    """Concatenate text/plain (preferred) then text/html parts of a Gmail payload."""
    out: list[str] = []

    def rec(part: dict) -> None:
        mime = str(part.get("mimeType") or "")
        body = part.get("body") or {}
        data = body.get("data")
        if data and ("text/plain" in mime or "text/html" in mime or not part.get("parts")):
            out.append(_b64url(data))
        for sub in part.get("parts") or []:
            rec(sub)

    rec(payload or {})
    return "\n".join(t for t in out if t)


class GmailReader:
    """Minimal Gmail REST reader. HTTP is injectable so the adapter is testable offline."""

    def __init__(self, access_token: str, *, http: Optional[Callable[..., Any]] = None,
                 user: str = "me") -> None:
        self.access_token = (access_token or "").strip()
        self._http = http or _requests_http
        self.user = user or "me"

    def _auth(self) -> dict:
        return {"Authorization": f"Bearer {self.access_token}"}

    def recent(self, query: str = "", *, max_results: int = 10) -> list[VerificationEmail]:
        """List recent messages (optionally filtered by a Gmail search query) and fetch each."""
        listing = _safe_json(self._http(
            "GET", f"{_GMAIL_BASE}/{self.user}/messages",
            headers=self._auth(),
            params={"maxResults": max_results, "q": query or "newer_than:1d"},
            timeout=30))
        out: list[VerificationEmail] = []
        for ref in listing.get("messages") or []:
            mid = ref.get("id")
            if not mid:
                continue
            msg = _safe_json(self._http(
                "GET", f"{_GMAIL_BASE}/{self.user}/messages/{mid}",
                headers=self._auth(), params={"format": "full"}, timeout=30))
            out.append(self._to_email(msg))
        return out

    @staticmethod
    def _to_email(msg: dict) -> VerificationEmail:
        payload = msg.get("payload") or {}
        headers = payload.get("headers") or []
        try:
            ts = int(msg.get("internalDate") or 0)
        except (TypeError, ValueError):
            ts = 0
        return VerificationEmail(
            id=str(msg.get("id") or ""),
            from_addr=_header(headers, "From"),
            subject=_header(headers, "Subject"),
            snippet=str(msg.get("snippet") or ""),
            body=_walk_body(payload),
            internal_ts=ts,
        )


def _safe_json(resp: Any) -> dict:
    try:
        out = resp.json()
        return out if isinstance(out, dict) else {}
    except Exception:
        return {}


# ── the reusable tool entrypoint ──────────────────────────────────────────────
def read_verification_code(
    service: str, *,
    reader: Optional[GmailReader] = None,
    emails: Optional[Sequence[VerificationEmail]] = None,
    query: str = "",
    max_results: int = 10,
    llm_extract: Optional[Callable[[str], Optional[str]]] = None,
) -> Optional[str]:
    """Return the latest verification code for ``service``.

    Supply ``emails`` (already-fetched fixtures, e.g. in tests) OR a live ``reader``. With a
    reader, the Gmail search defaults to recent mail; you can pass ``query`` to narrow it.
    """
    if emails is None:
        if reader is None:
            return None
        q = query or f'newer_than:1d "{next(iter(service_tokens(service)), service)}"'
        emails = reader.recent(q, max_results=max_results)
    hit = latest_code_for_service(emails, service, llm_extract=llm_extract)
    return hit.code if hit else None


def from_env(**kwargs: Any) -> Optional[GmailReader]:
    """Build a live reader if a Gmail access token is present in the environment, else None.

    (No token is checked in for S6 — the tool is exercised via fixtures. This factory is the
    seam the S9 product wire uses once a per-user Gmail token is available.)
    """
    load_local_env()
    token = os.environ.get("GMAIL_ACCESS_TOKEN") or os.environ.get("GOOGLE_ACCESS_TOKEN")
    if not token:
        return None
    return GmailReader(token, **kwargs)
