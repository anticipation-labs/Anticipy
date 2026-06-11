"""memory worker — handles read_context / write_memory on the frozen contract.

MemoryStub: the original canned stub (kept for its unit test).
MemoryWorker: the REAL worker the control core registers — read_context -> inject()
relevant memory; write_memory -> force-capture into a drawer. Takes a live-memory
object (duck-typed: needs .inject(about) + .capturer.capture(text, source, force)),
so this module stays free of live_memory imports.
"""
from __future__ import annotations

from typing import List

from ..envelopes import Job, JobStatus, Result
from ..worker import Worker
from .scriptable import ScriptableStub


class MemoryWorker(Worker):
    name = "memory"

    def __init__(self, live_memory) -> None:
        self.lm = live_memory

    def handles(self) -> List[str]:
        return ["read_context", "write_memory", "list_open_loops", "mark_loop"]

    async def handle(self, job: Job) -> Result:
        if job.intent == "list_open_loops":
            # the trigger watcher's condition source (Room 3): the commitment ledger, structured.
            loops = [l for l in self.lm.memory.open_loops.all() if l.status in ("open", "waiting")]
            out = [{"id": l.id, "task": l.fields.get("task", l.text), "due": l.fields.get("due", ""),
                    "due_ts": l.fields.get("due_ts"), "remind_ts": l.fields.get("remind_ts"),
                    "created_ts": l.timestamp, "text": l.text,
                    "fired_at": l.fields.get("fired_at")}
                   for l in loops]
            return Result(job_id=job.id, status=JobStatus.success, output={"loops": out},
                          proof={"loops": len(out)}, cost=0.0)
        if job.intent == "mark_loop":
            # ledger state change (e.g. a fired reminder -> waiting on the user), and/or
            # the durable fired stamp (ledger D16: trigger_tick stamps fired_at BEFORE any
            # send/act so a restart can never re-fire the loop). A pure fired_at stamp
            # leaves status alone; a call with neither arg keeps the legacy default.
            item = self.lm.memory.open_loops.get(str(job.args.get("id") or ""))
            if item is None:
                return Result(job_id=job.id, status=JobStatus.failed,
                              error="unknown open loop", proof=None)
            fired_at = job.args.get("fired_at")
            if fired_at is not None:
                item.fields["fired_at"] = float(fired_at)
            status = job.args.get("status")
            if status is not None or fired_at is None:
                item.status = str(status or "waiting")
            self.lm.memory.open_loops.update(item)
            return Result(job_id=job.id, status=JobStatus.success,
                          output={"id": item.id, "status": item.status,
                                  "fired_at": item.fields.get("fired_at")},
                          proof={"id": item.id}, cost=0.0)
        if job.intent == "read_context":
            inj = self.lm.inject(job.args.get("about", ""))
            ctx = {
                "notes": inj["text"],
                "open_loops": [i.text for i in inj["open_loops"]],
                "profile": [i.text for i in inj["profile"]],
                "history": [i.text for i in inj["history"]],
                "derived": [i.text for i in inj["derived"]],
            }
            return Result(job_id=job.id, status=JobStatus.success,
                          output={"context": ctx,
                                  "top_relevance": inj.get("top_relevance", 0.0),   # for the harm-line gray middle
                                  "abstain": inj.get("abstain", True)},
                          proof={"injected": len(inj["items"]), "open_loops": len(inj["open_loops"])}, cost=0.0)
        # write_memory: an explicit write — force-keep into the right drawer
        text = job.args.get("text") or job.args.get("note") or job.args.get("about") or ""
        res = self.lm.capturer.capture(text, source="write_memory", force=True)
        item = res.get("item")
        return Result(job_id=job.id, status=JobStatus.success,
                      output={"written": bool(res.get("kept"))},
                      proof={"memory_id": item.id if item else "none", "kind": res.get("kind")}, cost=0.0)

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
