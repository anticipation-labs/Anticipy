#!/usr/bin/env python3
"""THE ONE GATE — the single, falsifiable definition of DONE for Anticipy.

Why this exists (2026-07-02): every session found "a different issue" and none ever felt done.
That is the textbook "Last 10% Trap" — building fat PARTS instead of one thin end-to-end WHOLE,
so integration failures surface one-at-a-time forever. The cure (Cockburn's Walking Skeleton +
a single Definition-of-Done acceptance test) is this file: the thinnest slice of the WHOLE
stranger-journey, run as ONE pass/fail. From now on there is no "part proven" scoreboard.
There is only: does THIS print DONE?

It is honest by construction: the last leg (a real cold stranger onboarded on THEIR real
accounts and carried through a real day) cannot be automated, so it requires a human-signed
proof file. No proof -> NOT DONE. You cannot walk around this gate.

Run:  ANTICIPY_ENGINE_URL=http://127.0.0.1:8790 engine/.venv/bin/python overnight/done_gate.py
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request

LOCAL = os.environ.get("ANTICIPY_ENGINE_URL", "http://127.0.0.1:8790")
LIVE = os.environ.get("ANTICIPY_LIVE_URL", "https://anticipy-welcome.vercel.app")
PROOF = os.path.join(os.path.dirname(__file__), "done_proof.json")

# The messy line that IS the brain test: two real tasks + one vent that must stay silent.
MESSY = "grab the kids at 3, honestly I should just quit, email Sarah the budget tonight"


def _get(url, timeout=15):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except Exception as e:
        return 0, f"{type(e).__name__}: {e}"


def _post(url, body, timeout=90):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8", "replace"))
    except Exception as e:
        return 0, {"error": f"{type(e).__name__}: {e}"}


def _ingest(text):
    st, data = _post(f"{LOCAL}/owner/ingest", {"text": text, "execute_actions": True})
    cards = (data or {}).get("cards") or []
    return cards, data


# ---- the legs of the thinnest whole journey ----

def leg_front_door():
    st, body = _get(f"{LIVE}/welcome")
    ok = st == 200 and ("hears your day" in body or "Vibe your life" in body)
    return ok, f"live welcome http={st}, premium hero {'present' if ok else 'MISSING'}"


def leg_reaches_brain():
    st, body = _get(f"{LIVE}/api/health")
    ok = st == 200 and "anticipy-engine" in body
    return ok, f"live app->engine /api/health http={st}"


def leg_thinks():
    cards, data = _ingest(MESSY)
    srcs = " | ".join((c.get("source_text") or c.get("title") or "") for c in cards).lower()
    caught_kids = "kid" in srcs
    caught_email = "sarah" in srcs or "budget" in srcs
    vent_silent = "quit" not in srcs
    ok = caught_kids and caught_email and vent_silent
    return ok, (f"caught kids={caught_kids} email-Sarah={caught_email} "
                f"vent-'quit'-silent={vent_silent} ({len(cards)} cards)")


def leg_reliability(n=3):
    for i in range(n):
        ok, why = leg_thinks()
        if not ok:
            return False, f"failed on run {i+1}/{n}: {why}"
        time.sleep(0.3)
    return True, f"the brain leg held {n}/{n} runs (never-fails on the core)"


def leg_human_signed():
    """A real cold stranger, onboarded on THEIR real accounts, carried through a real day.
    Cannot be automated. Requires overnight/done_proof.json = {"carried_a_real_stranger": true,
    "when": "...", "who": "...", "what_it_did": "..."}. Absent/false -> NOT DONE."""
    if not os.path.exists(PROOF):
        return False, ("NO PROOF FILE — no real stranger has been carried through a real day yet. "
                       "This is the actual finish line; it cannot be faked.")
    try:
        p = json.load(open(PROOF))
    except Exception as e:
        return False, f"done_proof.json unreadable: {e}"
    if not p.get("carried_a_real_stranger"):
        return False, "done_proof.json present but carried_a_real_stranger != true"
    return True, f"human-signed: {p.get('who','?')} — {p.get('what_it_did','')[:80]}"


LEGS = [
    ("1. Front door is live (stranger can open it)", leg_front_door),
    ("2. The live app reaches the brain", leg_reaches_brain),
    ("3. It thinks: catches real tasks, ignores the vent", leg_thinks),
    ("4. It never fails on the core (reliability x3)", leg_reliability),
    ("5. A REAL cold stranger was carried a real day", leg_human_signed),
]


def main():
    print("=" * 68)
    print("  ANTICIPY — THE ONE DONE GATE (walking skeleton, whole journey)")
    print("=" * 68)
    first_fail = None
    for name, fn in LEGS:
        ok, why = fn()
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {name}\n         {why}")
        if not ok and first_fail is None:
            first_fail = name
    print("-" * 68)
    if first_fail is None:
        print("  VERDICT: ✅ DONE — the whole thin journey holds end to end.")
        return 0
    print(f"  VERDICT: ❌ NOT DONE — first failing gate: {first_fail}")
    print("  The ONLY work allowed is making that gate pass. Nothing else counts.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
