"""Inbound SMS poller test — the owner's replies close the loop (STAGE B item 3).

Fake-transport (injected fetch; zero network) pins:
  - the ask SMS now carries the short reply code, and an inbound "YES <code>" /
    "NO <code>" resolves exactly that pending ask THROUGH ControlCore.resolve
  - bare YES resolves only when exactly ONE ask is pending; ambiguity (two pending,
    or a code matching nothing) resolves NOTHING — never guess an approval
  - F18: an owner card record gets its resolution write-back even when the
    in-memory goal->record map is GONE (restart/desync) — the durable
    execution.goal_id linkage carries it
  - non-YES/NO inbound is owner speech -> the same /owner/ingest door (cards with
    source "sms")
  - safety: no OWNER_PHONE -> refuse everything; non-owner senders skipped;
    outbound-direction and pre-floor (stale) messages never act; a processed sid
    never replays — not in a later poll, not after a poller restart

Run:  PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_inbound.py
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
os.environ.pop("ANTICIPY_CHANNELS_MODE", None)   # mock everywhere; no transports
OWNER = "+15550009999"
os.environ["OWNER_PHONE"] = OWNER

from anticipy_engine.channels.inbound import InboundPoller  # noqa: E402
from anticipy_engine.core.control_core import ControlCore  # noqa: E402
from anticipy_engine.core.envelopes import GoalState  # noqa: E402

WIRE = "Wire money to the contractor."
# detrimental (money) -> ask; approved, it stub-plans into write_memory -> done
# (a browse_task plan would dead-end needs_human in mock: no browser link)
WIRE2 = "Remind me Friday to wire the deposit."
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
        ask1 = await core.feed("app", WIRE, {})
        ask2 = await core.feed("app", WIRE2, {})
        assert ask1["decision"] == "ask" and ask2["decision"] == "ask"
        code1, code2 = ask1["ask_id"][:6], ask2["ask_id"][:6]

        # the ask SMS itself advertises the exact code inbound accepts
        last_msg = core.text_channel.sent[-1]["message"]
        assert f"YES {code2}" in last_msg and f"NO {code2}" in last_msg, last_msg

        inbox = []
        poller = InboundPoller(core, fetch=lambda: list(inbox))

        # bare YES with TWO pending -> ambiguous, nothing resolves
        inbox.append(sms("SM1", "YES"))
        out = await poller.poll_once()
        assert not out["resolved"] and out["skipped"][0]["reason"] == "ambiguous", out
        assert len(core.pending_asks()) == 2

        # NO + code1 -> exactly ask1 declines (goal failed), ask2 untouched
        inbox.append(sms("SM2", f"no, {code1.upper()}"))
        out = await poller.poll_once()
        assert [r["ask_id"] for r in out["resolved"]] == [ask1["ask_id"]], out
        assert core.store.load(ask1["goal_id"]).state == GoalState.failed
        assert len(core.pending_asks()) == 1

        # bare YES with exactly ONE pending -> resolves it to done
        inbox.append(sms("SM3", "Yes."))
        out = await poller.poll_once()
        assert [r["ask_id"] for r in out["resolved"]] == [ask2["ask_id"]], out
        assert core.store.load(ask2["goal_id"]).state == GoalState.done
        assert not core.pending_asks()

        # same inbox again -> every sid already seen, nothing replays
        out = await poller.poll_once()
        assert not out["resolved"] and not out["ingested"] and not out["skipped"], out

        # poller RESTART (same data dir) -> seen set persisted, still no replay
        poller2 = InboundPoller(core, fetch=lambda: list(inbox))
        out = await poller2.poll_once()
        assert not out["resolved"] and not out["ingested"] and not out["skipped"], out
        assert json.loads((tmp / "inbound_seen.json").read_text())["sids"] == ["SM1", "SM2", "SM3"]
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
        ask = await core.feed("app", WIRE2, {})
        code = ask["ask_id"][:6]
        valid = f"yes {code}"

        # OWNER_PHONE unset -> the poller refuses to even fetch
        os.environ.pop("OWNER_PHONE", None)
        poller = InboundPoller(core, fetch=lambda: [sms("SM20", valid)])
        out = await poller.poll_once()
        assert out["fetched"] == 0 and not out["resolved"], out
        assert len(core.pending_asks()) == 1
        os.environ["OWNER_PHONE"] = OWNER

        # wrong sender / outbound echo / stale history: seen, never acted on
        poller = InboundPoller(core, fetch=lambda: [
            sms("SM21", valid, frm="+15551230000"),
            sms("SM22", valid, direction="outbound-api"),
            sms("SM23", valid, date_sent="Mon, 01 Jan 2024 00:00:00 +0000"),
            sms("SM24", "yes zzzz99"),   # well-formed code matching nothing
        ])
        out = await poller.poll_once()
        assert not out["resolved"] and not out["ingested"], out
        assert {s["reason"] for s in out["skipped"]} == {"sender", "stale", "ambiguous"}, out
        assert len(core.pending_asks()) == 1, "no unauthorized resolution may happen"

        # and the REAL owner reply still works after all that
        poller2 = InboundPoller(core, fetch=lambda: [sms("SM25", valid)])
        out = await poller2.poll_once()
        assert [r["ask_id"] for r in out["resolved"]] == [ask["ask_id"]], out
        assert core.store.load(ask["goal_id"]).state == GoalState.done
    finally:
        await core.stop()
        os.environ["OWNER_PHONE"] = OWNER


def main():
    # live_ready stays false throughout (no ANTICIPY_CHANNELS_MODE): this test
    # must never construct a Twilio transport
    assert not InboundPoller.live_ready()
    asyncio.run(code_roundtrip_check())
    asyncio.run(owner_card_check())
    asyncio.run(safety_check())
    print("PASS inbound: YES/NO+code -> ControlCore.resolve (F18 durable write-back), "
          "speech -> owner_ingest, ambiguity/sender/stale/replay all refused")


if __name__ == "__main__":
    main()
