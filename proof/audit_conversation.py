#!/usr/bin/env python3
"""Read the whole SMS history and find where she let him down.

This is the most productive diagnostic in the project. Every one of these
came out of it: commitments she invented and texted about, the same message
sent twice, a claim of progress while the task sat blocked, six texts about
one email, messages of his swallowed by an exception, and a numbered-choice
deadlock where she asked him to pick and then refused every way of picking.

Needs Twilio credentials, so run it through the worker's environment:

    cd ~/Anticipy-pendant
    railway run --service worker python3 proof/audit_conversation.py

Read-only. Sends nothing, writes nothing.
"""
from __future__ import annotations

import base64
import email.utils as eu
import json
import os
import re
import sys
import urllib.request
from collections import defaultdict

REPLY_WINDOW_S = 1800
BURST_WINDOW_S = 180      # several messages this close together is a burst
STOP = {"the", "a", "an", "and", "or", "to", "of", "in", "on", "at", "for",
        "with", "is", "are", "was", "be", "it", "this", "that", "you", "your",
        "i", "im", "ive", "hey", "hi", "just", "got", "get", "have", "has",
        "do", "did", "can", "will", "would", "about", "any", "some", "there",
        "up", "out", "so", "we", "me", "my", "ill", "let", "know", "when"}


def fetch_all() -> list[dict]:
    sid, tok = os.environ.get("TWILIO_ACCOUNT_SID"), os.environ.get("TWILIO_AUTH_TOKEN")
    if not (sid and tok):
        sys.exit("no Twilio credentials in env — run via: railway run --service worker")
    auth = base64.b64encode(f"{sid}:{tok}".encode()).decode()

    def get(url):
        req = urllib.request.Request(url)
        req.add_header("Authorization", "Basic " + auth)
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)

    page = get(f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json?PageSize=100")
    msgs, nxt, guard = page["messages"], page.get("next_page_uri"), 0
    while nxt and guard < 20:
        page = get("https://api.twilio.com" + nxt)
        msgs += page["messages"]
        nxt, guard = page.get("next_page_uri"), guard + 1
    out = []
    for m in msgs:
        try:
            m["_ts"] = eu.parsedate_to_datetime(m["date_sent"])
        except Exception:
            continue
        out.append(m)
    out.sort(key=lambda m: m["_ts"])
    return out


def words(text: str) -> set:
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower())
            if w not in STOP and len(w) > 2}


def main() -> int:
    msgs = fetch_all()
    inbound = [m for m in msgs if m["direction"] == "inbound"]
    outbound = [m for m in msgs if m["direction"].startswith("outbound")]
    print(f"{len(msgs)} messages · {len(inbound)} from him · {len(outbound)} from her\n")

    problems = 0

    # --- he spoke and heard nothing ---------------------------------------
    # A reply in the SAME second counts. Twilio's date_sent is second-granular
    # and a fast reply lands on the same tick as the message it answers —
    # sorting alone put it BEFORE, which made three answered messages look
    # unanswered in an earlier pass of this audit. Measure, then believe.
    silent = []
    for m in inbound:
        t = m["_ts"]
        if not any(0 <= (o["_ts"] - t).total_seconds() <= REPLY_WINDOW_S for o in outbound):
            silent.append(m)
    print(f"UNANSWERED — he texted, nothing came back within "
          f"{REPLY_WINDOW_S // 60} minutes: {len(silent)}")
    for m in silent:
        print(f"   {m['_ts']:%m-%d %H:%M:%S} | {(m['body'] or '')[:74]}")
    problems += len(silent)

    # --- she said the same thing twice -------------------------------------
    dupes = []
    for i, a in enumerate(outbound):
        wa = words(a["body"])
        if len(wa) < 4:
            continue
        for b in outbound[i + 1:]:
            if (b["_ts"] - a["_ts"]).total_seconds() > 86400:
                break
            wb = words(b["body"])
            # Divide by the LONGER message, not the shorter. Dividing by the
            # shorter one made every pair that shared her stock closing
            # ("I'll text you when I have something solid") look identical,
            # and the audit reported 753 duplicates where there were dozens.
            # An audit that cries wolf is worse than no audit — same lesson as
            # a test fake that ignores the query.
            if wb and len(wa & wb) / max(len(wa), len(wb)) >= 0.7:
                dupes.append((a, b))
                break
    print(f"\nREPEATED — she sent essentially the same message twice: {len(dupes)}")
    for a, b in dupes[-8:]:
        gap = int((b["_ts"] - a["_ts"]).total_seconds())
        print(f"   {a['_ts']:%m-%d %H:%M} +{gap}s | {(a['body'] or '')[:66]}")
    problems += len(dupes)

    # --- she piled on ------------------------------------------------------
    bursts, run = [], []
    for m in outbound:
        if run and (m["_ts"] - run[-1]["_ts"]).total_seconds() <= BURST_WINDOW_S:
            run.append(m)
        else:
            if len(run) >= 3:
                bursts.append(run)
            run = [m]
    if len(run) >= 3:
        bursts.append(run)
    print(f"\nBURSTS — 3+ of her messages inside {BURST_WINDOW_S}s: {len(bursts)}")
    for b in bursts[-5:]:
        print(f"   {b[0]['_ts']:%m-%d %H:%M} · {len(b)} messages")
        for m in b[:3]:
            print(f"        {(m['body'] or '')[:66]}")
    problems += len(bursts)

    print(f"\n{problems} problem(s) across the whole history."
          if problems else "\nNothing wrong found in the whole history.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
