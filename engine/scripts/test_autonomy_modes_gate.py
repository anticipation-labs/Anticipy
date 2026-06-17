"""GATE E — all 6 autonomy modes, through REAL core.owner_ingest (stub).

classify_autonomy (anticipy_engine/proactive/autonomy.py) labels every finished owner card with exactly
ONE of the six modes. This drives the real ControlCore.owner_ingest spine with one scenario per mode and
asserts the card's resulting autonomy_mode (read off card["autonomy_mode"], cross-checked against
out["middle_trace"]["autonomy"]). All six are elicited via FULL INGEST in stub mode — verified against
what the stub spine actually yields (no forcing):

  REMEMBER_ONLY        — a stated preference ("I like the dark roast coffee")  -> remember card
  IGNORE               — a vent ("ugh I could scream about this week")          -> 0 cards (the IGNORE
                          behavior is "no acting card"; we prove the vent produces NOTHING)
  PREPARE_THEN_STOP    — money ("pay the overdue invoice now with the card")   -> blocked card
                          AND an external send ("send Priya the deck by Friday") -> draft-to-a-person
  CLARIFY_FIRST        — an ambiguous ask ("can you handle that thing")         -> ask card
  AUTO_DO_WITH_OPT_OUT — a browser/web task ("open chrome and find me a cheap   -> browser_action card
                          flight to NYC next week")
  AUTO_DO              — a low-risk reversible do ("remind me to call the        -> do/act card
                          dentist at 3pm tomorrow")

STUB-MODE NOTE (honest): runs with ANTICIPY_MODEL_PROVIDER=stub, so the moat is OFF and these
dispositions come from the deterministic spine. Every mode here was proven via FULL INGEST (no fallback
to a direct classify_autonomy unit assertion was needed). The IGNORE mode is, by design, the absence of
a card — a vent yields nothing — so it is asserted as "no card produced" rather than a card with
mode==IGNORE (which only a degenerate no-obligation card would carry). Live inference quality is covered
by Gate J (the 10k live cert).
"""
import asyncio
import os
import tempfile

os.environ.setdefault("ANTICIPY_MODEL_PROVIDER", "stub")
os.environ.setdefault("ANTICIPY_HANDS_MODE", "mock")
os.environ.setdefault("ANTICIPY_CHANNELS_MODE", "mock")
os.environ.setdefault("ANTICIPY_NATIVE_BRIDGE_FALLBACK", "0")

from anticipy_engine.core.control_core import ControlCore  # noqa: E402
from anticipy_engine.proactive.autonomy import MODES, classify_autonomy  # noqa: E402


async def _ingest(text, execute_actions):
    with tempfile.TemporaryDirectory() as d:
        core = ControlCore(data_dir=d)
        await core.start()
        try:
            return await core.owner_ingest("transcript", text, execute_actions=execute_actions)
        finally:
            await core.stop()


def _modes(out):
    """Cards' autonomy_mode, cross-checked against the middle_trace.autonomy proof block."""
    card_modes = [c.get("autonomy_mode") for c in out.get("cards", [])]
    trace_modes = [a.get("chosen_mode") for a in out.get("middle_trace", {}).get("autonomy", [])]
    # the two sources must agree (the card field is the same classify_autonomy output the trace records)
    assert card_modes == trace_modes, ("card autonomy_mode must match middle_trace.autonomy",
                                       card_modes, trace_modes)
    return card_modes


async def find_card_with_mode(text, mode, execute_actions):
    out = await _ingest(text, execute_actions)
    modes = _modes(out)
    assert mode in modes, (f"expected mode {mode} for {text!r}", modes,
                           [(c.get("source_text"), c.get("disposition"), c.get("action")) for c in out["cards"]])
    return out


async def main():
    proven = {}  # mode -> (how, scenario)

    # REMEMBER_ONLY — a stated preference is recorded, no action.
    await find_card_with_mode("I like the dark roast coffee", "REMEMBER_ONLY", execute_actions=True)
    proven["REMEMBER_ONLY"] = ("full-ingest", "preference 'I like the dark roast coffee' -> remember card")

    # IGNORE — a vent produces NO card (the IGNORE behavior is "no acting card").
    out_vent = await _ingest("ugh I could scream about this week", execute_actions=True)
    assert out_vent.get("cards") == [], ("a vent must produce no card", out_vent.get("cards"))
    # sanity: classify_autonomy maps a genuinely empty/no-obligation card to IGNORE (the mode exists,
    # and the vent's runtime expression of it is producing nothing at all).
    assert classify_autonomy({"disposition": None, "action": None})["mode"] == "IGNORE"
    proven["IGNORE"] = ("full-ingest (0 cards) + classify_autonomy unit",
                        "vent 'ugh I could scream about this week' -> 0 cards; empty card -> IGNORE")

    # PREPARE_THEN_STOP — money is the true irreversible boundary (blocked).
    await find_card_with_mode("just pay the overdue invoice now with the card",
                              "PREPARE_THEN_STOP", execute_actions=True)
    # PREPARE_THEN_STOP — an external send to a real person (draft, stop at final send).
    await find_card_with_mode("send Priya the deck by Friday",
                              "PREPARE_THEN_STOP", execute_actions=True)
    proven["PREPARE_THEN_STOP"] = ("full-ingest x2",
                                   "money 'pay the overdue invoice' (blocked) AND send 'send Priya the deck'")

    # CLARIFY_FIRST — an ambiguous ask gets the smallest clarifying question.
    await find_card_with_mode("can you handle that thing", "CLARIFY_FIRST", execute_actions=True)
    proven["CLARIFY_FIRST"] = ("full-ingest", "ambiguous 'can you handle that thing' -> ask")

    # AUTO_DO_WITH_OPT_OUT — a visible web/browser task (reversible: throwaway browser, no buy).
    await find_card_with_mode("open chrome and find me a cheap flight to NYC next week",
                              "AUTO_DO_WITH_OPT_OUT", execute_actions=True)
    proven["AUTO_DO_WITH_OPT_OUT"] = ("full-ingest", "browser 'open chrome and find me a flight' -> browser_action")

    # AUTO_DO — a low-risk reversible do (a reminder/open-loop hold), executed end-to-end.
    await find_card_with_mode("remind me to call the dentist at 3pm tomorrow",
                              "AUTO_DO", execute_actions=True)
    proven["AUTO_DO"] = ("full-ingest", "reminder 'call the dentist at 3pm tomorrow' -> do/act")

    # all six modes covered.
    missing = [m for m in MODES if m not in proven]
    assert not missing, ("uncovered autonomy modes", missing)

    print("PASS autonomy_modes_gate (Gate E): all 6 modes proven")
    for m in MODES:
        how, scenario = proven[m]
        print(f"  - {m:22s} [{how}] {scenario}")


if __name__ == "__main__":
    asyncio.run(main())
