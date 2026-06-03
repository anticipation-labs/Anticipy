"""memory_stub — handles read_context / write_memory. Canned context; records writes."""
from __future__ import annotations

from typing import List

from ..envelopes import Job
from .scriptable import ScriptableStub

CANNED_CONTEXT = {
    "profile": {"name": "Omar", "role": "founder"},
    "open_loops": [],
    "recent": [],
}


class MemoryStub(ScriptableStub):
    name = "memory_stub"

    def handles(self) -> List[str]:
        return ["read_context", "write_memory"]

    def _output(self, job: Job) -> dict:
        if job.intent == "read_context":
            return {"context": CANNED_CONTEXT}
        return {"written": True}

    def _proof(self, job: Job) -> dict:
        if job.intent == "read_context":
            return {"context_read": True}
        return {"memory_id": f"stub-mem-{job.id[:8]}"}
