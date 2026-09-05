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
from overnight.is_the_brain_live import evaluate_rules, evaluate_slots  # noqa: E402


# `created` is UTC, exactly as PocketBase stores it. The quiet-hours and
# per-day rules are judged in the OWNER'S zone (CLOCK_TZ, default
# America/Vancouver = UTC-7 in August), so a fixture hour is NOT the hour the
# rule sees. Every timestamp below is UTC with its local time in a comment.
def says(created, decision, goal="", text="lorem", notified=True, link=""):
    # `link` is the reservation a said row was sent on (Omi port 10b): the
    # brain in this tree reserves an uninvited_slot row before Twilio and
    # stamps "uninvited:<owner>:<day>:<n>:said" on the said row.
    return {"kind": "anticipy_says", "created": created, "decision": decision,
            "goal": goal, "text": text, "notified": notified,
            "external_event_id": link}


def slot(day, n, owner=""):
    return f"uninvited:{owner}:{day}:{n}"


# A day that breaks nothing: one errand asked twice (the ceiling ALLOWS two),
# two uninvited nudges inside waking hours, each on its reserved slot, all
# differently worded.
CLEAN = [
    says("2026-08-18 09:12:00", "needs_user", "book the dentist", "Need a date."),
    says("2026-08-18 14:40:00", "needs_user", "book the dentist", "Still need a date."),
    says("2026-08-18 17:05:00", "clock", "bins out", "Bins tonight.",   # 10:05 local
         link=slot("2026-08-18", 1) + ":said"),
    says("2026-08-18 18:30:00", "clock", "call mum", "You said you'd call her.",  # 11:30 local
         link=slot("2026-08-18", 2) + ":said"),
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
    night = CLEAN + [says("2026-08-19 10:14:00", "clock", "bins", "Bins.")]  # 03:14 local
    assert verdict(evaluate_rules(night), "uninvited between") == "FAIL"


def test_his_own_blocked_errand_early_is_not_a_quiet_hours_breach():
    # docs ex 21: "6:59 a.m., HIS booking is blocked on one answer -> text now.
    # His own errand outranks the clock." Counting that as uninvited would make
    # the checker wrong about the product, not just noisy.
    early = CLEAN + [says("2026-08-19 13:59:00", "needs_user",   # 06:59 local
                          "confirm the booking", "One answer and it's held.")]
    assert verdict(evaluate_rules(early), "uninvited between") == "PASS"


def test_a_fourth_uninvited_message_in_one_day_screams():
    busy = CLEAN + [says(f"2026-08-18 {17 + i}:00:00", "clock", f"g{i}", f"nudge {i}")
                    for i in range(UNINVITED_TEXTS_PER_DAY + 1)]
    assert verdict(evaluate_rules(busy), "uninvited message") == "FAIL"


def test_the_budget_is_per_day_not_per_window():
    # Two separate days at the limit is compliance, not a violation; summing the
    # window would flag a system behaving correctly over a long read.
    two_days = []
    for day in ("2026-08-17", "2026-08-18"):
        two_days += [says(f"{day} {17 + i}:00:00", "clock", f"g{i}", f"nudge {day} {i}")
                     for i in range(UNINVITED_TEXTS_PER_DAY)]
    assert verdict(evaluate_rules(two_days), "uninvited message") == "PASS"


def test_the_same_sentence_twice_screams():
    same = [says("2026-08-18 09:00:00", "needs_user", "g", "Should I set it?"),
            says("2026-08-18 10:00:00", "needs_user", "g", "Should I set it?")]
    assert verdict(evaluate_rules(same), "word for word") == "FAIL"


def test_a_message_marked_never_delivered_screams():
    lost = CLEAN + [says("2026-08-18 19:00:00", "clock", "g", "t", notified=False)]  # 12:00 local
    rows = evaluate_rules(lost)
    assert verdict(rows, "never landed") == "FAIL"
    # And it must not appear at all on a clean day, or it is noise rather than
    # a finding.
    assert [r for r in evaluate_rules(CLEAN) if "never landed" in r[1]] == []


# --------------------------------------------------------------------------
# THE CLOCK THE ROWS ARE IN IS NOT THE CLOCK THE PROMISE IS IN.
#
# PocketBase stamps `created` in UTC. The quiet-hours promise is in the
# OWNER'S hours: brain/worker.py compares `datetime.fromtimestamp(now,
# CLOCK_TZ).hour` against CLOCK_QUIET_START/END, and CLOCK_TZ is the owner's
# own zone (worker.py:3078 sets it from their profile). Comparing a UTC hour
# to an owner-local constant is not a rounding error, it is a different
# question — America/Vancouver is UTC-7 in summer, so every message sent
# between 15:00 and 00:59 local reads as "night" to a UTC checker.
#
# Live on 2026-08-24 this reported "2 sent in quiet hours" and concluded the
# deployed brain was not this brain. Both rows were legal: 21:34 and 17:31
# America/Vancouver. A checker that cries wolf for ten hours of every day
# teaches everyone to ignore the one morning it is right.
# --------------------------------------------------------------------------

def owned(created, decision, owner_ref="owner-van", **kw):
    row = says(created, decision, **kw)
    row["owner_ref"] = owner_ref
    return row


VANCOUVER = {"owner-van": "America/Vancouver"}


def test_an_evening_nudge_is_not_a_quiet_hours_breach():
    # 04:34Z is 21:34 in Vancouver — the owner is awake and this is legal.
    # This is one of the two rows that raised the false alarm.
    evening = [owned("2026-08-24 04:34:00.000Z", "clock", goal="the draft",
                     text="Did you get a chance to send it?")]
    assert verdict(evaluate_rules(evening, VANCOUVER), "uninvited between") == "PASS"


def test_an_afternoon_nudge_is_not_a_quiet_hours_breach():
    # 00:31Z is 17:31 in Vancouver. The other false-alarm row.
    afternoon = [owned("2026-08-24 00:31:00.000Z", "clock", goal="the Amy deal",
                       text="Did you follow up?")]
    assert verdict(evaluate_rules(afternoon, VANCOUVER), "uninvited between") == "PASS"


def test_a_nudge_at_one_in_the_morning_HIS_time_still_screams():
    # 08:00Z is 01:00 in Vancouver — genuinely the middle of his night. The
    # timezone fix must not buy quiet by going blind.
    night = [owned("2026-08-24 08:00:00.000Z", "clock", goal="bins", text="Bins.")]
    assert verdict(evaluate_rules(night, VANCOUVER), "uninvited between") == "FAIL"


def test_two_owners_in_different_zones_are_judged_in_their_own_hours():
    # One worker process per account, each with its own CLOCK_TZ. 06:30Z is
    # 23:30 in Vancouver (a breach) and 02:30 in Berlin (also a breach); but
    # 14:00Z is 07:00 Vancouver (a breach, before 08:00) and 16:00 Berlin
    # (fine). A single zone for everyone gets one of them wrong.
    zones = {"van": "America/Vancouver", "ber": "Europe/Berlin"}
    berlin_afternoon = [owned("2026-08-24 14:00:00.000Z", "clock",
                              owner_ref="ber", goal="g", text="Berlin 16:00.")]
    assert verdict(evaluate_rules(berlin_afternoon, zones), "uninvited between") == "PASS"
    vancouver_dawn = [owned("2026-08-24 14:00:00.000Z", "clock",
                            owner_ref="van", goal="g", text="Vancouver 07:00.")]
    assert verdict(evaluate_rules(vancouver_dawn, zones), "uninvited between") == "FAIL"


def test_the_daily_budget_buckets_by_HIS_midnight_not_UTC():
    # UTC-7 means a Vancouver day straddles two UTC dates. Three nudges across
    # one Vancouver afternoon/evening are ONE day at the limit, not two days.
    # Bucketing on the UTC date splits them and reports a compliant day as two
    # quiet ones — the mirror image of the same defect.
    day = [owned("2026-08-24 18:00:00.000Z", "clock", goal="a", text="1"),   # 11:00 local
           owned("2026-08-25 01:00:00.000Z", "clock", goal="b", text="2"),   # 18:00 local
           owned("2026-08-25 03:00:00.000Z", "clock", goal="c", text="3")]   # 20:00 local
    rows = evaluate_rules(day, VANCOUVER)
    assert verdict(rows, "uninvited message") == "PASS"
    detail = [r for r in rows if "uninvited message" in r[1]][0][2]
    assert "busiest day: 3" in detail, f"all three are one local day, got {detail!r}"


def test_an_owner_with_no_timezone_on_file_uses_the_workers_own_default():
    # fetch_owner_timezone returning nothing leaves the worker on CLOCK_TZ's
    # default, so the checker must fall back the same way or it judges by a
    # clock the brain never used.
    from brain.worker import CLOCK_TZ
    import datetime as _dt
    # 08:00Z: night in Vancouver (01:00), which is the shipped default.
    unknown = [owned("2026-08-24 08:00:00.000Z", "clock", owner_ref="nobody",
                     goal="g", text="t")]
    expect = "FAIL" if _dt.datetime(2026, 8, 24, 8, tzinfo=_dt.timezone.utc)\
        .astimezone(CLOCK_TZ).hour >= 22 or _dt.datetime(
            2026, 8, 24, 8, tzinfo=_dt.timezone.utc).astimezone(CLOCK_TZ).hour < 8 else "PASS"
    assert verdict(evaluate_rules(unknown, {}), "uninvited between") == expect


# --------------------------------------------------------------------------
# THE BUDGET IS RESERVED, AND THE ROWS SAY SO (Omi port 10b, 2026-09-05).
#
# Until this date the per-day rule counted decision=="clock" alone — the one
# uninvited kind the brain's own counter excluded — and saw neither parked
# asks nor digests. "Uninvited" is the DOOR a row left through, never its
# words, and every door row must carry the reservation it was sent on.
# --------------------------------------------------------------------------

def linked(created, decision, n, goal="", text="lorem", day="2026-08-18"):
    return says(created, decision, goal, text, link=slot(day, n) + ":said")


def test_a_door_row_without_a_reservation_screams():
    """A clock row with no "uninvited:" link is a door that sent without
    reserving — or a brain older than this tree. Either way, not this brain."""
    unlinked = CLEAN + [says("2026-08-18 19:00:00", "clock", "g", "t")]  # 12:00 local
    assert verdict(evaluate_rules(unlinked), "carries its reservation") == "FAIL"
    assert verdict(evaluate_rules(CLEAN), "carries its reservation") == "PASS"


def test_a_goalless_ask_and_a_digest_count_against_the_day():
    """The parked ambient question (decision ask, EMPTY goal) and the meeting
    digest are uninvited doors. Three clock nudges plus one of either is a
    fourth text."""
    three = [linked(f"2026-08-18 {17 + i}:00:00", "clock", i + 1, f"g{i}", f"nudge {i}")
             for i in range(UNINVITED_TEXTS_PER_DAY)]
    ask = three + [linked("2026-08-18 21:00:00", "ask", 4, "", "which garage?")]
    assert verdict(evaluate_rules(ask), "uninvited message") == "FAIL"
    digest = three + [linked("2026-08-18 21:00:00", "digest", 4, "", "one thing ready")]
    assert verdict(evaluate_rules(digest), "uninvited message") == "FAIL"
    assert verdict(evaluate_rules(three), "uninvited message") == "PASS"


def test_an_invited_question_carries_its_goal_and_does_not_count():
    """A sufficiency question about work HE started carries the job's goal
    and is the opposite of uninvited; counting it once muted every FYI."""
    three = [linked(f"2026-08-18 {17 + i}:00:00", "clock", i + 1, f"g{i}", f"nudge {i}")
             for i in range(UNINVITED_TEXTS_PER_DAY)]
    invited = three + [says("2026-08-18 21:00:00", "ask", "book Cactus Club",
                            "which night?")]
    assert verdict(evaluate_rules(invited), "uninvited message") == "PASS"
    assert verdict(evaluate_rules(invited), "carries its reservation") == "PASS"


def test_the_overheard_receipt_is_seen_only_by_its_link():
    """decision "act" is an invited act OR an overheard-plan receipt; only the
    reservation link tells them apart, so a linked act counts and an
    unlinked one does not — and the link rule does not demand one."""
    three = [linked(f"2026-08-18 {17 + i}:00:00", "clock", i + 1, f"g{i}", f"nudge {i}")
             for i in range(UNINVITED_TEXTS_PER_DAY)]
    receipt = three + [linked("2026-08-18 21:00:00", "act", 4, "book dinner",
                              "caught your plan")]
    assert verdict(evaluate_rules(receipt), "uninvited message") == "FAIL"
    direct = three + [says("2026-08-18 21:00:00", "act", "book dinner", "on it")]
    assert verdict(evaluate_rules(direct), "uninvited message") == "PASS"
    assert verdict(evaluate_rules(direct), "carries its reservation") == "PASS"


def test_a_row_matching_two_door_shapes_counts_once():
    rows = [linked(f"2026-08-18 {17 + i}:00:00", "clock", i + 1, f"g{i}", f"nudge {i}")
            for i in range(UNINVITED_TEXTS_PER_DAY)]
    assert verdict(evaluate_rules(rows), "uninvited message") == "PASS"


def test_the_exempt_doors_have_their_own_rows():
    """The welcome and the deafness notice stay off the budget by name, so a
    regression in THEIR guards must show as itself, never laundered into the
    three."""
    for decision, needle in (("deaf", "deafness notice"), ("welcome", "the welcome")):
        one = CLEAN + [says("2026-08-18 19:00:00", decision, "", "notice")]
        assert verdict(evaluate_rules(one), needle) == "PASS"
        assert verdict(evaluate_rules(one), "uninvited message") == "PASS", \
            "an exempt door must not eat the budget"
        two = one + [says("2026-08-18 20:00:00", decision, "", "notice again")]
        assert verdict(evaluate_rules(two), needle) == "FAIL"


def slot_row(day, n, decision="clock", owner=""):
    return {"kind": "uninvited_slot", "decision": decision,
            "external_event_id": slot(day, n, owner),
            "created": f"{day} 17:00:00"}


def test_slot_rows_are_judged_in_both_directions():
    clean_slots = [slot_row("2026-08-18", 1), slot_row("2026-08-18", 2)]
    rows = evaluate_slots(clean_slots, CLEAN)
    assert rows and [r for r in rows if r[0] == "FAIL"] == []
    # A fourth slot row in one owner-day cannot come from this tree's index.
    four = clean_slots + [slot_row("2026-08-18", 3), slot_row("2026-08-18", 4)]
    assert verdict(evaluate_slots(four, CLEAN), "slot row(s) per owner-day") == "FAIL"
    # Two said rows claiming one slot.
    doubled = CLEAN + [linked("2026-08-18 19:00:00", "clock", 1, "again", "t")]
    assert verdict(evaluate_slots(clean_slots, doubled), "never outnumber") == "FAIL"
    # There is no release in this tree; one means a different brain.
    released = clean_slots + [slot_row("2026-08-18", 3, decision="released")]
    assert verdict(evaluate_slots(released, CLEAN), "ever released") == "FAIL"
    # Days are separate.
    two_days = clean_slots + [slot_row("2026-08-19", n) for n in (1, 2, 3)]
    assert verdict(evaluate_slots(two_days, CLEAN), "slot row(s) per owner-day") == "PASS"
