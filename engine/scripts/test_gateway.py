"""Piece 3 test: model gateway — cost-logged, smart locked to gate/plan, stub deterministic.

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_gateway.py
"""
import asyncio
import json

from anticipy_engine.core.gateway import CHEAP, SMART, ModelGateway


async def main() -> None:
    gw = ModelGateway()

    # cheap is allowed from anywhere and logged
    out = await gw.think("summarize this", tier=CHEAP, caller="triage")
    assert out.startswith("[stub:cheap")

    # smart from an allowed caller -> plan returns structured steps
    plan_raw = await gw.think(
        "Plan: I'll send Sarah the Q3 deck on Friday and book us lunch.",
        tier=SMART, caller="plan",
    )
    plan = json.loads(plan_raw)
    intents = [s["intent"] for s in plan["steps"]]
    assert intents == ["send_email", "create_event", "write_memory"], intents

    # smart gate -> a decision
    gate_raw = await gw.think("Gate: I'll send Sarah the deck and book lunch.", tier=SMART, caller="gate")
    assert json.loads(gate_raw)["decision"] == "do_and_notify"

    # smart from a disallowed caller is refused
    refused = False
    try:
        await gw.think("sneaky", tier=SMART, caller="some_worker")
    except PermissionError:
        refused = True
    assert refused, "smart tier must be refused outside gate/plan"

    # cost log: exactly two smart calls so far (plan + gate)
    assert len(gw.smart_calls) == 2
    assert gw.total_cost() > 0

    print("PASS piece 3: model gateway")
    print("  plan intents:", intents)
    print("  smart calls:", len(gw.smart_calls), "| total cost:", gw.total_cost())


if __name__ == "__main__":
    asyncio.run(main())
