"""Annie — the one who's responsible for everything.

Annie is Anticipy's orchestrator AND its personality. One mind that:
- hears every transcript line and files it into the temporal memory graph,
- decides what matters (ignore / ask / act) with memory as context,
- delegates: browser work to the action arm (extension / browser-use via the
  job queue), texts and calls to the voice arm (Twilio),
- tracks every open loop (commitment) until it's done,
- speaks in the first person: "How goes it today? I overheard X — I'm
  handling it. I'll ask before anything goes out."

Nothing irreversible executes without confirmation — that gate lives in the
job queue, outside any model.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Optional

import requests

from .llm import LLM
from .memory import Memory
from .orchestrator import Brain, Decision, IRREVERSIBLE

NAME = "Annie"

BRIEFING_SYSTEM = f"""You are {NAME}, the person's personal assistant who lives
in their Anticipy pendant. You are warm, brief, and competent — a trusted
chief-of-staff, never a robot. Given what you overheard today and your open
to-dos, write a 2-4 sentence spoken-style briefing in the first person, e.g.:
"How goes it today? I overheard you promised Sarah the pitch deck — I've got a
draft ready and I'll send it the second you say so." Never invent things that
aren't in the notes. No emojis, no bullet points."""


@dataclass
class LoopRecord:
    """One open loop Annie is personally responsible for closing."""
    commitment_id: int
    what: str
    status: str = "handling"     # handling | awaiting_ok | done | failed
    job_id: Optional[str] = None
    opened_ts: float = field(default_factory=time.time)


class Annie:
    def __init__(
        self,
        memory: Optional[Memory] = None,
        llm: Optional[LLM] = None,
        backend_url: str = "http://127.0.0.1:8090",
        voice=None,
        owner_phone: Optional[str] = None,
    ):
        self.llm = llm
        self.memory = memory or Memory(llm=llm)
        self.brain = Brain(llm=llm) if llm else None
        self.backend_url = backend_url.rstrip("/")
        self.voice = voice
        self.owner_phone = owner_phone
        self.loops: list[LoopRecord] = []
        self.session_start = time.time()

    # ------------------------------------------------------------ hearing

    def hear(self, line: str) -> dict:
        """One transcript line in; memory, decision, and delegation out."""
        mem = self.memory.ingest(line)
        decision = self._decide(line, mem)
        handled = None

        if decision.decision == "act" and decision.goal:
            job_id = self._queue_job(decision.goal, {"source": line},
                                     hold=decision.needs_confirmation)
            loop = LoopRecord(
                commitment_id=mem.get("commitment_id") or -1,
                what=decision.goal,
                status="awaiting_ok" if decision.needs_confirmation else "handling",
                job_id=job_id,
            )
            self.loops.append(loop)
            handled = self.say_handling(decision.goal, decision.needs_confirmation)
        elif decision.decision == "ask":
            handled = f"Quick question — {decision.reason or 'want me to take this on?'}"

        return {
            "memory": mem,
            "decision": decision,
            "annie_says": handled,
        }

    def _decide(self, line: str, mem: dict) -> Decision:
        if self.brain:
            context = self.memory.recall(line, limit=4)
            prompt = line
            if context:
                notes = "; ".join(f["fact"] for f in context)
                prompt = f"{line}\n(Related memory: {notes})"
            return self.brain.triage(prompt)
        # Deterministic offline path: a fresh commitment means act.
        if mem.get("commitment"):
            return Decision(decision="act", goal="agent_goal",
                            reason="heard a commitment", needs_confirmation=True)
        return Decision(decision="ignore", goal=None, reason="nothing to do")

    # ------------------------------------------------------------ speaking

    def say_handling(self, goal: str, needs_ok: bool) -> str:
        pretty = goal.replace("_", " ")
        if needs_ok:
            return f"I overheard that — I'm preparing the {pretty} now. Nothing goes out until you say so."
        return f"On it — I'm handling the {pretty}."

    def briefing(self) -> str:
        """Annie's greeting: what she heard, what she's handling."""
        facts = self.memory.briefing_facts(self.session_start)
        if self.llm:
            try:
                res = self.llm.chat(BRIEFING_SYSTEM, json.dumps(facts))
                text = res.text.strip()
                if text:
                    return text
            except Exception:
                pass
        heard = facts["heard"]
        loops = facts["open_loops"]
        parts = [f"How goes it today? I'm {NAME}."]
        if heard:
            parts.append(f"I overheard {len(heard)} thing{'s' if len(heard) != 1 else ''} worth remembering.")
        if loops:
            what = "; ".join(l["what"] for l in loops[:3])
            parts.append(f"I'm handling: {what}. I'll ask before anything goes out.")
        else:
            parts.append("Nothing needs you right now — go live your day.")
        return " ".join(parts)

    # ----------------------------------------------------------- voice arm

    def notify_owner(self, message: str, channel: str = "sms") -> Optional[dict]:
        if not (self.voice and self.owner_phone):
            return None
        if channel == "call":
            return self.voice.call(self.owner_phone, message)
        return self.voice.text(self.owner_phone, message)

    # ---------------------------------------------------------- action arm

    def _queue_job(self, goal: str, params: dict, hold: bool = False) -> Optional[str]:
        try:
            r = requests.post(
                f"{self.backend_url}/api/collections/jobs/records",
                json={"goal": goal, "params": json.dumps(params),
                      "status": "awaiting_confirm" if (hold or goal in IRREVERSIBLE) else "queued",
                      "device_id": "annie"},
                timeout=10,
            )
            r.raise_for_status()
            return r.json().get("id")
        except Exception:
            return None

    def review_loops(self) -> list[dict]:
        """Poll the job queue and close loops whose jobs finished."""
        out = []
        for loop in self.loops:
            if loop.job_id and loop.status in ("handling", "awaiting_ok"):
                try:
                    r = requests.get(
                        f"{self.backend_url}/api/collections/jobs/records/{loop.job_id}",
                        timeout=10)
                    status = r.json().get("status")
                    if status == "done":
                        loop.status = "done"
                        if loop.commitment_id > 0:
                            self.memory.resolve(loop.commitment_id)
                    elif status == "failed":
                        loop.status = "failed"
                    elif status == "awaiting_confirm":
                        loop.status = "awaiting_ok"
                except Exception:
                    pass
            out.append({"what": loop.what, "status": loop.status, "job": loop.job_id})
        return out
