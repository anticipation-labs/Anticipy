"""Room 1.5 — the P2 decider: a cheap-model second opinion on COMMITMENT.

Sits between triage (Room 1, recall-biased) and the harm-line (Room 2, deterministic,
FINAL). Triage answers "could this be actionable?"; the decider answers "did the person
actually decide to do a concrete thing?" — the judgment a word-shape rule cannot make
(vents that look like commands, musing that names real actions, retractions).

The prompt is the Track-B-proven seed (overnight/track_b/decider.py): principled,
abstract, contains no eval line, biased to SILENT because acting on a non-commitment
is the cardinal sin.

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
What matters is COMMITMENT, not topic — did the person actually decide to do a concrete thing?

ACT — the person clearly committed to, or directly asked for, a concrete action that is SAFE and
REVERSIBLE to do for them: a self-task, a reminder, adding to a list, drafting something, or
checking on a live loop they care about. There is real first-person intent about a doable thing.

ASK — there IS a real action, but the binding step commits them to a person or a thing: booking,
canceling on someone, sending/emailing/forwarding to a real person, RSVPing, or paying — OR the
request is half-formed / has options they have not chosen. Do the safe prep, but a human must
confirm the binding step. (If in doubt between ACT and ASK on something binding, choose ASK.)

SILENT — there is NO decision to act on: a vent or complaint, a wish or someday-maybe, a joke or
hyperbole, an opinion or reaction, or a remark ABOUT a person rather than a thing they will DO.
Tentative words like "maybe", "might", "should... someday", "keep meaning to", "I really need to"
(with no explicit request) are NOT commitments. When you are not sure it is a real commitment,
choose SILENT — acting on a non-commitment is the worst possible error.

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
