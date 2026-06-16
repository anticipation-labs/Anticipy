"""Room 5 — the annoyance budget (wearable 365 days).

An interruption is a withdrawal from a finite daily account, not a deposit: proactive agents
hit a hard ceiling of ~3-5 notifications/day before users take the pendant off. This caps
PROACTIVE interruptions (asks the ENGINE initiates), learns from declines (don't re-propose a
declined action-type), and prefers SUPPRESSING over deferring. USER-initiated asks are never
suppressed. The cap NUMBER is Omar's (DECISIONS-ONLY-OMAR) — configurable, default anchored to
the research 3-5/day ceiling. Recipe + sources: notes/proactive_room5.md.
"""
from __future__ import annotations

import os
import re
from typing import List, Optional, Set


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except (TypeError, ValueError):
        return default


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except (TypeError, ValueError):
        return default

_STOP = {"the", "a", "an", "to", "of", "for", "and", "or", "my", "me", "us", "it", "this",
         "that", "about", "on", "in", "with", "your", "his", "her", "their", "our"}
_TOK = re.compile(r"[a-z0-9]+")


def _signature(action: str, category: str) -> str:
    """A general action-TYPE signature: harm category + salient content tokens."""
    toks = sorted(t for t in _TOK.findall((action or "").lower()) if len(t) >= 4 and t not in _STOP)
    return category + "|" + " ".join(toks)


class AnnoyanceBudget:
    # REVERTED: a per-day MESSAGE CAP is the wrong anti-spam mechanism — Omar banned it explicitly.
    # Capping the mouth admits the brain is dumb; the real fix is the brain only ever speaking when
    # it genuinely should (the model-driven inference). This stays only as a blunt flood backstop
    # (the cold-boot guard is separate), NOT as the anti-spam strategy.
    def __init__(self, max_per_day: int = 5, window_s: float = 86400.0) -> None:
        self.max_per_day = max_per_day          # DECISIONS-ONLY-OMAR
        self.window_s = window_s
        self._interruptions: List[float] = []   # timestamps of proactive asks sent
        self._declined: Set[str] = set()        # action-type signatures the user has declined

    def count(self, now: float) -> int:
        return sum(1 for t in self._interruptions if now - t < self.window_s)

    def suppressed(self, action: str, category: str, now: float) -> Optional[str]:
        """Reason to suppress a PROACTIVE interruption, or None to allow it through."""
        if _signature(action, category) in self._declined:
            return "declined-type (user said no before)"
        if self.count(now) >= self.max_per_day:
            return f"over interruption budget ({self.max_per_day}/day)"
        return None

    def record_interruption(self, now: float) -> None:
        self._interruptions.append(now)

    def record_decline(self, action: str, category: str) -> None:
        self._declined.add(_signature(action, category))

    def declined_count(self) -> int:
        return len(self._declined)


class InterruptGuard:
    """A blunt HARD ceiling on PROACTIVE outbound interrupts, ON TOP OF the AnnoyanceBudget's
    soft per-type learning. A cold boot against a backlog of N due loops must NEVER become N
    texts (it once fired 6 in ~36s): cap per BOOT and per ROLLING WINDOW, failing toward
    SILENCE over the cap. It only ever makes a proactive interrupt MORE conservative
    (suppress) — it never acts, never escalates, and NEVER pre-empts a money/terminal block.
    User-initiated interrupts are never capped (the user is present and asked).
    """

    def __init__(self, max_boot: Optional[int] = None, max_window: Optional[int] = None,
                 window_s: Optional[float] = None) -> None:
        self.max_boot = _int_env("ANTICIPY_PROACTIVE_MAX_BOOT", 20) if max_boot is None else max_boot
        self.max_window = _int_env("ANTICIPY_PROACTIVE_MAX_WINDOW", 10) if max_window is None else max_window
        self.window_s = _float_env("ANTICIPY_PROACTIVE_WINDOW_S", 3600.0) if window_s is None else window_s
        self.boot_count = 0
        self._sent: List[float] = []   # timestamps of proactive interrupts actually sent

    def _window(self, now: float) -> int:
        self._sent = [t for t in self._sent if now - t < self.window_s]
        return len(self._sent)

    def blocked(self, now: float) -> Optional[str]:
        """Reason to suppress an over-cap proactive interrupt, or None to allow it through."""
        if self.boot_count >= self.max_boot:
            return f"interrupt cap reached ({self.max_boot}/boot)"
        if self._window(now) >= self.max_window:
            return f"interrupt cap reached ({self.max_window}/{self.window_s / 60:.0f}min)"
        return None

    def record(self, now: float) -> None:
        self.boot_count += 1
        self._sent.append(now)
