"""Google Drive source extractor for the cold-start dossier inhale.

Returns:

    {
        "source": "drive",
        "ok": bool,
        "recent_docs": [
            {"title": str, "co_editors": [str], "last_modified": str,
             "kind": str}     # 'doc' | 'sheet' | 'slide' | 'pdf' | ...
        ],
        "project_names": [str],   # inferred from doc title prefixes
        "error": str,
    }

Top 10 most-recent docs. Project names = the leading token of each
title when it looks like a project (e.g. 'Q3 roadmap - design notes'
yields 'Q3 roadmap'). The clarifier uses recent_docs + project_names
to guess "your big project is X".

Drive signed-out → ok=False with empty lists.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from . import _bridge_protocol as _bp


DRIVE_RECENT_URL = "https://drive.google.com/drive/recent"


def _norm_str_list(raw: Any, cap: int = 10) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for x in raw:
        s = str(x or "").strip()
        if not s:
            continue
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
        if len(out) >= cap:
            break
    return out


def _normalize_recent_docs(rows: list[dict], cap: int = 10) -> list[dict]:
    out: list[dict] = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        title = str(r.get("title") or "").strip()
        if not title:
            continue
        out.append({
            "title": title[:240],
            "co_editors": _norm_str_list(r.get("co_editors"), cap=10),
            "last_modified": str(r.get("last_modified")
                                 or r.get("modified") or "")[:60],
            "kind": str(r.get("kind") or "").strip().lower()[:24],
        })
        if len(out) >= cap:
            break
    return out


# Splits "Q3 roadmap - design notes" → "Q3 roadmap".
# Also splits on em-quotes, slashes, parens, colons.
_TITLE_SPLIT_RE = re.compile(r"\s*[-:|/()\[\]]+\s*")


def _infer_project_names(docs: list[dict]) -> list[str]:
    """Take leading title tokens, count, return the top few.

    Skips generic words like 'untitled', 'notes', 'doc'.
    """
    if not docs:
        return []
    GENERIC = {
        "untitled", "untitled document", "untitled spreadsheet",
        "notes", "note", "doc", "document", "draft",
        "scratch", "temp", "test", "copy of",
    }
    counts: Counter[str] = Counter()
    for d in docs:
        title = str((d or {}).get("title") or "").strip()
        if not title:
            continue
        head = _TITLE_SPLIT_RE.split(title, maxsplit=1)[0].strip()
        head_norm = head.lower()
        if head_norm in GENERIC:
            continue
        # Must be at least 3 chars and contain at least one alpha char
        if len(head) < 3:
            continue
        if not re.search(r"[A-Za-z]", head):
            continue
        counts[head] += 1
    out: list[str] = []
    for name, _freq in counts.most_common(6):
        out.append(name)
    return out


async def extract(bridge: Any) -> dict:
    """Drive the wearer's Chrome to read Drive recent docs.

    Extension is expected to return:

        {"docs": [{title, co_editors, last_modified, kind}, ...]}
    """
    payload = {
        "type": "extract_dossier_source",
        "source": "drive",
        "url": DRIVE_RECENT_URL,
        "row_cap": 40,
    }
    try:
        resp = await _bp.dispatch(bridge, payload)
    except Exception as exc:
        return {
            "source": "drive",
            "ok": False,
            "recent_docs": [],
            "project_names": [],
            "error": f"dispatch raised: {type(exc).__name__}: {exc}",
        }

    if not isinstance(resp, dict) or not resp.get("ok"):
        return {
            "source": "drive",
            "ok": False,
            "recent_docs": [],
            "project_names": [],
            "error": str((resp or {}).get("error") or "extension reported not ok"),
        }

    data = resp.get("data") or {}
    if not isinstance(data, dict):
        data = {}
    docs = data.get("docs") or []
    if not isinstance(docs, list):
        docs = []

    recent_docs = _normalize_recent_docs(docs, cap=10)
    return {
        "source": "drive",
        "ok": True,
        "recent_docs": recent_docs,
        "project_names": _infer_project_names(recent_docs),
    }


__all__ = ["extract", "DRIVE_RECENT_URL"]
