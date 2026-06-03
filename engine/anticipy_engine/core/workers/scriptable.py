"""Scriptable stub base. Every stub worker is one of these.

Per test, a stub can be told to: succeed (default), fail once then succeed,
return needs_human, or return success WITHOUT proof (to exercise the
orchestrator's verify-before-done). Behaviors are consumed FIFO; the last queued
behavior repeats once the queue is down to one.
"""
from __future__ import annotations

from typing import Dict, List

from ..envelopes import Job, JobStatus, Result
from ..worker import Worker

SUCCESS = "success"
FAIL = "fail"
NEEDS_HUMAN = "needs_human"
SUCCESS_NO_PROOF = "success_no_proof"


class ScriptableStub(Worker):
    name = "stub"

    def __init__(self) -> None:
        self._scripts: Dict[str, List[str]] = {}

    def handles(self) -> List[str]:
        raise NotImplementedError

    def script(self, intent: str, *behaviors: str) -> None:
        """Queue behaviors for an intent, consumed in order (last one sticks)."""
        self._scripts[intent] = list(behaviors)

    def _next_behavior(self, intent: str) -> str:
        q = self._scripts.get(intent)
        if not q:
            return SUCCESS
        return q.pop(0) if len(q) > 1 else q[0]

    # subclasses customize these
    def _proof(self, job: Job) -> dict:
        return {"stub_proof": f"{self.name}-{job.id[:8]}"}

    def _output(self, job: Job) -> dict:
        return {}

    async def handle(self, job: Job) -> Result:
        behavior = self._next_behavior(job.intent)
        if behavior == FAIL:
            return Result(job_id=job.id, status=JobStatus.failed,
                          error=f"{self.name}: scripted failure", proof=None)
        if behavior == NEEDS_HUMAN:
            return Result(job_id=job.id, status=JobStatus.needs_human,
                          output={"reason": "scripted needs_human"}, proof=None)
        if behavior == SUCCESS_NO_PROOF:
            # Deliberately violates the contract — used to prove the orchestrator
            # will NOT mark a step done without proof.
            return Result(job_id=job.id, status=JobStatus.success,
                          output=self._output(job), proof=None)
        return Result(job_id=job.id, status=JobStatus.success,
                      output=self._output(job), proof=self._proof(job), cost=0.0)
