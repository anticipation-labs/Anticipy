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

    # the post_to_x trigger is the WORD post — hyphen compounds and prefixes are
    # not social posts (a junk post step parks an otherwise-complete goal)
    gw2 = ModelGateway()
    plan2 = json.loads(await gw2.think(
        "Plan: remind me to ice my knee tomorrow, post-run.", tier=SMART, caller="plan"))
    assert [s["intent"] for s in plan2["steps"]] == ["write_memory"], plan2
    plan3 = json.loads(await gw2.think(
        "Plan: post the team update tonight.", tier=SMART, caller="plan"))
    assert "post_to_x" in [s["intent"] for s in plan3["steps"]], plan3

    # F28: a SELF-reminder line plans EXACTLY the open-loop hold, and the loop text is
    # the GOAL line itself (remind_ts grounds from the spoken time; Room 3 re-gates the
    # embedded action at fire time) — never the whole plan prompt, never a send-now step
    plan4 = json.loads(await gw2.think(
        "Plan the goal into ordered steps. ...\nGOAL: Remind me Wednesday at 7pm to send "
        "the revised Ramos site plan before the Thursday deadline.\n\nCAPTURE_CONTEXT:\ntimezone=UTC",
        tier=SMART, caller="plan"))
    assert [s["intent"] for s in plan4["steps"]] == ["write_memory"], plan4
    loop_text = plan4["steps"][0]["args"]["text"]
    assert loop_text.startswith("Remind me Wednesday at 7pm"), loop_text
    assert "Plan the goal" not in loop_text and "CAPTURE_CONTEXT" not in loop_text, loop_text

    # F28: a draft-framed request plans the DRAFT (never sends); undrafted email/send
    # requests keep the gated send step
    plan5 = json.loads(await gw2.think(
        "Plan: Draft the order email to Vicky so it's ready to send.", tier=SMART, caller="plan"))
    intents5 = [s["intent"] for s in plan5["steps"]]
    assert "send_email_draft" in intents5 and "send_email" not in intents5, plan5
    plan6 = json.loads(await gw2.think(
        "Plan: send Sarah the Q3 deck.", tier=SMART, caller="plan"))
    steps6 = {s["intent"]: s for s in plan6["steps"]}
    assert "send_email" in steps6 and steps6["send_email"]["risk"] == "needs_confirm", plan6

    # F27/F30: grounded calendar shapes plan EXACTLY one create_event whose args come
    # from the SPOKEN line — the canned placeholder args never ride a grounded shape,
    # and a bare keyword ("on site") never plants a junk browse step on a block line
    plan7 = json.loads(await gw2.think(
        "Plan the goal into ordered steps. ...\nGOAL: The office has Thursday 10am or "
        "Monday 2 open for Leo's checkup. Book the Thursday 10am one.", tier=SMART, caller="plan"))
    assert [s["intent"] for s in plan7["steps"]] == ["create_event"], plan7
    assert plan7["steps"][0]["args"]["when"] == "Thursday 10am", plan7
    assert "checkup" in plan7["steps"][0]["args"]["title"], plan7
    assert "Sarah" not in json.dumps(plan7), plan7
    plan8 = json.loads(await gw2.think(
        "Plan the goal into ordered steps. ...\nGOAL: Crew confirmed for the Pico job - "
        "block Tuesday 2 to 3 for the inspection walkthrough so I'm on site for it.",
        tier=SMART, caller="plan"))
    assert [s["intent"] for s in plan8["steps"]] == ["create_event"], plan8
    assert plan8["steps"][0]["args"]["when"] == "Tuesday 2 to 3", plan8
    assert plan8["steps"][0]["args"]["title"] == "inspection walkthrough", plan8
    plan9 = json.loads(await gw2.think(
        "Plan: Remind me tomorrow at 8am to block 9 to 10 for the gym.", tier=SMART, caller="plan"))
    assert [s["intent"] for s in plan9["steps"]] == ["write_memory"], plan9  # the reminder hold still wins
    plan10 = json.loads(await gw2.think(
        "Plan the goal into ordered steps. ...\nGOAL: The vendor call moved from Thursday "
        "to Friday at 9, block that so I stop double-booking.", tier=SMART, caller="plan"))
    assert [s["intent"] for s in plan10["steps"]] == ["create_event"], plan10
    assert plan10["steps"][0]["args"]["when"] == "Friday at 9", plan10
    assert plan10["steps"][0]["args"]["title"] == "vendor call", plan10
    plan11 = json.loads(await gw2.think(
        "Plan the goal into ordered steps. ...\nGOAL: Ari moved my Tuesday shift to noon, "
        "can you block the morning for the clinic ride.", tier=SMART, caller="plan"))
    assert [s["intent"] for s in plan11["steps"]] == ["create_event"], plan11
    assert plan11["steps"][0]["args"]["when"] == "Tuesday morning", plan11
    assert plan11["steps"][0]["args"]["title"] == "clinic ride", plan11
    forget_goal = "Renew the patio permit tomorrow morning before I forget again."
    plan12 = json.loads(await gw2.think(
        "Plan the goal into ordered steps. ...\nGOAL: " + forget_goal,
        tier=SMART, caller="plan"))
    assert [s["intent"] for s in plan12["steps"]] == ["write_memory"], plan12
    assert plan12["steps"][0]["args"] == {"kind": "open_loop", "text": forget_goal}, plan12

    print("PASS piece 3: model gateway")
    print("  plan intents:", intents)
    print("  smart calls:", len(gw.smart_calls), "| total cost:", gw.total_cost())


if __name__ == "__main__":
    asyncio.run(main())
