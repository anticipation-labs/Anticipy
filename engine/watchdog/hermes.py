"""Hermes lifecycle worker — watches anticipy_results_v2 for new
verifier verdicts and updates skill_library counters. Triggers
demote / retire transitions per correction #7:

  active < 70% over 10 runs   -> demote to shadow + queue recompile
  shadow < 50% over 5 runs    -> retire + route to general executor

Designed to run as a Supabase Realtime subscriber (long-lived
process), but also exposes a `sync_once()` for the watchdog to
invoke each tick — pulls recent results since last cursor and
applies updates in a batch.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_logger = logging.getLogger("anticipy.watchdog.hermes")

CURSOR_FILE = Path.home() / ".anticipy" / "hermes_cursor.iso"
DEMOTE_THRESHOLD = 0.70
DEMOTE_WINDOW = 10
RETIRE_THRESHOLD = 0.50
RETIRE_WINDOW = 5
# Per the master prompt: shadow -> active after 20 real usage runs at 85%+
PROMOTE_THRESHOLD = 0.85
PROMOTE_WINDOW = 20


@dataclass
class HermesAction:
    skill_id: str
    action: str  # "promote_active" | "demote_shadow" | "retire" | "no_change"
    rate: float
    sample: int
    detail: str = ""


def _read_cursor() -> str:
    if not CURSOR_FILE.exists():
        # default: 24h ago
        from datetime import timedelta
        return (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    return CURSOR_FILE.read_text().strip()


def _write_cursor(iso: str) -> None:
    CURSOR_FILE.parent.mkdir(parents=True, exist_ok=True)
    CURSOR_FILE.write_text(iso)


def _ensure_supabase():
    try:
        from supabase import create_client  # type: ignore
    except ImportError:
        return None
    url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        return None
    return create_client(url, key)


def sync_once() -> dict:
    """Pull recent results from anticipy_results_v2, group by skill_id
    (joined through tasks_v2), update skill_library counters, apply
    Hermes transitions. Returns a summary dict.
    """
    sb = _ensure_supabase()
    if sb is None:
        return {"ok": False, "reason": "no_supabase"}

    cursor = _read_cursor()
    actions: list[HermesAction] = []
    new_results: list[dict] = []
    try:
        # Pull results since cursor, joined to tasks_v2 for skill_id
        # We do this in two steps because Supabase Python client is
        # awkward with FK joins; first results, then look up skill_ids.
        rresp = (
            sb.table("anticipy_results_v2")
            .select("task_id,verifier_output,created_at")
            .gt("created_at", cursor)
            .order("created_at", desc=False)
            .limit(500)
            .execute()
        )
        new_results = getattr(rresp, "data", None) or []
        if not new_results:
            return {"ok": True, "updated": 0, "actions": []}

        # Map task_id -> skill_id
        task_ids = list({r["task_id"] for r in new_results})
        tresp = (
            sb.table("anticipy_tasks_v2")
            .select("task_id,skill_id")
            .in_("task_id", task_ids)
            .execute()
        )
        trows = getattr(tresp, "data", None) or []
        task_to_skill = {t["task_id"]: t.get("skill_id") for t in trows}

        # Aggregate per skill: hits, misses, last_at
        per_skill: dict[str, dict] = {}
        max_iso = cursor
        for r in new_results:
            sid = task_to_skill.get(r["task_id"])
            if not sid:
                continue
            agg = per_skill.setdefault(sid, {"hits": 0, "misses": 0, "last_at": cursor})
            if r["verifier_output"] == "CERTIFIED":
                agg["hits"] += 1
            else:
                agg["misses"] += 1
            if r["created_at"] > agg["last_at"]:
                agg["last_at"] = r["created_at"]
            if r["created_at"] > max_iso:
                max_iso = r["created_at"]

        # Apply per-skill counter bumps + Hermes transitions
        for sid, agg in per_skill.items():
            sresp = (
                sb.table("skill_library")
                .select("skill_id,status,success_count,failure_count")
                .eq("skill_id", sid)
                .limit(1)
                .execute()
            )
            rows = getattr(sresp, "data", None) or []
            srow = rows[0] if rows else None
            if not srow:
                # Skill not in library yet — auto-register as shadow on
                # first run. Bytea fields need base64 strings for the
                # supabase-py JSON wire format; empty string encodes to
                # empty bytea after the server decodes it.
                import base64
                empty_bytea_b64 = base64.b64encode(b"").decode("ascii")
                try:
                    sb.table("skill_library").insert({
                        "skill_id": sid,
                        "intent_match_pattern": sid,
                        "code": empty_bytea_b64,
                        "selector_chain": {},
                        "verifier_code": empty_bytea_b64,
                        "postcondition_spec": "",
                        "status": "shadow",
                        "success_count": agg["hits"],
                        "failure_count": agg["misses"],
                        "last_run_at": agg["last_at"],
                    }).execute()
                except Exception as e:
                    _logger.warning("auto-register skill %s failed: %s", sid, e)
                actions.append(HermesAction(sid, "auto_registered_shadow", 0.0, agg["hits"] + agg["misses"], ""))
                continue

            new_succ = (srow["success_count"] or 0) + agg["hits"]
            new_fail = (srow["failure_count"] or 0) + agg["misses"]
            total = new_succ + new_fail
            rate = new_succ / total if total else 0.0
            new_status = srow["status"]
            if srow["status"] == "active" and total >= DEMOTE_WINDOW and rate < DEMOTE_THRESHOLD:
                new_status = "shadow"
                actions.append(HermesAction(sid, "demote_shadow", rate, total, "below_70_over_10"))
            elif srow["status"] == "shadow" and total >= RETIRE_WINDOW and rate < RETIRE_THRESHOLD:
                new_status = "retired"
                actions.append(HermesAction(sid, "retire", rate, total, "below_50_over_5"))
            elif srow["status"] == "shadow" and total >= PROMOTE_WINDOW and rate >= PROMOTE_THRESHOLD:
                new_status = "active"
                actions.append(HermesAction(sid, "promote_active", rate, total, "above_85_over_20"))

            sb.table("skill_library").update({
                "success_count": new_succ,
                "failure_count": new_fail,
                "last_run_at": agg["last_at"],
                "status": new_status,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }).eq("skill_id", sid).execute()

        _write_cursor(max_iso)
    except Exception as e:
        _logger.error("hermes sync failed: %s", e)
        return {"ok": False, "reason": str(e), "scanned": len(new_results)}

    return {
        "ok": True,
        "updated": len(per_skill),
        "actions": [a.__dict__ for a in actions],
        "scanned": len(new_results),
        "cursor": max_iso,
    }


if __name__ == "__main__":
    from dotenv import load_dotenv
    repo_root = Path(__file__).resolve().parent.parent.parent
    load_dotenv(repo_root / ".env.local")
    import json
    out = sync_once()
    print(json.dumps(out, indent=2))
