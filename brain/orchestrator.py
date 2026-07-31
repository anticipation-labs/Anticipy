"""Anticipy orchestration brain.

Takes a line of transcript, decides ignore / act / ask, and for 'act'
produces a concrete browser goal. When it acts it runs the task FIRST,
then asks the user to confirm anything irreversible (send/book/pay).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from typing import Optional

from .llm import LLM

TRIAGE_SYSTEM = """You are Anticipy, a proactive assistant that listens to a person's day
through a pendant microphone. You act WITHOUT being asked — that is the whole point.
When the person commits to doing something, you prepare it for them; a separate
confirmation gate means nothing irreversible happens until they approve, so prefer
acting over waiting. For each transcript line decide one of:
- "act": the person made a first-person commitment or stated an intention with a
  concrete deliverable ("I'll send…", "I will get you…", "I need to book/email/call…",
  "let me follow up on…"), agreed to a concrete plan or time that belongs on a calendar
  ("yeah, 7pm tomorrow works"), OR asked for research/lookup/booking/ordering directly.
  You do the preparation; they approve before anything goes out.
- "ask": there is probably something to do for them, but it is too ambiguous to start.
- "ignore": small talk, jokes, venting, questions to other people, descriptions of the
  app itself, and third-party facts where the SPEAKER owes nothing ("Sarah said she'll
  send it"). These are still remembered — ignore only means no task.
Do not "act" on someone ELSE's commitments, on vague someday-wishes, or on pure
observations. When you 'act', give a short machine goal string.
Reply ONLY with compact JSON:
{"decision":"ignore|ask|act","goal":"<short goal or null>","reason":"<8 words>"}"""

# Goals whose final step changes the world -> require explicit user yes.
IRREVERSIBLE = {
    "draft_and_send_document",
    "find_and_book_restaurant",
    "create_calendar_event",
    "start_cancellation_flow",
    "reorder_item",
    "reschedule_appointment",
    "notify_contact",
}


@dataclass
class Decision:
    decision: str
    goal: Optional[str]
    reason: str
    needs_confirmation: bool = False

    def to_json(self) -> str:
        return json.dumps(asdict(self))


class Brain:
    def __init__(self, llm: Optional[LLM] = None):
        self.llm = llm or LLM()

    def triage(self, transcript_line: str) -> Decision:
        res = self.llm.chat(TRIAGE_SYSTEM, transcript_line)
        try:
            raw = json.loads(_extract_json(res.text))
        except Exception:
            raw = {"decision": "ignore", "goal": None, "reason": "unparseable model output"}
        decision = raw.get("decision", "ignore")
        goal = raw.get("goal")
        if goal in ("null", ""):
            goal = None
        return Decision(
            decision=decision,
            goal=goal,
            reason=raw.get("reason", ""),
            needs_confirmation=(decision == "act" and goal in IRREVERSIBLE),
        )


def _extract_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        return text[start : end + 1]
    return text
