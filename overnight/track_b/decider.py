"""Track B — the DECIDER (the judgment brain). Builder side.

Given ONE overheard line, return exactly ACT / ASK / SILENT. It uses a cheap model with a
PRINCIPLED prompt that states the commitment rule in the abstract — it contains NO line from the
answer key and never sees the marks (LAW #9: no hardcoding a line to pass). The bias is explicit:
when it is not clearly a real commitment, choose SILENT, because acting on a non-commitment (the
cardinal sin) is far worse than missing one.

This file NEVER imports the scorer or the answer key.
"""
from __future__ import annotations

import os

from anticipy_engine.core.gateway import CHEAP, PROVIDER_OPENROUTER, ModelGateway

_VALID = {"ACT", "ASK", "SILENT"}

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


def _gateway() -> ModelGateway:
    return ModelGateway(provider=PROVIDER_OPENROUTER,
                        cheap_model=os.environ.get("ANTICIPY_MODEL_CHEAP", "google/gemini-3.1-flash-lite"),
                        smart_model=os.environ.get("ANTICIPY_MODEL_SMART", "google/gemini-3.5-flash"))


async def decide(line: str, gw: ModelGateway | None = None) -> str:
    gw = gw or _gateway()
    raw = (await gw.think(_PROMPT.format(line=line), tier=CHEAP, caller="decider", temperature=0) or "").upper()
    for tok in _VALID:                  # tolerant parse: find the one word it said
        if tok in raw:
            return tok
    return "SILENT"                     # unparseable -> fail SAFE (never invent an action)
