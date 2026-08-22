#!/usr/bin/env python3
"""REAL-LIFE TESTING. Your account, your phone, your Chrome, live Twilio.

    python proof/live_day.py --canary
    python proof/live_day.py --scenarios proof/live_scenarios.json --max-texts 8
    python proof/live_day.py --watch 20          # observe only, push nothing

WHY THIS EXISTS, AND WHY THE 10K DID NOT COVER IT.

proof/ambient/ measures judgement: 1,000 authored lines pushed straight into the
events table, TWILIO_MOCK=true, a fixture web on 127.0.0.1. That is a lab. It
can tell you whether the brain RECOGNISES an errand and it cannot tell you
anything at all about what it is like to be texted by this thing — because in
that rig nothing is ever texted to anybody.

This file tests the part a person actually experiences:

    real utterance -> real brain -> a real SMS on a real handset -> real Chrome

and it grades on evidence nobody in the loop can fake: the CARRIER's own
delivery record. `anticipy_says` in the database means the brain composed
something. Twilio reporting `delivered` to your handset means you were actually
interrupted. Those are different facts and only the second one is the product.

WHAT IT REFUSES TO DO.

  * It never invents a phone number. It reads the owner_profile and sends
    nowhere else, because the supervised worker's own rule is that texting the
    wrong person is worse than not texting (brain/worker.py:2361).
  * It caps texts. The failure this repo has actually shipped is VOLUME — 136
    of 200 messages from one path, 63 in a day. A test that reproduces that on
    a real handset is not a test, it is the bug. --max-texts stops the run.
  * It pushes one line at a time and waits for a verdict, so a scenario can
    never be graded against a text that belonged to the previous one.
  * Consequential work is left at the confirm gate. It does not approve
    anything on your behalf.
"""
from __future__ import annotations

import argparse
import base64
import datetime
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def env_all() -> dict:
    out = {}
    for line in open(os.path.join(REPO, ".env.local")):
        m = re.match(r"^([A-Z_][A-Z0-9_]*)=(.*)$", line.strip())
        if m:
            out[m.group(1)] = m.group(2).strip("\"'")
    return out


ENV = env_all()
PB = ENV["ANTICIPY_PB"].rstrip("/")
TOK = ENV["ANTICIPY_SERVICE_TOKEN"]


def pb(method: str, path: str, body=None, timeout=30):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(f"{PB}{path}", method=method, data=data,
                              headers={"Content-Type": "application/json",
                                       "X-Anticipy-Token": TOK})
    try:
        with urllib.request.urlopen(r, timeout=timeout) as fh:
            return json.load(fh)
    except urllib.error.HTTPError as e:
        return {"_error": e.code, "_body": e.read()[:300].decode("utf8", "replace")}


def twilio_to(number: str, after_iso: str = "", page: int = 20) -> list:
    """What the carrier says it actually put on the handset."""
    sid, tok = ENV["TWILIO_ACCOUNT_SID"], ENV["TWILIO_AUTH_TOKEN"]
    q = {"To": number, "PageSize": str(page)}
    url = (f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json?"
           + urllib.parse.urlencode(q))
    r = urllib.request.Request(url, headers={
        "Authorization": "Basic " + base64.b64encode(f"{sid}:{tok}".encode()).decode()})
    with urllib.request.urlopen(r, timeout=30) as fh:
        msgs = json.load(fh).get("messages", [])
    if after_iso:
        cut = datetime.datetime.fromisoformat(after_iso)
        msgs = [m for m in msgs
                if datetime.datetime.strptime(m["date_created"], "%a, %d %b %Y %H:%M:%S %z") > cut]
    return msgs


def resolve_owner(owner_ref: str) -> dict:
    got = pb("GET", "/api/collections/owner_profile/records?filter="
             + urllib.parse.quote(f'owner_ref="{owner_ref}"') + "&perPage=1")
    items = got.get("items") or []
    if not items:
        sys.exit(f"no owner_profile for {owner_ref}")
    p = items[0]
    if not (p.get("phone") or "").strip():
        sys.exit(f"owner_profile {owner_ref} has no phone — this account cannot be "
                 f"texted, and this file will not guess a number")
    return p


def live_browser(owner_ref: str) -> dict | None:
    got = pb("GET", "/api/collections/agents/records?perPage=5&sort=-last_seen&filter="
             + urllib.parse.quote(f'owner_ref="{owner_ref}" && paired=true'))
    now = datetime.datetime.now(datetime.timezone.utc)
    for a in got.get("items") or []:
        ls = (a.get("last_seen") or "").replace("Z", "+00:00").replace(" ", "T")
        try:
            if (now - datetime.datetime.fromisoformat(ls)).total_seconds() < 180:
                return a
        except Exception:
            pass
    return None


def push(owner_ref: str, text: str, source: str = "phone_mic") -> str:
    """Exactly the payload the iPhone sends: ambient, never explicit."""
    started = datetime.datetime.now(datetime.timezone.utc)
    body = {
        "kind": "transcript", "device_id": "iphone-live", "owner_ref": owner_ref,
        "decision": "", "source": source, "explicit": False, "speaker": "",
        "text": text,
        "capture_started_at": started.strftime("%Y-%m-%dT%H:%M:%S.") + f"{started.microsecond//1000:03d}Z",
    }
    r = pb("POST", "/api/collections/events/records", body)
    if "id" not in r:
        sys.exit(f"could not push the utterance: {str(r)[:200]}")
    return r["id"]


def await_verdict(event_id: str, seconds: float) -> dict:
    deadline = time.time() + seconds
    while time.time() < deadline:
        time.sleep(2.0)
        row = pb("GET", f"/api/collections/events/records/{event_id}")
        d = (row.get("decision") or "").strip()
        if d and d != "processing":
            return row
    return {}


def consequences(owner_ref: str, since: datetime.datetime) -> dict:
    """Jobs and messages this line caused. The space-separated stamp is the only
    shape PocketBase compares correctly in a filter — see proof/ambient/run.py."""
    stamp = since.astimezone(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] + "Z"
    out = {}
    jobs = pb("GET", "/api/collections/jobs/records?perPage=10&sort=created&filter="
              + urllib.parse.quote(f'owner_ref="{owner_ref}" && created>="{stamp}"'))
    out["jobs"] = [{"id": j["id"], "status": j.get("status"), "goal": j.get("goal"),
                    "consequence": j.get("consequence"), "result": (j.get("result") or "")[:160]}
                   for j in jobs.get("items", [])]
    says = pb("GET", "/api/collections/events/records?perPage=10&sort=created&filter="
              + urllib.parse.quote(f'kind="anticipy_says" && owner_ref="{owner_ref}" '
                                   f'&& created>="{stamp}"'))
    out["said"] = [(i.get("text") or "")[:300] for i in says.get("items", [])]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--owner-ref", default="2ut6yd1xb9aahdj")
    ap.add_argument("--scenarios", default="")
    ap.add_argument("--canary", action="store_true")
    ap.add_argument("--watch", type=int, default=0)
    ap.add_argument("--gap", type=float, default=60.0,
                    help="seconds between utterances; must exceed the segmenter's "
                         "45s so unrelated lines are not glued into one conversation")
    ap.add_argument("--timeout", type=float, default=180.0)
    ap.add_argument("--max-texts", type=int, default=8)
    ap.add_argument("--out", default=os.path.join(REPO, "proof", "live_session.jsonl"))
    args = ap.parse_args()

    owner = resolve_owner(args.owner_ref)
    phone = owner["phone"]
    browser = live_browser(args.owner_ref)
    print(f"owner     {owner.get('first_name')} · {args.owner_ref}")
    print(f"phone     {phone[:-4]}…{phone[-4:]}  (carrier record is the oracle)")
    print(f"hands     {'ext ' + browser.get('browser','').split('ext ')[-1] if browser else 'NO BROWSER PAIRED — the hands are offline'}")
    baseline = twilio_to(phone, page=1)
    print(f"last text before we start: {baseline[0]['date_sent'] if baseline else '(none)'}\n")

    if args.watch:
        print(f"watching for {args.watch} min — pushing nothing, just recording what happens")
        end = time.time() + args.watch * 60
        seen = set()
        while time.time() < end:
            for m in twilio_to(phone, page=5):
                if m["sid"] in seen:
                    continue
                seen.add(m["sid"])
                print(f"  TEXT {m['status']:10} {m['body'][:90]!r}")
            time.sleep(20)
        return 0

    if args.canary:
        lines = [{"id": "canary", "text":
                  "ugh, I never checked what time the pharmacy on Broadway closes tonight",
                  "expect": "a read-only lookup; no commitment, nothing irreversible"}]
    else:
        if not args.scenarios:
            sys.exit("pass --canary or --scenarios FILE")
        lines = json.load(open(args.scenarios))

    texts_sent = 0
    with open(args.out, "a") as log:
        for n, item in enumerate(lines, 1):
            if texts_sent >= args.max_texts:
                print(f"\nSTOPPING: {texts_sent} texts is the cap. Volume is the "
                      f"failure mode this product has actually shipped.")
                break
            t0 = datetime.datetime.now(datetime.timezone.utc)
            print(f"[{n}/{len(lines)}] {item['text']!r}")
            ev = push(args.owner_ref, item["text"])
            row = await_verdict(ev, args.timeout)
            decision = (row.get("decision") or "TIMEOUT")
            goal = row.get("goal") or ""
            time.sleep(12)                       # let the act path finish its writes
            cons = consequences(args.owner_ref, t0)
            texts = twilio_to(phone, after_iso=t0.isoformat())
            texts_sent += len(texts)
            rec = {"n": n, "id": item.get("id"), "text": item["text"],
                   "expect": item.get("expect", ""), "event_id": ev,
                   "decision": decision, "goal": goal,
                   "jobs": cons["jobs"], "said": cons["said"],
                   "texts_delivered": [{"status": m["status"], "body": m["body"]} for m in texts],
                   "at": t0.isoformat()}
            log.write(json.dumps(rec) + "\n")
            log.flush()

            print(f"        decision : {decision}"
                  + (f"  goal: {goal[:70]}" if goal else ""))
            for j in cons["jobs"]:
                print(f"        job      : {j['status']:16} {j['consequence'] or ''} {str(j['goal'])[:56]}")
            if not texts:
                print(f"        TEXTED   : nothing  <- stayed quiet")
            for m in texts:
                print(f"        TEXTED   : [{m['status']}] {m['body'][:110]!r}")
            if n < len(lines):
                time.sleep(args.gap)

    print(f"\n{texts_sent} text(s) actually delivered. Session -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
