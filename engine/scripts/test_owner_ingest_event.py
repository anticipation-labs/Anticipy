"""Owner-lane honesty seam + ONE-BRAIN card execution test (TARGET STAGE B; F17).

With ANTICIPY_OWNER_INGEST=1 the same POST /event pipe the persona runner drives
routes through the owner card path and answers in the proactive shape
({decision, goal_id, ask_id}), so the UNCHANGED factory runner+scorer measure
owner cards with worst-persona honesty. Since F17 the proven proactive spine
(triage -> decider -> harm-line) is the ONLY act/ask/silent decision-maker:
the regex classifier only shapes records, pre-gates money, and adds silent
memory. This pins:
  - a spine-caught line becomes a card that EXECUTED through the orchestrator +
    mock hands; the durable record mirrors the REAL goal state with proof
    (artifact id) — done only when the goal finished with proof
  - a line the spine catches but the regex cannot shape STILL becomes a card
    (the F17 catch fix: the regex can no longer drop what the brain caught)
  - a line the spine judges silent reports that verdict verbatim even when the
    regex shaped a card — the card stays a durable open loop, NEVER a paper ask
  - an ask card is a REAL pending ask: it appears in /pending, YES resumes the
    exact paused goal to done and writes state+proof back onto the record,
    NO marks the record declined
  - a money/blocked card NEVER executes: state "blocked", never in /pending,
    no goal — even with execution on (the pre-gate + harm-line are final)
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
SEND_SAM = "okay just send Sam the revised decking file before Friday."
# the bare reported promise (ledger F21, FIXED): triage's reported-promise shape now
# catches it and the harm-line re-gates the send -> a REAL pending ask, resolvable —
# never a silent drop, never a paper ask
REPORTED_PROMISE = "Sam needs the revised decking before Friday; I told him I'd send it."
# an imperative the spine catches but the regex cannot shape (the F17 catch fix)
UNSHAPED_ACT = "Set up a quick review with the roofing vendor for Thursday 2pm, 30 minutes."
SCHEDULE_CHANGE = "The vendor call moved from Thursday to Friday at 9, block that so I stop double-booking."
FORGET_HOLD = "Renew the patio permit tomorrow morning before I forget again."
SLOT_CONTEXT = "Marta texted that she can look at the furnace Tuesday morning."
SLOT_BOOKING = "Book the Tuesday morning one with Marta before she fills up."
NOTE_TO_CUSTOMERS = "Add a note to tell customers candle restock is Friday, not today."
CART_CONTEXT = "Was comparing spiral notebooks at Staples; liked the 5x8 recycled notebook pack."
CART_DERIVED_NO_BUY = "That notebook size I liked at Staples, cart one pack so I can check shipping later, no buying."
LOWES_CONTEXT = "Was comparing shower grab bars at Lowe's for Dad's bathroom; preferred the Moen 24-inch bar."
LOWES_CART_NO_CHECKOUT = "That grab bar I was looking at for Dad's shower, put it in the cart at Lowe's, no checkout."
BH_CONTEXT = "Was comparing compact light stands at B&H Photo; liked the travel stand best."
BH_CART_NO_BUY = "That light stand thing, put it in the cart if the same one is still at B&H, don't buy it."
INVOICE_DRAFT = "Invoice the client today? No, draft it and let Jordan sanity-check the hours first."
# F28 requested-action scope: a draft request whose line carries work vocabulary
# ("supply order", "purchasing window", "ready to send") is NOT money, NOT a send —
# the pre-gate must not block it, the spine must act, and the plan is the DRAFT
DRAFT_ORDER = ("That supply order is STILL not submitted - the purchasing window closes "
               "soon. Draft the order email to Marta with the list from my desk file so "
               "it's ready to send.")
CART_NO_BUY = "that water-table thing for the birthday, put it in the cart if you find it, don't buy it."
MONEY = "order the replacement filter today and just pay whatever it costs."
# F23: a money-flavored SELF-TALK VENT (self-address vocative + hedge/deferral tail) —
# the spine's own triage vents it, so a pre-gate blocked ask would be a junk interrupt;
# it stays SILENT, and silence (like blocked) has no execution path: money never runs
MONEY_VENT = "Ugh, just buy the dumb gift already, me. Maybe next month. Probably."
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
        promise = await core.feed("app", REPORTED_PROMISE, {})
        unshaped = await core.feed("app", UNSHAPED_ACT, {})
        schedule_change = await core.feed("app", SCHEDULE_CHANGE, {})
        forget_hold = await core.feed("app", FORGET_HOLD, {})
        slot_context = await core.feed("app", SLOT_CONTEXT, {})
        slot_booking = await core.feed("app", SLOT_BOOKING, {})
        note_to_customers = await core.feed("app", NOTE_TO_CUSTOMERS, {})
        cart_context = await core.feed("app", CART_CONTEXT, {})
        cart_derived = await core.feed("app", CART_DERIVED_NO_BUY, {})
        lowes_context = await core.feed("app", LOWES_CONTEXT, {})
        lowes_cart = await core.feed("app", LOWES_CART_NO_CHECKOUT, {})
        bh_context = await core.feed("app", BH_CONTEXT, {})
        bh_cart = await core.feed("app", BH_CART_NO_BUY, {})
        invoice_draft = await core.feed("app", INVOICE_DRAFT, {})
        draft_order = await core.feed("app", DRAFT_ORDER, {})
        cart = await core.feed("app", CART_NO_BUY, {})
        money = await core.feed("app", MONEY, {})
        money_vent = await core.feed("app", MONEY_VENT, {})
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
    for out in (noise, act, ask, promise, unshaped, schedule_change, forget_hold,
                slot_context, slot_booking, note_to_customers, cart_context,
                cart_derived, lowes_context, lowes_cart, bh_context, bh_cart,
                invoice_draft, draft_order, cart, money, money_vent, remember, clarify):
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
    # the proof must reference a real artifact: an external id, or the drawer
    # memory_id for a reminder line whose honest plan is the open-loop write
    # (plans no longer carry memory-noise side steps, so PICKUP plans exactly that)
    assert any((p or {}).get("id") or (p or {}).get("memory_id")
               for p in rec["proof"].values()), rec["proof"]
    assert "pickup" in rec["description"].lower(), rec
    card_proof = rec["owner_card"]["proof"]
    assert any(p["type"] == "memory_write" for p in card_proof), rec
    assert any(p["type"] == "memory_read_back" for p in card_proof), rec
    assert any(p["type"] == "engine_execution" for p in card_proof), rec
    assert any(p["type"] == "card_record" for p in card_proof), rec

    # a line the spine catches but the regex cannot shape STILL becomes a card —
    # the F17 catch fix: the weak shaper can no longer drop what the brain caught
    assert unshaped["decision"] == "act", unshaped
    un_rec = _record(tmp, unshaped["goal_id"])
    assert un_rec["state"] == "done" and un_rec["proof"], un_rec
    assert un_rec["owner_card"]["action"] == "execute_owner_task", un_rec
    assert any(p["type"] == "engine_execution" for p in un_rec["owner_card"]["proof"]), un_rec

    # v2 schedule-change hold: the spine catches an unshaped moved/block line, the
    # stub planner grounds the spoken new slot, and the owner card mirrors proof.
    assert schedule_change["decision"] == "act", schedule_change
    sc_rec = _record(tmp, schedule_change["goal_id"])
    assert sc_rec["state"] == "done" and sc_rec["proof"], sc_rec
    sc_steps = [s.get("intent") for s in sc_rec["steps"]]
    assert sc_steps == ["create_event"], sc_steps
    assert sc_rec["steps"][0]["args"]["when"] == "Friday at 9", sc_rec
    assert sc_rec["steps"][0]["args"]["title"] == "vendor call", sc_rec

    # A time-anchored "before I forget" line is a reversible hold: write the
    # exact open loop now, and re-gate any external action when it fires.
    assert forget_hold["decision"] == "act", forget_hold
    fh_rec = _record(tmp, forget_hold["goal_id"])
    assert fh_rec["state"] == "done" and fh_rec["proof"], fh_rec
    fh_steps = [s.get("intent") for s in fh_rec["steps"]]
    assert fh_steps == ["write_memory"], fh_rec
    assert fh_rec["steps"][0]["args"] == {"kind": "open_loop", "text": FORGET_HOLD}, fh_rec

    # Context-backed slot anaphor: the memory line names Cal and Friday afternoon,
    # so "the Friday afternoon one" can be held on the calendar without asking.
    assert slot_context["decision"] == "ignore", slot_context
    assert slot_booking["decision"] == "act", slot_booking
    sb_rec = _record(tmp, slot_booking["goal_id"])
    assert sb_rec["state"] == "done" and sb_rec["proof"], sb_rec
    sb_steps = [s.get("intent") for s in sb_rec["steps"]]
    assert sb_steps == ["create_event"], sb_rec
    assert sb_rec["steps"][0]["args"]["when"] == "Tuesday morning", sb_rec
    assert sb_rec["steps"][0]["args"]["title"] == "furnace with Marta", sb_rec

    # An imperative note command is reversible capture. The audience phrase is
    # note content, not a binding send.
    assert note_to_customers["decision"] == "act", note_to_customers
    note_rec = _record(tmp, note_to_customers["goal_id"])
    assert note_rec["state"] == "done" and note_rec["proof"], note_rec
    note_steps = [s.get("intent") for s in note_rec["steps"]]
    assert note_steps == ["write_memory"], note_rec
    assert note_rec["steps"][0]["args"] == {"kind": "open_loop", "text": NOTE_TO_CUSTOMERS}, note_rec

    # Cart-only browser tasks can execute only when memory resolves a derivable
    # store and item. The no-buy phrase is a safety bound, not money intent.
    assert cart_context["decision"] == "ignore", cart_context
    assert cart_derived["decision"] == "act", cart_derived
    cd_rec = _record(tmp, cart_derived["goal_id"])
    assert cd_rec["state"] == "done" and cd_rec["proof"], cd_rec
    cd_steps = [s.get("intent") for s in cd_rec["steps"]]
    assert cd_steps == ["browse_task"], cd_rec
    assert cd_rec["steps"][0]["args"]["url"] == "https://www.staples.com", cd_rec
    assert cd_rec["owner_card"]["route"] == "browser", cd_rec

    assert lowes_context["decision"] == "ignore", lowes_context
    assert lowes_cart["decision"] == "act", lowes_cart
    lw_rec = _record(tmp, lowes_cart["goal_id"])
    assert lw_rec["state"] == "done" and lw_rec["proof"], lw_rec
    lw_steps = [s.get("intent") for s in lw_rec["steps"]]
    assert lw_steps == ["browse_task"], lw_rec
    assert lw_rec["steps"][0]["args"]["url"] == "https://www.lowes.com", lw_rec
    assert lw_rec["steps"][0]["args"]["memory_resolution"]["item"] == "Moen 24-inch bar", lw_rec

    assert bh_context["decision"] == "ignore", bh_context
    assert bh_cart["decision"] == "act", bh_cart
    bh_rec = _record(tmp, bh_cart["goal_id"])
    assert bh_rec["state"] == "done" and bh_rec["proof"], bh_rec
    bh_steps = [s.get("intent") for s in bh_rec["steps"]]
    assert bh_steps == ["browse_task"], bh_rec
    assert bh_rec["steps"][0]["args"]["url"] == "https://www.bhphotovideo.com", bh_rec
    assert bh_rec["steps"][0]["args"]["memory_resolution"]["item"] == "travel stand", bh_rec

    # Money-adjacent invoice drafting is not silent and not executed. It becomes
    # a real waiting ask card with a pending ask id.
    assert invoice_draft["decision"] == "ask" and invoice_draft["ask_id"], invoice_draft
    inv_rec = _record(tmp, invoice_draft["goal_id"])
    assert inv_rec["state"] == "waiting", inv_rec
    assert not inv_rec["steps"] and not inv_rec["proof"], inv_rec
    assert inv_rec["owner_card"]["execution"]["decision"] == "ask", inv_rec

    # F28: the draft request acts (no money pre-gate on the noun "order"; no send
    # reading on the purpose tail) and the executed plan is the DRAFT — never a send
    assert draft_order["decision"] == "act", draft_order
    do_rec = _record(tmp, draft_order["goal_id"])
    assert do_rec["state"] == "done" and do_rec["proof"], do_rec
    do_steps = [s.get("intent") for s in do_rec["steps"]]
    assert "send_email_draft" in do_steps and "send_email" not in do_steps, do_steps

    # no-memory cart card: the truthful decision is ask, never a paper act or
    # fake browse proof. The no-buy phrase is a safety bound, not purchase intent.
    assert cart["decision"] == "ask" and cart["ask_id"], cart
    assert cart["cards"][0]["args"].get("payment_allowed") is False, cart
    cart_rec = _record(tmp, cart["goal_id"])
    assert cart_rec["state"] == "waiting", "an unresolved cart card must never look done"
    assert not cart_rec["proof"], cart_rec
    assert cart_rec["owner_card"]["execution"]["decision"] == "ask", cart_rec

    # the bare reported promise is a real commitment (F21 FIXED): the spine catches
    # it, the harm-line re-gates the send, and the card is a REAL pending ask (the
    # F17 one-brain contract unchanged — this is the spine's verdict, not the regex's)
    assert promise["decision"] == "ask" and promise["ask_id"], promise
    pr_rec = _record(tmp, promise["goal_id"])
    assert pr_rec["state"] == "waiting", pr_rec
    assert pr_rec["owner_card"]["execution"]["decision"] == "ask", pr_rec

    # ask card: a REAL pending ask in /pending, resolvable by the existing flow
    assert ask["decision"] == "ask" and ask["ask_id"], ask
    assert ask["cards"][0]["args"].get("person") == "Sam", ask
    assert _record(tmp, ask["goal_id"])["state"] == "waiting", ask

    # money without an explicit no-buy is a blocked card -> surfaces as a non-resolvable wall, NEVER executes
    assert money["decision"] == "ask" and money["ask_id"] is None, money
    assert money["cards"][0]["disposition"] == "blocked", money
    money_rec = _record(tmp, money["goal_id"])
    assert money_rec["state"] == "blocked", money_rec
    assert not money_rec["steps"] and not money_rec["proof"], money_rec
    assert not (tmp / "goals" / f"{money['goal_id']}.json").exists(), "blocked card grew a goal"

    # F23: a money-flavored vent the spine's OWN triage silences stays SILENT — no
    # junk ask, no card, no record, no goal, nothing resolvable. The MONEY pin above
    # is the other half of the bound: a triage-actionable money line keeps its
    # blocked card, so the consult can only ever trade blocked -> silence, never -> act.
    assert money_vent["decision"] == "ignore" and money_vent["ask_id"] is None, money_vent
    assert money_vent["goal_id"] is None and not money_vent["cards"], money_vent

    # /pending carries exactly the ask cards — the blocked money card is NOT resolvable
    pending_ids = {p["ask_id"] for p in pending}
    assert ask["ask_id"] in pending_ids and clarify["ask_id"] in pending_ids, pending
    assert promise["ask_id"] in pending_ids and cart["ask_id"] in pending_ids, pending
    assert invoice_draft["ask_id"] in pending_ids, pending
    assert money["goal_id"] not in pending_ids and len(pending) == 5, pending

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
    print("PASS owner_ingest_event: ONE BRAIN (F17) — the proven spine rules every owner "
          "line (catches the regex-unshapeable, never a paper act/ask), cards EXECUTE with "
          "proof write-back, real /pending YES/NO, money never executes; default path untouched")


if __name__ == "__main__":
    main()
