"""Owner-lane honesty seam test (TARGET STAGE B item 1).

With ANTICIPY_OWNER_INGEST=1 the same POST /event pipe the persona runner drives
routes through the owner card path and answers in the proactive shape
({decision, goal_id, ask_id}), so the UNCHANGED factory runner+scorer measure
owner cards with worst-persona honesty. This pins:
  - decision mapping fails toward ask (ask/blocked > do > remember > silence)
  - each card persists a goal-shaped durable record (id/intent/steps/state) the
    run collector already harvests, state "open" — never fake-done
  - the default path is untouched when the env var is absent
  - the execute_actions recursion guard keeps card feeds on the proactive path
"""
import asyncio
import json
import os
import tempfile
from pathlib import Path

os.environ.setdefault("ANTICIPY_MODEL_PROVIDER", "stub")
os.environ.setdefault("ANTICIPY_HANDS_MODE", "mock")
os.environ.pop("ANTICIPY_OWNER_INGEST", None)

from anticipy_engine.core.control_core import ControlCore  # noqa: E402

NOISE = "oh sure, I'll just clone myself, that'll fix the schedule."
PICKUP = "school moved pickup to 3 today, please remind me before I forget."
SEND_SAM = "Sam needs the revised decking before Friday; I told him I'd send it."
CART_NO_BUY = "that water-table thing for the birthday, put it in the cart if you find it, don't buy it."
MONEY = "order the replacement filter today and just pay whatever it costs."
PROFILE = "My wife Maya prefers texts after lunch."


async def default_path_check():
    """Without the env var, /event is the proactive path — byte-for-byte behavior."""
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-ownerev-off-"))
    core = ControlCore(data_dir=tmp)
    await core.start()
    try:
        out = await core.feed("app", PICKUP, {})
    finally:
        await core.stop()
    assert "owner_lane" not in out, out
    assert "decision" in out and "goal_id" in out and "ask_id" in out, out
    assert not (tmp / "owner_cards").exists(), "default path must write no owner card records"


async def owner_lane_check():
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-ownerev-on-"))
    core = ControlCore(data_dir=tmp)
    await core.start()
    os.environ["ANTICIPY_OWNER_INGEST"] = "1"
    try:
        noise = await core.feed("app", NOISE, {})
        act = await core.feed("app", PICKUP, {})
        ask = await core.feed("app", SEND_SAM, {})
        cart = await core.feed("app", CART_NO_BUY, {})
        money = await core.feed("app", MONEY, {})
        remember = await core.feed("app", PROFILE, {})
        # recursion guard: an execute_actions card feed stays on the proactive path
        guarded = await core.feed("app", PICKUP, {"owner_ingest_execute": True})
    finally:
        os.environ.pop("ANTICIPY_OWNER_INGEST", None)
        await core.stop()

    # the realday/scorer contract: decision + goal_id + ask_id on every response
    for out in (noise, act, ask, cart, money, remember):
        assert out.get("owner_lane") is True, out
        assert "decision" in out and "goal_id" in out and "ask_id" in out, out

    assert noise["decision"] not in ("act", "ask"), noise
    assert noise["goal_id"] is None, noise

    assert act["decision"] == "act", act
    assert ask["decision"] == "ask", ask
    assert ask["cards"][0]["args"].get("person") == "Sam", ask

    assert cart["decision"] == "act", cart
    assert cart["cards"][0]["args"].get("payment_allowed") is False, cart
    # money without an explicit no-buy is a blocked card -> surfaces as ask, never act
    assert money["decision"] == "ask", money
    assert money["cards"][0]["disposition"] == "blocked", money

    assert remember["decision"] == "remember", remember

    assert "owner_lane" not in guarded, guarded

    # durable goal-shaped record, exactly what the run collector harvests
    rec_path = tmp / "owner_cards" / f"{act['goal_id']}.json"
    assert rec_path.exists(), rec_path
    rec = json.loads(rec_path.read_text(encoding="utf-8"))
    for key in ("id", "intent", "steps", "state"):
        assert key in rec, rec
    assert rec["state"] == "open", "a card that never executed must never look done"
    assert rec["id"] == act["goal_id"], rec
    assert "pickup" in rec["description"].lower(), rec
    assert any(p["type"] == "memory_write" for p in rec["owner_card"]["proof"]), rec
    assert any(p["type"] == "card_record" for p in rec["owner_card"]["proof"]), rec

    # cards landed in the real memory drawers too (one ledger, both doors)
    owner_loops = [i for i in core.memory.open_loops.all() if i.fields.get("owner_card_id")]
    assert len(owner_loops) >= 4, [i.text for i in owner_loops]


def main():
    asyncio.run(default_path_check())
    asyncio.run(owner_lane_check())
    print("PASS owner_ingest_event: ANTICIPY_OWNER_INGEST=1 routes /event through owner cards "
          "in the scorer's shape; default path untouched")


if __name__ == "__main__":
    main()
