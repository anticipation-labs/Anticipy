"""Reusable artifact proof helpers for browser-agent read-back.

The browser agent should only complete a mutation after an independently read
artifact stays visible across repeated reads. This module keeps that discipline
target-agnostic so carts, submitted forms, drafts, and other future surfaces can
share the same fail-closed behavior.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional


Observation = dict[str, Any]
ReadOnce = Callable[[], Awaitable[tuple[Observation, Any]]]
Verifier = Callable[[Observation], bool]
Scorer = Callable[[Observation], float]
Sleeper = Callable[[float], Awaitable[None]]


@dataclass(frozen=True)
class ArtifactProof:
    observation: Observation
    shot: Any
    confirmed: bool
    reads: int
    failed_read_index: Optional[int] = None


def _score_or_zero(score: Optional[Scorer], observation: Observation) -> float:
    if score is None:
        return 0.0
    try:
        return float(score(observation or {}))
    except Exception:
        return 0.0


async def confirm_stable_artifact(
    read_once: ReadOnce,
    is_verified: Verifier,
    *,
    score: Optional[Scorer] = None,
    reads: int = 3,
    delay_seconds: float = 0.0,
    sleep: Sleeper = asyncio.sleep,
) -> ArtifactProof:
    """Return confirmed only when every delayed read verifies the artifact.

    The best passing observation is kept for success, but the first failed read
    is returned on rejection. That prevents a stale earlier success from hiding a
    later disappearance or flicker.
    """
    total_reads = max(1, int(reads))
    delay = max(0.0, float(delay_seconds))
    best_out: Observation = {}
    best_shot: Any = None
    best_score: Optional[float] = None

    for idx in range(total_reads):
        if idx and delay:
            await sleep(delay)
        try:
            out, shot = await read_once()
        except Exception:
            return ArtifactProof({}, None, False, idx + 1, idx)

        out = out or {}
        if out:
            current_score = _score_or_zero(score, out)
            if best_score is None or current_score >= best_score:
                best_out = out
                best_shot = shot or best_shot
                best_score = current_score

        try:
            verified = bool(is_verified(out))
        except Exception:
            verified = False
        if not verified:
            return ArtifactProof(out, shot, False, idx + 1, idx)

    return ArtifactProof(best_out, best_shot, True, total_reads, None)
