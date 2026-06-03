"""The act-vs-ask gate.

Maps an action's risk to what should happen before it runs:
  low           -> act      (do it autonomously)
  needs_confirm -> confirm  (surface a confirm in the app first)
  ask_human     -> escalate (hand to a human)
This is the slot; richer policy lands with the action chunk.
"""
from __future__ import annotations

from ..shared.schema import ActionRequest

_DECISION = {"low": "act", "needs_confirm": "confirm", "ask_human": "escalate"}


class ActGate:
    def decide(self, request: ActionRequest) -> str:
        return _DECISION[request.risk]
