"""Anticipy cold start.

Two layers:

  - ``ramp`` (MH-P10): the act-threshold experience around the FROZEN
    autonomy ramp, owns the ASK-budget / trust-earning policy on day
    zero. Reuses the frozen ramp read-only; never redefines it.
  - ``auto_inhale`` + ``cdp_walker`` (planning/10-instant-cold-start):
    the background inhale that walks the user's already-logged-in
    Chrome (Gmail inbox + sent, Google Calendar agenda) via the
    existing loopback bridge on 127.0.0.1:7777, batches raw row text
    through DeepSeek V4 Flash, and merges structured deltas into the
    active dossier so the pendant is useful from minute one.

Both layers are additive. They do not modify any frozen path and
they do not redefine the dossier schema; ``auto_inhale.merge_delta``
appends/updates inside the existing ``DossierLoader`` shape.
"""

from .auto_inhale import (
    SYSTEM_PROMPT,
    DEFAULT_ACCOUNT_ID,
    InhaleState,
    merge_delta,
    run_state,
    start_inhale,
)
from .cdp_walker import (
    BRIDGE_URL,
    CDP_BASE,
    CDPWalker,
    WalkerRow,
)

__all__ = [
    "BRIDGE_URL",
    "CDP_BASE",
    "CDPWalker",
    "DEFAULT_ACCOUNT_ID",
    "InhaleState",
    "SYSTEM_PROMPT",
    "WalkerRow",
    "merge_delta",
    "run_state",
    "start_inhale",
]
