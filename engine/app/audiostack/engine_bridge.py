"""P4 wiring: the four-layer stack -> the FROZEN proactive engine.

The stack emits ONLY trusted wearer-conversation spans onto the
existing platform_adapter.transcript_source() seam. This bridge
drains that seam and calls the FROZEN ProactiveEngine.decide (p0..
p11, byte-unchanged) with the action engine MOCKED (P6 wires the
real one). Two independent defenses: the stack decides "is this a
real instruction to the wearer", the frozen engine then decides "is
this a real committed task and is it safe to act". Nothing here
modifies a frozen file; the only contact is the engine's public
decide() through the existing seam.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Optional

from app.audiostack import audio as A
from app.audiostack.stack import AudioStack


@dataclass
class E2EResult:
    item_id: str
    category: str
    label: str
    stack_outcome: str          # ACTIONABLE | CONFIRM | LIFE_LOG | DEGRADED_LOG
    engine_decision: str        # ACT | STORE_AS_LATENT | ASK | IGNORE | n/a
    end_to_end_acted: bool      # stack emitted AND frozen engine ACTed
    degraded_declared: bool


def _ctx(user_id: str = "wearer"):
    from app.anticipy.seams import UserContext, UserProfile

    # SCALE: never seed Omar-specific identity into a stranger's
    # decision context. Start from an EMPTY profile (no name, no
    # people, no role) so the frozen engine reads the real wearer's
    # state only via the dossier loader where downstream code looks.
    return UserContext.from_profile(UserProfile(
        user_id=user_id, name="", role_title="",
        what_they_do="", mandate="",
        people={},
        trajectory_confidence=0.0, days_since_onboard=0))


def run_end_to_end(item: dict, stack: AudioStack, ctx) -> E2EResult:
    """One corpus item, stack -> frozen engine (mock action)."""
    from app.anticipy import platform_adapter

    # clear any residue so this item's emit is isolated
    platform_adapter.transcript_source().drain()
    wav = A.load_wav(item["wav_path"])
    dec, _utts = stack.process(wav, {"category": item["category"],
                                     "ts": 0.0})
    eng = "n/a"
    acted = False
    if dec.outcome == "ACTIONABLE":
        lines = platform_adapter.transcript_source().drain()
        if lines:
            from app.anticipy.proactive_engine import ProactiveEngine

            try:
                r = asyncio.run(ProactiveEngine().decide(
                    lines, ctx, "mac_mic"))
                eng = getattr(r, "decision", "IGNORE")
            except Exception as e:
                eng = f"ERROR:{type(e).__name__}"
            acted = eng == "ACT"
    return E2EResult(
        item_id=item["item_id"], category=item["category"],
        label=item["label"], stack_outcome=dec.outcome,
        engine_decision=eng, end_to_end_acted=acted,
        degraded_declared=dec.degraded_declared)


def to_item_result(e: E2EResult):
    """Map the end-to-end outcome onto the honest metrics schema.
    end-to-end ACTIONABLE requires BOTH the stack to emit AND the
    frozen engine to ACT (the two independent defenses agreeing).
    """
    from app.audiostack import metrics as M

    if e.end_to_end_acted:
        outcome = "ACTIONABLE"
    elif e.stack_outcome == "CONFIRM":
        outcome = "CONFIRM"
    elif e.stack_outcome == "DEGRADED_LOG":
        outcome = "DEGRADED_LOG"
    else:
        outcome = "LIFE_LOG"
    return M.ItemResult(
        item_id=e.item_id, category=e.category, label=e.label,
        outcome=outcome, degraded_declared=e.degraded_declared,
        content_ok=True,
        blind_fire_on_low_conf=(e.category == "LOADBEARING_WORD_STRESS"
                                and outcome == "ACTIONABLE"))
