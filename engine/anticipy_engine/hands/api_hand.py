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
from typing import Optional

from ..agent.proof import confirm_stable_artifact
from ..core.envelopes import Job, JobStatus, Result, Risk
from ..core.worker import Worker

MODE_MOCK = "mock"
MODE_LIVE = "live"

WRITE_INTENTS = {"send_email", "send_email_draft", "create_event", "message"}

# How many independent reads the read-back must agree on. >=2 means the write
# echo alone can never satisfy it (Law 4/5: the receipt is the only currency).
READ_BACK_READS = max(2, int(os.environ.get("ANTICIPY_API_READBACK_READS", "2")))

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

# Independent READ-BACK tools, one per live WRITE intent. After a write succeeds, the
# hand issues a SECOND, independent client.tools.execute against this read tool and
# confirms the just-written artifact actually appears. The write call's own echo is
# NEVER trusted as proof (the actor must not grade its own homework).
#
# Verified Arcade tool names are wired live. Uncertain names are left as explicit
# UNVERIFIED TODO sentinels (None) so the live path FAILS CLOSED — it must never
# invent a tool name (a bad name 400s/404s live and could mask a real write as a
# phantom failure, or worse pass an unverified write). Confirm against Arcade's
# catalog in Slice 1 before flipping these on.
READ_BACK = {
    # create_event: ListEvents is confirmed present (also used by read_calendar). We
    # match the created event id against the listed events.
    "create_event": "GoogleCalendar.ListEvents",
    # send_email: a sent message is read back via ListEmails (confirmed present).
    "send_email": "Gmail.ListEmails",
    # send_email_draft: read back via Gmail.ListDraftEmails — CONFIRMED in the live Arcade
    # catalog (tools.list, toolkit=gmail) with NO required inputs. The created draft's id is
    # matched against the listed drafts (same _read_contains_id gate as calendar). Both the
    # draft WRITE (gmail.compose) and this read need the Gmail scope granted; until then the
    # whole path is connect-gated, so no draft can be written for this to mis-verify.
    "send_email_draft": "Gmail.ListDraftEmails",
    # message (Slack): no verified Slack read tool. TODO(slice-1): confirm name.
    "message": None,
}


class NotFundedError(RuntimeError):
    """Loud failure for a missing/empty/rejected/unfunded key. Never silent."""


def _app_name(tool: str) -> str:
    return tool.split(".")[0]  # "Gmail.SendEmail" -> "Gmail" (never the word "API")


def _default_arcade_client(api_key: str):
    """Build a real Arcade client from a key. Used for the per-user (vault) auth path;
    arcadepy does no network at construction, so this is safe to call lazily per call."""
    from arcadepy import Arcade
    return Arcade(api_key=api_key)


class ApiHand(Worker):
    def __init__(self, *, user_id: str, client=None, mode: str = MODE_MOCK,
                 idem: Optional[dict] = None, approval_required: bool = True,
                 broker=None, client_factory=None) -> None:
        self.user_id = user_id
        self._client = client
        self.mode = mode
        self.idem = idem if idem is not None else {}
        self.approval_required = approval_required
        # Concurrency guard (Law 4: no faked success; here, no DOUBLE real write).
        # The idempotency check (`ikey in self.idem`) only catches a SEQUENTIAL retry:
        # `self.idem[ikey]` is populated AFTER the write+read-back, so two CONCURRENT
        # presses of the same line both pass the check and both fire a real write
        # (duplicate calendar event / draft). `_inflight` records keys whose write is
        # underway so a second concurrent write reserves-or-waits on the FIRST, never
        # double-fires. `_idem_lock` makes reserve-or-wait atomic across coroutines.
        self._idem_lock = asyncio.Lock()
        self._inflight: dict = {}
        # Writes whose LIVE side-effect already FIRED (execute() returned an id) but whose
        # independent read-back has NOT yet confirmed. A retry or concurrent joiner must NEVER
        # re-execute one of these — the email is already sent / the event already created — it
        # re-verifies (read-back only) instead. Cleared once `idem` holds the confirmed proof.
        # (Closes the audit's duplicate-send-on-read-back-failure hole.)
        self._fired: dict = {}
        # Per-person API mesh: an optional TokenBroker (token_vault.py). When set AND
        # this user has connected the app a LIVE call touches, the hand authenticates
        # with THAT user's short-lived vault token instead of the shared ARCADE_API_KEY.
        # None (the default) keeps the legacy shared-key behavior unchanged (back-compat).
        self._broker = broker
        # builds an Arcade client from a per-user token. Default = the real arcadepy
        # client (no network at construction); injectable so tests prove the per-user
        # auth path with NO network and NO real OAuth.
        self._client_factory = client_factory or _default_arcade_client
        # records which path each (user, app) live call took — for the round-trip proof
        # and audit. Never stores a token, only the path name + whether the broker was hit.
        self.last_auth_path: Optional[dict] = None

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

    # The vault keys apps by a lowercase short name ("gmail", "googlecalendar", a niche
    # CRM); Arcade tool names are "Gmail.SendEmail" / "GoogleCalendar.ListEvents". The app
    # for a (user, tool) is the toolkit prefix, lowercased, so the broker lookup matches
    # what onboarding stored. General (not per-tool): never the literal word "api".
    @staticmethod
    def _vault_app(tool: str) -> str:
        return _app_name(tool).lower()

    def _live_client(self, tool: str):
        """Return the Arcade client to use for this LIVE call, and record which auth path
        was taken. When a per-user broker is configured AND this user has connected the
        app, build a client bound to THAT user's short-lived token (broker.get_token →
        SecretToken.reveal() ONLY here, at the real auth handshake — never logged/prompted).
        Fall back to the shared ARCADE_API_KEY only when no broker is wired or this user
        hasn't connected the app (back-compat)."""
        app = self._vault_app(tool)
        if self._broker is not None:
            revealed = None
            try:
                secret = self._broker.get_token(self.user_id, app)
                # The ONE place the plaintext is revealed: the per-user auth handshake.
                # reveal() can raise VaultError if the lease / at-rest token has EXPIRED —
                # kept inside the try so a stale token degrades to the shared key, never
                # crashes the call. The revealed value never leaves this scope.
                revealed = secret.reveal()
            except Exception:
                # This user has not connected this app (TokenNotFound), the lease could not
                # be issued, or the stored token expired — fall back to the shared key. We do
                # NOT swallow auth errors from the real handshake (authorize/execute, below);
                # only token ACQUISITION here.
                revealed = None
            if revealed is not None:
                client = self._client_factory(revealed)
                self.last_auth_path = {"path": "per_user", "app": app,
                                       "broker_consulted": True, "shared_key": False}
                return client
        # no broker, or this user hasn't connected the app -> shared-key path (legacy)
        self.last_auth_path = {"path": "shared_key", "app": app,
                               "broker_consulted": self._broker is not None,
                               "shared_key": True}
        return self._client_or_build()

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
    }

    @staticmethod
    def _listevents_window(args: dict | None, *, tight: bool) -> dict:
        """The time window GoogleCalendar.ListEvents@3.x REQUIRES (min_end_datetime /
        max_start_datetime). Without it the call 400s — which silently broke EVERY calendar
        read AND the create_event read-back (so real events were marked 'not done'). When a
        write carries the event's own start_datetime we center a TIGHT window on it so the
        read-back's result set is small and definitely contains the just-created event; the id
        match remains the hard gate. Otherwise a wide now-anchored span. RFC3339 / tz-aware."""
        import datetime
        now = datetime.datetime.now(datetime.timezone.utc)
        start = _parse_iso_dt(_calendar_value(args or {}, "start_datetime"))
        if tight and start is not None:
            lo, hi = start - datetime.timedelta(days=1), start + datetime.timedelta(days=1)
        else:
            lo, hi = now - datetime.timedelta(days=1), now + datetime.timedelta(days=730)
        return {"min_end_datetime": lo.replace(microsecond=0).isoformat(),
                "max_start_datetime": hi.replace(microsecond=0).isoformat()}

    @classmethod
    def _tool_input(cls, job: Job) -> dict:
        tool = INTENT_MAP.get(job.intent) or ""
        out = {k: v for k, v in job.args.items() if k != "approved"}
        for src, dst in cls._ALIASES.get(tool, {}).items():
            if src in out and dst not in out:
                out[dst] = out.pop(src)
        # ListEvents@3.x requires a time window — fill it only if the caller didn't.
        if tool == "GoogleCalendar.ListEvents":
            for k, v in cls._listevents_window(out, tight=False).items():
                out.setdefault(k, v)
        return out

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

        blocked = self._block_ungrounded_calendar_write(job)
        if blocked is not None:
            return blocked

        # idempotency: a retried write that already produced proof must NOT re-send
        ikey = self._idem_key(job)
        if is_write and ikey in self.idem:
            return Result(job_id=job.id, status=JobStatus.success,
                          proof=self.idem[ikey], output={"idempotent": True})
        # a write whose side-effect already FIRED but wasn't confirmed: re-verify only, NEVER
        # re-execute (the artifact already exists — re-running would duplicate the real send).
        if is_write and ikey in self._fired:
            return await self._reverify_fired(job, tool, ikey)

        # CONCURRENCY: a write goes through the reserve-or-join guard so two presses of
        # the SAME line (same ikey) never both fire a real write. Reads never mutate, so
        # they skip the guard entirely (no contention, no behavior change).
        if is_write:
            return await self._run_write_guarded(job, tool, ikey)
        return await self._execute(job, tool, ikey, is_write=False)

    async def _run_write_guarded(self, job: Job, tool: str, ikey: str) -> Result:
        """Reserve-or-join the in-flight write for ``ikey`` so a concurrent second press
        of the same remembered line returns the FIRST write's receipt (idempotent) instead
        of firing a duplicate real write. The reserve (marker insert) happens under the
        lock BEFORE the write's first await, closing the read-check-act window that the
        bare ``ikey in self.idem`` check leaves open (idem is only populated AFTER the
        write+read-back). A joiner that finds the winner FAILED with NOTHING fired (idem unset
        AND _fired unset) is free to run its own write — a clean failure left no artifact. But
        a joiner that finds the winner FIRED-but-unconfirmed (_fired set) must re-verify, NEVER
        re-write, or it would duplicate the real send."""
        while True:
            winner = False
            async with self._idem_lock:
                # The winner may have finished between the fast-path check and the lock.
                if ikey in self.idem:
                    return Result(job_id=job.id, status=JobStatus.success,
                                  proof=self.idem[ikey], output={"idempotent": True})
                if ikey in self._fired:
                    break  # winner fired the side-effect but didn't confirm -> re-verify, no re-write
                task = self._inflight.get(ikey)
                if task is None:
                    # We are the winner: reserve the key (the in-flight task also clears
                    # the marker in its own finally, so a joiner never sees a stale entry
                    # for a finished task) and run the real write OUTSIDE this lock.
                    task = asyncio.ensure_future(self._write_and_release(job, tool, ikey))
                    self._inflight[ikey] = task
                    winner = True
            if winner:
                return await task
            # JOINER: wait for the in-flight write to finish, then loop. Next pass returns
            # idempotent (winner confirmed -> idem), re-verifies (winner fired-but-unconfirmed
            # -> _fired), or reserves its own write (clean failure -> nothing fired).
            try:
                await asyncio.shield(task)
            except Exception:
                pass
        return await self._reverify_fired(job, tool, ikey)

    async def _write_and_release(self, job: Job, tool: str, ikey: str) -> Result:
        """Run one real write and ALWAYS clear the in-flight marker when it finishes, so a
        joiner awaiting this task never observes a stale reservation for a completed write."""
        try:
            return await self._execute(job, tool, ikey, is_write=True)
        finally:
            async with self._idem_lock:
                self._inflight.pop(ikey, None)

    async def _reverify_fired(self, job: Job, tool: str, ikey: str) -> Result:
        """A write whose side-effect already FIRED but was never confirmed: re-verify via an
        independent read-back ONLY — never re-execute (the email is already sent / the event
        already exists). If the read-back now confirms, succeed; otherwise hand to the human
        and NEVER resend."""
        rec = self._fired.get(ikey) or {}
        written_id = rec.get("written_id")
        if not written_id:
            return Result(job_id=job.id, status=JobStatus.needs_human, proof=None,
                          output={"reason": "a prior attempt already fired this action but it could "
                                            "not be verified; not resending — please check manually",
                                  "already_fired": True})
        if self.mode == MODE_MOCK:
            return Result(job_id=job.id, status=JobStatus.success,
                          proof=self.idem.get(ikey) or {"id": written_id, "readback": True},
                          output={"idempotent": True})
        client = self._live_client(tool)
        result = await self._readback_or_fail(job, client, tool, written_id, rec.get("value"), ikey)
        if result.status == JobStatus.success:
            self._fired.pop(ikey, None)
            return result
        # read-back still cannot confirm — but the side-effect HAPPENED. Hand to the human;
        # do NOT resend.
        return Result(job_id=job.id, status=JobStatus.needs_human, proof=None,
                      output={"reason": f"already sent (id={written_id}) but could not auto-verify; "
                                        "NOT resending — please confirm manually",
                              "already_fired": True, "written_id": written_id})

    async def _execute(self, job: Job, tool: str, ikey: str, *, is_write: bool) -> Result:
        if self.mode == MODE_MOCK:
            mock_id = f"mock-{ikey if is_write else job.id[:8]}"
            proof = {"id": mock_id, "mock": True, "tool": tool}
            if is_write:
                # Exercise the SAME read-back discipline in mock: a simulated independent
                # read that re-observes the just-written id, so the live path is the only
                # one shipping echo-only proof — and that path now fails closed.
                confirmed = await self._mock_readback(mock_id)
                if not confirmed:
                    return Result(job_id=job.id, status=JobStatus.failed, proof=None,
                                  error="mock read-back did not re-observe the artifact")
                proof["readback"] = True
                proof["self_attested"] = False
                self.idem[ikey] = proof
            return Result(job_id=job.id, status=JobStatus.success, proof=proof, output={"mock": True})

        # ---- LIVE ----
        # Per-person mesh: pick THIS user's vault-backed client when a broker is wired and
        # the user has connected the app; otherwise the shared-key client (back-compat).
        client = self._live_client(tool)
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

        # READS / non-write actions: the execute() response IS the artifact (a LIST of events/
        # emails, a fetched doc) — there is nothing to read back. A list read has no single
        # top-level id, so requiring one here wrongly failed EVERY calendar/email READ as
        # 'invalid proof'. The value is the proof; an id is only needed for a WRITE's read-back.
        if not is_write:
            return Result(job_id=job.id, status=JobStatus.success, proof=(proof or {"read": tool}),
                          output={"value": value if isinstance(value, dict) else str(value)})

        written_id = proof.get("id")
        if not written_id:
            return Result(job_id=job.id, status=JobStatus.failed, proof=None,
                          error="no id in tool output (invalid proof)")

        # WRITES: the execute() response is the actor grading its own homework. It is NOT
        # trusted as proof on its own. Issue a SECOND, independent read of the artifact and
        # only report success if the written id is re-observed there. Fail closed otherwise.
        #
        # The write's side-effect HAS happened now (the email is sent / the event created), so
        # record it BEFORE the read-back. If the read-back below fails, a retry/joiner will see
        # this marker and re-verify instead of re-executing — never a duplicate real send.
        self._fired[ikey] = {"written_id": written_id, "tool": tool, "value": value}
        result = await self._readback_or_fail(job, client, tool, written_id, value, ikey)
        if result.status == JobStatus.success:
            self._fired.pop(ikey, None)  # confirmed -> idem now holds the proof
        return result

    # The read the mock read-back "observes". A real artifact store would return the row
    # just written; here it echoes the written id back through the SAME confirm path. A
    # fail-closed test overrides this to return an empty store (artifact not found).
    async def _mock_read_once(self, written_id):
        return {"items": [{"id": written_id}]}, f"mock-read-req-{written_id}"

    async def _mock_readback(self, written_id) -> bool:
        artifact = await confirm_stable_artifact(
            lambda: self._mock_read_once(written_id),
            lambda observed: self._read_contains_id(observed, written_id),
            reads=READ_BACK_READS,
        )
        return artifact.confirmed

    async def _readback_or_fail(self, job, client, tool, written_id, write_value, ikey) -> Result:
        """Confirm a live write by an independent read-back. The write echo is never proof."""
        read_tool = READ_BACK.get(job.intent)
        if not read_tool:
            # Uncertain/unverified read tool -> we structurally CANNOT confirm the artifact.
            # Fail closed (surface to the human) rather than trust the write echo. Never
            # invent an Arcade tool name. (TODO(slice-1): wire the verified read tool.)
            return Result(job_id=job.id, status=JobStatus.needs_human, proof=None,
                          output={"reason": (f"wrote via {tool} but cannot independently "
                                             f"verify it: no read-back tool wired for "
                                             f"'{job.intent}' yet"),
                                  "unverified_write": True})

        read_input = self._readback_input(job, written_id)
        last_read_value: dict = {}

        async def read_once():
            # The SECOND, independent execute(): a fresh read of the live artifact store.
            nonlocal last_read_value
            resp = await asyncio.to_thread(
                client.tools.execute, tool_name=read_tool,
                input=read_input, user_id=self.user_id)
            out = getattr(resp, "output", None)
            value = getattr(out, "value", None) if out is not None else None
            err = getattr(out, "error", None) if out is not None else None
            if err or value is None:
                raise RuntimeError(f"read-back execute error: {err or 'empty output'}")
            last_read_value = value if isinstance(value, dict) else {"value": value}
            req_id = getattr(resp, "id", None) or getattr(out, "id", None)
            return last_read_value, req_id

        try:
            artifact = await confirm_stable_artifact(
                read_once,
                lambda observed: self._read_contains_id(observed, written_id),
                reads=READ_BACK_READS,
            )
        except Exception as exc:  # noqa: BLE001 — read-back failure is a hard fail-closed
            return Result(job_id=job.id, status=JobStatus.failed, proof=None,
                          error=f"read-back failed ({type(exc).__name__}): {exc}")

        if not artifact.confirmed:
            # Wrote, but an independent read did NOT re-observe the artifact. NOT done.
            return Result(job_id=job.id, status=JobStatus.failed, proof=None,
                          error=(f"write echoed id={written_id} but read-back via "
                                 f"{read_tool} did not re-observe it (not done)"))

        proof = {
            "id": written_id,
            "tool": tool,
            "self_attested": False,
            "readback": True,
            "verified_by_read": read_tool,
            "read_request_id": artifact.shot,   # distinct read request id, recorded for audit
            "read_back": artifact.observation,  # evidence from the independent read
        }
        self.idem[ikey] = proof
        return Result(job_id=job.id, status=JobStatus.success, proof=proof,
                      output={"value": write_value if isinstance(write_value, dict) else str(write_value),
                              "verified_by_read": read_tool})

    @classmethod
    def _readback_input(cls, job: Job, written_id) -> dict:
        """Input for the read-back call. ListEvents@3.x REQUIRES min_end_datetime/max_start_datetime,
        so for create_event we always supply a window TIGHT around the just-created event (the id
        match is still the hard gate). Was returning start/end only -> the read 400'd and every
        calendar write was wrongly marked 'not done'."""
        if job.intent == "create_event":
            return cls._listevents_window(job.args, tight=True)
        return {}

    @classmethod
    def _read_contains_id(cls, observed, written_id) -> bool:
        """True only if the independently-read artifact carries the just-written id."""
        if not written_id:
            return False
        target = str(written_id)
        # direct id on the read result (GetEvent/GetDraft-shaped single artifact)
        if cls._find_id(observed) and str(cls._find_id(observed)) == target:
            return True
        # list-shaped reads (ListEvents/ListEmails): scan items for the id
        for items in cls._iter_candidate_lists(observed):
            for item in items:
                if isinstance(item, dict) and cls._find_id(item) and str(cls._find_id(item)) == target:
                    return True
        return False

    @staticmethod
    def _iter_candidate_lists(observed):
        if not isinstance(observed, dict):
            return
        for v in observed.values():
            if isinstance(v, list):
                yield v

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
                # Re-auth on the SAME client this user's call used (per-user vault client
                # when a broker is wired and they connected the app; shared client else).
                auth = self._live_client(tool).tools.authorize(tool_name=tool, user_id=self.user_id)
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

    def _block_ungrounded_calendar_write(self, job: Job) -> Optional[Result]:
        if self.mode != MODE_LIVE or job.intent != "create_event":
            return None
        if _has_concrete_calendar_window(job.args):
            return None
        return Result(
            job_id=job.id,
            status=JobStatus.needs_human,
            proof=None,
            output={
                "reason": (
                    "calendar write blocked until the event has concrete "
                    "start_datetime and end_datetime values"
                ),
                "blocked": True,
            },
        )


_ISO_DATE_TIME = re.compile(r"\b\d{4}-\d{2}-\d{2}[T ][0-2]?\d:[0-5]\d")


def _looks_concrete_datetime(value) -> bool:
    if isinstance(value, dict):
        return any(_looks_concrete_datetime(value.get(k)) for k in ("dateTime", "date_time", "datetime"))
    if not isinstance(value, str):
        return False
    return bool(_ISO_DATE_TIME.search(value.strip()))


def _calendar_value(args: dict, key: str):
    if key in args:
        return args.get(key)
    event = args.get("event")
    if isinstance(event, dict) and key in event:
        return event.get(key)
    return None


def _parse_iso_dt(value):
    """Parse an ISO-8601/RFC3339 datetime string to a tz-aware datetime (UTC if naive); None on
    anything unparseable. Used to anchor the ListEvents read-back window on a created event."""
    if not isinstance(value, str) or not value.strip():
        return None
    import datetime
    try:
        dt = datetime.datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.replace(tzinfo=datetime.timezone.utc) if dt.tzinfo is None else dt


def _has_concrete_calendar_window(args: dict) -> bool:
    if not isinstance(args, dict):
        return False
    return (
        _looks_concrete_datetime(_calendar_value(args, "start_datetime"))
        and _looks_concrete_datetime(_calendar_value(args, "end_datetime"))
    )
