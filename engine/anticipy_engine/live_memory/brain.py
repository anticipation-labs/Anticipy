"""LiveMemoryBrain — the memory agent behind the proactive engine.

It owns the hot write path (capture), hot read path (inject), cold cleanup
(maintain), cold inference (infer), and retrieval audit (self-check). The live
model enrichment seams are optional; the default deterministic path is real and
must keep working without model calls.
"""
from __future__ import annotations

from typing import Dict, List

from ..memory.store import Memory
from ..shared.schema import CaptureEvent, ContextPack, ContextPurpose
from .capture import Capturer
from .context_builder import ContextBuilder
from .infer import Inferrer
from .inject import Injector
from .maintain import Maintainer
from .selfcheck import SelfCheck


class LiveMemoryBrain:
    def __init__(self, memory: Memory, gateway=None, scorecard=None) -> None:
        self.memory = memory
        self.capturer = Capturer(memory, gateway=gateway)
        self.injector = Injector(memory, gateway=gateway)
        self.context_builder = ContextBuilder(self.injector)
        self.maintainer = Maintainer(memory, gateway=gateway)
        self.inferrer = Inferrer(memory, gateway=gateway)
        self.selfcheck = SelfCheck(memory, scorecard=scorecard, gateway=gateway)

    def build_context(self, about: str = "", purpose: ContextPurpose = "decide",
                      k=None, as_of=None) -> ContextPack:
        """The ONE context assembler every consumer calls (decider, hands, voice).
        Returns a typed ContextPack; see live_memory/context_builder.py. `as_of` filters
        by bi-temporal validity at a moment (M3) — expired ephemeral facts don't surface."""
        return self.context_builder.build(about, purpose=purpose, k=k, as_of=as_of)

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
        """REAL cold sweep: supersede changed facts, consolidate dup episodes, decay stale,
        expire the raw buffer (M4)."""
        return self.maintainer.sweep()

    def maintain_at(self, at) -> Dict[str, object]:
        """Cold sweep evaluated AS OF a moment (M4 raw-buffer expiry uses bi-temporal validity)."""
        return self.maintainer.sweep(at=at)

    def forget_all(self) -> Dict[str, object]:
        """RIGHT-TO-DELETE (M5), gated like the money hard-stop: wipe every trace of the user —
        all four drawers AND the inert remember-list. Returns {removed}."""
        return {"removed": self.memory.forget_everything()}
