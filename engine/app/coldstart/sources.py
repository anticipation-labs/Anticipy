"""Cold-start inhale source registry.

The cold-start orchestrator (``auto_inhale.py``) reads which Chrome
surfaces to walk from a user-editable JSON config at
``~/.anticipy/inhale_sources.json``. URLs MUST NOT live in Python
source files (rule 1 of ``planning/00-handoff/NORTH_STAR_v2.md``:
universal action agent, no per-app code). The DOM walker and the
LLM extraction are generic; this module externalizes the URL
CHOICES so a user can edit the file (or POST to
``/api/coldstart/sources``) to add Outlook, Slack, Notion, or any
other surface they are already logged into in Chrome.

Behavior:

* On first call ``load_enabled()`` materializes the file with the
  shipped defaults (Gmail inbox, Google Calendar week view, Google
  Drive recents) and a top-level ``_comment`` explaining each field.
* All writes are atomic (temp file + ``os.replace``) and chmod 0644.
* ``load_all()`` returns the full config dict (including disabled
  rows and version) for the UI; ``load_enabled()`` returns only the
  rows that are ``enabled`` and sorted by ``priority`` ascending,
  which is what the walker iterates.
* ``validate_payload()`` rejects malformed POSTs with a list of
  errors so the route handler can return HTTP 400 with detail.

This module owns NO knowledge of Gmail or Google. The default
config could just as well be empty; we ship the same three rows
the engine had hardcoded so behavior does not regress on a fresh
install.
"""

from __future__ import annotations

import json
import os
import stat
import tempfile
import threading
from pathlib import Path
from typing import Any


CONFIG_VERSION = 1


# Required fields every entry in ``sources`` must define. The walker
# tolerates missing optional fields (``scrape_selector``,
# ``max_pages``) but the LLM batching pipeline does not depend on
# them. Keeping the schema small reduces surface area for breakage.
_REQUIRED_FIELDS = ("id", "label", "url", "enabled", "priority")
_OPTIONAL_FIELDS = ("scrape_selector", "max_pages")


# Shipped default config template. Lives as a JSON file alongside
# this module at ``data/inhale_sources.default.json`` so the URL
# CHOICES are NOT embedded in any Python source file (rule 1 of
# planning/00-handoff/NORTH_STAR_v2.md: no per-app code; URL
# literals are data, not code).

def _default_template_path() -> Path:
    """Resolve the shipped default JSON template path.

    Tries `__file__`-relative first (source tree), then falls back to
    PyInstaller's `_MEIPASS` extraction dir when running from a
    frozen sidecar binary. Both are searched at call time so a
    bundle that ships the data file under either layout still works.
    """
    here = Path(__file__).parent / "data" / "inhale_sources.default.json"
    if here.exists():
        return here
    # PyInstaller frozen bundle: data files unpacked under sys._MEIPASS.
    import sys
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        m = Path(meipass) / "app" / "coldstart" / "data" / \
            "inhale_sources.default.json"
        if m.exists():
            return m
    return here  # original path; read attempt below returns OSError


_DEFAULT_TEMPLATE_PATH = _default_template_path()


_FALLBACK_COMMENT = (
    "Edit this file or use /api/coldstart/sources to change which "
    "sources Anticipy reads on cold start. Set enabled=false to "
    "skip a source. Add any source you are logged into in Chrome "
    "by appending a new entry."
)


# Embedded last-resort defaults. The JSON template at
# ``data/inhale_sources.default.json`` is the source of truth (data,
# not code, per rule 1). These constants exist ONLY as a safety net
# for shipped sidecar binaries that fail to ship the data file in the
# bundle (PyInstaller spec mistake, etc). Cold-start on a fresh
# install must work in 90s; an empty source list means 0 people
# inhaled, which is the failure mode this guard prevents. Keep these
# in sync with the JSON template.
_EMBEDDED_DEFAULT_SOURCES = [
    {
        "id": "gmail",
        "label": "Gmail contacts and senders",
        "url": "https://mail.google.com/mail/u/0/#inbox",
        "scrape_selector": "[role='row']",
        "max_pages": 5,
        "enabled": True,
        "priority": 1,
    },
    {
        "id": "google_calendar",
        "label": "Google Calendar attendees",
        "url": "https://calendar.google.com/calendar/r/week",
        "scrape_selector": "[data-eventid]",
        "max_pages": 1,
        "enabled": True,
        "priority": 2,
    },
    {
        "id": "google_drive",
        "label": "Google Drive collaborators",
        "url": "https://drive.google.com/drive/recent",
        "scrape_selector": "[data-id]",
        "max_pages": 3,
        "enabled": True,
        "priority": 3,
    },
]


def _embedded_fallback_doc() -> dict[str, Any]:
    """Last-resort defaults so a fresh install still inhales."""
    return {
        "version": CONFIG_VERSION,
        "sources": [dict(s) for s in _EMBEDDED_DEFAULT_SOURCES],
        "_comment": _FALLBACK_COMMENT,
    }


def _load_default_template() -> dict[str, Any]:
    """Read the shipped default JSON template (the data file).

    Returns a defensive copy so callers can mutate freely. If the
    template is missing or corrupt we fall back to the embedded
    constants above so cold-start still works in shipped bundles
    that did not include the data file.
    """
    path = _default_template_path()
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return _embedded_fallback_doc()
    try:
        parsed = json.loads(raw)
    except Exception:
        return _embedded_fallback_doc()
    if not isinstance(parsed, dict):
        return _embedded_fallback_doc()
    parsed.setdefault("version", CONFIG_VERSION)
    if not isinstance(parsed.get("sources"), list):
        parsed["sources"] = []
    # If the file is present but empty, fall back to embedded defaults
    # so the engine still has something to inhale on first launch.
    if not parsed["sources"]:
        parsed["sources"] = [dict(s) for s in _EMBEDDED_DEFAULT_SOURCES]
    parsed.setdefault("_comment", _FALLBACK_COMMENT)
    parsed["sources"] = [dict(s) for s in parsed["sources"]
                         if isinstance(s, dict)]
    return parsed


_LOCK = threading.Lock()


def _config_dir() -> Path:
    """Resolve the directory the file lives in.

    Honors ``ANTICIPY_INHALE_SOURCES_DIR`` so the smoke test (and
    other automated callers) can sandbox writes. Falls back to
    ``~/.anticipy``.
    """
    raw = os.environ.get("ANTICIPY_INHALE_SOURCES_DIR", "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".anticipy"


def config_path() -> Path:
    """Canonical path to ``inhale_sources.json``."""
    override = os.environ.get("ANTICIPY_INHALE_SOURCES_PATH", "").strip()
    if override:
        return Path(override).expanduser()
    return _config_dir() / "inhale_sources.json"


def _default_doc() -> dict[str, Any]:
    """Return a fresh copy of the default config document.

    Read straight from the shipped JSON template so URL choices
    never live in this Python file.
    """
    return _load_default_template()


def _atomic_write(path: Path, data: dict[str, Any]) -> None:
    """Write ``data`` to ``path`` atomically with 0644 perms.

    Uses ``NamedTemporaryFile`` in the same directory so
    ``os.replace`` is atomic on the same filesystem.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2, ensure_ascii=False)
    fd, tmp_path = tempfile.mkstemp(
        prefix=".inhale_sources.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
            fh.flush()
            try:
                os.fsync(fh.fileno())
            except OSError:
                pass
        os.replace(tmp_path, path)
        try:
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR
                     | stat.S_IRGRP | stat.S_IROTH)
        except OSError:
            pass
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _coerce_entry(raw: Any) -> dict[str, Any] | None:
    """Normalize one entry, dropping unknown fields, fixing types."""
    if not isinstance(raw, dict):
        return None
    out: dict[str, Any] = {}
    for f in _REQUIRED_FIELDS + _OPTIONAL_FIELDS:
        if f in raw:
            out[f] = raw[f]
    return out


def validate_payload(payload: Any) -> tuple[bool, list[str], dict[str, Any]]:
    """Validate a POST body, return ``(ok, errors, normalized_doc)``.

    A valid payload is ``{"version": int, "sources": [..]}``. Each
    source must define every field in ``_REQUIRED_FIELDS`` with the
    correct type. Unknown keys are dropped (forward compatibility).
    """
    errors: list[str] = []
    if not isinstance(payload, dict):
        return False, ["payload must be a JSON object"], {}
    sources = payload.get("sources")
    if not isinstance(sources, list):
        errors.append("sources must be a list")
        return False, errors, {}
    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for idx, raw in enumerate(sources):
        if not isinstance(raw, dict):
            errors.append(f"sources[{idx}]: not an object")
            continue
        # Required field presence + type.
        sid = raw.get("id")
        if not isinstance(sid, str) or not sid.strip():
            errors.append(f"sources[{idx}].id: must be non-empty string")
            sid = ""
        else:
            sid = sid.strip()
        if sid:
            if sid in seen_ids:
                errors.append(f"sources[{idx}].id: duplicate id {sid!r}")
            seen_ids.add(sid)
        label = raw.get("label")
        if not isinstance(label, str) or not label.strip():
            errors.append(f"sources[{idx}].label: must be non-empty string")
        url = raw.get("url")
        if (not isinstance(url, str)
                or not url.strip()
                or not (url.startswith("http://")
                        or url.startswith("https://"))):
            errors.append(
                f"sources[{idx}].url: must be http(s) URL string")
        enabled = raw.get("enabled")
        if not isinstance(enabled, bool):
            errors.append(f"sources[{idx}].enabled: must be boolean")
        priority = raw.get("priority")
        if not isinstance(priority, int) or isinstance(priority, bool):
            errors.append(f"sources[{idx}].priority: must be integer")
        # Optional fields: validate type only if present.
        if "scrape_selector" in raw and not isinstance(
                raw["scrape_selector"], str):
            errors.append(
                f"sources[{idx}].scrape_selector: must be string when set")
        if "max_pages" in raw:
            mp = raw["max_pages"]
            if not isinstance(mp, int) or isinstance(mp, bool) or mp < 0:
                errors.append(
                    f"sources[{idx}].max_pages: "
                    "must be non-negative integer when set")
        normalized.append(_coerce_entry(raw) or {})
    version = payload.get("version", CONFIG_VERSION)
    if not isinstance(version, int) or isinstance(version, bool):
        errors.append("version: must be integer")
        version = CONFIG_VERSION
    comment = payload.get("_comment", _FALLBACK_COMMENT)
    if not isinstance(comment, str):
        comment = _FALLBACK_COMMENT
    doc = {
        "version": int(version),
        "sources": normalized,
        "_comment": comment,
    }
    return (len(errors) == 0), errors, doc


def _ensure_initialized() -> Path:
    """Materialize the file with defaults if it does not exist."""
    path = config_path()
    if path.exists():
        return path
    with _LOCK:
        if not path.exists():
            _atomic_write(path, _default_doc())
    return path


def load_all() -> dict[str, Any]:
    """Return the full config dict, materializing defaults if needed.

    Read errors fall back to defaults (the file may be malformed
    mid-edit). Callers wanting strict validation should call
    ``validate_payload`` themselves.
    """
    path = _ensure_initialized()
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return _default_doc()
    try:
        parsed = json.loads(raw)
    except Exception:
        return _default_doc()
    if not isinstance(parsed, dict):
        return _default_doc()
    parsed.setdefault("version", CONFIG_VERSION)
    parsed.setdefault("sources", [])
    parsed.setdefault("_comment", _FALLBACK_COMMENT)
    if not isinstance(parsed.get("sources"), list):
        parsed["sources"] = []
    return parsed


def load_enabled() -> list[dict[str, Any]]:
    """Return only the sources flagged enabled, sorted by priority.

    The walker iterates this list. Disabled rows are silently
    skipped here so the orchestrator does not need to know about
    the enabled flag.
    """
    doc = load_all()
    out: list[dict[str, Any]] = []
    for raw in doc.get("sources") or []:
        if not isinstance(raw, dict):
            continue
        if not raw.get("enabled"):
            continue
        out.append(dict(raw))
    out.sort(key=lambda r: (
        int(r.get("priority") or 0),
        str(r.get("id") or ""),
    ))
    return out


def save(doc: dict[str, Any]) -> Path:
    """Persist a validated config document atomically.

    Caller MUST have already passed the doc through
    ``validate_payload`` (or constructed it from
    ``load_all`` + edits). Returns the path written.
    """
    path = config_path()
    with _LOCK:
        _atomic_write(path, doc)
    return path


def default_sources() -> list[dict[str, Any]]:
    """Expose the shipped defaults (a copy) for tests."""
    return list(_load_default_template().get("sources") or [])


def default_comment() -> str:
    return str(_load_default_template().get("_comment")
               or _FALLBACK_COMMENT)


__all__ = [
    "CONFIG_VERSION",
    "config_path",
    "default_comment",
    "default_sources",
    "load_all",
    "load_enabled",
    "save",
    "validate_payload",
]
