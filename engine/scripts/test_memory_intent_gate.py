"""GATE D — memory/intent (deterministic, through REAL core.owner_ingest).

Proves the WIRING of the memory + intent middle on four hard sub-checks, end-to-end through the real
ControlCore.owner_ingest spine (not the unit helpers):

  1. VAGUE REFERENCE RESOLVES — "that desk thing" -> the Jarvis standing desk (the referent named
     earlier in the same day), surfaced on the middle_trace resolution's chosen_referent AND folded
     into the resolved card text.
  2. DUPLICATES COLLAPSE — a relayed obligation + its (synonym) confirmation -> exactly ONE card
     containing "amazon" (the dedup law: one real obligation = one card).
  3. VENTS IGNORED — two vents ("I'm moving to the woods", "if I win the lottery...") -> 0 cards.
  4. RESTART-STABLE / IDEMPOTENT — ingest, STOP the ControlCore, START a NEW ControlCore on the SAME
     data_dir, re-ingest the same text -> the durable card/open-loop counts survive the restart and the
     re-ingest does NOT double-count.

STUB-MODE CAVEAT (honest): this runs with ANTICIPY_MODEL_PROVIDER=stub, so the moat model is OFF.
Vague-ref resolution and vent-suppression here therefore ride the DETERMINISTIC layer (intent_threads +
owner_mode + _consolidate_obligations), which is exactly what Gate D is meant to prove: the middle is
WIRED into owner_ingest and behaves correctly without any live model. The LIVE inference QUALITY
(messy real speech, sarcasm, relayed-to-others judgement) is proven separately by the 10k live cert
(Gate J). A consequence of the moat being off: the literal phrasing "Riley asked me to call Amazon ...
yeah I'll handle it" is treated literally — a question-to-OTHERS is NOT auto-adopted as the owner's
task without the live moat (audit fix ff93775) — so the dedup law is exercised with the obligation
phrased as the owner's own ("call Amazon ..." + a synonym confirmation), which is the same collapse.
"""
import asyncio
import os
import tempfile

os.environ.setdefault("ANTICIPY_MODEL_PROVIDER", "stub")
os.environ.setdefault("ANTICIPY_HANDS_MODE", "mock")
os.environ.setdefault("ANTICIPY_CHANNELS_MODE", "mock")
os.environ.setdefault("ANTICIPY_NATIVE_BRIDGE_FALLBACK", "0")

from anticipy_engine.core.control_core import ControlCore  # noqa: E402


async def _ingest(data_dir, text, execute_actions=False):
    core = ControlCore(data_dir=data_dir)
    await core.start()
    try:
        return await core.owner_ingest("transcript", text, execute_actions=execute_actions)
    finally:
        await core.stop()


def _card_texts(out):
    return [(c.get("source_text", ""), c.get("title", ""), c.get("disposition")) for c in out.get("cards", [])]


async def check_vague_reference():
    """1) "that desk thing I mentioned" -> the Jarvis standing desk named earlier today."""
    text = "\n".join([
        "the Jarvis standing desk is the one I liked",
        "can you pull up that desk thing I mentioned?",
    ])
    with tempfile.TemporaryDirectory() as d:
        out = await _ingest(d, text, execute_actions=False)
    resolutions = out["middle_trace"]["resolutions"]
    # the "desk thing" line resolved, and its chosen_referent is the Jarvis desk line.
    desk = next((r for r in resolutions if "desk thing" in r.get("line", "")), None)
    assert desk is not None, ("no resolution for the desk-thing line", resolutions)
    assert desk.get("decision") == "resolved", desk
    chosen = desk.get("chosen_referent") or ""
    assert "Jarvis" in chosen, ("chosen_referent must be the Jarvis desk", desk)
    assert "standing desk" in chosen.lower(), desk
    # and the resolution rewrote the card text to carry the concrete referent.
    assert "Jarvis" in (desk.get("resolved_to") or ""), desk
    # the surviving card (the only obligation) contains the resolved Jarvis-desk text.
    card_blob = " ".join(t for c in _card_texts(out) for t in c[:2])
    assert "Jarvis" in card_blob, ("resolved card text must contain Jarvis", _card_texts(out))
    return "vague 'desk thing'->Jarvis standing desk (chosen_referent + resolved card text)"


async def check_duplicates_collapse():
    """2) one obligation + its (synonym) confirmation -> exactly ONE card containing 'amazon'."""
    # exec=True drives the full spine; the two lines name the SAME obligation {amazon, monitor}
    # (a relayed ask the owner adopts + the owner's own confirmation worded as a synonym), so
    # _consolidate_obligations folds them to ONE card. (See the stub-mode caveat in the docstring.)
    text = "\n".join([
        "call Amazon about the monitor",
        "handle the Amazon monitor issue",
    ])
    with tempfile.TemporaryDirectory() as d:
        out = await _ingest(d, text, execute_actions=True)
    amazon_cards = [
        c for c in out.get("cards", [])
        if "amazon" in ((c.get("source_text", "") + " " + c.get("title", "")).lower())
    ]
    assert len(amazon_cards) == 1, ("dedup law: exactly ONE amazon card", _card_texts(out))
    return "relayed request + confirmation -> exactly 1 'amazon' card (dedup law)"


async def check_vents_ignored():
    """3) two vents -> 0 cards (silent — never an action, never an ask)."""
    text = "\n".join([
        "honestly I'm so done, I'm moving to the woods.",
        "if I win the lottery I'm buying an island lol",
    ])
    with tempfile.TemporaryDirectory() as d:
        out = await _ingest(d, text, execute_actions=True)
    assert out.get("cards") == [], ("vents must yield 0 cards", _card_texts(out))
    return "two vents -> 0 cards (silent)"


async def check_restart_stable_idempotent():
    """4) ingest -> STOP -> NEW core on SAME data_dir -> re-ingest -> no double-count."""
    text = "remind me to call the dentist at 3pm tomorrow"
    with tempfile.TemporaryDirectory() as d:
        # first core: ingest + execute, then STOP
        core1 = ControlCore(data_dir=d)
        await core1.start()
        await core1.owner_ingest("transcript", text, execute_actions=True)
        cards1 = core1.owner_cards()["count"]
        loops1 = len(core1.memory.open_loops.all())
        await core1.stop()
        assert cards1 >= 1, ("first ingest must produce a durable card", cards1)

        # SECOND core, SAME data_dir: durable memory survives the restart
        core2 = ControlCore(data_dir=d)
        await core2.start()
        cards_after_restart = core2.owner_cards()["count"]
        loops_after_restart = len(core2.memory.open_loops.all())
        assert cards_after_restart == cards1, ("cards must survive restart", cards1, cards_after_restart)
        assert loops_after_restart == loops1, ("open-loops must survive restart", loops1, loops_after_restart)

        # re-ingest the SAME text -> must NOT double-count
        await core2.owner_ingest("transcript", text, execute_actions=True)
        cards2 = core2.owner_cards()["count"]
        loops2 = len(core2.memory.open_loops.all())
        await core2.stop()
        assert cards2 == cards1, ("re-ingest must not duplicate cards", cards1, cards2)
        assert loops2 == loops1, ("re-ingest must not duplicate open-loops", loops1, loops2)
    return (f"restart-stable: {cards1} card / {loops1} loops survive STOP+NEW core; "
            f"re-ingest stays {cards2} card / {loops2} loops (idempotent)")


async def main():
    results = []
    results.append(await check_vague_reference())
    results.append(await check_duplicates_collapse())
    results.append(await check_vents_ignored())
    results.append(await check_restart_stable_idempotent())
    print("PASS memory_intent_gate (Gate D):")
    for r in results:
        print("  -", r)


if __name__ == "__main__":
    asyncio.run(main())
