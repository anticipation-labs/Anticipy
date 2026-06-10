"""Due-time grounding test — spoken phrases -> absolute timestamps, anchored to
the utterance clock (meta observed_at), never engine time.

Pure rules, deterministic, zero model calls. Covers: relative ("in an hour"),
day words (tomorrow/weekday), clock times (am/pm, ambiguous bare hours with the
documented daytime bias), conservative None cases, and the capture wiring
(open_loop fields gain due_ts + remind_ts = due-15min; other drawers never do).
Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_duetime.py
"""
import datetime as dt
import tempfile
from pathlib import Path
from zoneinfo import ZoneInfo

from anticipy_engine.live_memory.capture import Capturer
from anticipy_engine.live_memory.duetime import (REMIND_LEAD_S, anchor_from_meta,
                                                 parse_due)
from anticipy_engine.memory import Memory

TZ = ZoneInfo("America/Los_Angeles")
# Wednesday 2026-06-10, 08:00 local — a fixed anchor so every case is reproducible
WED_8AM = dt.datetime(2026, 6, 10, 8, 0, tzinfo=TZ)
WED_5PM = dt.datetime(2026, 6, 10, 17, 0, tzinfo=TZ)


def expect(text, anchor, want):
    got = parse_due(text, anchor)
    if want is None:
        return None if got is None else f"{text!r} @ {anchor:%a %H:%M}: wanted None, got {got}"
    if got is None:
        return f"{text!r} @ {anchor:%a %H:%M}: wanted {want}, got None"
    if abs((got - want).total_seconds()) > 1:
        return f"{text!r} @ {anchor:%a %H:%M}: wanted {want}, got {got}"
    return None


def main():
    d = dt.datetime
    cases = [
        # relative
        ("call the bank in an hour", WED_8AM, WED_8AM + dt.timedelta(hours=1)),
        ("remind me in 30 minutes", WED_8AM, WED_8AM + dt.timedelta(minutes=30)),
        ("follow up in 2 days", WED_8AM, WED_8AM + dt.timedelta(days=2)),
        ("renew it in a week", WED_8AM, WED_8AM + dt.timedelta(days=7)),
        # tomorrow
        ("send it tomorrow 9am", WED_8AM, d(2026, 6, 11, 9, 0, tzinfo=TZ)),
        ("remind me tomorrow", WED_8AM, d(2026, 6, 11, 9, 0, tzinfo=TZ)),
        ("remind me at 9pm tomorrow", WED_8AM, d(2026, 6, 11, 21, 0, tzinfo=TZ)),
        # weekdays (anchor is Wednesday)
        ("submit the report friday at 2pm", WED_8AM, d(2026, 6, 12, 14, 0, tzinfo=TZ)),
        ("pay rent by friday", WED_8AM, d(2026, 6, 12, 9, 0, tzinfo=TZ)),
        ("call mom on wednesday", WED_8AM, d(2026, 6, 10, 9, 0, tzinfo=TZ)),   # today, 9am still ahead
        ("call mom on wednesday", WED_5PM, d(2026, 6, 17, 9, 0, tzinfo=TZ)),   # 9am gone -> next week
        # clock times
        ("remind me to stretch at 4:57am", d(2026, 6, 10, 4, 55, tzinfo=TZ),
         d(2026, 6, 10, 4, 57, tzinfo=TZ)),                                    # the gate-S2 shape
        ("remind me at 3pm", WED_5PM, d(2026, 6, 11, 15, 0, tzinfo=TZ)),       # past -> next day
        ("call him at 3", WED_8AM, d(2026, 6, 10, 15, 0, tzinfo=TZ)),          # bare 3 -> 3pm today
        ("call him at 3", WED_5PM, d(2026, 6, 11, 15, 0, tzinfo=TZ)),          # 5pm said -> 3pm tomorrow, not 3am
        ("the standup is at 9", WED_8AM, d(2026, 6, 10, 9, 0, tzinfo=TZ)),
        ("review at 15:30", WED_8AM, d(2026, 6, 10, 15, 30, tzinfo=TZ)),       # 24h clock
        # day-part words
        ("take the trash out tonight", WED_8AM, d(2026, 6, 10, 20, 0, tzinfo=TZ)),
        ("take the trash out tonight", d(2026, 6, 10, 21, 0, tzinfo=TZ), None),  # already past 8pm
        ("finish the memo by eod", WED_8AM, d(2026, 6, 10, 17, 0, tzinfo=TZ)),
        ("lunch with Ana at noon", WED_8AM, d(2026, 6, 10, 12, 0, tzinfo=TZ)),
        ("lunch with Ana at noon", WED_5PM, d(2026, 6, 11, 12, 0, tzinfo=TZ)),
        # conservative: no confident ground -> None
        ("ugh, I should really call my landlord someday", WED_8AM, None),
        ("I need to finish the deck", WED_8AM, None),
        ("pick up the package when I get a chance", WED_8AM, None),
    ]
    fails = [e for e in (expect(*c) for c in cases) if e]

    # anchor_from_meta: tz-aware passthrough, naive + timezone name, missing -> ~now
    a = anchor_from_meta({"observed_at": "2026-06-10T08:00:00-07:00"})
    if a != WED_8AM:
        fails.append(f"anchor_from_meta tz-aware: {a} != {WED_8AM}")
    a = anchor_from_meta({"observed_at": "2026-06-10T08:00:00", "timezone": "America/Los_Angeles"})
    if a.utcoffset() != WED_8AM.utcoffset() or a.replace(tzinfo=None) != WED_8AM.replace(tzinfo=None):
        fails.append(f"anchor_from_meta naive+zone: {a}")
    a = anchor_from_meta(None)
    if a.tzinfo is None or abs((a - dt.datetime.now().astimezone()).total_seconds()) > 5:
        fails.append(f"anchor_from_meta default should be ~local now: {a}")

    # capture wiring: open_loop gets due_ts + remind_ts; non-commitments never do
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-duetime-"))
    cap = Capturer(Memory(data_dir=tmp))
    meta = {"observed_at": "2026-06-10T04:55:00-07:00"}
    r = cap.capture("remind me to [Anticipy test] stretch at 4:57am", source="app", meta=meta)
    f = r["item"].fields if r.get("kept") else {}
    want_due = dt.datetime(2026, 6, 10, 4, 57, tzinfo=TZ).timestamp()
    if r.get("kind") != "open_loop" or abs(f.get("due_ts", 0) - want_due) > 1:
        fails.append(f"capture grounding: kind={r.get('kind')} fields={f}")
    elif abs(f["remind_ts"] - (want_due - REMIND_LEAD_S)) > 1:
        fails.append(f"remind_ts should be due-15min: {f}")
    r = cap.capture("I need to email the landlord eventually", source="app", meta=meta)
    if r.get("kind") == "open_loop" and "due_ts" in r["item"].fields:
        fails.append("ungroundable commitment must not get a due_ts")
    r = cap.capture("nice weather at 3pm today", source="app", meta=meta)
    if r.get("kind") == "open_loop":
        fails.append("non-commitment line must not become an open loop")

    print("==== DUE-TIME GROUNDING ====")
    print(f"  {len(cases)} parse cases + anchor + capture wiring")
    if fails:
        print("==== FAIL ====")
        for f_ in fails:
            print("   -", f_)
        raise SystemExit(1)
    print("==== PASS ====")


if __name__ == "__main__":
    main()
