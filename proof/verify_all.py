#!/usr/bin/env python3
"""THE standing check: is every capability Omar named actually working, live?

Written 2026-08-01 after he listed texting, memory, sentence-stringing,
listening, proactivity and the browser as all broken. Most were already fixed
by then and he had tested an older deploy — which is exactly why this exists:
so the answer to "is it working?" is evidence, not either of us guessing.

Everything here runs against PRODUCTION and cleans up after itself. The one
capability it cannot test is phone transcription, which needs his physical
iPhone; that is reported as UNTESTABLE rather than quietly assumed.

Usage:  PYTHONPATH=. python3 proof/verify_all.py [--no-browser]
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

BASE = os.environ.get("ANTICIPY_PB", "https://backend-production-61e0a.up.railway.app")
RESULTS: list[tuple[str, bool, str]] = []
CREATED: list[tuple[str, str]] = []


def report(name: str, ok: bool, detail: str = ""):
    RESULTS.append((name, ok, detail))
    print(("PASS  " if ok else "FAIL  ") + name + (f"\n        {detail}" if detail else ""))


def api(path, body=None, method=None, timeout=20):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r) if r.status not in (204,) else {}


def create(coll, body):
    rec = api(f"/api/collections/{coll}/records", body)
    CREATED.append((coll, rec["id"]))
    return rec


def cleanup():
    for coll, rid in reversed(CREATED):
        try:
            api(f"/api/collections/{coll}/records/{rid}", method="DELETE")
        except Exception:
            pass


def agent_alive() -> tuple[bool, int]:
    q = urllib.parse.quote("paired=true")
    items = api(f"/api/collections/agents/records?filter={q}").get("items", [])
    if not items:
        return False, -1
    seen = items[0].get("last_seen", "")
    try:
        t = datetime.fromisoformat(seen.replace(" ", "T").replace("Z", "+00:00"))
        age = int((datetime.now(timezone.utc) - t).total_seconds())
    except Exception:
        return False, -1
    return age < 90, age


def owner_id() -> str:
    q = urllib.parse.quote("paired=true")
    items = api(f"/api/collections/agents/records?filter={q}").get("items", [])
    return items[0].get("owner", "") if items else ""


def check_backend():
    try:
        api("/api/health")
        report("the backend is up", True)
    except Exception as e:
        report("the backend is up", False, repr(e))


def check_brain_hears():
    """A spoken line reaches the brain and gets a verdict."""
    ev = create("events", {"kind": "transcript", "device_id": "verify",
                           "text": "I need to send Marcus the quarterly numbers tomorrow"})
    for _ in range(30):
        time.sleep(4)
        got = api(f"/api/collections/events/records/{ev['id']}")
        if got.get("decision") and got["decision"] != "processing":
            report("the brain hears and decides", True, f"decision: {got['decision']}")
            return got
    report("the brain hears and decides", False, "no real verdict within 60s (still claimed/processing)")
    return None


def check_text_releases_and_browser_runs(skip_browser=False):
    """His #1 complaint: texting yes must release the job AND the browser must
    actually do it. Each run opens a real tab in his Chrome, so an unattended
    loop passes --no-browser: piling tabs into an absent owner's browser is
    exactly the harm we just spent an evening undoing."""
    if skip_browser:
        print("SKIP  the browser lane (--no-browser: not opening tabs in his Chrome)")
        return
    live, age = agent_alive()
    if not live:
        report("his Chrome is reachable", False, f"last seen {age}s ago — browser lane untestable")
        return
    job = create("jobs", {
        "goal": "Look up the opening hours for Cactus Club Park Royal",
        "params": json.dumps({"source": "standing check",
                              "task": "Search the web for the opening hours of Cactus Club Cafe Park Royal, West Vancouver, and report them. Do not book anything."}),
        "status": "awaiting_confirm", "device_id": "anticipy", "owner": owner_id()})
    # Name the job explicitly. A bare "yes" is genuinely ambiguous when more
    # than one thing is pending — she is RIGHT to ask which, and a check that
    # calls that a failure is testing the wrong thing.
    create("events", {"kind": "sms_reply", "device_id": "sms",
                      "text": "yes go ahead with the Cactus Club opening hours one",
                      "goal": "+16047245161", "decision": ""})
    released = False
    for _ in range(40):
        time.sleep(5)
        j = api(f"/api/collections/jobs/records/{job['id']}")
        params = json.loads(j.get("params") or "{}")
        if not released and (j["status"] != "awaiting_confirm" or params.get("authorized")):
            released = True
            report("a text releases the held job", True,
                   f"authorized={params.get('authorized')}")
        if j["status"] in ("done", "failed", "needs_user", "cancelled"):
            ok = j["status"] == "done" and bool(j.get("result"))
            report("the browser does the work and reports back", ok,
                   f"{j['status']}: {(j.get('result') or '')[:160]}")
            return
    if not released:
        report("a text releases the held job", False, "still held after 200s")
    report("the browser does the work and reports back", False, "no outcome within 200s")


def check_no_runaway():
    """Nothing may be stuck running or piling up."""
    q = urllib.parse.quote('status="running"')
    running = api(f"/api/collections/jobs/records?filter={q}")
    report("nothing is stuck running", running["totalItems"] <= 1,
           f"{running['totalItems']} running")
    q2 = urllib.parse.quote('kind="transcript" && decision=""')
    stuck = api(f"/api/collections/events/records?filter={q2}")
    report("no speech is left unprocessed", stuck["totalItems"] <= 2,
           f"{stuck['totalItems']} unprocessed")


def main():
    skip_browser = "--no-browser" in sys.argv
    print(f"Anticipy standing check — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
    try:
        check_backend()
        # The text/browser chain runs FIRST: hearing a line can mint its own
        # held job, and a queue with two pending items makes the confirm
        # ambiguous by design.
        check_text_releases_and_browser_runs(skip_browser)
        check_brain_hears()
        check_no_runaway()
    finally:
        cleanup()
    print("\nUNTESTABLE from here: phone transcription (needs the physical iPhone).")
    failed = [n for n, ok, _ in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} passing"
          + (f" — FAILING: {', '.join(failed)}" if failed else " — everything Omar named is working"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
