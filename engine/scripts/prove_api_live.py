#!/usr/bin/env python3
"""Gate G (API arm) live proof.

Drives the REAL Arcade client the same way engine/anticipy_engine/hands/api_hand.py
does (same INTENT_MAP tool names, same independent read-back discipline) to prove a
genuine round trip with INDEPENDENT read-back:

  1. CALENDAR: create event -> independent ListEvents read-back asserts id present ->
     DeleteEvent -> second independent read-back asserts id is GONE.
  2. GMAIL: create a DRAFT (never send) -> independent ListDraftEmails asserts present.

SAFETY: Gmail uses WriteDraftEmail only (never SendEmail). The calendar test event is
deleted after read-back. No money. No other recipients (draft addressed to ADMIN_EMAIL).

AUTH: if a tool's authorize() status != "completed", we DO NOT fail silently or write a
phantom proof — we capture the OAuth connect_url and STOP that tool's proof, so the
foreman can open it for the owner to tap. Whatever IS authorized is still proven.

Run:
  set -a; source .env.local; set +a
  PYTHONPATH=engine ANTICIPY_HANDS_MODE=live engine/.venv/bin/python engine/scripts/prove_api_live.py
"""
from __future__ import annotations

import datetime
import json
import os
import sys
from pathlib import Path

from arcadepy import Arcade

# Reuse the production hand's tool names + read-back map so the proof exercises the SAME
# contract the engine ships with (no invented tool names).
from anticipy_engine.hands.api_hand import INTENT_MAP, READ_BACK, ApiHand

REPO = Path(__file__).resolve().parents[2]
PROOF_PATH = REPO / "docs" / "guarantee" / "proof" / "G_api.json"


def _exec(client: Arcade, tool: str, inp: dict, uid: str):
    """One real execute(); returns (value, error). Mirrors api_hand's value/error unwrap."""
    resp = client.tools.execute(tool_name=tool, input=inp, user_id=uid)
    out = getattr(resp, "output", None)
    value = getattr(out, "value", None) if out is not None else None
    err = getattr(out, "error", None) if out is not None else None
    return value, err


def _auth_or_url(client: Arcade, tool: str, uid: str):
    """Return (completed: bool, connect_url: str|None). Never silently proceeds on pending."""
    a = client.tools.authorize(tool_name=tool, user_id=uid)
    status = getattr(a, "status", None)
    url = getattr(a, "url", None)
    return (status == "completed"), url, status


def prove_calendar(client: Arcade, uid: str) -> dict:
    """Create -> independent read-back -> delete -> read-back-gone. Returns a result dict."""
    create_tool = INTENT_MAP["create_event"]            # GoogleCalendar.CreateEvent
    list_tool = READ_BACK["create_event"]               # GoogleCalendar.ListEvents
    delete_tool = "GoogleCalendar.DeleteEvent"          # direct Arcade tool (not a wired intent)

    completed, url, status = _auth_or_url(client, create_tool, uid)
    if not completed:
        return {"pass": False, "step": "auth", "connect_url": url, "status": status,
                "detail": f"calendar not authorized (status={status}); connect_url captured"}

    # Concrete window: tomorrow 15:00-15:30 LOCAL time, RFC3339 with offset.
    local_tz = datetime.datetime.now().astimezone().tzinfo
    tomorrow = (datetime.datetime.now(local_tz) + datetime.timedelta(days=1)).date()
    start = datetime.datetime.combine(tomorrow, datetime.time(15, 0), tzinfo=local_tz)
    end = datetime.datetime.combine(tomorrow, datetime.time(15, 30), tzinfo=local_tz)
    start_iso, end_iso = start.isoformat(), end.isoformat()
    title = "[Anticipy test] gate G calendar"

    create_value, err = _exec(client, create_tool, {
        "summary": title, "start_datetime": start_iso, "end_datetime": end_iso,
        "description": "[Anticipy test] Gate G live proof — auto-deleted after read-back.",
    }, uid)
    if err or not create_value:
        return {"pass": False, "step": "create", "error": str(err or "empty output")}

    event_id = ApiHand._find_id(create_value)
    if not event_id:
        return {"pass": False, "step": "create", "error": "no event id in CreateEvent output",
                "raw": str(create_value)[:300]}

    # INDEPENDENT read-back #1: ListEvents in a tight window around the created start.
    window = ApiHand._listevents_window(ApiHand._event_start_from_write(create_value) or start_iso)
    list_value, err = _exec(client, list_tool, window, uid)
    if err or list_value is None:
        return {"pass": False, "step": "readback_create", "event_id": event_id,
                "error": str(err or "empty output")}
    present = ApiHand._read_contains_id(list_value if isinstance(list_value, dict)
                                        else {"value": list_value}, event_id)
    if not present:
        return {"pass": False, "step": "readback_create", "event_id": event_id,
                "error": "created event id NOT re-observed by independent ListEvents read-back"}

    # DELETE the test event (cleanup) — direct Arcade tool call by event id.
    del_completed, del_url, del_status = _auth_or_url(client, delete_tool, uid)
    if not del_completed:
        # Created+verified, but cannot delete without a grant. Report honestly; event stays.
        return {"pass": False, "step": "delete_auth", "event_id": event_id,
                "connect_url": del_url, "status": del_status,
                "detail": f"created+read-back OK (id={event_id}) but DeleteEvent not authorized "
                          f"(status={del_status}); event NOT deleted — manual cleanup needed"}
    del_value, err = _exec(client, delete_tool, {"event_id": event_id}, uid)
    if err:
        return {"pass": False, "step": "delete", "event_id": event_id, "error": str(err)}

    # INDEPENDENT read-back #2: confirm the event is GONE.
    list_after, err = _exec(client, list_tool, window, uid)
    if err or list_after is None:
        return {"pass": False, "step": "readback_delete", "event_id": event_id,
                "error": str(err or "empty output")}
    still_present = ApiHand._read_contains_id(list_after if isinstance(list_after, dict)
                                              else {"value": list_after}, event_id)
    if still_present:
        return {"pass": False, "step": "readback_delete", "event_id": event_id,
                "error": "event still present after DeleteEvent (delete not confirmed)"}

    return {"pass": True, "event_id": event_id, "title": title,
            "start": start_iso, "end": end_iso,
            "detail": f"created id={event_id}, read-back OK, deleted, read-back-gone OK"}


def prove_gmail_draft(client: Arcade, uid: str, recipient: str) -> dict:
    """Create a DRAFT (never send) -> independent ListDraftEmails read-back. Returns result dict."""
    draft_tool = INTENT_MAP["send_email_draft"]         # Gmail.WriteDraftEmail (NEVER sends)
    list_tool = READ_BACK["send_email_draft"]           # Gmail.ListDraftEmails

    # Both the write scope and the read need the Gmail grant. Check BEFORE writing so we never
    # half-act. If pending, STOP with the connect_url.
    completed, url, status = _auth_or_url(client, draft_tool, uid)
    if not completed:
        return {"pass": False, "step": "auth", "connect_url": url, "status": status,
                "detail": f"gmail not authorized (status={status}); connect_url captured — "
                          f"owner must tap to grant gmail.compose. NOTHING written, NOTHING sent."}

    subject = "[Anticipy test] gate G draft"
    body = "[Anticipy test] Gate G live proof — unsent draft. Safe to delete."
    draft_value, err = _exec(client, draft_tool, {
        "subject": subject, "body": body, "recipient": recipient,
    }, uid)
    if err or not draft_value:
        return {"pass": False, "step": "create", "error": str(err or "empty output")}

    draft_id = ApiHand._find_id(draft_value)
    if not draft_id:
        return {"pass": False, "step": "create", "error": "no draft id in WriteDraftEmail output",
                "raw": str(draft_value)[:300]}

    # INDEPENDENT read-back: ListDraftEmails must re-observe the created draft id.
    list_value, err = _exec(client, list_tool, {"n_drafts": 50}, uid)
    if err or list_value is None:
        return {"pass": False, "step": "readback", "draft_id": draft_id,
                "error": str(err or "empty output")}
    present = ApiHand._read_contains_id(list_value if isinstance(list_value, dict)
                                        else {"value": list_value}, draft_id)
    if not present:
        return {"pass": False, "step": "readback", "draft_id": draft_id,
                "error": "created draft id NOT re-observed by independent ListDraftEmails read-back"}

    return {"pass": True, "draft_id": draft_id, "subject": subject, "recipient": recipient,
            "detail": f"draft created id={draft_id}, read-back OK (NEVER sent)"}


def main() -> int:
    key = os.environ.get("ARCADE_API_KEY")
    uid = os.environ.get("ARCADE_USER_ID")
    recipient = os.environ.get("ADMIN_EMAIL") or uid
    mode = os.environ.get("ANTICIPY_HANDS_MODE", "")
    if not key or not uid:
        print("FATAL: ARCADE_API_KEY / ARCADE_USER_ID not set (source .env.local)", file=sys.stderr)
        return 2
    if mode != "live":
        print(f"FATAL: ANTICIPY_HANDS_MODE must be 'live' (got '{mode}')", file=sys.stderr)
        return 2

    client = Arcade(api_key=key)
    print(f"== Gate G live proof | user={uid} | recipient={recipient} ==\n")

    try:
        cal = prove_calendar(client, uid)
    except Exception as exc:  # surface the exact error, never swallow
        cal = {"pass": False, "step": "exception", "error": f"{type(exc).__name__}: {exc}"}
    print("CALENDAR:", json.dumps(cal, indent=2), "\n")

    try:
        gmail = prove_gmail_draft(client, uid, recipient)
    except Exception as exc:
        gmail = {"pass": False, "step": "exception", "error": f"{type(exc).__name__}: {exc}"}
    print("GMAIL:", json.dumps(gmail, indent=2), "\n")

    overall = bool(cal.get("pass")) and bool(gmail.get("pass"))

    # Build honest evidence + detail strings.
    cal_ev = (f"event id={cal.get('event_id')} read-back OK + deleted"
              if cal.get("pass")
              else f"calendar FAIL: {cal.get('detail') or cal.get('error')}"
                   + (f" connect_url={cal.get('connect_url')}" if cal.get("connect_url") else ""))
    gm_ev = (f"draft id={gmail.get('draft_id')} read-back OK (never sent)"
             if gmail.get("pass")
             else "gmail needs OAuth tap: " + str(gmail.get("connect_url"))
                  if gmail.get("connect_url")
                  else f"gmail FAIL: {gmail.get('detail') or gmail.get('error')}")

    cal_detail = ("calendar: created id=%s read-back OK, deleted OK" % cal.get("event_id")
                  if cal.get("pass") else "calendar: " + str(cal.get("detail") or cal.get("error")))
    gm_detail = ("gmail draft: created id=%s read-back OK (never sent)" % gmail.get("draft_id")
                 if gmail.get("pass")
                 else ("gmail: needs OAuth tap: " + str(gmail.get("connect_url"))
                       if gmail.get("connect_url")
                       else "gmail: " + str(gmail.get("detail") or gmail.get("error"))))

    proof = {
        "gate": "G_api",
        "pass": overall,
        "mode": "live",
        "evidence": f"{cal_ev} | {gm_ev}",
        "verified_at": datetime.date.today().isoformat(),
        "detail": f"{cal_detail} | {gm_detail}",
        "calendar": cal,
        "gmail": gmail,
        "nothing_sent": True,
    }
    PROOF_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROOF_PATH.write_text(json.dumps(proof, indent=2) + "\n")
    print("WROTE:", PROOF_PATH)
    print("OVERALL pass:", overall)
    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())
