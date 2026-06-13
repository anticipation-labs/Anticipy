"""Inbound SMS poller test — the owner's replies close the loop (STAGE B item 3).

Fake-transport (injected fetch; zero network) pins:
  - the ask SMS now carries the short reply code, and an inbound "YES <code>" /
    "NO <code>" resolves exactly that pending ask THROUGH ControlCore.resolve
  - bare YES resolves only when exactly ONE ask is pending; ambiguity (two pending,
    or a code matching nothing) resolves NOTHING — never guess an approval
  - F20: an ambiguous owner reply draws EXACTLY ONE bounded clarification SMS per
    poll pass (listing the pending codes; "nothing pending" when there are none),
    to the owner only, budget-counted and budget-suppressed toward silence; it
    never resolves anything, and the exact-code path still works regardless
  - F18: an owner card record gets its resolution write-back even when the
    in-memory goal->record map is GONE (restart/desync) — the durable
    execution.goal_id linkage carries it
  - non-YES/NO inbound is owner speech -> the same /owner/ingest door (cards with
    source "sms")
  - safety: no OWNER_PHONE -> refuse everything; non-owner senders skipped (and
    never clarified); outbound-direction and pre-floor (stale) messages never act;
    a processed sid never replays — not in a later poll, not after a poller restart

Run:  PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_inbound.py
"""
import asyncio
import json
import os
import tempfile
import time
from pathlib import Path

os.environ.setdefault("ANTICIPY_MODEL_PROVIDER", "stub")
os.environ.setdefault("ANTICIPY_HANDS_MODE", "mock")
os.environ.setdefault("ANTICIPY_NATIVE_BRIDGE_FALLBACK", "0")
os.environ.pop("ANTICIPY_OWNER_INGEST", None)
os.environ.pop("ANTICIPY_CHANNELS_MODE", None)   # mock everywhere; no transports
OWNER = "+15550009999"
os.environ["OWNER_PHONE"] = OWNER

from anticipy_engine.channels.inbound import InboundPoller  # noqa: E402
from anticipy_engine.core.control_core import ControlCore  # noqa: E402
from anticipy_engine.core.envelopes import GoalState  # noqa: E402

WIRE = "Wire money to the contractor."
WIRE2 = "Remind me Friday to wire the deposit."
SEND_INVESTOR = "Email the investor the signed contract."
SEND_PRIYA = "Text Priya the revised deck before Friday."
# a direct send the spine asks on (F17 one brain: the spine, not the regex,
# decides every owner-lane ask — this line must keep drawing a REAL pending ask)
SEND_SAM = "okay just send Sam the revised decking file before Friday."
PICKUP = "school moved pickup to 3 today, please remind me before I forget."


def sms(sid, body, frm=OWNER, direction="inbound", date_sent=None):
    return {"sid": sid, "body": body, "from": frm, "to": "+15550000000",
            "direction": direction, "date_sent": date_sent}


async def code_roundtrip_check():
    """Two pending asks: ambiguity refuses, codes resolve, bare YES needs exactly one."""
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-inb-code-"))
    core = ControlCore(data_dir=tmp)
    await core.start()
    try:
        ask1 = await core.feed("app", SEND_INVESTOR, {})
        ask2 = await core.feed("app", SEND_PRIYA, {})
        assert ask1["decision"] == "ask" and ask2["decision"] == "ask"
        code1, code2 = ask1["ask_id"][:6], ask2["ask_id"][:6]

        # the ask SMS itself advertises the exact code inbound accepts
        last_msg = core.text_channel.sent[-1]["message"]
        assert f"YES {code2}" in last_msg and f"NO {code2}" in last_msg, last_msg

        inbox = []
        poller = InboundPoller(core, fetch=lambda: list(inbox))

        # bare YES with TWO pending -> ambiguous, nothing resolves — and the owner
        # is TOLD so (F20): exactly one bounded clarification listing both codes
        sends0 = len(core.text_channel.sent)
        b0 = core.proactive.budget.count(time.time())
        inbox.append(sms("SM1", "YES"))
        out = await poller.poll_once()
        assert not out["resolved"] and out["skipped"][0]["reason"] == "ambiguous", out
        assert len(core.pending_asks()) == 2
        assert out["clarified"] == [{"sid": "SM1", "pending": 2, "sent": True}], out
        assert len(core.text_channel.sent) == sends0 + 1
        clar = core.text_channel.sent[-1]
        assert clar["to"] == OWNER and clar.get("mock"), clar
        assert code1 in clar["message"] and code2 in clar["message"], clar["message"]
        assert "ambiguous" in clar["message"].lower(), clar["message"]
        assert core.proactive.budget.count(time.time()) == b0 + 1, \
            "a clarification draws on the interruption budget (F20)"

        # NO + code1 -> exactly ask1 declines (goal failed), ask2 untouched
        inbox.append(sms("SM2", f"no, {code1.upper()}"))
        out = await poller.poll_once()
        assert [r["ask_id"] for r in out["resolved"]] == [ask1["ask_id"]], out
        assert core.store.load(ask1["goal_id"]).state == GoalState.failed
        assert len(core.pending_asks()) == 1

        # bare YES with exactly ONE pending -> resolves it to done, no clarification
        inbox.append(sms("SM3", "Yes."))
        out = await poller.poll_once()
        assert [r["ask_id"] for r in out["resolved"]] == [ask2["ask_id"]], out
        assert core.store.load(ask2["goal_id"]).state == GoalState.done
        assert not core.pending_asks()
        assert not out["clarified"], out

        # bare YES with ZERO pending -> still ambiguous, still refused; the
        # clarification honestly says nothing is pending (no codes to invent)
        inbox.append(sms("SM4", "yes"))
        out = await poller.poll_once()
        assert not out["resolved"] and out["skipped"][0]["reason"] == "ambiguous", out
        assert out["clarified"] and out["clarified"][0]["pending"] == 0, out
        assert "nothing is pending" in core.text_channel.sent[-1]["message"], \
            core.text_channel.sent[-1]

        # same inbox again -> every sid already seen, nothing replays (and a seen
        # ambiguous reply never re-clarifies)
        sends1 = len(core.text_channel.sent)
        out = await poller.poll_once()
        assert not out["resolved"] and not out["ingested"] and not out["skipped"], out
        assert not out["clarified"] and len(core.text_channel.sent) == sends1, out

        # poller RESTART (same data dir) -> seen set persisted, still no replay
        poller2 = InboundPoller(core, fetch=lambda: list(inbox))
        out = await poller2.poll_once()
        assert not out["resolved"] and not out["ingested"] and not out["skipped"], out
        assert not out["clarified"] and len(core.text_channel.sent) == sends1, out
        assert json.loads((tmp / "inbound_seen.json").read_text())["sids"] == [
            "SM1", "SM2", "SM3", "SM4"]
    finally:
        await core.stop()


async def owner_card_check():
    """F18: inbound resolution writes the owner card record back even with the
    in-memory map gone; non-reply inbound enters the owner_ingest door."""
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-inb-card-"))
    core = ControlCore(data_dir=tmp)
    await core.start()
    os.environ["ANTICIPY_OWNER_INGEST"] = "1"
    try:
        ask = await core.feed("app", SEND_SAM, {})
    finally:
        os.environ.pop("ANTICIPY_OWNER_INGEST", None)
    try:
        assert ask["decision"] == "ask" and ask["ask_id"], ask
        record_path = tmp / "owner_cards" / f"{ask['goal_id']}.json"
        assert json.loads(record_path.read_text())["state"] == "waiting"

        core._owner_card_goals.clear()   # simulate restart/desync: the map is GONE

        poller = InboundPoller(core, fetch=lambda: [
            sms("SM10", f"yes {ask['ask_id'][:6]}"),
            sms("SM11", PICKUP),
        ])
        out = await poller.poll_once()

        # the durable execution.goal_id linkage carried the write-back (F18)
        assert [r["ask_id"] for r in out["resolved"]] == [ask["ask_id"]], out
        record = json.loads(record_path.read_text())
        assert record["state"] == "done", record
        assert record["resolution"] == {"ask_id": ask["ask_id"], "approved": True}, record
        assert any((p or {}).get("id") for p in record["proof"].values()), record["proof"]

        # owner speech over SMS -> the SAME Action Engine door, cards stamped source=sms
        assert out["ingested"] and out["ingested"][0]["cards"] >= 1, out
        sms_cards = [json.loads(p.read_text()) for p in (tmp / "owner_cards").glob("*.json")
                     if json.loads(p.read_text())["owner_card"]["source"] == "sms"]
        assert sms_cards and any("pickup" in c["description"].lower() for c in sms_cards)
    finally:
        await core.stop()


async def safety_check():
    """The doors that must NOT open: no owner identity, wrong sender, outbound
    echoes, stale history, codes that match nothing."""
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-inb-safe-"))
    core = ControlCore(data_dir=tmp)
    await core.start()
    try:
        ask = await core.feed("app", SEND_PRIYA, {})
        code = ask["ask_id"][:6]
        valid = f"yes {code}"

        # OWNER_PHONE unset -> the poller refuses to even fetch (and cannot clarify:
        # there is no verified number to text)
        os.environ.pop("OWNER_PHONE", None)
        sends0 = len(core.text_channel.sent)
        poller = InboundPoller(core, fetch=lambda: [sms("SM20", valid)])
        out = await poller.poll_once()
        assert out["fetched"] == 0 and not out["resolved"], out
        assert len(core.pending_asks()) == 1
        assert len(core.text_channel.sent) == sends0
        os.environ["OWNER_PHONE"] = OWNER

        # wrong sender / outbound echo / stale history: seen, never acted on.
        # The two ambiguous OWNER replies in the SAME pass draw exactly ONE
        # clarification (F20 burst bound); the wrong-sender valid code draws none.
        poller = InboundPoller(core, fetch=lambda: [
            sms("SM21", valid, frm="+15551230000"),
            sms("SM22", valid, direction="outbound-api"),
            sms("SM23", valid, date_sent="Mon, 01 Jan 2024 00:00:00 +0000"),
            sms("SM24", "yes zzzz99"),   # well-formed code matching nothing
            sms("SM26", "no qqqq11"),    # second ambiguous reply, same pass
        ])
        out = await poller.poll_once()
        assert not out["resolved"] and not out["ingested"], out
        assert {s["reason"] for s in out["skipped"]} == {"sender", "stale", "ambiguous"}, out
        assert len(core.pending_asks()) == 1, "no unauthorized resolution may happen"
        assert [c["sid"] for c in out["clarified"]] == ["SM24"], out
        assert len(core.text_channel.sent) == sends0 + 1, "one clarification per pass"
        clar = core.text_channel.sent[-1]
        assert clar["to"] == OWNER and "ZZZZ99" in clar["message"], clar
        assert code in clar["message"], "the clarification lists the real pending code"

        # and the REAL owner reply still works after all that
        poller2 = InboundPoller(core, fetch=lambda: [sms("SM25", valid)])
        out = await poller2.poll_once()
        assert [r["ask_id"] for r in out["resolved"]] == [ask["ask_id"]], out
        assert core.store.load(ask["goal_id"]).state == GoalState.done
    finally:
        await core.stop()
        os.environ["OWNER_PHONE"] = OWNER


async def budget_clarify_check():
    """F20 budget bound: a spent interruption budget suppresses the clarification
    (toward silence — the glassbox entry still records the refusal) but NEVER
    gates the owner's exact-code resolution itself."""
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-inb-budget-"))
    core = ControlCore(data_dir=tmp)
    await core.start()
    try:
        ask = await core.feed("app", SEND_PRIYA, {})
        assert ask["decision"] == "ask"
        budget = core.proactive.budget
        now = time.time()
        while budget.count(now) < budget.max_per_day:
            budget.record_interruption(now)

        sends0 = len(core.text_channel.sent)
        poller = InboundPoller(core, fetch=lambda: [sms("SM30", "yes zzzz99")])
        out = await poller.poll_once()
        assert out["skipped"][0]["reason"] == "ambiguous" and not out["clarified"], out
        assert len(core.text_channel.sent) == sends0, "over budget -> silent"
        assert len(core.pending_asks()) == 1

        # resolution is the owner's own action, never an interruption: the exact
        # code resolves even with the budget fully spent
        poller2 = InboundPoller(core, fetch=lambda: [sms("SM31", f"yes {ask['ask_id'][:6]}")])
        out = await poller2.poll_once()
        assert [r["ask_id"] for r in out["resolved"]] == [ask["ask_id"]], out
        assert core.store.load(ask["goal_id"]).state == GoalState.done
    finally:
        await core.stop()


async def money_wall_check():
    """Money never becomes an approvable pending ask. A stale money ask code also
    fails closed if it somehow exists from an old pending file."""
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-inb-money-"))
    core = ControlCore(data_dir=tmp)
    await core.start()
    try:
        blocked = await core.feed("app", WIRE, {})
        assert blocked["decision"] == "blocked" and blocked["category"] == "money", blocked
        assert blocked["ask_id"] is None and not core.pending_asks(), blocked
        assert core.store.load(blocked["goal_id"]).state == GoalState.failed
        assert core.store.load(blocked["goal_id"]).proof.get("blocked", {}).get("category") == "money"

        old = await core.feed("app", SEND_INVESTOR, {})
        assert old["decision"] == "ask" and old["ask_id"], old
        core.proactive.pending[old["ask_id"]]["action"] = WIRE2
        core.proactive.pending[old["ask_id"]]["category"] = "money"
        core.proactive._persist_pending()

        poller = InboundPoller(core, fetch=lambda: [sms("SM40", f"yes {old['ask_id'][:6]}")])
        out = await poller.poll_once()
        assert [r["ask_id"] for r in out["resolved"]] == [old["ask_id"]], out
        assert core.store.load(old["goal_id"]).state == GoalState.failed
        assert core.store.load(old["goal_id"]).proof.get("blocked", {}).get("category") == "money"
        assert not core.pending_asks()
    finally:
        await core.stop()


def main():
    # live_ready stays false throughout (no ANTICIPY_CHANNELS_MODE): this test
    # must never construct a Twilio transport
    assert not InboundPoller.live_ready()
    asyncio.run(code_roundtrip_check())
    asyncio.run(owner_card_check())
    asyncio.run(safety_check())
    asyncio.run(budget_clarify_check())
    asyncio.run(money_wall_check())
    print("PASS inbound: YES/NO+code -> ControlCore.resolve (F18 durable write-back), "
          "speech -> owner_ingest, ambiguity/sender/stale/replay all refused, "
          "ambiguous owner replies draw ONE bounded budget-capped clarification (F20)")


if __name__ == "__main__":
    main()
