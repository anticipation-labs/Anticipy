"""Anticipy — the one who's responsible for everything.

Anticipy is the orchestrator AND its personality. One mind that:
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
import re
import time
from dataclasses import dataclass, field
from typing import Optional

import requests

from .llm import LLM
from .memory import Memory
from .orchestrator import Brain, Decision, IRREVERSIBLE

NAME = "Anticipy"

# Policy layer OUTSIDE the model: any goal whose text implies something that
# leaves the owner's world (sending, booking, buying, signing up, calling,
# posting, deleting) is held for confirmation regardless of what triage said.
# LLM goal strings are free-form, so exact-match sets are not enough.
_IRREVERSIBLE_RE = re.compile(
    r"\b(send|email|book|reserve|buy|purchase|order|pay|sign(\s+\w+)?\s*up|register|"
    r"subscribe|submit|post|publish|reply|message|text|call|cancel|delete|"
    r"unsubscribe|transfer|schedule|invite|rsvp)\b",
    re.IGNORECASE,
)


def is_consequential(goal: str, params: dict | None = None) -> bool:
    blob = f"{goal} {json.dumps(params or {})}"
    return bool(_IRREVERSIBLE_RE.search(blob))

BRIEFING_SYSTEM = f"""You are {NAME}, the person's personal assistant who lives
in their Anticipy pendant. You are warm, brief, and competent — a trusted
chief-of-staff, never a robot. Given what you overheard today and your open
to-dos, write a 2-4 sentence spoken-style briefing in the first person, e.g.:
"How goes it today? I overheard you promised Sarah the pitch deck — I've got a
draft ready and I'll send it the second you say so." Never invent things that
aren't in the notes. Every item carries a status — only say something is done
if its status is "done"; declined or cancelled items were NOT done; anything
else is at most "in progress" or "waiting on you". No emojis, no bullets."""


@dataclass
class LoopRecord:
    """One open loop Anticipy is personally responsible for closing."""
    commitment_id: int
    what: str
    status: str = "handling"     # handling | awaiting_ok | done | failed
    job_id: Optional[str] = None
    opened_ts: float = field(default_factory=time.time)


class Anticipy:
    def __init__(
        self,
        memory: Optional[Memory] = None,
        llm: Optional[LLM] = None,
        backend_url: str = "http://127.0.0.1:8090",
        voice=None,
        owner_phone: Optional[str] = None,
        owner_id: str = "",
        conversation=None,
    ):
        self.llm = llm
        self.memory = memory or Memory(llm=llm)
        self.brain = Brain(llm=llm) if llm else None
        self.backend_url = backend_url.rstrip("/")
        self.voice = voice
        self.owner_phone = owner_phone
        self.owner_id = owner_id
        self.conversation = conversation
        self.loops: list[LoopRecord] = []
        self.session_start = time.time()

    # ------------------------------------------------------------ hearing

    def hear(self, line: str) -> dict:
        """One transcript line in; memory, decision, and delegation out."""
        mem = self.memory.ingest(line)
        decision = self._decide(line, mem)
        handled = None

        if decision.decision == "act" and decision.goal:
            params = {"source": line}
            # The EFFECTIVE hold: triage's flag OR the policy layer. The owner
            # must be told whenever the job is actually held, or held jobs
            # would sit silently forever.
            held = (decision.needs_confirmation
                    or decision.goal in IRREVERSIBLE
                    or is_consequential(decision.goal, params))
            job_id = self._queue_job(decision.goal, params, hold=held)
            loop = LoopRecord(
                commitment_id=mem.get("commitment_id") or -1,
                what=decision.goal,
                status="awaiting_ok" if held else "handling",
                job_id=job_id,
            )
            self.loops.append(loop)
            handled = self.say_handling(decision.goal, held)
            # Details first, browser second: before anything irreversible she
            # texts the owner — their go-ahead releases the held job.
            if held:
                self.notify_owner(
                    f"{handled} Say the word and it goes, or tell me what to change.")
        elif decision.decision == "ask":
            handled = f"Quick question — {decision.reason or 'want me to take this on?'}"
            self.notify_owner(handled)

        return {
            "memory": mem,
            "decision": decision,
            "anticipy_says": handled,
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
        """Anticipy's greeting: what she heard, what she's handling."""
        facts = self.memory.briefing_facts(self.session_start)
        # Ground the briefing in actual outcomes so she never claims a thing
        # happened that didn't.
        facts["task_statuses"] = [{"what": l.what, "status": l.status}
                                  for l in self.loops]
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
        # Conversational channel first: she opens a real thread, not a
        # "reply YES" wall; free-form replies come back via Conversation.on_reply.
        if self.conversation and self.owner_phone and channel == "sms":
            return self.conversation.reach_out(self.owner_phone, message)
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
                      "status": "awaiting_confirm"
                      if (hold or goal in IRREVERSIBLE or is_consequential(goal, params))
                      else "queued",
                      "device_id": "anticipy", "owner": self.owner_id},
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
                    elif status == "needs_user":
                        loop.status = "needs_you"
                    elif status == "cancelled":
                        loop.status = "declined"
                except Exception:
                    pass
            out.append({"what": loop.what, "status": loop.status, "job": loop.job_id})
        return out
