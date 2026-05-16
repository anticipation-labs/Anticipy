"""Per user trajectory logger. The flywheel substrate, built from the
first phase that produces decisions, not deferred.

Every decision is logged in a portable exportable per user JSONL record:
the input, the source path, the features, the decision, the confidence,
the memory state at decision time, the profile state at decision time,
and later the real outcome. The product's real accuracy comes from
retraining on these logs over months. This build delivers the substrate,
not the trained up accuracy.

A log write must never block or fail a decision. If the primary write
fails, the record is appended to a fallback file and the failure is
flagged, because a silent logging gap poisons the future flywheel.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Optional

from app.anticipy import platform_adapter

_lock = threading.Lock()


def _primary_path(user_id: str) -> Path:
    return platform_adapter.user_data_dir(user_id) / "trajectory.jsonl"


def _fallback_path() -> Path:
    return platform_adapter.data_dir() / "trajectory_fallback.jsonl"


def _flag_path() -> Path:
    return platform_adapter.data_dir() / "trajectory_write_failures.flag"


def log_decision(
    user_id: str,
    input_text: str,
    source: str,
    features: dict,
    decision: str,
    confidence: float,
    memory_state: Optional[dict] = None,
    profile_state: Optional[dict] = None,
    extra: Optional[dict] = None,
) -> bool:
    """Append one decision record. Returns True on primary write, False
    if it fell back. Never raises.
    """
    record = {
        "ts": time.time(),
        "user_id": user_id,
        "input_text": input_text,
        "source": source,
        "features": features,
        "decision": decision,
        "confidence": confidence,
        "memory_state": memory_state or {},
        "profile_state": profile_state or {},
        "outcome": None,  # filled later when the real world result is known
    }
    if extra:
        record["extra"] = extra
    line = json.dumps(record, ensure_ascii=False)
    try:
        with _lock:
            with _primary_path(user_id).open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        return True
    except Exception as primary_err:
        try:
            with _lock:
                with _fallback_path().open("a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
                with _flag_path().open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps({"ts": time.time(), "user_id": user_id, "error": str(primary_err)}) + "\n")
        except Exception:
            pass
        return False


def record_outcome(user_id: str, match_key: str, outcome: dict) -> bool:
    """Attach a real world outcome to the most recent record whose
    input_text matches match_key. Outcome backfill is what turns the log
    into training data. Best effort, never raises.
    """
    try:
        path = _primary_path(user_id)
        if not path.exists():
            return False
        with _lock:
            lines = path.read_text(encoding="utf-8").splitlines()
            for i in range(len(lines) - 1, -1, -1):
                try:
                    rec = json.loads(lines[i])
                except Exception:
                    continue
                if rec.get("input_text") == match_key and rec.get("outcome") is None:
                    rec["outcome"] = outcome
                    lines[i] = json.dumps(rec, ensure_ascii=False)
                    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
                    return True
        return False
    except Exception:
        return False


def read_all(user_id: str) -> list[dict]:
    path = _primary_path(user_id)
    if not path.exists():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


def export_jsonl(user_id: str) -> str:
    """Portable export: the raw JSONL the future training pipeline
    consumes. Same format local and at scale.
    """
    path = _primary_path(user_id)
    return path.read_text(encoding="utf-8") if path.exists() else ""
