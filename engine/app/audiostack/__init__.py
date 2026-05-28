"""Anticipy audio stack (NEW build, on top of the frozen reasoning
system p0..p11 and the frozen action engine phase-v4).

This package is the front of the system: raw audio in, only trusted
wearer-conversation instruction spans out, everything else demoted to
the LIFE_LOG. It feeds the FROZEN proactive engine through the
existing platform_adapter.transcript_source() seam and never modifies
a frozen file.

Four layers (see stack.py):
  L1 conversation membership  wearer anchor + turn-taking
  L2 directed-speech gate + explicit DEGRADED state
  L3 load-bearing slot trust  per-token confidence -> confirm or fire
  L4 demotion                 sub-threshold -> LIFE_LOG, never promoted

Safe failure is asymmetric and hard-coded: when membership is
uncertain the span does NOT pass as actionable (it still goes to the
LIFE_LOG); when a load-bearing slot is uncertain the action does NOT
fire (it confirms). Over-trust is the disaster; bias to under-trust.
"""

__all__ = [
    "audio",
    "corpus",
    "enrollment",
    "lifelog",
    "metrics",
    "stack",
]
