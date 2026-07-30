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
through a pendant microphone. For each transcript line decide one of:
- "ignore": small talk, jokes, complaints, AND plain facts/logistics the person is just
  mentioning (times, dates, places, who said what). Facts are remembered automatically —
  do NOT create calendar events, reminders, or notes for things merely overheard.
- "ask": the person asked YOU for something but it is too ambiguous to start.
- "act": the person asked for research/lookup/comparison, asked you to sign up/book/order
  something, or made an explicit commitment whose work you can do in a browser.
Never "act" or "ask" on ambient chatter or overheard logistics — when in doubt, ignore
(it is still remembered). When you 'act', give a short machine goal string.
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
