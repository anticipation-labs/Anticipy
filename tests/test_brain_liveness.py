"""The liveness checker must be able to fail, and to pass.

A checker that has only ever been seen red on real data is indistinguishable
from one that is hard-coded red; a checker that has only ever been seen green is
worse. So every rule gets both directions, driven by synthetic rows rather than
production.

The clean fixture is deliberately a REALISTIC clean day, not an empty list: an
empty list passes every rule vacuously and would prove nothing about the rules.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain.worker import STUCK_ASKS_CEILING, UNINVITED_TEXTS_PER_DAY  # noqa: E402
from overnight.is_the_brain_live import evaluate_rules  # noqa: E402


def says(created, decision, goal="", text="lorem", notified=True):
    return {"kind": "anticipy_says", "created": created, "decision": decision,
            "goal": goal, "text": text, "notified": notified}


# A day that breaks nothing: one errand asked twice (the ceiling ALLOWS two),
# two uninvited nudges inside waking hours, all differently worded.
CLEAN = [
    says("2026-08-18 09:12:00", "needs_user", "book the dentist", "Need a date."),
    says("2026-08-18 14:40:00", "needs_user", "book the dentist", "Still need a date."),
    says("2026-08-18 10:05:00", "clock", "bins out", "Bins tonight."),
    says("2026-08-18 18:30:00", "clock", "call mum", "You said you'd call her."),
    says("2026-08-18 11:00:00", "done", "book the dentist", "Booked for Tuesday."),
]


def verdict(rows, needle):
    """The status of the one rule whose name contains `needle`."""
    hits = [r for r in rows if needle in r[1]]
    assert len(hits) == 1, f"expected exactly one rule matching {needle!r}, got {hits}"
    return hits[0][0]


def test_a_clean_day_passes_every_rule():
    rows = evaluate_rules(CLEAN)
    assert rows, "no rules were evaluated at all"
    assert [r for r in rows if r[0] == "FAIL"] == []


def test_exactly_at_the_ceiling_is_allowed():
    # STUCK_ASKS_CEILING = 2 means two asks are the promise being KEPT. An
    # off-by-one here would report every healthy re-ask as a production breach
    # and train everyone to ignore the checker.
    at_limit = [says(f"2026-08-18 0{i}:00:00", "needs_user", "one goal", f"ask {i}")
                for i in range(STUCK_ASKS_CEILING)]
    assert verdict(evaluate_rules(at_limit), "asked more than") == "PASS"


def test_one_ask_past_the_ceiling_screams():
    over = [says(f"2026-08-18 0{i}:00:00", "needs_user", "one goal", f"ask {i}")
            for i in range(STUCK_ASKS_CEILING + 1)]
    assert verdict(evaluate_rules(over), "asked more than") == "FAIL"


def test_the_real_incident_is_caught():
    # The 2026-08-18 alarm job: 18 asks, one goal, every wording different --
    # which is why wording-based dedupe missed it and this counts the goal.
    incident = [says(f"2026-08-18 {h:02d}:21:00", "needs_user",
                     "set alarm for 7:10 AM on Wednesday, August 19, 2026",
                     f"differently worded ask number {h}")
                for h in range(6, 24)]
    rows = evaluate_rules(incident)
    assert verdict(rows, "asked more than") == "FAIL"
    detail = [r for r in rows if "asked more than" in r[1]][0][2]
    assert "18x" in detail, f"the count must be reported, got {detail!r}"


def test_rewording_the_obstacle_does_not_launder_the_count():
    # docs ex 24: "the wording of the obstacle changing does NOT reset it."
    reworded = [says("2026-08-18 01:00:00", "needs_user", "g", "Need a date."),
                says("2026-08-18 02:00:00", "needs_user", "g", "What day works?"),
                says("2026-08-18 03:00:00", "needs_user", "g", "Which date?")]
    assert verdict(evaluate_rules(reworded), "asked more than") == "FAIL"


def test_a_clock_nudge_at_three_in_the_morning_screams():
    night = CLEAN + [says("2026-08-19 03:14:00", "clock", "bins", "Bins.")]
    assert verdict(evaluate_rules(night), "uninvited between") == "FAIL"


def test_his_own_blocked_errand_early_is_not_a_quiet_hours_breach():
    # docs ex 21: "6:59 a.m., HIS booking is blocked on one answer -> text now.
    # His own errand outranks the clock." Counting that as uninvited would make
    # the checker wrong about the product, not just noisy.
    early = CLEAN + [says("2026-08-19 06:59:00", "needs_user",
                          "confirm the booking", "One answer and it's held.")]
    assert verdict(evaluate_rules(early), "uninvited between") == "PASS"


def test_a_fourth_uninvited_message_in_one_day_screams():
    busy = CLEAN + [says(f"2026-08-18 1{i}:00:00", "clock", f"g{i}", f"nudge {i}")
                    for i in range(UNINVITED_TEXTS_PER_DAY + 1)]
    assert verdict(evaluate_rules(busy), "uninvited message") == "FAIL"


def test_the_budget_is_per_day_not_per_window():
    # Two separate days at the limit is compliance, not a violation; summing the
    # window would flag a system behaving correctly over a long read.
    two_days = []
    for day in ("2026-08-17", "2026-08-18"):
        two_days += [says(f"{day} 1{i}:00:00", "clock", f"g{i}", f"nudge {day} {i}")
                     for i in range(UNINVITED_TEXTS_PER_DAY)]
    assert verdict(evaluate_rules(two_days), "uninvited message") == "PASS"


def test_the_same_sentence_twice_screams():
    same = [says("2026-08-18 09:00:00", "needs_user", "g", "Should I set it?"),
            says("2026-08-18 10:00:00", "needs_user", "g", "Should I set it?")]
    assert verdict(evaluate_rules(same), "word for word") == "FAIL"


def test_a_message_marked_never_delivered_screams():
    lost = CLEAN + [says("2026-08-18 12:00:00", "clock", "g", "t", notified=False)]
    rows = evaluate_rules(lost)
    assert verdict(rows, "never landed") == "FAIL"
    # And it must not appear at all on a clean day, or it is noise rather than
    # a finding.
    assert [r for r in evaluate_rules(CLEAN) if "never landed" in r[1]] == []
