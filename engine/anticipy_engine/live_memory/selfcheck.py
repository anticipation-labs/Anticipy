"""SELF-CHECK — the watcher at the memory -> brain seam.

After context is assembled, a cheap audit asks "relevant + complete for this
moment?" and logs a recall hit/miss to the Scorecard so retrieval quality is
MEASURED, not assumed. Deterministic in stub (zero model calls); a cheap model
can judge relevance in live mode. Two checks:
  - COMPLETE: every open/waiting loop the ledger holds is present in the injection
    (the spine must never be dropped).
  - RELEVANT/RECALL: when ground-truth expected items are known (eval), they must
    be surfaced; otherwise a heuristic (non-empty) stands in.
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional

from ..memory.store import Memory


class SelfCheck:
    def __init__(self, memory: Memory, scorecard=None, gateway=None, mode: Optional[str] = None) -> None:
        self.memory = memory
        self.scorecard = scorecard
        self.gateway = gateway
        self.mode = mode or os.environ.get("ANTICIPY_MEMORY_MODE", "stub")

    def audit(self, query: str, injected: Dict[str, object],
              expected_ids: Optional[List[str]] = None) -> Dict[str, object]:
        item_ids = {i.id for i in injected.get("items", [])}
        surfaced_loops = {i.id for i in injected.get("open_loops", [])}

        # COMPLETE: all open/waiting loops must be surfaced
        need_loops = [l.id for l in self.memory.open_loops.all() if l.status in ("open", "waiting")]
        complete = all(lid in surfaced_loops for lid in need_loops)

        # RELEVANT / RECALL
        if expected_ids is not None:
            relevant = all(eid in item_ids for eid in expected_ids)
            why = "" if relevant else "missing expected items"
        else:
            if self.mode == "live" and self.gateway:
                pass  # TODO(live): cheap model judges relevance; never in tests
            relevant = len(item_ids) > 0
            why = "" if relevant else "empty injection"

        hit = relevant and complete
        reason = why
        if not complete:
            reason = (reason + "; " if reason else "") + "open loops not all surfaced"

        if self.scorecard is not None:
            self.scorecard.record_recall(query, hit, len(item_ids), reason)
        return {"hit": hit, "relevant": relevant, "complete": complete,
                "reason": reason, "smart_calls": 0}
