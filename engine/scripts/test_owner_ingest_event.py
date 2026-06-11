"""Owner-lane honesty seam + card execution test (TARGET STAGE B items 1+2).

With ANTICIPY_OWNER_INGEST=1 the same POST /event pipe the persona runner drives
routes through the owner card path and answers in the proactive shape
({decision, goal_id, ask_id}), so the UNCHANGED factory runner+scorer measure
owner cards with worst-persona honesty. Since STAGE B item 2 the cards EXECUTE,
and the decision reported is what the engine actually DID. This pins:
  - a do card executes through the proven proactive spine (orchestrator + mock
    hands) and the durable card record mirrors the REAL goal state with proof
    (artifact id) — done only when the goal finished with proof
  - a do card the spine refuses reports "ignore" (never a paper "act") and stays
    a durable open record
  - an ask card becomes a REAL pending ask: it appears in /pending, YES resumes
    the exact paused goal to done and writes state+proof back onto the record,
    NO marks the record declined
  - a money/blocked card NEVER executes: state "blocked", never in /pending,
    no goal — even with execution on (the harm-line is final)
  - a remember card carries drawer read-back proof of its memory write
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
os.environ.setdefault("ANTICIPY_NATIVE_BRIDGE_FALLBACK", "0")
os.environ.pop("ANTICIPY_OWNER_INGEST", None)

from anticipy_engine.core.control_core import ControlCore  # noqa: E402

NOISE = "oh sure, I'll just clone myself, that'll fix the schedule."
PICKUP = "school moved pickup to 3 today, please remind me before I forget."
SEND_SAM = "Sam needs the revised decking before Friday; I told him I'd send it."
CART_NO_BUY = "that water-table thing for the birthday, put it in the cart if you find it, don't buy it."
MONEY = "order the replacement filter today and just pay whatever it costs."
PROFILE = "My wife Maya prefers texts after lunch."
CLARIFY = "can you check with Priya about the vendor call?"


def _record(tmp: Path, card_id: str) -> dict:
    return json.loads((tmp / "owner_cards" / f"{card_id}.json").read_text(encoding="utf-8"))


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
        clarify = await core.feed("app", CLARIFY, {})
        # recursion guard: an execute_actions card feed stays on the proactive path
        guarded = await core.feed("app", PICKUP, {"owner_ingest_execute": True})
        pending = core.pending_asks()
        declined = await core.resolve(clarify["ask_id"], False)
        pending_after = core.pending_asks()
    finally:
        os.environ.pop("ANTICIPY_OWNER_INGEST", None)
        await core.stop()

    # the realday/scorer contract: decision + goal_id + ask_id on every response
    for out in (noise, act, ask, cart, money, remember, clarify):
        assert out.get("owner_lane") is True, out
        assert "decision" in out and "goal_id" in out and "ask_id" in out, out

    assert noise["decision"] not in ("act", "ask"), noise
    assert noise["goal_id"] is None, noise

    # do card, spine accepted: REAL execution — record mirrors the finished goal
    assert act["decision"] == "act", act
    rec = _record(tmp, act["goal_id"])
    for key in ("id", "intent", "steps", "state"):
        assert key in rec, rec
    assert rec["state"] == "done", "an executed do card must mirror its goal's state"
    assert rec["steps"], rec
    assert rec["proof"], "done without proof is the cardinal orchestrator sin"
    assert any((p or {}).get("id") for p in rec["proof"].values()), rec["proof"]
    assert "pickup" in rec["description"].lower(), rec
    card_proof = rec["owner_card"]["proof"]
    assert any(p["type"] == "memory_write" for p in card_proof), rec
    assert any(p["type"] == "memory_read_back" for p in card_proof), rec
    assert any(p["type"] == "engine_execution" for p in card_proof), rec
    assert any(p["type"] == "card_record" for p in card_proof), rec

    # do card the spine refuses: the truthful decision is ignore, never a paper act
    assert cart["decision"] == "ignore", cart
    assert cart["cards"][0]["args"].get("payment_allowed") is False, cart
    cart_rec = _record(tmp, cart["goal_id"])
    assert cart_rec["state"] == "open", "a card that never executed must never look done"
    assert not cart_rec["proof"], cart_rec

    # ask card: a REAL pending ask in /pending, resolvable by the existing flow
    assert ask["decision"] == "ask" and ask["ask_id"], ask
    assert ask["cards"][0]["args"].get("person") == "Sam", ask
    assert _record(tmp, ask["goal_id"])["state"] == "waiting", ask

    # money without an explicit no-buy is a blocked card -> surfaces as ask, NEVER executes
    assert money["decision"] == "ask" and money["ask_id"] is None, money
    assert money["cards"][0]["disposition"] == "blocked", money
    money_rec = _record(tmp, money["goal_id"])
    assert money_rec["state"] == "blocked", money_rec
    assert not money_rec["steps"] and not money_rec["proof"], money_rec
    assert not (tmp / "goals" / f"{money['goal_id']}.json").exists(), "blocked card grew a goal"

    # /pending carries exactly the ask cards — the blocked money card is NOT resolvable
    pending_ids = {p["ask_id"] for p in pending}
    assert ask["ask_id"] in pending_ids and clarify["ask_id"] in pending_ids, pending
    assert money["goal_id"] not in pending_ids and len(pending) == 2, pending

    # NO declines: record marked, ask gone from /pending
    assert declined["approved"] is False, declined
    assert _record(tmp, clarify["goal_id"])["state"] == "declined", declined
    assert all(p["ask_id"] != clarify["ask_id"] for p in pending_after), pending_after

    assert remember["decision"] == "remember", remember
    rem_rec = _record(tmp, remember["goal_id"])
    assert rem_rec["state"] == "done" and rem_rec["proof"].get("read_back"), rem_rec

    assert "owner_lane" not in guarded, guarded

    # cards landed in the real memory drawers too (one ledger, both doors)
    owner_loops = [i for i in core.memory.open_loops.all() if i.fields.get("owner_card_id")]
    assert len(owner_loops) >= 4, [i.text for i in owner_loops]


async def yes_roundtrip_check():
    """YES on an owner ask card resumes the EXACT paused goal through the existing
    resolve flow and writes the finished state + artifact proof back onto the record."""
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-ownerev-yes-"))
    core = ControlCore(data_dir=tmp)
    await core.start()
    os.environ["ANTICIPY_OWNER_INGEST"] = "1"
    try:
        ask = await core.feed("app", SEND_SAM, {})
        res = await core.resolve(ask["ask_id"], True)
    finally:
        os.environ.pop("ANTICIPY_OWNER_INGEST", None)
        await core.stop()
    assert res["approved"] is True and res["state"] == "done", res
    rec = _record(tmp, ask["goal_id"])
    assert rec["state"] == "done", rec
    assert rec["resolution"] == {"ask_id": ask["ask_id"], "approved": True}, rec
    assert any((p or {}).get("id") for p in rec["proof"].values()), rec["proof"]
    assert rec["owner_card"]["status"] == "done", rec


def main():
    asyncio.run(default_path_check())
    asyncio.run(owner_lane_check())
    asyncio.run(yes_roundtrip_check())
    print("PASS owner_ingest_event: owner cards EXECUTE (spine-gated, proof write-back, "
          "real /pending YES/NO, money never executes); default path untouched")


if __name__ == "__main__":
    main()
