"""Track A — the JUDGE (the boss; reads reality). Checker side.

It logs into the REAL Google Calendar (Arcade ListEvents) and confirms the worker's claimed event
actually exists there, by its real Arcade id, with the claimed summary + time. Pass/fail comes from
the real calendar, never from the worker's say-so.

LAW #3: this file NEVER imports/reads the worker. LAW #4: `self_prove()` plants a real pass AND a
fake and REQUIRES the judge to pass the real one and FAIL the fake — run it before trusting any lap.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta

from arcadepy import Arcade


def _client() -> Arcade:
    return Arcade(api_key=os.environ["ARCADE_API_KEY"])


def _uid() -> str:
    return os.environ["ARCADE_USER_ID"]


def _list_window(start: datetime, span_days: int = 1) -> list:
    """Independent reality read: events overlapping [start-span, start+span]."""
    lo = (start - timedelta(days=span_days))
    hi = (start + timedelta(days=span_days))
    resp = _client().tools.execute(tool_name="GoogleCalendar.ListEvents", user_id=_uid(),
                                   input={"min_end_datetime": lo.isoformat(), "max_start_datetime": hi.isoformat()})
    out = getattr(resp, "output", None)
    val = getattr(out, "value", None) if out else None
    if not isinstance(val, dict):
        return []
    return val.get("events", []) or []


def confirm(claim: dict) -> dict:
    """Return {pass, reason, evidence}. Pass ONLY if the real calendar contains the claimed event id."""
    if claim.get("status") != "created" or not claim.get("event_id"):
        return {"pass": False, "reason": f"worker did not create an event (status={claim.get('status')})",
                "evidence": None}
    try:
        start = datetime.fromisoformat(str(claim["start_datetime"]))
    except Exception as e:
        return {"pass": False, "reason": f"claim has no parseable start ({e})", "evidence": None}
    want_id = claim["event_id"]
    want_summary = (claim.get("summary") or "").strip()
    try:
        events = _list_window(start)
    except Exception as e:
        return {"pass": False, "reason": f"calendar read failed: {type(e).__name__} {e}", "evidence": None}
    for ev in events:
        if ev.get("id") == want_id:
            real_summary = (ev.get("summary") or "").strip()
            if want_summary and real_summary != want_summary:
                return {"pass": False, "reason": f"id present but summary mismatch (real={real_summary!r})",
                        "evidence": ev}
            return {"pass": True, "reason": "event id found in the real calendar with matching summary",
                    "evidence": {"id": ev.get("id"), "summary": ev.get("summary"),
                                 "start": (ev.get("start") or {}).get("dateTime"),
                                 "htmlLink": ev.get("htmlLink")}}
    return {"pass": False, "reason": f"claimed id {want_id} not found in the real calendar", "evidence": None}


def self_prove() -> bool:
    """Plant a real pass + a fake; the judge MUST pass the real and FAIL the fake. Cleans up after."""
    uid, client = _uid(), _client()
    start = (datetime.now().astimezone() + timedelta(days=1)).replace(hour=11, minute=0, second=0, microsecond=0)
    end = start + timedelta(minutes=30)
    summary = "[Anticipy test] judge self-prove — auto-deleted"
    resp = client.tools.execute(tool_name="GoogleCalendar.CreateEvent", user_id=uid,
                                input={"summary": summary, "start_datetime": start.isoformat(),
                                       "end_datetime": end.isoformat()})
    val = getattr(getattr(resp, "output", None), "value", None) or {}
    real_id = (val.get("event") or {}).get("id")
    if not real_id:
        print("  self-prove SETUP FAILED: could not create the planted real event"); return False

    real_claim = {"status": "created", "event_id": real_id, "summary": summary,
                  "start_datetime": start.isoformat()}
    fake_claim = {"status": "created", "event_id": "fake-this-id-does-not-exist-000", "summary": summary,
                  "start_datetime": start.isoformat()}
    real_v = confirm(real_claim)
    fake_v = confirm(fake_claim)

    # cleanup the planted event
    try:
        client.tools.execute(tool_name="GoogleCalendar.DeleteEvent", user_id=uid, input={"event_id": real_id})
    except Exception:
        pass

    ok = real_v["pass"] is True and fake_v["pass"] is False
    print(f"  planted REAL  -> {'PASS' if real_v['pass'] else 'FAIL'}  ({real_v['reason']})")
    print(f"  planted FAKE  -> {'PASS' if fake_v['pass'] else 'FAIL'}  ({fake_v['reason']})")
    print(f"  JUDGE {'TRUSTWORTHY (caught the fake)' if ok else 'BROKEN — do not trust'}")
    return ok


if __name__ == "__main__":
    import sys
    from anticipy_engine.core.env import load_local_env
    load_local_env()
    sys.exit(0 if self_prove() else 1)
