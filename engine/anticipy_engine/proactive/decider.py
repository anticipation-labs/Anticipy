"""Room 1.5 — the P2 decider: a cheap-model second opinion on COMMITMENT.

Sits between triage (Room 1, recall-biased) and the harm-line (Room 2, deterministic,
FINAL). Triage answers "could this be actionable?"; the decider answers "did the person
actually decide to do a concrete thing?" — the judgment a word-shape rule cannot make
(vents that look like commands, musing that names real actions, retractions).

The prompt grew from the Track-B seed (overnight/track_b/decider.py) and was revised
at lap 20260610T072358Z after the first live-tier run showed the cheap model reading
NARRATION as commitment (false-acting on "telling Beto to try him" / "tomorrow:
inspection prep" lines; probe evidence in that lap's probe_decider.py — 14/24 -> 24/24).
The revision centers the HANDOFF test: narration of one's own past/plans/social acts is
never a task; a task exists only when the line delegates one (instruction, request,
ownerless "someone should..." voicing, or unmistakable self-task). Lap 20260610T074854Z
re-landed it (the authoring session ended at its turn bound before committing) and added
the present-progressive clause ("setting up the..." openings are self-activity, not
instructions — probe 26/27 -> 27/27, no true-positive regressions). Principled, abstract,
contains no eval line, biased to SILENT because acting on a non-commitment is the
cardinal sin.

Safety contract (enforced by the caller, core/proactive.py):
  - LIVE-ONLY: the pipeline constructs a Decider only when the model gateway has a
    real provider (ANTICIPY_MODEL_PROVIDER=openrouter). Stub mode bypasses it entirely
    so the suite and stub-tier persona evals stay deterministic and free.
  - ONE-WAY: the decider may move a decision toward SILENT or ASK; it can never turn
    the harm-line's ASK into an ACT. The harm-line is FINAL on binding/detrimental.
  - FAIL-SILENT: any model failure (no key, network error, empty or unparseable
    reply) returns SILENT — never invent an action from a broken read.
"""
from __future__ import annotations

import re

from ..core.gateway import CHEAP, ModelGateway

ACT = "ACT"
ASK = "ASK"
SILENT = "SILENT"

# Tolerant parse: word-boundary only ("multitasking" must not read as ASK), and when
# the model rambles and names more than one verdict, take the SAFEST one mentioned.
_WORD_RE = re.compile(r"\b(ACT|ASK|SILENT)\b")
_SAFETY_ORDER = (SILENT, ASK, ACT)

_PROMPT = """You are the judgment gate of a proactive assistant that quietly overhears what a person says.
For the ONE line below, decide exactly one of: ACT, ASK, SILENT.
The person is NOT talking to you. They are living their day out loud. Most lines are
narration — describing what they did, are doing, or will do themselves — and narration is
never a task. A line only matters when a task is actually HANDED OFF. A task is handed
off when the line is an instruction or request about a concrete doable thing ("remind
me...", "put X on the calendar", "draft...", "book...", "get X to Y", "add X to the
list"), or when it voices a needed task with no owner ("someone should chase X",
"someone needs to fix Y" — voicing it IS the handoff), or an unmistakable self-task they
clearly want captured.

ACT — a handed-off task that is safe and reversible to just do: a reminder, a calendar
entry for themselves, adding to a list or cart, drafting something for their own later
review. An instruction about a doable thing, not a description of their own activity.

ASK — a handed-off task whose binding step commits them to another person or to money:
contacting/sending/giving something to a real person, booking, canceling on someone,
RSVPing, chasing a person down, or paying anything at all. Do the safe prep, but a human
must confirm the binding step. (If in doubt between ACT and ASK on something binding,
choose ASK. "Someone should..." tasks about a person are ASK.)

SILENT — no task was handed off, which is MOST lines:
- reports of what already happened (past tense = SILENT, no exceptions)
- the person narrating their own plan, schedule, or routine ("early start tomorrow",
  "tomorrow: X then Y") — they are doing it themselves; nothing was delegated
- "-ing" openings describing their own activity in progress ("setting up the...",
  "packing the...", "heading out to...") — they are doing it themselves right now, even
  when a purpose tail explains why ("so the morning isn't chaos", "so I actually go");
  a real instruction is imperative ("set up X", "remind me to X"), not a description
- self-talk and self-personification ("future me", "tomorrow-me will thank me",
  scolding or bribing themselves into habits) — managing their own behavior out loud
  is still narration; nothing was handed to anyone
- things THEY will personally tell, show, or mention to someone in conversation
  ("telling Sam to come by", "showing Ana the photos") — their own social act, not a
  message for you to send
- jokes, hyperbole, idioms, predictions, banter, opinions, vents, complaints
- wishes and someday-maybes ("should really...", "would be nice...", "one of these days")
When you are not sure a task was actually handed off, choose SILENT — acting on a
non-task is the worst possible error.

Reply with ONLY one word: ACT, ASK, or SILENT.
Line: "{line}"
"""


def parse_verdict(raw: str) -> str:
    """Extract the verdict from a model reply. Unparseable -> SILENT (fail safe);
    multiple verdicts mentioned -> the safest of them."""
    found = set(_WORD_RE.findall((raw or "").upper()))
    for word in _SAFETY_ORDER:
        if word in found:
            return word
    return SILENT


class Decider:
    """`decide(line)` -> ACT | ASK | SILENT via one cheap-model call at temperature 0."""

    def __init__(self, gateway: ModelGateway, glassbox=None) -> None:
        self.gateway = gateway
        self.glassbox = glassbox
        self.calls = 0

    async def decide(self, line: str) -> str:
        self.calls += 1
        try:
            raw = await self.gateway.think(
                _PROMPT.format(line=line), tier=CHEAP, caller="decider", temperature=0
            )
        except Exception as e:  # no key / transport / provider error -> fail SILENT
            if self.glassbox is not None:
                self.glassbox.log("decider_error", {"line": line, "error": str(e)})
            return SILENT
        word = parse_verdict(raw or "")
        if self.glassbox is not None:
            self.glassbox.log("decider", {"line": line, "raw": (raw or "")[:200], "verdict": word})
        return word
