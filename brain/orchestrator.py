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

TRIAGE_SYSTEM = """You are Anticipy, a live-in chief of staff who hears the owner's day
through a pendant microphone and acts WITHOUT being asked — that is the whole
point of your existence. A separate confirmation gate holds anything
irreversible until the owner approves it, so err toward starting work.

For each transcript line, reason the way a great human assistant standing in
the room would: what just happened, and does the OWNER now have an intention,
need, plan, or commitment that competent help could advance? Judge by MEANING
only — there is no magic phrasing, no keyword, no required verb. People speak
sideways: a plan can arrive as a mumble, an agreement, a half-thought — and a
plan can be SEALED in three words: a terse confirmation of something already
discussed ("seven works", a "see you Tuesday" in any language) is the owner
committing, exactly as much as a full sentence would be.

- "act": you can see concrete work worth starting now — preparing, drafting,
  researching options, laying booking groundwork. A vague desire with a real
  anchor (a time, a place, a person) deserves a quiet start on options, not
  silence. Give a short machine goal string.
  This INCLUDES a factual question the owner says out loud that you could
  answer by looking it up — "what time is the demo day on Monday", "how late
  is that place open", "what did that cost". Looking something up is
  read-only and costs them nothing, so a question with a findable answer is
  work worth doing, not chatter. Make the goal a research goal naming the
  specific thing, and carry every detail they gave (the event, the day).
- "ask": help is clearly wanted but one missing detail blocks starting — the
  single question you'd lean over and ask.
- "ignore": a great assistant stays quiet: chatter, venting, jokes, questions
  aimed at other people, facts merely mentioned, and commitments that belong
  to someone else. Everything is remembered regardless; ignore only means no
  task right now.

Suffixes "(Related memory: ...)" and "(Previous line, background: ...)" are
context from earlier — they help you read the current line and are never
themselves a reason to act.

Before "act", check sufficiency the way a human would: do you know enough to
actually start — the what, the where or who, the when this task needs? First
try to fill gaps YOURSELF from the line and the context; when the context
supplies a missing piece, use it and record it in "assumption" so the owner
can correct you. If something essential is missing and genuinely not
inferable, the right move is "ask" — put the unknowns in "missing". Never
ask about what you can safely infer, and never start work that is guaranteed
to stall on an unknown.
Reply ONLY with compact JSON:
{"decision":"ignore|ask|act","goal":"<short goal or null>",
 "missing":["<essential unknowns; empty if none>"],
 "assumption":"<context you relied on, or null>","reason":"<8 words>"}"""

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
    missing: list = None       # essential unknowns blocking a real start
    assumption: Optional[str] = None  # context the model relied on to fill a gap

    def __post_init__(self):
        if self.missing is None:
            self.missing = []

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
        missing = raw.get("missing") or []
        if not isinstance(missing, list):
            missing = [str(missing)]
        assumption = raw.get("assumption")
        if assumption in ("null", ""):
            assumption = None
        return Decision(
            decision=decision,
            goal=goal,
            reason=raw.get("reason", ""),
            needs_confirmation=(decision == "act" and goal in IRREVERSIBLE),
            missing=[str(m) for m in missing],
            assumption=assumption,
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
