"""The API hand — real app actions through Arcade, per user, on the frozen contract.

Dumb executor: it receives a fully-resolved, already-gated job and does it. It
does NOT decide who someone is, whether to act, or whether to escalate. Read and
write intents (onboarding reuses the reads). MOCK by default (no real calls);
LIVE only when explicitly set. Defense in depth: refuses a high-risk write that
doesn't carry the gate's approval flag. Idempotent on retries (no double-sends).

Reconciliation note: the frozen Result enum is {success, failed, needs_human}
and the contract/orchestrator are not to be touched. "needs_other_worker" is
therefore expressed as status=failed + output.needs_other_worker=True; ControlCore
configures the orchestrator's `alternates` so such intents reroute to the browser
hand via the EXISTING reroute path — no orchestrator change.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from typing import Optional

from ..core.envelopes import Job, JobStatus, Result, Risk
from ..core.worker import Worker

MODE_MOCK = "mock"
MODE_LIVE = "live"

WRITE_INTENTS = {"send_email", "create_event", "message"}

# One place to extend. Tool names follow Arcade's catalog (Gmail.SendEmail is
# confirmed live; others are best-known and validated when wired live).
INTENT_MAP = {
    # writes
    "send_email": "Gmail.SendEmail",
    "create_event": "GoogleCalendar.CreateEvent",
    "message": "Slack.SendMessageToChannel",
    # reads (onboarding reuses these)
    "read_email": "Gmail.ListEmails",
    "read_calendar": "GoogleCalendar.ListEvents",
    "read_contacts": "Gmail.ListThreads",
    "read_doc": "GoogleDocs.GetDocumentById",
    # recognized app action with NO Arcade tool -> routes to the browser hand
    "post_to_x": None,
}


class NotFundedError(RuntimeError):
    """Loud failure for a missing/empty/rejected/unfunded key. Never silent."""


def _app_name(tool: str) -> str:
    return tool.split(".")[0]  # "Gmail.SendEmail" -> "Gmail" (never the word "API")


class ApiHand(Worker):
    def __init__(self, *, user_id: str, client=None, mode: str = MODE_MOCK,
                 idem: Optional[dict] = None, approval_required: bool = True) -> None:
        self.user_id = user_id
        self._client = client
        self.mode = mode
        self.idem = idem if idem is not None else {}
        self.approval_required = approval_required

    def handles(self):
        return list(INTENT_MAP.keys())

    # ---- client ----
    def _client_or_build(self):
        if self._client is not None:
            return self._client
        key = os.environ.get("ARCADE_API_KEY")
        if not key:
            raise NotFundedError("ARCADE_API_KEY NOT SET / NOT FUNDED")
        from arcadepy import Arcade
        self._client = Arcade(api_key=key)
        return self._client

    def _idem_key(self, job: Job) -> str:
        raw = f"{job.goal_id}|{job.intent}|{json.dumps(job.args, sort_keys=True, default=str)}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    @staticmethod
    def _tool_input(job: Job) -> dict:
        return {k: v for k, v in job.args.items() if k != "approved"}

    async def handle(self, job: Job) -> Result:
        tool = INTENT_MAP.get(job.intent)
        if tool is None:
            # no API tool -> route to the browser hand (via orchestrator alternates)
            return Result(job_id=job.id, status=JobStatus.failed, proof=None,
                          error=f"needs_other_worker: no tool for '{job.intent}'",
                          output={"needs_other_worker": True})

        is_write = job.intent in WRITE_INTENTS
        high_risk = job.risk in (Risk.needs_confirm, Risk.ask_human)

        # defense in depth: refuse a HIGH-RISK write that doesn't carry the gate's
        # approval flag (low-risk writes proceed; the gate ran upstream).
        if is_write and high_risk and self.approval_required and not job.args.get("approved"):
            return Result(job_id=job.id, status=JobStatus.needs_human, proof=None,
                          output={"reason": "high-risk action missing approval flag"})

        # idempotency: a retried write that already produced proof must NOT re-send
        ikey = self._idem_key(job)
        if is_write and ikey in self.idem:
            return Result(job_id=job.id, status=JobStatus.success,
                          proof=self.idem[ikey], output={"idempotent": True})

        if self.mode == MODE_MOCK:
            proof = {"id": f"mock-{ikey if is_write else job.id[:8]}", "mock": True, "tool": tool}
            if is_write:
                self.idem[ikey] = proof
            return Result(job_id=job.id, status=JobStatus.success, proof=proof, output={"mock": True})

        # ---- LIVE ----
        client = self._client_or_build()
        try:
            auth = client.tools.authorize(tool_name=tool, user_id=self.user_id)
        except Exception as exc:
            return await self._on_error(job, exc)
        if getattr(auth, "status", None) != "completed":
            # never the word "API": "connect Gmail"
            return Result(job_id=job.id, status=JobStatus.needs_human, proof=None,
                          output={"connect": _app_name(tool), "connect_url": getattr(auth, "url", None)})

        try:
            resp = client.tools.execute(tool_name=tool, input=self._tool_input(job), user_id=self.user_id)
        except Exception as exc:
            return await self._on_error(job, exc)

        out = getattr(resp, "output", None)
        value = getattr(out, "value", None) if out is not None else None
        err = getattr(out, "error", None) if out is not None else None
        if err or not value:
            return Result(job_id=job.id, status=JobStatus.failed, proof=None,
                          error=f"execute error: {err or 'empty output'}")

        proof = self._proof_from(value, tool)
        if not proof.get("id"):
            return Result(job_id=job.id, status=JobStatus.failed, proof=None,
                          error="no id in tool output (invalid proof)")
        if is_write:
            self.idem[ikey] = proof
        return Result(job_id=job.id, status=JobStatus.success, proof=proof,
                      output={"value": value if isinstance(value, dict) else str(value)})

    @staticmethod
    def _proof_from(value, tool: str) -> dict:
        if isinstance(value, dict):
            mid = (value.get("id") or value.get("message_id") or value.get("messageId")
                   or value.get("eventId") or value.get("event_id") or value.get("ts"))
            return {"id": mid, "tool": tool, "value": value}
        return {"id": str(value) if value else None, "tool": tool}

    async def _on_error(self, job: Job, exc: Exception) -> Result:
        code = getattr(exc, "status_code", None)
        name = type(exc).__name__
        if code == 401 or "Authentication" in name:
            raise NotFundedError(f"ARCADE_API_KEY REJECTED (401) — NOT FUNDED / invalid: {exc}")
        if code == 403 or "PermissionDenied" in name:
            url = None
            try:
                tool = INTENT_MAP.get(job.intent)
                auth = self._client.tools.authorize(tool_name=tool, user_id=self.user_id)
                url = getattr(auth, "url", None)
            except Exception:
                pass
            return Result(job_id=job.id, status=JobStatus.needs_human, proof=None,
                          output={"connect": _app_name(INTENT_MAP[job.intent]),
                                  "connect_url": url, "reason": "additional permission needed"})
        if code == 429 or "RateLimit" in name:
            await asyncio.sleep(0.2)  # gentle hand-side backoff; never hammer
            return Result(job_id=job.id, status=JobStatus.failed, proof=None,
                          error="rate limited, will retry")
        if (code or 0) >= 500 or "Connection" in name or "Timeout" in name:
            await asyncio.sleep(0.1)
            return Result(job_id=job.id, status=JobStatus.failed, proof=None,
                          error=f"transient ({name}), will retry")
        return Result(job_id=job.id, status=JobStatus.failed, proof=None, error=f"{name}: {exc}")
