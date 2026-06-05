"""Track C — Gmail DRAFT judge (BUILT, NOT VERIFIED until the gmail.compose tap).

Independently reads the real Gmail drafts (Arcade `Gmail.ListDraftEmails`) and confirms the worker's
claimed draft id is actually there. Mirrors Track A's judge contract: pass/fail from reality, never
the worker's say-so; `self_prove()` plants a real draft + a fake and requires the fake to FAIL.
Cannot self-prove tonight (scope pending) — it will the moment the scope is granted.

LAW: never imports/reads the worker.
"""
from __future__ import annotations

import os

from arcadepy import Arcade


def _client() -> Arcade:
    return Arcade(api_key=os.environ["ARCADE_API_KEY"])


def _uid() -> str:
    return os.environ["ARCADE_USER_ID"]


def _list_drafts(n: int = 50) -> list:
    resp = _client().tools.execute(tool_name="Gmail.ListDraftEmails", user_id=_uid(),
                                   input={"n_drafts": n})
    val = getattr(getattr(resp, "output", None), "value", None) or {}
    # tolerate shape variants: {"drafts":[...]} / {"emails":[...]} / a bare list
    for key in ("drafts", "emails", "messages", "items"):
        if isinstance(val, dict) and isinstance(val.get(key), list):
            return val[key]
    return val if isinstance(val, list) else []


def confirm(claim: dict) -> dict:
    if claim.get("status") != "created" or not claim.get("draft_id"):
        return {"pass": False, "reason": f"worker created no draft (status={claim.get('status')})"}
    want = str(claim["draft_id"])
    try:
        drafts = _list_drafts()
    except Exception as e:
        return {"pass": False, "reason": f"gmail read failed: {type(e).__name__} {e}"}
    for d in drafts:
        did = str(d.get("id") or d.get("draft_id") or (d.get("message") or {}).get("id") or "")
        if did == want:
            return {"pass": True, "reason": "draft id found in the real mailbox", "evidence": d}
    return {"pass": False, "reason": f"claimed draft id {want} not found in the real drafts"}


def self_prove() -> bool:
    """Plant a real draft + a fake; the judge MUST pass the real and fail the fake. Needs auth."""
    uid, client = _uid(), _client()
    try:
        resp = client.tools.execute(tool_name="Gmail.WriteDraftEmail", user_id=uid, input={
            "recipient": uid, "subject": "[Anticipy test] draft-judge self-prove",
            "body": "self-prove; auto-deleted."})
    except Exception as e:
        print(f"  self-prove BLOCKED (scope not granted yet): {type(e).__name__} {str(e)[:100]}")
        return False
    val = getattr(getattr(resp, "output", None), "value", None) or {}
    real_id = (val.get("id") or (val.get("draft") or {}).get("id"))
    if not real_id:
        print("  self-prove SETUP FAILED: no draft id returned"); return False
    real_v = confirm({"status": "created", "draft_id": real_id})
    fake_v = confirm({"status": "created", "draft_id": "fake-draft-000"})
    try:
        client.tools.execute(tool_name="Gmail.DeleteDraftEmail", user_id=uid, input={"draft_id": real_id})
    except Exception:
        pass
    ok = real_v["pass"] and not fake_v["pass"]
    print(f"  planted REAL -> {'PASS' if real_v['pass'] else 'FAIL'}; "
          f"planted FAKE -> {'PASS' if fake_v['pass'] else 'FAIL'}; "
          f"judge {'TRUSTWORTHY' if ok else 'BROKEN'}")
    return ok
