"""Regression: GoogleCalendar.ListEvents@3.x REQUIRES a time window.

The live read-back called ListEvents with NO min_end_datetime/max_start_datetime, so Arcade
400'd it — and because the read-back could never confirm, EVERY calendar write (a real event
created on the user's calendar) was wrongly reported as "not done". This pins that the engine
now always supplies the required window, both on a direct list and on the create_event read-back,
and that a caller-supplied window is never overridden.

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_api_calendar_window.py
"""
from anticipy_engine.core.envelopes import Job
from anticipy_engine.hands.api_hand import ApiHand, _parse_iso_dt

WIN = ("min_end_datetime", "max_start_datetime")


def _job(intent, args):
    return Job(intent=intent, args=args)


def main():
    # 1) a direct calendar list (read_calendar -> ListEvents) gets the required window filled in
    ti = ApiHand._tool_input(_job("read_calendar", {}))
    assert all(k in ti for k in WIN), ti
    assert _parse_iso_dt(ti["min_end_datetime"]) < _parse_iso_dt(ti["max_start_datetime"]), ti

    # the window ALWAYS sets a high max_results — the default ~10-result cap was the second half of
    # the miss (a wide-window read-back never saw a near-future event behind today's events)
    assert ti.get("max_results", 0) >= 100, ti

    # 2) the create_event READ-BACK (the bug) supplies the window, TIGHT around the event so the
    #    just-created event is inside ListEvents' result cap
    start, end = "2026-09-10T16:00:00+00:00", "2026-09-10T16:30:00+00:00"
    rb = ApiHand._readback_input(_job("create_event", {"start_datetime": start, "end_datetime": end}), "evid123")
    assert all(k in rb for k in WIN), rb
    lo, hi, s = _parse_iso_dt(rb["min_end_datetime"]), _parse_iso_dt(rb["max_start_datetime"]), _parse_iso_dt(start)
    assert lo < s < hi, ("the window must contain the created event", rb)
    assert (hi - lo).days <= 3 and rb.get("max_results", 0) >= 100, ("read-back window must be TIGHT + uncapped", rb)

    # 2b) THE execute_owner_task FIX: the request args DON'T carry start_datetime, but the CreateEvent
    #     RESPONSE does ({"event": {"start": {"dateTime": ...}}}). The read-back must anchor on THAT,
    #     not fall back to a wide window the 10-cap would defeat.
    wv = {"event": {"id": "e1", "start": {"dateTime": "2027-03-04T09:00:00-08:00", "timeZone": "America/Vancouver"}}}
    rb2 = ApiHand._readback_input(_job("create_event", {"task_text": "set up a block"}), "e1", wv)
    es = _parse_iso_dt("2027-03-04T09:00:00-08:00")
    lo2, hi2 = _parse_iso_dt(rb2["min_end_datetime"]), _parse_iso_dt(rb2["max_start_datetime"])
    assert lo2 < es < hi2 and (hi2 - lo2).days <= 3, ("must anchor the window on the WRITE RESPONSE start", rb2)

    # 3) a window the caller already supplied is NOT overridden
    custom = {"min_end_datetime": "2030-01-01T00:00:00+00:00", "max_start_datetime": "2030-02-01T00:00:00+00:00"}
    ti2 = ApiHand._tool_input(_job("read_calendar", dict(custom)))
    assert ti2["min_end_datetime"] == custom["min_end_datetime"], ti2

    # 4) non-calendar intents are untouched (no spurious window)
    assert ApiHand._readback_input(_job("send_email", {"recipient": "x@y.z"}), "id") == {}

    # 5) the iso parser: tz-aware out, None on junk, naive -> UTC
    assert _parse_iso_dt("2026-09-10T16:00:00Z").tzinfo is not None
    assert _parse_iso_dt("not a date") is None and _parse_iso_dt(None) is None
    assert _parse_iso_dt("2026-09-10T16:00:00").tzinfo is not None  # naive coerced to UTC

    print("PASS api_calendar_window: ListEvents always gets its required window (direct + read-back), "
          "tight around the event, caller window preserved — the calendar read-back can confirm again")


if __name__ == "__main__":
    main()
