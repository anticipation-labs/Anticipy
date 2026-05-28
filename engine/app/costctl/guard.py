"""MH-P8: cost + rate control at scale.

Per-user spend ceiling, loop/runaway protection, throttle, and a
hard kill on a cost spike. The defining safety property: a runaway
is stopped BEFORE it can exceed the ceiling (pre-authorization, not
post-mortem), while normal load is completely unaffected.

  PRE-AUTH CEILING  charge() is called BEFORE the spend. If this
    charge would push cumulative spend over the ceiling, it is
    refused and the run is killed; cumulative spend therefore never
    exceeds the ceiling.
  LOOP BREAKER      the same operation signature repeating more than
    LOOP_N times inside LOOP_WINDOW_S is a runaway -> hard kill.
  THROTTLE          more than RATE_MAX calls inside RATE_WINDOW_S is
    backpressure (the call is denied THIS tick, not killed) so a
    busy-but-legitimate user is slowed, not terminated.
  SPIKE KILL        spend velocity over SPIKE_USD_PER_S is an
    immediate hard kill.

Deterministic; a virtual clock is injectable so the gate is exact.
Nothing frozen is touched.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Optional


class HardKill(RuntimeError):
    """The run was terminated by the cost/rate guard."""

    def __init__(self, reason: str, spend: float):
        super().__init__(reason)
        self.reason = reason
        self.spend = spend


class Throttled(RuntimeError):
    """This call is denied this tick (backpressure), not a kill."""


@dataclass
class CostGuard:
    user_id: str
    ceiling_usd: float = 1.00
    loop_n: int = 25
    loop_window_s: float = 5.0
    rate_max: int = 30
    rate_window_s: float = 10.0
    spike_usd_per_s: float = 0.50
    clock: Callable[[], float] = None            # injectable virtual clock

    spend: float = 0.0
    killed: bool = False
    kill_reason: Optional[str] = None
    _calls: deque = field(default_factory=deque)        # (ts) for rate
    _ops: deque = field(default_factory=deque)          # (ts, sig) for loop
    _spend_pts: deque = field(default_factory=deque)    # (ts, spend)

    def _now(self) -> float:
        import time

        return self.clock() if self.clock else time.time()

    def authorize(self, op_sig: str, est_cost: float) -> None:
        """Call BEFORE doing the work. Raises HardKill if the run must
        stop, Throttled if this call is backpressured. If it returns,
        the work + charge are pre-authorized.
        """
        if self.killed:
            raise HardKill(self.kill_reason or "already killed",
                           self.spend)
        now = self._now()

        # --- pre-authorization ceiling: never EXCEED it ---
        if self.spend + est_cost > self.ceiling_usd:
            self.killed = True
            self.kill_reason = (
                f"ceiling: spend {self.spend:.4f}+{est_cost:.4f} would "
                f"exceed {self.ceiling_usd:.2f}")
            raise HardKill(self.kill_reason, self.spend)

        # --- loop / runaway breaker ---
        self._ops.append((now, op_sig))
        while self._ops and now - self._ops[0][0] > self.loop_window_s:
            self._ops.popleft()
        same = sum(1 for _t, s in self._ops if s == op_sig)
        if same > self.loop_n:
            self.killed = True
            self.kill_reason = (f"loop breaker: op {op_sig!r} x{same} "
                                f"in {self.loop_window_s}s")
            raise HardKill(self.kill_reason, self.spend)

        # --- spike kill (spend velocity) ---
        self._spend_pts.append((now, self.spend))
        while self._spend_pts and now - self._spend_pts[0][0] > 1.0:
            self._spend_pts.popleft()
        if len(self._spend_pts) >= 2:
            dt = now - self._spend_pts[0][0]
            dv = (self.spend + est_cost) - self._spend_pts[0][1]
            if dt > 0 and (dv / dt) > self.spike_usd_per_s:
                self.killed = True
                self.kill_reason = (f"spike: {dv / dt:.3f} usd/s > "
                                    f"{self.spike_usd_per_s}")
                raise HardKill(self.kill_reason, self.spend)

        # --- throttle (backpressure, NOT a kill) ---
        self._calls.append(now)
        while self._calls and now - self._calls[0] > self.rate_window_s:
            self._calls.popleft()
        if len(self._calls) > self.rate_max:
            self._calls.pop()                    # this call did not pass
            raise Throttled(
                f"rate {len(self._calls)}>{self.rate_max} per "
                f"{self.rate_window_s}s")

    def charge(self, actual_cost: float) -> None:
        """Record the actual spend AFTER a pre-authorized call."""
        self.spend += float(actual_cost)
