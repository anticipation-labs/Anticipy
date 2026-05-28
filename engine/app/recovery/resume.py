"""MH-P6: failure recovery in the real world.

A real in-flight action gets interrupted: the browser hangs, the
site changed under us, the network drops mid-step, the power dies
at 60%. The binding invariant for every one of those:

  an interrupted action EITHER completes on resume (idempotent,
  from its durable checkpoint, exactly once) OR fails safe and
  SURFACES for the wearer; it is NEVER left silently half-applied
  and NEVER double-applied.

Mechanism: a per-action journal of idempotent ops. Each op has a
stable op_id; an applied op is recorded so a resume never re-applies
it (no double). A precondition guard captures the world fact each
op depended on; if on resume that fact CHANGED (site changed), the
action does not blindly continue, it fails safe and surfaces. A
crash (power loss) just means the journal is reloaded and the
action resumes from the last applied op. Nothing frozen is touched.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Callable, Optional


class Interrupt(Exception):
    """Injected real-world interruption."""

    def __init__(self, kind: str):
        super().__init__(kind)
        self.kind = kind          # hang | network | power | site_changed


@dataclass
class Op:
    op_id: str
    apply: Callable[[], None]
    precond: Optional[Callable[[], str]] = None   # captured world fact


@dataclass
class ActionJournal:
    action_id: str
    applied: dict = field(default_factory=dict)    # op_id -> precond snap
    status: str = "in_flight"                      # in_flight|completed|
    #                                                surfaced_failsafe
    surfaced: Optional[str] = None

    def dumps(self) -> str:
        return json.dumps(self.__dict__, default=str)


class Recover:
    """Runs an action's ops with checkpointing; survives an injected
    interruption; resumes idempotently or fails safe + surfaces.
    """

    def __init__(self) -> None:
        self._jrnl: dict[str, ActionJournal] = {}

    def _j(self, action_id: str) -> ActionJournal:
        return self._jrnl.setdefault(action_id,
                                     ActionJournal(action_id=action_id))

    def run(self, action_id: str, ops: list,
            fault: Optional[tuple] = None,
            surface: Optional[Callable[[str], None]] = None
            ) -> ActionJournal:
        """Execute ops. `fault`=(op_index, Interrupt) injects a
        real-world interruption right before that op is applied.
        Re-call with fault=None to simulate the resume after the
        process came back. Returns the journal.
        """
        j = self._j(action_id)
        if j.status in ("completed", "surfaced_failsafe"):
            return j                                # idempotent: terminal

        for i, op in enumerate(ops):
            if op.op_id in j.applied:
                # already applied (resume): site-changed guard.
                if op.precond is not None:
                    if op.precond() != j.applied[op.op_id]:
                        j.status = "surfaced_failsafe"
                        j.surfaced = (f"{action_id}: precondition for "
                                      f"{op.op_id} changed since it was "
                                      f"applied; not continuing blindly")
                        if surface:
                            surface(j.surfaced)
                        return j
                continue                            # no double-apply

            if fault and fault[0] == i:
                itr: Interrupt = fault[1]
                if itr.kind == "site_changed":
                    # the page we were about to act on changed: do NOT
                    # apply, fail safe and surface.
                    j.status = "surfaced_failsafe"
                    j.surfaced = (f"{action_id}: site changed before "
                                  f"{op.op_id}; failed safe, surfaced")
                    if surface:
                        surface(j.surfaced)
                    return j
                # hang / network / power: the process is interrupted
                # BEFORE this op is applied. Journal holds; caller
                # will resume. Nothing half-applied.
                raise itr

            snap = op.precond() if op.precond else ""
            op.apply()                              # the real side effect
            j.applied[op.op_id] = snap              # checkpoint AFTER

        j.status = "completed"
        return j

    def resume(self, action_id: str, ops: list,
               surface: Optional[Callable[[str], None]] = None
               ) -> ActionJournal:
        """Resume after an interruption. Reloads the journal (a real
        restart would deserialize it) and continues from the last
        applied op, idempotently.
        """
        return self.run(action_id, ops, fault=None, surface=surface)
