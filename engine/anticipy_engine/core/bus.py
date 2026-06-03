"""The bus — dumb pipes. In-process async pub/sub + a correlated job queue.

It carries messages and decides nothing. Lightweight (one Mac, one engine), not
heavy infrastructure. Events fan out to subscribers; Jobs are queued, run by the
worker registered for their intent, and the matching Result is handed back to the
submitter. Everything that flows is logged to the glass-box if one is attached.

Single worker-runner: workers must not submit nested jobs (none do — the gate
submits its context read from the proactive loop, not from inside a worker).
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Awaitable, Callable, Dict, List, Optional

from .envelopes import Event, Job, MessageType, Result, JobStatus

Handler = Callable[[object], Awaitable[None]]


class Bus:
    def __init__(self, glassbox=None) -> None:
        self._subscribers: Dict[MessageType, List[Handler]] = defaultdict(list)
        self._workers: Dict[str, object] = {}
        self._queue: "asyncio.Queue[Job]" = asyncio.Queue()
        self._results: Dict[str, "asyncio.Future[Result]"] = {}
        self._runner: Optional[asyncio.Task] = None
        self.glassbox = glassbox

    # ---- wiring ----
    def subscribe(self, mtype: MessageType, handler: Handler) -> None:
        self._subscribers[mtype].append(handler)

    def register_worker(self, worker) -> None:
        for intent in worker.handles():
            self._workers[intent] = worker

    def worker_for(self, intent: str):
        return self._workers.get(intent)

    # ---- lifecycle ----
    async def start(self) -> None:
        if self._runner is None:
            self._runner = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._runner is not None:
            self._runner.cancel()
            try:
                await self._runner
            except asyncio.CancelledError:
                pass
            self._runner = None

    # ---- publish / subscribe ----
    async def publish(self, message) -> None:
        if self.glassbox is not None:
            self.glassbox.log(message.type.value, message.model_dump(mode="json"))
        for handler in list(self._subscribers.get(message.type, [])):
            await handler(message)

    # ---- jobs (request/response) ----
    async def submit_job(self, job: Job) -> Result:
        if self.glassbox is not None:
            self.glassbox.log("job", job.model_dump(mode="json"))
        loop = asyncio.get_running_loop()
        fut: "asyncio.Future[Result]" = loop.create_future()
        self._results[job.id] = fut
        await self._queue.put(job)
        return await fut

    async def _run(self) -> None:
        while True:
            job = await self._queue.get()
            worker = self._workers.get(job.intent)
            if worker is None:
                result = Result(
                    job_id=job.id,
                    status=JobStatus.failed,
                    error=f"no worker registered for intent '{job.intent}'",
                    proof=None,
                )
            else:
                try:
                    result = await worker.handle(job)
                except Exception as exc:  # a worker blowing up must not kill the bus
                    result = Result(job_id=job.id, status=JobStatus.failed,
                                    error=f"{type(exc).__name__}: {exc}", proof=None)
            await self.publish(result)  # glass-box + RESULT subscribers see it
            fut = self._results.pop(job.id, None)
            if fut is not None and not fut.done():
                fut.set_result(result)
            self._queue.task_done()
