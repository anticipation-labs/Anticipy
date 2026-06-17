"""GATE MIDDLE-1 — intent-shaped memory handoff (deterministic).

Proves the hard middle on the exact scenario: a vague reference resolves to the RIGHT intent thread
(Jarvis standing desk, not Mia pickup), a bare follow-up attaches to the right thread (the Sam deck,
not the desk/pickup), preferences/vents are classified out of the action path, and an ambiguous
reference is NOT guessed. Pure-Python, no model — so it is reliable and re-runnable.
"""
import os

os.environ.setdefault("ANTICIPY_MODEL_PROVIDER", "stub")

from anticipy_engine.proactive.intent_threads import (  # noqa: E402
    build_threads, classify, resolve_reference, rank_referents,
)

LINES = [
    "Mia pickup moved to 3.",                                        # 0 action (pickup)
    "The Jarvis standing desk is the one I liked. Don't buy it yet.",# 1 preference (desk referent)
    "I hate this coffee machine, I'm moving to the woods.",          # 2 vent
    "Can you put that desk thing in the cart?",                      # 3 action w/ vague ref -> desk
    "If I win the lottery I'm buying an island.",                    # 4 vent
    "I told Sam I'd send the revised deck Friday.",                  # 5 action (Sam deck thread)
    "Actually remind me before I send it.",                          # 6 followup -> Sam deck
]


def main():
    threads = build_threads(LINES)

    # classification: vents and preference are OUT of the action path
    assert classify(LINES[1]) == "preference", classify(LINES[1])
    assert classify(LINES[2]) == "vent", classify(LINES[2])
    assert classify(LINES[4]) == "vent", classify(LINES[4])
    assert classify(LINES[6]) == "followup", classify(LINES[6])
    assert classify(LINES[5]) == "action", classify(LINES[5])

    # 1) "that desk thing" -> Jarvis standing desk, NOT Mia pickup, NOT coffee.
    resolved, tr = resolve_reference(LINES[3], threads, self_idx=3)
    assert "Jarvis" in (tr["chosen"] or ""), tr
    assert "standing desk" in resolved.lower(), resolved
    assert "Jarvis standing desk" in resolved, resolved
    assert "pickup" not in (tr["chosen"] or "").lower(), tr
    # the pickup thread was considered and REJECTED; the coffee VENT is excluded from candidates entirely
    assert any("pickup" in r.lower() for r in tr["rejected"]), tr
    assert all("coffee" not in c["text"].lower() for c in tr["candidates"]), "vent must not be a referent candidate"

    # 2) bare follow-up "send it" -> the Sam deck thread (sendable), not the desk/pickup.
    resolved2, tr2 = resolve_reference(LINES[6], threads, self_idx=6)
    assert tr2["chosen"] is not None and "deck" in tr2["chosen"].lower(), tr2
    assert "deck" in resolved2.lower() and "desk" not in resolved2.lower(), resolved2

    # 3) a genuinely AMBIGUOUS bare reference with no sendable/object cue is NOT guessed.
    amb_threads = build_threads(["Call the dentist.", "Email the vendor.", "Handle that."])
    _, tr3 = resolve_reference("Handle that.", amb_threads, self_idx=2)
    assert tr3["chosen"] is None, ("ambiguous ref must not be guessed", tr3)

    # 4) the proof fields exist for the desk resolution.
    tr_full = rank_referents(LINES[3], threads, self_idx=3)
    assert tr_full["candidates"] and tr_full["chosen"] and tr_full["rejected"], tr_full

    print("PASS memory_handoff: 'that desk thing'->Jarvis standing desk (pickup/coffee rejected); "
          "'send it'->Sam deck; ambiguous ref not guessed; vents/preference classified out")


if __name__ == "__main__":
    main()
