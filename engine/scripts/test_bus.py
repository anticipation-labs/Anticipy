"""Piece 1 test: the bus carries events and jobs, correlates results, decides nothing.

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_bus.py
"""
import asyncio

from anticipy_engine.core.bus import Bus
from anticipy_engine.core.envelopes import Event, EventSource, Job, JobStatus, MessageType, Result


class Echo:
    def handles(self):
        return ["echo"]

    async def handle(self, job: Job) -> Result:
        return Result(job_id=job.id, status=JobStatus.success, output={"echo": job.args}, proof={"ok": True})


async def main() -> None:
    seen_events: list = []
    seen_results: list = []

    async def on_event(m):
        seen_events.append(m)

    async def on_result(m):
        seen_results.append(m)

    bus = Bus()
    bus.subscribe(MessageType.EVENT, on_event)
    bus.subscribe(MessageType.RESULT, on_result)
    bus.register_worker(Echo())
    await bus.start()
    try:
        # pub/sub: an event reaches subscribers
        ev = Event(source=EventSource.system, text="ping")
        await bus.publish(ev)
        assert seen_events and seen_events[-1].id == ev.id

        # job/result: dispatched to the registered worker, result correlated back
        res = await bus.submit_job(Job(intent="echo", args={"n": 1}))
        assert res.status == JobStatus.success
        assert res.output == {"echo": {"n": 1}} and res.proof == {"ok": True}
        assert seen_results and seen_results[-1].job_id == res.job_id  # result also published

        # unknown intent -> failed with an error, no crash
        miss = await bus.submit_job(Job(intent="nope"))
        assert miss.status == JobStatus.failed and "no worker" in (miss.error or "")
    finally:
        await bus.stop()

    print("PASS piece 1: bus (pub/sub + correlated job queue)")
    print("  events seen:", len(seen_events), "| results seen:", len(seen_results))


if __name__ == "__main__":
    asyncio.run(main())
