"""connector_stub — handles app actions (create_event, etc.). Fake proof, never real."""
from __future__ import annotations

from typing import List

from ..envelopes import Job
from .scriptable import ScriptableStub


class ConnectorStub(ScriptableStub):
    name = "connector_stub"

    def handles(self) -> List[str]:
        return ["create_event", "create_doc", "update_record"]

    def _proof(self, job: Job) -> dict:
        return {"record_id": f"stub-rec-{job.id[:8]}", "action": job.intent}

    def _output(self, job: Job) -> dict:
        return {"applied": "stubbed"}
