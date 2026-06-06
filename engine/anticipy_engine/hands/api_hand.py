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
import re
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..core.envelopes import Job, JobStatus, Result, Risk
from ..core.worker import Worker

MODE_MOCK = "mock"
MODE_LIVE = "live"

WRITE_INTENTS = {"send_email", "send_email_draft", "create_event", "message"}
TEST_EVENT_PREFIX = "[Anticipy test]"

# One place to extend. Tool names follow Arcade's catalog (Gmail.SendEmail + GoogleCalendar.*
# are confirmed live; Gmail.WriteDraftEmail discovered via tools.list, schema verified, awaiting the
# gmail.compose scope grant; others are best-known and validated when wired live).
INTENT_MAP = {
    # writes
    "send_email": "Gmail.SendEmail",
    "send_email_draft": "Gmail.WriteDraftEmail",   # creates a draft; NEVER sends
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

    # Natural arg aliases -> the tool's REAL input contract. A real planner emits human-natural
    # names ("to" for an email's recipient); the executor owns its tool's schema and adapts. General
    # (not per-task) and evidence-anchored: Arcade's Gmail.SendEmail@7 requires "recipient", not "to"
    # (a mismatch silently 400s the send). Only the LIVE execute path calls this, so mock tests are
    # untouched. A canonical key the model already produced always wins over an alias.
    _ALIASES = {
        "Gmail.SendEmail": {"to": "recipient", "recipients": "recipient", "email": "recipient",
                            "to_email": "recipient", "address": "recipient"},
        "GoogleCalendar.CreateEvent": {"title": "summary", "start": "start_datetime",
                                       "start_time": "start_datetime", "end": "end_datetime",
                                       "end_time": "end_datetime"},
    }

    @classmethod
    def _tool_input(cls, job: Job) -> dict:
        out = {k: v for k, v in job.args.items() if k != "approved"}
        for src, dst in cls._ALIASES.get(INTENT_MAP.get(job.intent) or "", {}).items():
            if src in out and dst not in out:
                out[dst] = out.pop(src)
        if INTENT_MAP.get(job.intent) == "GoogleCalendar.CreateEvent":
            cls._normalize_calendar_input(out)
        return out

    @classmethod
    def _normalize_calendar_input(cls, out: dict) -> None:
        if "summary" in out:
            out["summary"] = str(out["summary"]).strip()
        when = str(out.get("when") or "").strip()
        if when and "start_datetime" not in out:
            parsed = _parse_natural_event_time(when)
            if parsed:
                out.update(parsed)
                out.pop("when", None)
        if "start_datetime" in out and "end_datetime" not in out:
            start = _parse_iso_datetime(str(out["start_datetime"]))
            if start is not None:
                out["end_datetime"] = (start + timedelta(minutes=30)).isoformat()

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

        safety = self._apply_build_test_safety(job)
        if safety is not None:
            return safety

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

    # id fields Arcade tools return, across toolkits. Some tools nest the result under a single
    # wrapper ({"event": {...}} for Calendar, {"draft": {...}} for Gmail drafts), so we look at the
    # top level AND one level into child dicts. General (not per-tool); never descends far enough to
    # grab an unrelated nested id (e.g. creator/organizer carry email, not these id keys).
    _ID_KEYS = ("id", "message_id", "messageId", "eventId", "event_id", "draft_id", "draftId",
                "thread_id", "threadId", "ts")

    @classmethod
    def _find_id(cls, value, _depth: int = 0):
        if not isinstance(value, dict):
            return None
        for k in cls._ID_KEYS:
            if value.get(k):
                return value[k]
        if _depth < 1:
            for v in value.values():
                got = cls._find_id(v, _depth + 1)
                if got:
                    return got
        return None

    @classmethod
    def _proof_from(cls, value, tool: str) -> dict:
        if isinstance(value, dict):
            return {"id": cls._find_id(value), "tool": tool, "value": value}
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

    def _build_test_safe_mode(self) -> bool:
        if self.mode != MODE_LIVE:
            return False
        explicit = os.environ.get("ANTICIPY_BUILD_TEST_SAFE_MODE")
        if explicit is not None:
            return explicit.strip().lower() not in {"0", "false", "no", "off"}
        if os.environ.get("ANTICIPY_ALLOW_EXTERNAL_REAL_ACTIONS", "").strip().lower() in {"1", "true", "yes", "on"}:
            return False
        return self._client is None

    def _self_owned_email(self) -> str:
        return (
            os.environ.get("ANTICIPY_TEST_EMAIL")
            or os.environ.get("ADMIN_EMAIL")
            or os.environ.get("ARCADE_USER_ID")
            or self.user_id
        ).strip().lower()

    def _apply_build_test_safety(self, job: Job) -> Optional[Result]:
        """Autopilot/build-test live writes must be reversible and self-owned."""
        if not self._build_test_safe_mode() or job.intent not in WRITE_INTENTS:
            return None

        if job.intent in {"send_email", "send_email_draft"}:
            args = self._tool_input(job)
            recipient = str(args.get("recipient") or "").strip().lower()
            if not recipient or recipient != self._self_owned_email():
                return Result(
                    job_id=job.id,
                    status=JobStatus.needs_human,
                    proof=None,
                    output={
                        "reason": "build/test safety blocked email to a non-self recipient",
                        "blocked": True,
                    },
                )
            job.args.update(args)
            return None

        if job.intent == "create_event":
            args = self._tool_input(job)
            if not args.get("summary") or not args.get("start_datetime") or not args.get("end_datetime"):
                return Result(
                    job_id=job.id,
                    status=JobStatus.needs_human,
                    proof=None,
                    output={
                        "reason": "build/test safety blocked calendar event without a concrete time",
                        "blocked": True,
                    },
                )
            title = str(args.get("summary") or "Anticipy event").strip()
            if not title.startswith(TEST_EVENT_PREFIX):
                args["summary"] = f"{TEST_EVENT_PREFIX} {title}"
            job.args.update(args)
            return None

        if job.intent == "message":
            return Result(
                job_id=job.id,
                status=JobStatus.needs_human,
                proof=None,
                output={
                    "reason": "build/test safety blocked messaging a real third party",
                    "blocked": True,
                },
            )

        return None


def _parse_iso_datetime(value: str):
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def _local_tz():
    name = os.environ.get("ANTICIPY_TIMEZONE") or os.environ.get("TZ")
    if name:
        try:
            return ZoneInfo(name)
        except ZoneInfoNotFoundError:
            pass
    return datetime.now().astimezone().tzinfo


def _parse_natural_event_time(text: str) -> Optional[dict]:
    now = datetime.now(_local_tz())
    day = now.date()
    lower = text.lower()

    if "tomorrow" in lower:
        day = (now + timedelta(days=1)).date()
    else:
        weekday = _weekday_target(lower, now)
        if weekday is not None:
            day = (now + timedelta(days=weekday)).date()

    hour, minute = _time_of_day(lower)
    if hour is None:
        return None

    start = datetime(day.year, day.month, day.day, hour, minute, tzinfo=now.tzinfo)
    if start <= now:
        start += timedelta(days=1)
    end = start + _duration(lower)
    return {"start_datetime": start.isoformat(), "end_datetime": end.isoformat()}


def _time_of_day(text: str) -> tuple[Optional[int], int]:
    m = re.search(r"\b(?:at\s*)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", text)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2) or 0)
        suffix = m.group(3)
        if suffix == "pm" and hour != 12:
            hour += 12
        if suffix == "am" and hour == 12:
            hour = 0
        return hour, minute

    m = re.search(r"\b(?:at\s*)?([01]?\d|2[0-3]):([0-5]\d)\b", text)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None, 0


def _duration(text: str) -> timedelta:
    m = re.search(r"\bfor\s+(\d{1,2})\s*(hour|hours|hr|hrs)\b", text)
    if m:
        return timedelta(hours=int(m.group(1)))
    m = re.search(r"\bfor\s+(\d{1,3})\s*(minute|minutes|min|mins)\b", text)
    if m:
        return timedelta(minutes=int(m.group(1)))
    return timedelta(minutes=30)


def _weekday_target(text: str, now: datetime) -> Optional[int]:
    weekdays = {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
        "sunday": 6,
    }
    for name, index in weekdays.items():
        if re.search(rf"\b(next|this)?\s*{name}\b", text):
            days = (index - now.weekday()) % 7
            if re.search(rf"\bnext\s+{name}\b", text) and days == 0:
                days = 7
            return days
    return None
