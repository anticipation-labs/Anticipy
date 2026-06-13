"""Messy owner transcript -> memory-aware proactive execution.

This pins the public-product behavior Omar cares about in a small story:
normal speech can include vents, vague references, prior browsing context,
human-impacting commitments, and money. The handoff must still produce honest
cards:
  - safe reminder/event work executes with receipts
  - human-impacting sends wait for approval
  - vague browser work executes only when memory resolves the item/site
  - vague browser work without memory asks instead of faking success
  - money stays blocked with no approval path
"""
import asyncio
import json
import os
import tempfile
from pathlib import Path

os.environ.setdefault("ANTICIPY_MODEL_PROVIDER", "stub")
os.environ.setdefault("ANTICIPY_HANDS_MODE", "mock")
os.environ.setdefault("ANTICIPY_NATIVE_BRIDGE_FALLBACK", "0")
os.environ.setdefault("ANTICIPY_TICK_SECONDS", "0")
os.environ.setdefault("ANTICIPY_INBOUND_POLL_SECONDS", "0")

from anticipy_engine.core.control_core import ControlCore  # noqa: E402


MESSY_DAY = """
[08:01] Omar: yeah yeah whatever, this week is cooked.
[08:04] Maya: school moved pickup to 3 today, please remind me before I forget.
[08:05] Omar: oh sure, I will just clone myself, that will fix the schedule.
[09:12] Sam needs the revised deck before Friday; I told him I would send it.
[10:17] I was comparing compact label makers at Staples; liked the Brother cube one.
[10:22] That label thing I liked at Staples, cart it so I can check shipping later, no buying.
[11:33] That random gadget thing, put it in the cart if it looks right, don't buy it.
[12:10] order the replacement filter today and just pay whatever it costs.
[12:20] pay the overdue thing now with card.
[13:00] My wife Maya prefers texts after lunch.
"""


def _record(data_dir: Path, card_id: str) -> dict:
    return json.loads((data_dir / "owner_cards" / f"{card_id}.json").read_text(encoding="utf-8"))


def _by_source(cards: list[dict], needle: str) -> dict:
    matches = [card for card in cards if needle.lower() in card["source_text"].lower()]
    assert len(matches) == 1, (needle, matches, cards)
    return matches[0]


async def main():
    data_dir = Path(tempfile.mkdtemp(prefix="anticipy-messy-handoff-"))
    core = ControlCore(data_dir=data_dir)
    await core.start()
    try:
        out = await core.owner_ingest(
            "typed",
            MESSY_DAY,
            {"test": "messy_proactive_handoff"},
            execute_actions=True,
        )
        pending = core.pending_asks()
    finally:
        await core.stop()

    cards = out["cards"]
    assert out["ignored_line_count"] >= 3, out

    pickup = _by_source(cards, "pickup to 3")
    assert pickup["status"] == "done", pickup
    pickup_record = _record(data_dir, pickup["id"])
    assert pickup_record["state"] == "done" and pickup_record["proof"], pickup_record

    send = _by_source(cards, "Sam needs")
    assert send["status"] == "waiting" and send["execution"]["ask_id"], send
    assert any(item["ask_id"] == send["execution"]["ask_id"] for item in pending), pending

    resolved_cart = _by_source(cards, "label thing")
    assert resolved_cart["status"] == "done", resolved_cart
    resolved_record = _record(data_dir, resolved_cart["id"])
    assert resolved_record["state"] == "done", resolved_record
    step = resolved_record["steps"][0]
    assert step["intent"] == "browse_task", resolved_record
    assert step["args"]["url"] == "https://www.staples.com", step
    resolution = step["args"]["memory_resolution"]
    assert "Brother cube" in resolution["item"], resolution
    assert any(p.get("type") == "memory_resolution" for p in resolved_cart["proof"]), resolved_cart

    unresolved_cart = _by_source(cards, "random gadget")
    assert unresolved_cart["status"] == "waiting", unresolved_cart
    assert unresolved_cart["execution"]["decision"] == "ask", unresolved_cart
    unresolved_record = _record(data_dir, unresolved_cart["id"])
    assert unresolved_record["state"] == "waiting", unresolved_record
    assert not unresolved_record["steps"] and not unresolved_record["proof"], unresolved_record

    money = _by_source(cards, "pay whatever")
    assert money["status"] == "blocked", money
    assert money["execution"]["goal_id"] is None and money["execution"]["ask_id"] is None, money
    money_record = _record(data_dir, money["id"])
    assert money_record["state"] == "blocked", money_record
    assert not money_record["steps"] and not money_record["proof"], money_record

    direct_money = _by_source(cards, "overdue thing")
    assert direct_money["status"] == "blocked", direct_money
    assert direct_money["execution"]["goal_id"] is None and direct_money["execution"]["ask_id"] is None, direct_money
    direct_money_record = _record(data_dir, direct_money["id"])
    assert direct_money_record["state"] == "blocked", direct_money_record
    assert not direct_money_record["steps"] and not direct_money_record["proof"], direct_money_record

    profile = _by_source(cards, "prefers texts")
    assert profile["status"] == "done", profile

    print("PASS messy_proactive_handoff: messy transcript -> memory-aware cards, safe asks, money wall")


if __name__ == "__main__":
    asyncio.run(main())
