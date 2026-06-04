"""LiveMemoryBrain — stubbed seam between memory and the proactive engine.

- inject(context):  later, select the memory that matters for `context`.
                    Scaffold: returns the shape, selects nothing.
- capture(event):   fold a capture event into memory (history). Minimal wiring.
- maintain():       later, dedupe/decay/summarize. Scaffold: no-op stub.
"""
from __future__ import annotations

from typing import Dict, List

from ..memory.store import Memory
from ..shared.schema import CaptureEvent
from .capture import Capturer
from .infer import Inferrer
from .inject import Injector
from .maintain import Maintainer
from .selfcheck import SelfCheck


class LiveMemoryBrain:
    def __init__(self, memory: Memory, gateway=None, scorecard=None) -> None:
        self.memory = memory
        self.capturer = Capturer(memory, gateway=gateway)
        self.injector = Injector(memory, gateway=gateway)
        self.maintainer = Maintainer(memory, gateway=gateway)
        self.inferrer = Inferrer(memory, gateway=gateway)
        self.selfcheck = SelfCheck(memory, scorecard=scorecard, gateway=gateway)

    def infer(self) -> Dict[str, object]:
        """Derive routines/recurring-people as DERIVED facts (never promoted)."""
        return self.inferrer.infer()

    def recall_check(self, query, injected, expected_ids=None) -> Dict[str, object]:
        """Audit an injection (relevant+complete) and log recall to the scorecard."""
        return self.selfcheck.audit(query, injected, expected_ids=expected_ids)

    def inject_checked(self, context: str = "", k=None) -> Dict[str, object]:
        """Inject AND self-check in one hop (the watcher at the seam)."""
        res = self.injector.inject(context, k=k)
        res["self_check"] = self.selfcheck.audit(context, res)
        return res

    def inject(self, context: str = "", k=None) -> Dict[str, object]:
        """REAL hybrid retrieval (semantic+keyword+recency+importance), budgeted,
        with ALL open/waiting loops always surfaced."""
        return self.injector.inject(context, k=k)

    def capture(self, event: CaptureEvent) -> Dict[str, object]:
        """REAL capture: keep/drop gate -> classify -> dedupe -> route to a drawer.
        Returns {kept, kind, item, reason, smart_calls}."""
        return self.capturer.capture(event.text, source=getattr(event, "source", ""))

    def maintain(self) -> Dict[str, object]:
        """REAL cold sweep: supersede changed facts, consolidate dup episodes, decay stale."""
        return self.maintainer.sweep()
