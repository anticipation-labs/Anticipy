"""MH-P9: the per-decision observability trace.

When a real user complains "it sent the wrong thing", support must
reconstruct EXACTLY what happened from stored data alone, without
re-running anything and without the live objects. One structured,
append-only trace per decision records every stage:

  heard      raw transcript span, ts, speaker label
  attributed wearer vs other, anchor match score
  gate       the frozen instruction decision (ACT/ASK/IGNORE/...)
  resolved   each load-bearing ref, its value, its confidence,
             and where it came from (world / memory draw / slot)
  timing     now / deferred / scheduled / hold
  reconcile  completion / cancel / conflict outcome
  comms      channel, recipient, the exact body sent
  outcome    final outcome + the one-line WHY

The trace is the single source of truth for a complaint. The gate
proves a synthetic WRONG action is fully reconstructable from the
persisted trace ALONE (the live state is discarded first). Nothing
frozen is touched.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

STAGES = ("heard", "attributed", "gate", "resolved", "timing",
          "reconcile", "comms", "outcome")


@dataclass
class DecisionTrace:
    user_id: str
    decision_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: float = field(default_factory=time.time)
    stages: dict = field(default_factory=dict)        # stage -> payload

    def record(self, stage: str, **payload) -> "DecisionTrace":
        if stage not in STAGES:
            raise ValueError(f"unknown trace stage {stage!r}")
        self.stages[stage] = {"ts": time.time(), **payload}
        return self

    def to_json(self) -> str:
        return json.dumps({
            "user_id": self.user_id,
            "decision_id": self.decision_id,
            "created_at": self.created_at,
            "stages": self.stages,
        }, sort_keys=True, default=str)

    @staticmethod
    def from_json(s: str) -> "DecisionTrace":
        d = json.loads(s)
        t = DecisionTrace(user_id=d["user_id"],
                          decision_id=d["decision_id"],
                          created_at=d["created_at"])
        t.stages = d["stages"]
        return t

    def is_complete(self) -> bool:
        """Every stage of a decision that REACHED comms must be
        present. A decision that stopped early (e.g. LIFE_LOG) is
        complete at its terminal stage.
        """
        if "outcome" not in self.stages:
            return False
        terminal = self.stages["outcome"].get("outcome")
        need = ["heard", "attributed", "gate", "outcome"]
        if terminal in ("ACTED", "DEFERRED", "CONFIRMED"):
            need += ["resolved", "timing"]
        if terminal in ("ACTED", "DEFERRED"):
            need += ["comms"]
        return all(s in self.stages for s in need)

    def reconstruct(self) -> str:
        """The human answer to 'why did it do that?', built ONLY
        from this stored trace. Names the decisive step.
        """
        s = self.stages
        out: list[str] = [f"decision {self.decision_id} for "
                          f"{self.user_id}:"]
        if "heard" in s:
            out.append(f"  heard {s['heard'].get('text')!r} from "
                       f"{s['heard'].get('speaker')}")
        if "attributed" in s:
            out.append(f"  attributed -> {s['attributed'].get('label')} "
                       f"(anchor {s['attributed'].get('anchor_score')})")
        if "gate" in s:
            out.append(f"  frozen gate -> {s['gate'].get('decision')}")
        if "resolved" in s:
            for r in s["resolved"].get("refs", []):
                out.append(f"  ref {r.get('surface')!r} -> "
                           f"{r.get('value')!r} conf={r.get('conf')} "
                           f"src={r.get('source')}")
        if "timing" in s:
            out.append(f"  timing -> {s['timing'].get('when')}")
        if "reconcile" in s:
            out.append(f"  reconcile -> {s['reconcile'].get('result')}")
        if "comms" in s:
            c = s["comms"]
            out.append(f"  SENT via {c.get('channel')} to "
                       f"{c.get('to')!r}: {c.get('body')!r}")
        if "outcome" in s:
            out.append(f"  outcome {s['outcome'].get('outcome')} "
                       f"because: {s['outcome'].get('why')}")
        return "\n".join(out)

    def root_cause(self) -> Optional[str]:
        """The single decisive step that produced the outcome, for a
        complaint. Derived only from the trace.
        """
        s = self.stages
        if "resolved" in s:
            for r in s["resolved"].get("refs", []):
                if r.get("source") and r.get("conf") is not None \
                        and float(r.get("conf")) < 0.70:
                    return (f"low-confidence ref {r.get('surface')!r} "
                            f"resolved to {r.get('value')!r} at "
                            f"conf={r.get('conf')} (source "
                            f"{r.get('source')}) yet the action "
                            f"proceeded")
        if s.get("gate", {}).get("decision") == "ACT" and \
                s.get("outcome", {}).get("outcome") == "ACTED":
            return ("frozen gate said ACT and every ref cleared; the "
                    "wrong content originates upstream of resolution")
        return s.get("outcome", {}).get("why")


@dataclass
class TraceStore:
    """Per-user queryable trace store (append-only). Production is a
    table; here it is an exact in-process + JSON round-trip so the
    gate proves reconstruction from PERSISTED bytes, not live state.
    """
    _rows: dict = field(default_factory=dict)        # decision_id -> json

    def put(self, t: DecisionTrace) -> None:
        self._rows[t.decision_id] = t.to_json()

    def for_user(self, user_id: str) -> list:
        return [DecisionTrace.from_json(j) for j in self._rows.values()
                if json.loads(j)["user_id"] == user_id]

    def get(self, decision_id: str) -> Optional[DecisionTrace]:
        j = self._rows.get(decision_id)
        return DecisionTrace.from_json(j) if j else None
