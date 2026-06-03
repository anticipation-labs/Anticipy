"""The universal worker contract — FROZEN.

Every worker, real or stub, implements exactly this and registers which intents
it handles. The orchestrator dispatches a Job by intent and neither knows nor
cares whether the worker behind it is a stub or real. This is the exact spec
every real worker (browser, connectors, memory, channels) must hit in later
chunks. Do not change its shape.

A worker MUST return a Result whose `proof` is present and truthy on success —
the orchestrator refuses to count a step done without it.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from .envelopes import Job, Result


class Worker(ABC):
    @abstractmethod
    def handles(self) -> List[str]:
        """Intents this worker can service."""

    @abstractmethod
    async def handle(self, job: Job) -> Result:
        """Do the one thing. Return a Result; include proof on success."""
