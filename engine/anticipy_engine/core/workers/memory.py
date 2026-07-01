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
from ...memory.store import is_active_open_loop
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
            loops = [l for l in self.lm.memory.open_loops.all() if is_active_open_loop(l)]
            out = [{"id": l.id, "task": l.fields.get("task", l.text), "due": l.fields.get("due", ""),
                    "due_ts": l.fields.get("due_ts"), "remind_ts": l.fields.get("remind_ts"),
                    "created_ts": l.timestamp, "text": l.text,
                    "fired_at": l.fields.get("fired_at"),
                    # the full structured fields ride along so the trigger path can read the
                    # loop's kind (e.g. a scheduled follow_up) + its link to the original card.
                    "fields": l.fields}
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
                # BENIGN NO-OP: nothing to mark (the loop may have been consolidated away, never
                # created, or already cleaned). This MUST be success, never failed — a missing
                # bookkeeping target must not fail the whole goal and thereby HIDE a successful
                # primary action (e.g. a real calendar event created in the prior step) behind a
                # "failed" goal with empty proof. Surfaced by GUI human-testing of the calendar arm.
                return Result(job_id=job.id, status=JobStatus.success,
                              output={"id": str(job.args.get("id") or ""), "status": "not_found",
                                      "noop": True},
                              proof={"noop": "open loop not found — nothing to mark"}, cost=0.0)
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
            # THE single context seam: everyone reads through the one ContextPack builder
            # (decider=decide, hands=act, voice=speak) so the pieces share one context.
            purpose = str(job.args.get("purpose") or "decide")
            pack = self.lm.build_context(job.args.get("about", ""), purpose=purpose)
            return Result(job_id=job.id, status=JobStatus.success,
                          output={"context": pack.as_ctx_dict(),
                                  "top_relevance": pack.top_relevance,   # for the harm-line gray middle
                                  "abstain": pack.abstain,
                                  "purpose": pack.purpose},
                          proof={"injected": pack.item_count, "open_loops": len(pack.open_loops)}, cost=0.0)
        # write_memory: an explicit write — force-keep into the requested drawer
        text = job.args.get("text") or job.args.get("note") or job.args.get("about") or ""
        requested = str(job.args.get("kind") or "").strip().lower()
        drawer_by_kind = {
            "profile": self.lm.memory.profile,
            "profile_fact": self.lm.memory.profile,
            "history": self.lm.memory.history,
            "derived": self.lm.memory.derived,
            "open_loop": self.lm.memory.open_loops,
            "open_loops": self.lm.memory.open_loops,
        }
        drawer = drawer_by_kind.get(requested)
        if drawer is not None and text:
            status = "open" if drawer.name == "open_loops" else "active"
            if drawer.name == "open_loops":
                norm = " ".join(text.split()).lower()
                item = next((
                    loop for loop in drawer.all()
                    if " ".join(loop.text.split()).lower() == norm
                ), None)
                if item is None:
                    item = drawer.write_text(text, fields={"task": text}, provenance="write_memory", status=status)
            else:
                item = drawer.write_text(text, provenance="write_memory", status=status)
            kind = drawer.kind
            written = True
        else:
            res = self.lm.capturer.capture(text, source="write_memory", force=True)
            item = res.get("item")
            kind = res.get("kind")
            written = bool(res.get("kept"))
        return Result(job_id=job.id, status=JobStatus.success,
                      output={"written": written},
                      proof={"memory_id": item.id if item else "none", "kind": kind}, cost=0.0)

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
