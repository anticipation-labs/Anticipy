"""The model gateway — one swappable entry point, cost-disciplined.

`think(task, tier, caller)` routes through OUR endpoint (swappable model behind
it), logs the cost of every call, and ENFORCES that the smart tier is only
invoked from the two allowed places: the proactive gate's decision and the
orchestrator's plan. Everything else must be cheap or pure code.

Default is a deterministic stub model so tests are reproducible and free; the
real endpoint wires in behind the same interface.
"""
from __future__ import annotations

import json
from typing import List, Optional

CHEAP = "cheap"
SMART = "smart"
COST = {CHEAP: 0.0005, SMART: 0.02}


class ModelGateway:
    SMART_CALLERS = frozenset({"gate", "plan"})

    def __init__(self, endpoint: Optional[str] = None, stub=None, timeout: float = 30.0) -> None:
        self.endpoint = endpoint
        self.timeout = timeout
        self.calls: List[dict] = []  # cost log
        self._stub = stub or default_stub

    async def think(self, task: str, tier: str, caller: str) -> str:
        if tier == SMART and caller not in self.SMART_CALLERS:
            raise PermissionError(f"smart tier not allowed from caller '{caller}'")
        self.calls.append({"tier": tier, "caller": caller, "cost": COST.get(tier, 0.0)})
        if self.endpoint:
            import httpx
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(self.endpoint, json={"tier": tier, "task": task})
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"]
        return self._stub(task, tier, caller)

    @property
    def smart_calls(self) -> List[dict]:
        return [c for c in self.calls if c["tier"] == SMART]

    def total_cost(self) -> float:
        return round(sum(c["cost"] for c in self.calls), 6)


# ---------------------------------------------------------------------------
# Deterministic stub "model". Reproducible, free, and good enough to drive the
# brain end to end. The real model lives behind the same interface.
# ---------------------------------------------------------------------------
def default_stub(task: str, tier: str, caller: str) -> str:
    t = task.lower()
    if caller == "gate":
        risky = any(k in t for k in ("wire money", "delete", "pay ", "transfer"))
        actionable = any(k in t for k in ("send", "book", "schedule", "email", "remind", "call", "set up"))
        if risky:
            decision = "ask_first"
        elif actionable:
            decision = "do_and_notify"
        else:
            decision = "ignore"
        return json.dumps({"decision": decision, "reason": f"stub gate read of: {task[:80]}"})

    if caller == "plan":
        steps = []
        if any(k in t for k in ("email", "send", "deck", "draft")):
            steps.append({"intent": "send_email",
                          "args": {"to": "Sarah", "subject": "Q3 deck", "body": "Attached."},
                          "risk": "needs_confirm"})
        if any(k in t for k in ("lunch", "book", "calendar", "meet", "schedule")):
            steps.append({"intent": "create_event",
                          "args": {"title": "Lunch with Sarah", "when": "Friday 12:00"},
                          "risk": "low"})
        if any(k in t for k in ("remind", "friday", "follow", "later")):
            steps.append({"intent": "write_memory",
                          "args": {"kind": "open_loop", "text": "Send Sarah the Q3 deck Friday"},
                          "risk": "low"})
        if not steps:
            steps.append({"intent": "browse_task", "args": {"task": task}, "risk": "low"})
        return json.dumps({"steps": steps})

    # cheap / everything else: deterministic, trivial
    return f"[stub:{tier}:{caller}] {task[:120]}"
