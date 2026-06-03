"""channel_stub — handles send_email / send_text / call. Never really sends."""
from __future__ import annotations

from typing import List

from ..envelopes import Job
from .scriptable import ScriptableStub


class ChannelStub(ScriptableStub):
    name = "channel_stub"

    def handles(self) -> List[str]:
        return ["send_email", "send_text", "call"]

    def _proof(self, job: Job) -> dict:
        return {"message_id": f"stub-msg-{job.id[:8]}", "channel": job.intent}

    def _output(self, job: Job) -> dict:
        return {"delivered": "stubbed"}
