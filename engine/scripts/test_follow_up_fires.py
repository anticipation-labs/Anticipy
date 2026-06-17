"""FOLLOW-UP FIRES — end-to-end proof (deterministic, stub model, no network).

The product claim: when an obligation's outcome depends on someone else, Anticipy schedules a
CHECK for later and, when that time arrives, ACTUALLY nudges the owner — linked to the exact
original obligation + its proof. This test proves the whole chain on the REAL assembled engine:

  (a) FIRES: ingesting "send Priya the deck by Friday and make sure it lands" attaches a
      follow_up plan to the card AND writes a durable, fireable open_loop carrying remind_ts ==
      when_ts. Advancing the clock past when_ts and running the SAME trigger tick that fires
      reminders delivers a REAL channel artifact (the nudge), linked to the original card id +
      its proof. Fire-once holds (a second tick fires nothing).

  (b) IDEMPOTENT: re-ingesting the same line does NOT churn when_ts and does NOT double-schedule
      (exactly one follow-up loop for the obligation, same scheduled time).

  (c) NO NUISANCE NUDGES: a plain low-risk do card (a self-reminder), a vent, a preference, and
      a money card each get NO follow_up plan and write NO follow-up loop.

Run: PYTHONPATH=engine ANTICIPY_MODEL_PROVIDER=stub engine/.venv/bin/python engine/scripts/test_follow_up_fires.py
It MUST print PASS and exit 0.
"""
import asyncio
import os
import tempfile
from pathlib import Path

os.environ.setdefault("ANTICIPY_MODEL_PROVIDER", "stub")
os.environ.setdefault("ANTICIPY_HANDS_MODE", "mock")
os.environ.setdefault("ANTICIPY_CHANNELS_MODE", "mock")
os.environ.setdefault("ANTICIPY_NATIVE_BRIDGE_FALLBACK", "0")

from anticipy_engine.core.control_core import ControlCore  # noqa: E402
from anticipy_engine.proactive.follow_up import plan_follow_up, warrants_follow_up  # noqa: E402

_DAY = 24 * 3600

# An obligation whose outcome depends on someone else (a directed send + an explicit
# "make sure it lands" outcome-check) — the canonical follow-up case.
EXTERNAL = "send Priya the deck by Friday and make sure it lands."
# A plain low-risk self-reminder — actionable, but its outcome depends on no one else.
PLAIN = "remind me to stretch before the standup tomorrow."
# A vent — never a card, never a follow-up.
VENT = "ugh I should just quit and move to a beach, this is pointless."
# A pure preference — remembered, never a follow-up.
PREF = "my wife Maya prefers texts after lunch."
# Money — the hard wall; never a follow-up even if it slips past blocked.
MONEY = "order the replacement filter today and just pay whatever it costs."


def _follow_up_loops(core):
    return [l for l in core.memory.open_loops.all() if l.fields.get("kind") == "follow_up"]


async def fires_check(fails):
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-fu-fires-"))
    core = ControlCore(data_dir=tmp)
    await core.start()
    try:
        out = await core.owner_ingest("transcript", EXTERNAL, execute_actions=True)
        cards = out.get("cards", [])
        if not cards:
            fails.append("external-dependency line produced no card")
            return
        card = cards[0]
        fu = card.get("follow_up")
        if not fu or "when_ts" not in fu:
            fails.append(f"external-dependency card got NO follow_up plan: {card.get('follow_up')}")
            return
        when_ts = float(fu["when_ts"])

        # a durable, fireable follow-up loop was written, carrying remind_ts == when_ts and
        # the LINK to the original card id + its proof
        loops = _follow_up_loops(core)
        if len(loops) != 1:
            fails.append(f"expected exactly ONE follow-up loop, got {len(loops)}")
            return
        loop = loops[0]
        if abs(float(loop.fields.get("remind_ts", 0)) - when_ts) > 1e-6:
            fails.append(f"loop remind_ts != plan when_ts: {loop.fields.get('remind_ts')} vs {when_ts}")
        if loop.fields.get("follow_up_for_card_id") != card["id"]:
            fails.append(f"follow-up loop not linked to original card id: {loop.fields}")
        if not loop.fields.get("origin_proof"):
            fails.append("follow-up loop carries no origin proof link")
        if loop.status != "open" or loop.fields.get("fired_at") is not None:
            fails.append(f"fresh follow-up loop must be open + unfired: status={loop.status} "
                         f"fired_at={loop.fields.get('fired_at')}")

        # BEFORE when_ts: a trigger tick must NOT fire the follow-up (it's in the future)
        before = await core.proactive.trigger_tick(now=when_ts - 60)
        if any(f.get("loop_id") == loop.id for f in before):
            fails.append(f"follow-up fired BEFORE its when_ts: {before}")
        sent_before = len(core.text_channel.sent)

        # ADVANCE the clock past when_ts and run the SAME trigger tick reminders use:
        # the nudge ACTUALLY FIRES as a delivered channel artifact, linked to the original.
        fired = await core.proactive.trigger_tick(now=when_ts + 60)
        ff = next((f for f in fired if f.get("loop_id") == loop.id), None)
        if ff is None:
            fails.append(f"follow-up did NOT fire after when_ts: {fired}")
            return
        if ff.get("decision") != "notify":
            fails.append(f"follow-up should fire as a notify nudge, got: {ff.get('decision')}")
        if ff.get("follow_up_for_card_id") != card["id"]:
            fails.append(f"fired nudge not linked to original card: {ff}")
        # a REAL delivered artifact: a new channel send happened on this tick
        new_sends = core.text_channel.sent[sent_before:]
        if not new_sends:
            fails.append(f"no channel artifact delivered when the follow-up fired: {core.text_channel.sent}")

        # FIRE-ONCE: a second tick at the same time fires nothing (no duplicate nudge)
        again = await core.proactive.trigger_tick(now=when_ts + 120)
        if any(f.get("loop_id") == loop.id for f in again):
            fails.append(f"follow-up fired twice (fire-once violated): {again}")
        # the loop is durably marked fired_at so a restart never re-fires it
        refired_loop = core.memory.open_loops.get(loop.id)
        if refired_loop.fields.get("fired_at") is None:
            fails.append("fired follow-up loop carries no durable fired_at stamp")
    finally:
        await core.stop()


async def idempotent_check(fails):
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-fu-idem-"))
    core = ControlCore(data_dir=tmp)
    await core.start()
    try:
        out1 = await core.owner_ingest("transcript", EXTERNAL, execute_actions=True)
        when1 = float(out1["cards"][0]["follow_up"]["when_ts"])
        loops1 = _follow_up_loops(core)
        # re-ingest the SAME line: must reuse the same loop + the same scheduled time
        out2 = await core.owner_ingest("transcript", EXTERNAL, execute_actions=True)
        when2 = float(out2["cards"][0]["follow_up"]["when_ts"])
        loops2 = _follow_up_loops(core)
        if len(loops2) != 1:
            fails.append(f"re-ingest double-scheduled the follow-up: {len(loops2)} loops")
        if abs(when1 - when2) > 1e-6:
            fails.append(f"when_ts churned on re-ingest: {when1} -> {when2}")
        if loops1 and loops2 and loops1[0].id != loops2[0].id:
            fails.append("re-ingest wrote a NEW follow-up loop id (not idempotent)")
    finally:
        await core.stop()


async def no_nuisance_check(fails):
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-fu-none-"))
    core = ControlCore(data_dir=tmp)
    await core.start()
    try:
        for label, line in (("plain do", PLAIN), ("vent", VENT),
                            ("preference", PREF), ("money", MONEY)):
            out = await core.owner_ingest("transcript", line, execute_actions=True)
            for c in out.get("cards", []):
                if c.get("follow_up"):
                    fails.append(f"{label} card got a spurious follow_up: {c.get('follow_up')}")
        # and NO follow-up loops were written for any of them
        if _follow_up_loops(core):
            fails.append(f"nuisance follow-up loops were written: "
                         f"{[l.text for l in _follow_up_loops(core)]}")
    finally:
        await core.stop()


def unit_gate_check(fails):
    """The deterministic gate itself, in isolation (no engine): the tightened rules."""
    # external-dependency ACTION -> warranted
    if not warrants_follow_up({"disposition": "do", "action": "draft_or_confirm_message",
                               "source_text": "let Sam know"}):
        fails.append("external-dependency action should warrant a follow-up")
    # explicit external-dependency phrase -> warranted
    if not warrants_follow_up({"disposition": "do", "action": "execute_owner_task",
                               "source_text": "send Priya the deck and make sure it lands"}):
        fails.append("explicit 'send ... make sure it lands' should warrant a follow-up")
    # a BARE verb mention with no external dependency -> NOT warranted (no nuisance)
    if warrants_follow_up({"disposition": "do", "action": "execute_owner_task",
                           "source_text": "remind me to confirm my own RSVP for the party"}):
        fails.append("a bare 'confirm' mention (self, no external party) must NOT warrant a follow-up")
    if warrants_follow_up({"disposition": "do", "action": "execute_owner_task",
                           "source_text": "I should reply-all less in meetings"}):
        fails.append("a bare 'reply' mention must NOT warrant a follow-up")
    # vent / preference / money never
    if warrants_follow_up({"disposition": "ignore", "source_text": "send help, this is hell"}):
        fails.append("a vent (ignore) must never warrant a follow-up")
    if warrants_follow_up({"disposition": "remember", "source_text": "email me before 9am, I prefer it"}):
        fails.append("a preference (remember) must never warrant a follow-up")
    if warrants_follow_up({"disposition": "blocked", "category": "money",
                           "source_text": "wire the deposit to the vendor and confirm receipt"}):
        fails.append("a money/blocked card must never warrant a follow-up")
    # money category guard even without disposition==blocked
    if warrants_follow_up({"disposition": "do", "category": "money",
                           "source_text": "send the payment to Priya and confirm it landed"}):
        fails.append("a money-category card must never warrant a follow-up")


async def main():
    fails: list[str] = []
    unit_gate_check(fails)
    await fires_check(fails)
    await idempotent_check(fails)
    await no_nuisance_check(fails)

    print("==== FOLLOW-UP FIRES (deterministic, stub) ====")
    print("  (a) external-dep obligation -> plan + durable fireable loop -> trigger tick "
          "past when_ts delivers a linked nudge; fire-once holds")
    print("  (b) re-ingest is idempotent (no when_ts churn, no double-schedule)")
    print("  (c) plain do / vent / preference / money -> NO follow_up, NO loop")
    if fails:
        print("==== FAIL ====")
        for x in fails:
            print("   -", x)
        raise SystemExit(1)
    print("PASS test_follow_up_fires")


if __name__ == "__main__":
    asyncio.run(main())
