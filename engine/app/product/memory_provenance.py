"""V7 memory provenance enforcer (plan section 6 schema).

Enforces the eight required provenance fields on every `ScopedMemory`
write. Invalid writes are logged to
`~/.anticipy/v7/memory_validation_errors.jsonl` and never persisted.
"""

from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

REQUIRED_FIELDS = [
    "account_id", "device_id", "source", "timestamp",
    "confidence", "kind", "active", "provenance",
]
ALLOWED_SOURCES = [
    "onboarding", "asr-transcript", "upload-asr", "mic-asr",
    "user-correction", "action-success", "action-failure",
    "engine-inference", "cloud-sync",
]
_ISO_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}"
    r"(\.\d+)?(Z|[+-]\d{2}:?\d{2})?$"
)
_ERRORS_LOCK = threading.Lock()


def _errors_path() -> Path:
    raw = os.environ.get("ANTICIPY_V7_MEMORY_ERRORS_PATH", "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".anticipy" / "v7" / "memory_validation_errors.jsonl"


def _is_iso8601(value: Any) -> bool:
    if not isinstance(value, str) or not value or not _ISO_RE.match(value):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except Exception:
        return False


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def validate_item(item: dict) -> dict:
    """Type-check required fields. Returns {valid, missing, errors}."""
    missing: list[str] = []; errors: list[str] = []
    if not isinstance(item, dict):
        return {"valid": False, "missing": list(REQUIRED_FIELDS),
                "errors": ["item is not a dict"]}
    for f in REQUIRED_FIELDS:
        if f not in item or item[f] in (None, ""):
            if f == "active" and "active" in item:
                continue
            missing.append(f)
    for f in ("account_id", "device_id", "kind", "source", "provenance"):
        if f in item and not isinstance(item[f], str):
            errors.append(f"{f} must be str")
    if "confidence" in item:
        try:
            c = float(item["confidence"])
            if c < 0.0 or c > 1.0:
                errors.append("confidence must be between 0 and 1")
        except (TypeError, ValueError):
            errors.append("confidence must be a number")
    if "active" in item and not isinstance(item["active"], bool):
        errors.append("active must be bool")
    if item.get("timestamp") and not _is_iso8601(item["timestamp"]):
        errors.append("timestamp must be ISO-8601 string")
    if item.get("source") and item["source"] not in ALLOWED_SOURCES:
        errors.append(f"source must be one of {ALLOWED_SOURCES}; "
                      f"got {item['source']!r}")
    return {"valid": not missing and not errors,
            "missing": missing, "errors": errors}


def normalize_item(item: dict, defaults: Optional[dict] = None) -> dict:
    """Fill missing fields with defaults. Raises if scope IDs missing."""
    defaults = dict(defaults or {})
    out = dict(item or {})
    for sf in ("account_id", "device_id"):
        if not out.get(sf):
            sd = defaults.get(sf)
            if not sd:
                raise ValueError(f"{sf} is required and was not provided")
            out[sf] = sd
    if not out.get("timestamp"):
        out["timestamp"] = defaults.get("timestamp") or _now_iso()
    if "active" not in out or out["active"] in (None, ""):
        out["active"] = bool(defaults.get("active", True))
    if out.get("confidence") in (None, ""):
        out["confidence"] = float(defaults.get("confidence", 0.7))
    if not out.get("source"):
        out["source"] = defaults.get("source", "engine-inference")
    if not out.get("provenance"):
        out["provenance"] = defaults.get("provenance", "direct_write")
    if not out.get("kind"):
        out["kind"] = defaults.get("kind", "fact")
    return out


def _log_validation_error(item: dict, missing: list[str],
                          errors: list[str]) -> None:
    path = _errors_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        rec = {"timestamp": _now_iso(),
               "account_id": str(item.get("account_id") or ""),
               "device_id": str(item.get("device_id") or ""),
               "kind": str(item.get("kind") or ""),
               "missing": list(missing), "errors": list(errors),
               "item": {k: v for k, v in (item or {}).items()
                        if k != "value" or len(str(v)) < 500}}
        with _ERRORS_LOCK, path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False,
                                default=str) + "\n")
    except Exception:
        pass


class ProvenanceWrapper:
    """Intercept ScopedMemory writes; normalize then validate."""

    def __init__(self, scoped_memory: Any,
                 defaults: Optional[dict] = None) -> None:
        self.inner = scoped_memory
        self._defaults = dict(defaults or {})
        self._defaults.setdefault("account_id",
                                  getattr(scoped_memory, "account_id", ""))
        self._defaults.setdefault("device_id",
                                  getattr(scoped_memory, "device_id", ""))

    def write(self, **kwargs: Any) -> Optional[Any]:
        d = self._defaults
        item = {"account_id": kwargs.get("account_id") or d.get("account_id"),
                "device_id": kwargs.get("device_id") or d.get("device_id"),
                "kind": kwargs.get("kind"), "key": kwargs.get("key"),
                "value": kwargs.get("value"),
                "source": kwargs.get("source"),
                "provenance": kwargs.get("provenance"),
                "confidence": kwargs.get("confidence"),
                "active": kwargs.get("active", True),
                "timestamp": kwargs.get("timestamp")}
        try:
            item = normalize_item(item, d)
        except ValueError as exc:
            _log_validation_error(item, ["account_id/device_id"], [str(exc)])
            return None
        v = validate_item(item)
        if not v["valid"]:
            _log_validation_error(item, v["missing"], v["errors"])
            return None
        return self.inner.write(
            kind=item["kind"], key=str(kwargs.get("key") or ""),
            value=str(kwargs.get("value") or ""),
            source=item["source"], provenance=item["provenance"],
            confidence=float(item["confidence"]),
            extra=dict(kwargs.get("extra") or {}),
            dedupe=bool(kwargs.get("dedupe", True)))


class ActiveFlagEnforcer:
    """Filter read results to active items by default."""

    def __init__(self, scoped_memory: Any) -> None:
        self.inner = scoped_memory

    def read_active_only(self, **query: Any) -> list[dict]:
        query.pop("active_only", None)
        return self.inner.read(active_only=True, **query)

    def read_all_including_inactive(self, **query: Any) -> list[dict]:
        query.pop("active_only", None)
        return self.inner.read(active_only=False, **query)

    def _set_active(self, memory_id: str, active: bool) -> bool:
        path = getattr(self.inner, "path", None)
        if not path or not Path(path).exists():
            return False
        try:
            lines = Path(path).read_text(encoding="utf-8").splitlines()
        except Exception:
            return False
        changed = False; out: list[str] = []
        for ln in lines:
            ln = ln.strip()
            if not ln:
                continue
            try:
                rec = json.loads(ln)
            except Exception:
                out.append(ln); continue
            if str(rec.get("item_id") or "") == str(memory_id):
                rec["active"] = bool(active); changed = True
            out.append(json.dumps(rec, ensure_ascii=False))
        if not changed:
            return False
        tmp = Path(str(path) + ".tmp")
        tmp.write_text("\n".join(out) + "\n", encoding="utf-8")
        os.replace(tmp, path)
        return True

    def deactivate(self, memory_id: str) -> bool:
        return self._set_active(memory_id, False)

    def reactivate(self, memory_id: str) -> bool:
        return self._set_active(memory_id, True)


def read_validation_errors(account_id: Optional[str] = None,
                           limit: int = 200) -> list[dict]:
    """Return recent validation failures, most recent first."""
    path = _errors_path()
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    out: list[dict] = []
    for ln in reversed(lines):
        ln = ln.strip()
        if not ln:
            continue
        try:
            rec = json.loads(ln)
        except Exception:
            continue
        if account_id and str(rec.get("account_id") or "") != account_id:
            continue
        out.append(rec)
        if len(out) >= max(1, int(limit)):
            break
    return out


__all__ = ["REQUIRED_FIELDS", "ALLOWED_SOURCES", "validate_item",
           "normalize_item", "ProvenanceWrapper", "ActiveFlagEnforcer",
           "read_validation_errors"]
