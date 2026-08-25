#!/usr/bin/env python3
"""ARE HER TEXTS ARRIVING? — the gate for a user who can never answer.

Written 2026-08-25 because of a failure nobody could see from inside the
product: `+17868735256` was sent 15 messages between 08-19 and 08-25 and NOT ONE
was delivered. Every one failed with Twilio error 30034 — the sending number is
not registered for A2P 10DLC. From the product's side everything looked healthy:
`voice_arm.text()` got a 201 Created back from Twilio each time, the row was
written, the send was "successful". Delivery failed afterwards, asynchronously,
and nothing here ever read the receipt.

A person in that state cannot reply, cannot approve a held job, and cannot
answer a question — not because they ignored her but because the question never
arrived. Their day looks, from every scoreboard we own, exactly like a quiet one.

WHY A THRESHOLD IS LEGAL HERE (HARNESS-LAWS Law 1). This gate never reads the
TEXT of a message and never decides what anything MEANS. It reads Twilio's own
delivery receipts — `status` and `error_code`, machine facts about whether bytes
reached a handset. Law 1 permits pattern-matching in deterministic gates; this is
one, and it could not classify an utterance if it wanted to, because it never
fetches a body.

WHAT IT WILL NOT DO: it will not go red because a message is still in flight
(`queued`, `sending`, `sent` are all pending, not failures), and it will not go
red on a single failure — one undelivered text is a phone off, a carrier hiccup,
a full inbox. The shape it catches is a number where messages ACCUMULATE and NONE
land, which is what a registration or blocklist problem looks like and what a bad
evening does not.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import _env  # noqa: E402  sibling module; gates are run as scripts
_ENV_LOADED = _env.load_and_announce(ROOT)

# Twilio's own vocabulary. Not ours, and not interpreted.
DELIVERED = {"delivered", "received"}
PENDING = {"queued", "accepted", "scheduled", "sending", "sent"}
FAILED = {"undelivered", "failed"}

# How many messages must pile up unheard before silence is a finding rather
# than an evening. Three is the smallest number that cannot be one bad night:
# a phone off, a tunnel, a full inbox. It is a REPORTING floor on delivery
# receipts, never a judgement about anybody's words.
MIN_MESSAGES = 3

WINDOW = 200  # most recent outbound messages to read


def _auth_header() -> str:
    sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
    tok = os.environ.get("TWILIO_AUTH_TOKEN", "")
    raw = f"{sid}:{tok}".encode()
    return "Basic " + base64.b64encode(raw).decode()


def fetch_outbound(limit: int = WINDOW) -> list:
    """Read recent outbound messages. GET only — this gate never sends."""
    sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
    frm = os.environ.get("TWILIO_PHONE_NUMBER") or os.environ.get("TWILIO_FROM") or ""
    if not sid or not os.environ.get("TWILIO_AUTH_TOKEN"):
        raise RuntimeError(
            "cannot verify: no Twilio credentials. Set TWILIO_ACCOUNT_SID and "
            "TWILIO_AUTH_TOKEN. A leg that cannot be tested does not pass")
    q = {"PageSize": str(min(limit, 1000))}
    if frm:
        q["From"] = frm
    url = (f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json?"
           + urllib.parse.urlencode(q))
    req = urllib.request.Request(url, headers={"Authorization": _auth_header()})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.load(r).get("messages", []) or []


def unreachable(messages: list, min_messages: int = MIN_MESSAGES) -> list:
    """Numbers where messages accumulate and NONE arrive.

    Pure function over Twilio's receipts so it can be tested without a network.
    Pending messages are counted but never held against a number — a text sent
    ninety seconds ago has not failed, it has not finished.
    """
    by_to: dict = {}
    for m in messages:
        if (m.get("direction") or "").startswith("inbound"):
            continue
        to = m.get("to") or ""
        if not to:
            continue
        slot = by_to.setdefault(to, {"delivered": 0, "failed": 0, "pending": 0,
                                     "errors": {}, "total": 0, "newest": None})
        slot["total"] += 1
        status = (m.get("status") or "").lower()
        if status in DELIVERED:
            slot["delivered"] += 1
        elif status in FAILED:
            slot["failed"] += 1
            code = str(m.get("error_code") or "").strip()
            if code:
                slot["errors"][code] = slot["errors"].get(code, 0) + 1
        elif status in PENDING:
            slot["pending"] += 1
        if slot["newest"] is None:
            slot["newest"] = m.get("date_sent") or m.get("date_created")

    out = []
    for to, s in by_to.items():
        settled = s["delivered"] + s["failed"]
        # Nothing settled yet is not a finding — it is a message in flight.
        if settled < min_messages:
            continue
        if s["delivered"] == 0:
            out.append({"to": to, **s})
    out.sort(key=lambda x: -x["failed"])
    return out


def main() -> int:
    print()
    print("  ARE HER TEXTS ARRIVING?")
    print("  " + "-" * 62)
    try:
        msgs = fetch_outbound()
    except Exception as e:
        print(f"  [1] fail  SHE CAN BE HEARD AT ALL")
        print(f"        {e}")
        print("  " + "-" * 62)
        print("  UNPROVEN — a leg that cannot be tested does not pass")
        return 2

    bad = unreachable(msgs)
    total_out = sum(1 for m in msgs if not (m.get("direction") or "").startswith("inbound"))
    print(f"  [....] outbound messages read              {total_out}")
    print(f"  [....] numbers that never receive anything  {len(bad)}")
    if not bad:
        print("  [1] PASS  EVERY NUMBER SHE WRITES TO RECEIVES SOMETHING")
        print("  " + "-" * 62)
        return 0

    print("  [1] FAIL  SOMEBODY CANNOT HEAR HER AT ALL")
    for b in bad:
        codes = ", ".join(f"{c} x{n}" for c, n in sorted(b["errors"].items()))
        print(f"        {b['to']}: {b['total']} sent, {b['delivered']} delivered, "
              f"{b['failed']} failed" + (f" — Twilio error {codes}" if codes else ""))
        if "30034" in b["errors"]:
            print("          30034 = the sending number is not registered for A2P "
                  "10DLC. This is a Twilio console + business-identity task, not a "
                  "code change, and no deploy fixes it.")
        print("          This person cannot reply, cannot approve a held job, and "
              "cannot answer a question — the question never arrived. Their day "
              "reads as quiet from every other scoreboard we own.")
    print("  " + "-" * 62)
    print("  NOT REACHING THEM — fix this before spending anybody's week")
    return 1


if __name__ == "__main__":
    sys.exit(main())
