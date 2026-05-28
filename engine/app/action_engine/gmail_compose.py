"""Gmail draft creation through the user's real CDP Chrome.

This module parses explicit draft requests, opens Gmail's compose URL
in Chrome over CDP, and leaves the message as a draft.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


@dataclass(frozen=True)
class DraftRequest:
    to: str
    subject: str
    body: str


@dataclass(frozen=True)
class DraftResult:
    ok: bool
    error: str
    evidence: str
    compose_url: str


_EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
_MARKER_RE = re.compile(r"\be10-[A-Za-z0-9-]{12,}\b")


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip(" .,:;")


def _first_email(text: str) -> str:
    match = _EMAIL_RE.search(text or "")
    return match.group(0) if match else ""


def _marker(text: str) -> str:
    match = _MARKER_RE.search(text or "")
    return match.group(0) if match else ""


def _quoted_after(label: str, text: str) -> str:
    pattern = rf"\b{label}\s+(['\"])(?P<value>.+?)(?<!\\)\1"
    match = re.search(pattern, text or "", re.IGNORECASE | re.DOTALL)
    if match:
        return match.group("value").strip()
    return ""


def _subject_from_text(text: str, marker: str) -> str:
    subject = _quoted_after("subject", text)
    if subject:
        return subject
    match = re.search(
        r"\bsubject\s*[:=-]\s*(?P<value>.+?)(?:\b(?:and|with)\s+body\b|$)",
        text or "",
        re.IGNORECASE | re.DOTALL,
    )
    if match:
        subject = _clean(match.group("value"))
        if subject:
            return subject
    match = re.search(
        r"\babout\s+(?P<value>.+?)(?:[.!?]\s|$)",
        text or "",
        re.IGNORECASE | re.DOTALL,
    )
    if match:
        subject = _clean(match.group("value"))
        if subject:
            return subject[:180]
    return f"Anticipy proof {marker}" if marker else "Anticipy draft"


def _body_from_text(text: str, marker: str) -> str:
    body = _quoted_after("body", text)
    if not body:
        match = re.search(
            r"\b(?:saying|body\s*[:=-])\s*(?P<value>.+?)(?:\s+Do not send|$)",
            text or "",
            re.IGNORECASE | re.DOTALL,
        )
        if match:
            body = match.group("value").strip()
    if not body:
        body = "Draft created by Anticipy for review."
    if marker and marker not in body:
        body = body.rstrip() + f"\n\nProof marker UUID: {marker}"
    return body.strip()


def parse_draft_intent(text: str) -> DraftRequest | None:
    low = (text or "").lower()
    if not re.search(r"\b(draft|email|mail|gmail|send|follow up|share)\b", low):
        return None
    to = _first_email(text)
    if not to:
        return None
    marker = _marker(text)
    subject = _subject_from_text(text, marker)
    body = _body_from_text(text, marker)
    if not subject or not body:
        return None
    return DraftRequest(to=to, subject=subject, body=body)


def _compose_url(request: DraftRequest) -> str:
    params = urllib.parse.urlencode(
        {
            "view": "cm",
            "fs": "1",
            "tf": "1",
            "to": request.to,
            "su": request.subject,
            "body": request.body,
        }
    )
    return f"https://mail.google.com/mail/?{params}"


def _cdp_json(cdp_port: int, path: str, method: str = "GET") -> tuple[Any | None, str]:
    req = urllib.request.Request(
        f"http://127.0.0.1:{cdp_port}{path}",
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
        if raw:
            return json.loads(raw), ""
        return {}, ""
    except urllib.error.HTTPError as exc:
        return None, f"HTTP {exc.code}: {exc.read().decode(errors='replace')[:1000]}"
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def _open_tab(cdp_port: int, url: str) -> tuple[dict[str, Any], str]:
    encoded = urllib.parse.quote(url, safe=":/?&=%#")
    data, error = _cdp_json(cdp_port, f"/json/new?{encoded}", method="PUT")
    if error:
        data, error = _cdp_json(cdp_port, f"/json/new?{encoded}")
    if error or not isinstance(data, dict):
        return {}, error or "CDP /json/new did not return a target"
    target_id = str(data.get("id") or "")
    if target_id:
        _cdp_json(cdp_port, f"/json/activate/{target_id}")
    return data, ""


def _tabs(cdp_port: int) -> tuple[list[dict[str, Any]], str]:
    data, error = _cdp_json(cdp_port, "/json/list")
    if error:
        return [], error
    if not isinstance(data, list):
        return [], "CDP /json/list did not return a list"
    return [item for item in data if isinstance(item, dict)], ""


def create_gmail_draft(
    request: DraftRequest, cdp_port: int = 9222, marker: str = ""
) -> DraftResult:
    compose_url = _compose_url(request)
    target, error = _open_tab(cdp_port, compose_url)
    if error:
        evidence = json.dumps(
            {
                "type": "gmail_cdp_compose",
                "cdp_port": cdp_port,
                "compose_url": compose_url,
                "error": error,
            },
            sort_keys=True,
        )
        return DraftResult(False, error, evidence, compose_url)

    time.sleep(4.0)
    tabs, tabs_error = _tabs(cdp_port)
    proof_blob = json.dumps(
        {
            "type": "gmail_cdp_compose",
            "cdp_port": cdp_port,
            "compose_url": compose_url,
            "target": target,
            "tabs": [
                {
                    "id": tab.get("id"),
                    "type": tab.get("type"),
                    "url": tab.get("url"),
                    "title": tab.get("title"),
                }
                for tab in tabs
                if tab.get("type") == "page"
            ],
            "tabs_error": tabs_error,
            "to": request.to,
            "subject": request.subject,
            "body_contains_marker": bool(marker and marker in request.body),
            "marker_uuid": marker,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return DraftResult(True, "", proof_blob, compose_url)


def draft_from_transcript(text: str, cdp_port: int = 9222) -> DraftResult | None:
    request = parse_draft_intent(text)
    if request is None:
        return None
    return create_gmail_draft(request, cdp_port=cdp_port, marker=_marker(text))
