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
        return ["read_context", "write_memory", "list_open_loops"]

    async def handle(self, job: Job) -> Result:
        if job.intent == "list_open_loops":
            # the trigger watcher's condition source (Room 3): the commitment ledger, structured.
            loops = [l for l in self.lm.memory.open_loops.all() if l.status in ("open", "waiting")]
            out = [{"id": l.id, "task": l.fields.get("task", l.text), "due": l.fields.get("due", ""),
                    "due_ts": l.fields.get("due_ts"), "created_ts": l.timestamp, "text": l.text}
                   for l in loops]
            return Result(job_id=job.id, status=JobStatus.success, output={"loops": out},
                          proof={"loops": len(out)}, cost=0.0)
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
