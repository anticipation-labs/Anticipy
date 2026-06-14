"""Owner Action Engine intake test.

The product input is not clean commands. This pins the first operating contract:
all owner doors feed the same messy transcript path, useless lines are ignored,
useful lines become durable action cards, and no card uses a special pass-off
mode instead of a real route/status.
"""
import asyncio
import json
import os
import tempfile
from pathlib import Path

os.environ.setdefault("ANTICIPY_MODEL_PROVIDER", "stub")
os.environ.setdefault("ANTICIPY_HANDS_MODE", "mock")

from anticipy_engine.core.control_core import ControlCore  # noqa: E402
from anticipy_engine.owner_mode import OwnerMode  # noqa: E402


NOISY_DAY = """
[08:02] Omar: yeah okay no the coffee machine is being weird again and I do not care.
[08:04] Maya: school moved pickup to 3 today, please remind me before I forget.
[08:05] Omar: oh sure, I'll just clone myself, that'll fix the schedule.
[09:12] Sam needs the revised decking before Friday; I told him I'd send it.
[09:15] Omar: anyway the blue cup is on the counter, whatever.
[11:22] Omar: that water-table thing for Leila's birthday, put it in the cart if you find it, don't buy it.
[13:00] Omar: My wife Maya prefers texts after lunch.
[16:10] Omar: this whole week is ridiculous, lol.
"""


def signature(result):
    return [
        (c.title, c.disposition, c.route, c.action, c.args.get("person"), c.args.get("kind"))
        for c in result.cards
    ]


async def control_core_check():
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-owner-"))
    core = ControlCore(data_dir=tmp)
    await core.start()
    try:
        out = await core.owner_ingest("mp3", NOISY_DAY)
    finally:
        await core.stop()

    owner_loops = [i for i in core.memory.open_loops.all() if i.fields.get("owner_card_id")]
    owner_profile = [i for i in core.memory.profile.all() if i.fields.get("owner_card_id")]
    assert len(out["cards"]) == 4, out
    assert len(owner_loops) == 3, [i.model_dump(mode="json") for i in owner_loops]
    assert len(owner_profile) == 1, [i.model_dump(mode="json") for i in owner_profile]
    assert {i.fields["route"] for i in owner_loops} == {"api", "voice_text", "browser"}
    assert all(i.fields["action"] for i in owner_loops)
    assert "handoff" not in json.dumps(out).lower()


def main():
    mode = OwnerMode()
    sources = ["pay_to_try", "start_listening", "mp3", "transcript"]
    results = [mode.ingest(NOISY_DAY, source=s) for s in sources]
    expected = signature(results[0])
    for result in results[1:]:
        assert signature(result) == expected, (result.source, signature(result), expected)

    cards = results[0].cards
    assert len(cards) == 4, [c.model_dump(mode="json") for c in cards]
    assert results[0].ignored_line_count >= 3
    assert any(c.action == "create_calendar_or_reminder" and c.route == "api" for c in cards)
    assert any(c.action == "draft_or_confirm_message" and c.args.get("person") == "Sam" for c in cards)
    assert any(c.action == "find_or_cart_without_purchase" and c.route == "browser" for c in cards)
    assert any(c.action == "write_profile_memory" and c.route == "memory" for c in cards)
    assert not any("clone myself" in c.source_text.lower() for c in cards)
    assert "handoff" not in json.dumps([c.model_dump(mode="json") for c in cards]).lower()

    # F28: the money pre-gate matches "order" as the SPEND-VERB shape, never the bare
    # noun — a draft request about a supply order is NOT money-blocked (the spine rules
    # it), while real order-commands stay blocked. Work vocabulary stays cardless.
    draft_order = mode.ingest("Draft the order email to Vicky with the list from my desk doc.")
    assert not any(c.disposition == "blocked" for c in draft_order.cards), signature(draft_order)
    beakers = mode.ingest("Order the beakers for the lab demo on the district card.")
    assert any(c.disposition == "blocked" for c in beakers.cards), signature(beakers)
    direct_pay = mode.ingest("Pay the overdue invoice now with the card on file.")
    assert any(c.disposition == "blocked" for c in direct_pay.cards), signature(direct_pay)
    noun_order = mode.ingest("That's a change order. Everything is a change order.")
    assert not noun_order.cards, signature(noun_order)

    # ---- RECALL FALLBACK pin (Apollo wave 2): a bare actionable line — clause-initial
    # scheduling/contact verb (book/schedule/call/meet) + a concrete time — that none of the
    # earlier shapes catch must NO LONGER be dropped; it shapes a do/api timed-action card.
    for bare in ("Book the dentist at 3pm tomorrow.",
                 "Call the plumber this afternoon.",
                 "Schedule the design review for Monday.",
                 "Meet the contractor at 9am Friday."):
        cards_b = mode.ingest(bare).cards
        assert any(c.action == "create_calendar_or_reminder" and c.disposition == "do"
                   and c.route == "api" for c in cards_b), (bare, signature(mode.ingest(bare)))
    # the time anchor is REQUIRED: a bare verb with no time still falls through (no card)
    assert not mode.ingest("Book the dentist.").cards
    # the fallback must NOT preempt the spine's richer catch paths: an open phrasal head
    # ("Set up ...") and an anaphoric memory-resolved slot ("the Tuesday morning one") stay
    # UNSHAPED so ControlCore keeps catching+executing them through the proven spine.
    assert not mode.ingest("Set up a quick review with the vendor for Thursday 2pm.").cards
    assert not mode.ingest("Book the Tuesday morning one with Marta before she fills up.").cards
    # CARDINAL-SIN pin: hyperbole/joke versions of a scheduling verb must produce NO card
    # (is_vent_shape gates them before any shaping) — acting on a vent is the cardinal sin.
    for vent in ("schedule a vacation for me forever",
                 "call my therapist forever lol",
                 "book a one-way ticket to mars tomorrow, lol",
                 "delete my whole calendar today"):
        assert not mode.ingest(vent).cards, (vent, signature(mode.ingest(vent)))

    # ---- Apollo wave 3 SPINE VENT pin: the spine now gates on is_vent() (the SINGLE SOURCE
    # OF TRUTH, superset of is_vent_shape), so a "Remind me ..." line that self-cancels with a
    # trailing hedge ("..., probably.") or a countermand ("Never mind, forget it.") makes NO
    # card. Before this, owner_mode used only is_vent_shape (no hedge/countermand arm) and
    # SHAPED a reminder card for a self-cancelled line — acting on a self-cancel (Law 2).
    for spine_vent in ("Remind me to email the landlord, probably.",
                       "Remind me to book the trip. Never mind, forget it.",
                       "Remind me to renew the gym, maybe.",
                       "Remind me that I hate this job, ugh.",
                       "Remind me to never agree to a 7am meeting again, lol."):
        assert not mode.ingest(spine_vent).cards, (spine_vent, signature(mode.ingest(spine_vent)))
    # recall guard: a genuine "Remind me ..." with no self-cancel still shapes a card
    assert any(c.action == "create_reminder_or_open_loop"
               for c in mode.ingest("Remind me to call the dentist tomorrow.").cards)

    # ---- Apollo wave 3 SPINE MONEY pin: the money interlock runs BEFORE the person+send
    # branch and reuses the harm-line money signal (harm.py _MONEY_SIGNAL/_MONEY_IDIOMS), so a
    # payment wearing a benign message skin ("email Sam the rent payment of 1200 dollars",
    # "text Priya the five hundred we owe her") is BLOCKED, never a draft_or_confirm_message.
    for pay in ("email Sam the rent payment of 1200 dollars",
                "text Priya the five hundred we owe her",
                "send Jordan the invoice balance of 800",
                "reply to Maya, send her the 200 bucks we owe",
                "Send my landlord the deposit over Zelle."):
        cards_p = mode.ingest(pay).cards
        assert any(c.disposition == "blocked"
                   and c.action == "prepare_purchase_path_without_payment" for c in cards_p), \
            (pay, signature(mode.ingest(pay)))
        assert not any(c.action == "draft_or_confirm_message" for c in cards_p), \
            (pay, "money must never shape a benign message", signature(mode.ingest(pay)))
    # money carve-outs (mirror the harm-line): a real spend on an invoice still BLOCKS, but an
    # invoice DRAFT/REVIEW ask falls THROUGH (None) to the spine's invoice_draft ask path, and a
    # cart-prep "...don't buy it" line stays a no-purchase cart card (its "buy" is a bound).
    assert any(c.disposition == "blocked"
               for c in mode.ingest("Pay the invoice now with the card on file.").cards)
    assert not mode.ingest(
        "Invoice the client today? No, draft it and let Jordan sanity-check the hours first."
    ).cards
    assert any(c.action == "find_or_cart_without_purchase" for c in mode.ingest(
        "That camera strap I liked, put it in the cart if it's there, don't buy it."
    ).cards)

    asyncio.run(control_core_check())
    print("PASS owner_mode: noisy owner transcript -> shared durable action cards")


if __name__ == "__main__":
    main()
