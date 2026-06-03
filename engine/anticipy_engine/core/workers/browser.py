"""browser_stub — handles browse_task. Fake proof; scriptable to fail."""
from __future__ import annotations

from typing import List

from ..envelopes import Job
from .scriptable import ScriptableStub


class BrowserStub(ScriptableStub):
    name = "browser_stub"

    def handles(self) -> List[str]:
        return ["browse_task"]

    def _proof(self, job: Job) -> dict:
        return {"screenshot": f"stub://shot/{job.id[:8]}.png"}

    def _output(self, job: Job) -> dict:
        return {"page": "stubbed"}
