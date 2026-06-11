"""Reaching the user: channel_stub (all-fake) + ChannelWorker (the real one).

ChannelStub still services send_email (no real email channel yet) and remains the
scriptable fake the orchestrator/worker tests drive. ChannelWorker is the REAL
send_text/call worker on the frozen contract: it routes through the real
TextChannel/CallChannel (mock by default, live only with ANTICIPY_CHANNELS_MODE=live
+ Twilio env), succeeds only when the channel reports sent, and proves the send with
the channel's audit record (Twilio sid when live, a deterministic mock id otherwise).
"""
from __future__ import annotations

from typing import List, Optional

from ..envelopes import Job, JobStatus, Result
from ..worker import Worker
from .scriptable import ScriptableStub
from ...channels.call import CallChannel
from ...channels.text import TextChannel


class ChannelStub(ScriptableStub):
    name = "channel_stub"

    def handles(self) -> List[str]:
        return ["send_email", "send_text", "call"]

    def _proof(self, job: Job) -> dict:
        return {"message_id": f"stub-msg-{job.id[:8]}", "channel": job.intent}

    def _output(self, job: Job) -> dict:
        return {"delivered": "stubbed"}


class ChannelWorker(Worker):
    """send_text/call through the real channels. Registers AFTER ChannelStub so it
    owns those two intents; send_email stays with the stub."""

    name = "channel"

    def __init__(self, text: Optional[TextChannel] = None,
                 call: Optional[CallChannel] = None, contact=None) -> None:
        self.text = text or TextChannel()
        self.call = call or CallChannel()
        self.contact = contact   # str or callable -> str: fallback recipient

    def handles(self) -> List[str]:
        return ["send_text", "call"]

    def _default_contact(self) -> str:
        c = self.contact() if callable(self.contact) else self.contact
        return c or "user"

    async def handle(self, job: Job) -> Result:
        args = job.args or {}
        to = args.get("recipient") or args.get("to") or self._default_contact()
        body = args.get("body") or args.get("message") or args.get("text") or ""
        channel = self.text if job.intent == "send_text" else self.call
        rec = channel.send(to, body)
        if not rec.get("sent"):
            return Result(job_id=job.id, status=JobStatus.failed,
                          error=f"channel {channel.name}: {rec.get('error', 'send failed')}",
                          proof=None)
        message_id = rec.get("call_sid") or (
            f"{'mock' if rec.get('mock') else 'live'}-{channel.name}-{job.id[:8]}")
        return Result(job_id=job.id, status=JobStatus.success,
                      output={"delivered": "mock" if rec.get("mock") else "live",
                              "channel": channel.name},
                      proof={"message_id": message_id, "channel": channel.name,
                             "to": to, "mock": bool(rec.get("mock"))},
                      cost=0.0)
