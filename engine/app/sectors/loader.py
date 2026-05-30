"""Sector hint loader.

Reads YAML hint packages from ``profiles/`` and returns dicts with the
canonical schema. Results are cached because the dict is reused on every
planner call and the YAML never changes at runtime.

Also exposes ``format_system_prompt`` which renders the hints into the
fragment the planner prepends to its system prompt.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import yaml

_PROFILES_DIR = Path(__file__).resolve().parent / "profiles"

REQUIRED_FIELDS = (
    "sector",
    "display_name",
    "common_tools",
    "common_goals",
    "vocab_hints",
    "preferred_channels",
    "detection_signals",
    "sample_personas",
)

# The nine canonical sector names: eight verticals plus the generic fallback.
KNOWN_SECTORS = (
    "construction",
    "sales",
    "job_seeking",
    "healthcare",
    "startup_founder",
    "stay_at_home_parent",
    "pensioner",
    "freelance",
    "generic",
)

_CACHE: dict[str, dict[str, Any]] = {}
_CACHE_LOCK = threading.Lock()
_LOAD_COUNTER: dict[str, int] = {}


def _yaml_path(sector_name: str) -> Path:
    return _PROFILES_DIR / f"{sector_name}.yaml"


def _validate(sector_name: str, data: dict[str, Any]) -> None:
    """Raise if required fields are missing or empty."""
    if not isinstance(data, dict):
        raise ValueError(f"sector {sector_name!r}: yaml root must be a mapping")
    missing = [f for f in REQUIRED_FIELDS if f not in data]
    if missing:
        raise ValueError(
            f"sector {sector_name!r}: yaml missing required fields: {missing}"
        )
    # sector value must agree with filename
    if str(data.get("sector", "")).strip() != sector_name:
        raise ValueError(
            f"sector {sector_name!r}: yaml 'sector' field "
            f"({data.get('sector')!r}) does not match filename"
        )
    list_fields = (
        "common_tools",
        "common_goals",
        "vocab_hints",
        "preferred_channels",
        "detection_signals",
        "sample_personas",
    )
    for f in list_fields:
        v = data.get(f)
        if not isinstance(v, list) or not v:
            raise ValueError(
                f"sector {sector_name!r}: field {f!r} must be a non-empty list"
            )


def load_hints(sector_name: str) -> dict[str, Any]:
    """Load and cache the hint package for ``sector_name``.

    Unknown sectors fall back to ``generic``. The returned dict is the
    same object on every call (cached), so callers must not mutate it.
    """
    name = (sector_name or "").strip().lower()
    if name not in KNOWN_SECTORS:
        name = "generic"

    with _CACHE_LOCK:
        cached = _CACHE.get(name)
        if cached is not None:
            return cached

    path = _yaml_path(name)
    if not path.is_file():
        raise FileNotFoundError(f"sector profile yaml missing: {path}")

    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    _validate(name, raw)

    with _CACHE_LOCK:
        # double check inside lock (another thread may have raced)
        cached = _CACHE.get(name)
        if cached is not None:
            return cached
        _CACHE[name] = raw
        _LOAD_COUNTER[name] = _LOAD_COUNTER.get(name, 0) + 1
        return raw


def cache_reset() -> None:
    """Clear the in-memory cache. Used by tests.

    Also clears the detector's distinctive-keyword cache so that any
    test patching profiles or KNOWN_SECTORS sees a fresh recomputation
    on the next ``detect_sector`` call.
    """
    with _CACHE_LOCK:
        _CACHE.clear()
        _LOAD_COUNTER.clear()
    try:
        from . import detector as _detector  # local import avoids cycle
        _detector._reset_keyword_cache()
    except Exception:
        pass


def load_count(sector_name: str) -> int:
    """How many times ``load_hints`` actually read the YAML from disk.

    Used in tests to prove the cache is doing its job.
    """
    name = (sector_name or "").strip().lower()
    with _CACHE_LOCK:
        return int(_LOAD_COUNTER.get(name, 0))


def _csv(items: list[Any]) -> str:
    """Join a list as a comma separated string, trimming and dropping blanks."""
    cleaned = [str(x).strip() for x in (items or []) if str(x).strip()]
    return ", ".join(cleaned)


def format_system_prompt(hints: dict[str, Any]) -> str:
    """Render hints as the planner system prompt fragment.

    Returns a single sentence describing the user. The exact template
    matches the spec in the Phase 8 brief.
    """
    display_name = str(hints.get("display_name", "user")).strip() or "user"
    tools = _csv(hints.get("common_tools", []))
    goals = _csv(hints.get("common_goals", []))
    vocab = _csv(hints.get("vocab_hints", []))
    channels = _csv(hints.get("preferred_channels", []))

    return (
        f"The user is a {display_name}. "
        f"They typically use: {tools}. "
        f"Common goals: {goals}. "
        f"Vocab they use: {vocab}. "
        f"Prefer {channels} for receipts."
    )
