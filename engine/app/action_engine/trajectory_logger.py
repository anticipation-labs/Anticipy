"""Phase V4-8: real-time trajectory logging to Supabase.

Every task run and every loop iteration is written to Supabase as it
happens (not batched at the end) so partial/failed runs still produce
useful distillation data. Step screenshots are uploaded to the public
`action-engine-shots` storage bucket and their URLs stored on the step
row.

Hard rule: logging must NEVER slow or break the agent. Every network
call is best-effort with a short timeout and swallows all errors
(same degrade-gracefully contract as app/supabase_client.py). If
Supabase creds are absent the logger is a silent no-op.

Tables (migration 20260516_action_engine_trajectories.sql):
  action_engine_tasks  - one row per task
  action_engine_steps  - one row per iteration
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv

load_dotenv(os.path.expanduser("~/.anticipy/.env"))

_log = logging.getLogger("anticipy.action_engine.traj_logger")

SUPABASE_URL = (os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
                or os.environ.get("SUPABASE_URL") or "").rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
BUCKET = "action-engine-shots"


def _enabled() -> bool:
    return bool(SUPABASE_URL and SERVICE_KEY)


def _headers(extra: Optional[dict] = None) -> dict:
    h = {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
    }
    if extra:
        h.update(extra)
    return h


class TrajectoryLogger:
    """Best-effort real-time logger. All methods swallow errors."""

    def __init__(self, task_id: str):
        self.task_id = task_id
        self.ok = _enabled()

    # ── task lifecycle ────────────────────────────────────────────
    def start_task(self, goal: str, model: str = "",
                    force_model: Optional[str] = None,
                    tier: Optional[int] = None,
                    task_name: Optional[str] = None) -> None:
        if not self.ok:
            return
        try:
            httpx.post(
                f"{SUPABASE_URL}/rest/v1/action_engine_tasks",
                headers=_headers({"Prefer": "resolution=merge-duplicates"}),
                json={
                    "task_id": self.task_id, "goal": goal[:4000],
                    "status": "running", "model": model,
                    "force_model": force_model, "tier": tier,
                    "task_name": task_name,
                },
                timeout=8.0,
            )
        except Exception as e:
            _log.debug("start_task best-effort failed: %s", e)

    def finish_task(self, status: str, answer: str = "", evidence: str = "",
                    n_iterations: int = 0, error: Optional[str] = None) -> None:
        if not self.ok:
            return
        try:
            httpx.patch(
                f"{SUPABASE_URL}/rest/v1/action_engine_tasks"
                f"?task_id=eq.{self.task_id}",
                headers=_headers(),
                json={
                    "status": status, "answer": (answer or "")[:4000],
                    "evidence": (evidence or "")[:4000],
                    "n_iterations": n_iterations,
                    "error": (error or None),
                    "updated_at": "now()",
                },
                timeout=8.0,
            )
        except Exception as e:
            _log.debug("finish_task best-effort failed: %s", e)

    # ── screenshots ───────────────────────────────────────────────
    def _upload_shot(self, local_path: Path, key: str) -> Optional[str]:
        if not self.ok or not local_path or not local_path.exists():
            return None
        try:
            data = local_path.read_bytes()
            r = httpx.post(
                f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{key}",
                headers={
                    "apikey": SERVICE_KEY,
                    "Authorization": f"Bearer {SERVICE_KEY}",
                    "Content-Type": "image/png",
                    "x-upsert": "true",
                },
                content=data,
                timeout=12.0,
            )
            if r.status_code in (200, 201):
                return f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET}/{key}"
        except Exception as e:
            _log.debug("shot upload best-effort failed: %s", e)
        return None

    # ── per-iteration ─────────────────────────────────────────────
    def log_step(self, subtask_index: int, iteration: int,
                 action: Optional[dict], ax_tree: str,
                 before_png: Optional[Path], after_png: Optional[Path],
                 verifier_verdict: str = "", verifier_evidence: str = "",
                 verifier_confidence: Optional[float] = None,
                 latency_decide_s: Optional[float] = None,
                 latency_verify_s: Optional[float] = None) -> None:
        if not self.ok:
            return
        try:
            tag = f"{self.task_id}/s{subtask_index}_i{iteration:02d}"
            before_url = self._upload_shot(before_png, f"{tag}_b.png") if before_png else None
            after_url = self._upload_shot(after_png, f"{tag}_a.png") if after_png else None
            a = action or {}
            httpx.post(
                f"{SUPABASE_URL}/rest/v1/action_engine_steps",
                headers=_headers(),
                json={
                    "task_id": self.task_id,
                    "subtask_index": subtask_index,
                    "iteration": iteration,
                    "action_kind": a.get("action"),
                    "action_ref": a.get("target_ref"),
                    "action_url": a.get("url"),
                    "action_text": (a.get("text") or "")[:2000] or None,
                    "ax_tree": (ax_tree or "")[:8000],
                    "screenshot_before_url": before_url,
                    "screenshot_after_url": after_url,
                    "verifier_verdict": verifier_verdict or None,
                    "verifier_evidence": (verifier_evidence or "")[:1000] or None,
                    "verifier_confidence": verifier_confidence,
                    "latency_decide_s": latency_decide_s,
                    "latency_verify_s": latency_verify_s,
                },
                timeout=8.0,
            )
        except Exception as e:
            _log.debug("log_step best-effort failed: %s", e)


def make_logger(task_id: str) -> TrajectoryLogger:
    return TrajectoryLogger(task_id)
