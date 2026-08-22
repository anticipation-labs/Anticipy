#!/usr/bin/env python3
"""PARALLEL TEST LANES. One command to get N isolated copies of the product.

    ~/.anticipy-rig/venv/bin/python proof/lanes.py provision voice 6
    ~/.anticipy-rig/venv/bin/python proof/lanes.py provision arm 3
    ~/.anticipy-rig/venv/bin/python proof/lanes.py list
    ~/.anticipy-rig/venv/bin/python proof/lanes.py clean voice

WHY LANES EXIST. Everything in this rig is bound to exactly ONE owner_ref, and
nothing says so until a measurement is already wrong:

  * brain/worker.py:45 reads ACTIVE_OWNER_REF once at process start and
    fetch_unprocessed() fails closed without it, so one worker serves one owner
    and a second corpus pushed at the same owner queues behind the first.
  * extension/background.js:420 claims `owner_ref="<ref>"`, and
    requeueStaleJobs() at :290 is owner-scoped but skips only the jobs in ITS
    OWN activeJobs map. Two browsers paired to one owner therefore fight: the
    moment one lease looks expired to the other, the other requeues it, and on
    a consequential task that is a SECOND EXECUTION of a real commit.
  * proof/fixtures/server.mjs keeps its whole ledger in one module global that
    POST /__fixture/reset replaces wholesale, so two batteries on one port wipe
    each other's bookings mid-run and mix the request logs that prove a page
    was ever loaded.

So the unit of parallelism is not "another process", it is a whole vertical
slice: its own owner, its own worker or browser, its own fixture port. This
file hands those out and keeps a registry so a second invocation reuses them
rather than littering the database with owners nobody can name.

TWO KINDS OF LANE, and mixing them is the mistake this file exists to prevent.

  voice-N   an owner plus a brain worker, and DELIBERATELY NO BROWSER.
            Ambient corpus work is graded on what the brain decided and what
            it queued (proof/ambient/score.py reads exactly `said` and `jobs`).
            Pair a Chrome to a voice lane and it starts claiming those queued
            errands and driving the live web with them: minutes per line
            instead of seconds, real sites, and a corpus run that measures the
            browser's luck instead of the brain's judgement.

  arm-N     an owner plus a paired Chrome plus its own fixture port, and NO
            brain worker. proof/battery/run.mjs mints its own job rows, so a
            worker here would only add a second writer to the same queue.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RIG = os.environ.get("ANTICIPY_RIG_DIR", os.path.expanduser("~/.anticipy-rig"))
REGISTRY = os.path.join(RIG, "state", "lanes.json")
PB = os.environ.get("ANTICIPY_PB", "http://127.0.0.1:8090")

# Only this machine. A lane provisions owners and then lets a browser act as
# them; pointed at production that is somebody's real life.
LOOPBACK = {"127.0.0.1", "localhost", "::1"}
if (urllib.parse.urlparse(PB).hostname or "") not in LOOPBACK:
    sys.exit(f"refusing to provision lanes against {PB}: loopback only")

PASSWORD = "lanepassword1234"


def req(method: str, path: str, body=None, timeout=20):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(f"{PB}{path}", method=method, data=data,
                               headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=timeout) as fh:
            return json.load(fh)
    except urllib.error.HTTPError as e:
        try:
            return {"_error": json.load(e)}
        except Exception:
            return {"_error": {"status": e.code}}


def load_registry() -> dict:
    if os.path.exists(REGISTRY):
        try:
            return json.load(open(REGISTRY))
        except Exception:
            pass
    return {}


def save_registry(reg: dict) -> None:
    os.makedirs(os.path.dirname(REGISTRY), exist_ok=True)
    tmp = REGISTRY + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(reg, fh, indent=1, sort_keys=True)
    os.replace(tmp, REGISTRY)


def provision_owner(tag: str) -> str:
    """Create (or recover) the owners record for one lane.

    IDEMPOTENT BY legacy_uuid. Re-running `provision` after a crash must not
    mint a second owner for the same lane: the first one still holds that
    lane's events, its memory database and, for an arm lane, the agents row a
    browser is already paired to. A duplicate would look identical from the
    outside and quietly split the lane's history in half.
    """
    found = req("GET", "/api/collections/owners/records?filter="
                + urllib.parse.quote(f'legacy_uuid="{tag}"') + "&perPage=1")
    items = (found or {}).get("items") or []
    if items:
        return items[0]["id"]

    email = f"{tag}@lane.test"
    made = req("POST", "/api/collections/owners/records",
               {"email": email, "password": PASSWORD,
                "passwordConfirm": PASSWORD, "legacy_uuid": tag})
    if "id" not in made:
        # An auth collection hides its rows from an anonymous list, so a
        # duplicate-email refusal is the ONLY way we learn the owner already
        # exists. Recover the id by signing in as it rather than giving up.
        auth = req("POST", "/api/collections/owners/auth-with-password",
                   {"identity": email, "password": PASSWORD})
        if auth.get("record", {}).get("id"):
            return auth["record"]["id"]
        sys.exit(f"could not create owner {tag}: {str(made)[:300]}")
    ref = made["id"]

    # The profile is what /agent/key hands the browser as "who this is for".
    # Without it the agent runs with an empty owner and every task that needs
    # a name or an email has to hand back.
    req("POST", "/api/collections/owner_profile/records",
        {"owner_id": tag, "owner_ref": ref, "first_name": "Alex",
         "email": email, "phone": "+16045550142",
         "timezone": "America/Vancouver"})
    return ref


def cmd_provision(kind: str, count: int) -> int:
    if kind not in ("voice", "arm"):
        sys.exit("kind must be 'voice' or 'arm'")
    reg = load_registry()
    for i in range(1, count + 1):
        tag = f"{kind}-{i}"
        ref = provision_owner(tag)
        lane = reg.get(tag, {})
        lane.update({"tag": tag, "kind": kind, "owner_ref": ref,
                     "owner_id": tag})
        if kind == "voice":
            # Per-lane memory and clock. Sharing one memory.db across workers
            # means lane 3 answers using facts lane 5 just learned, and the
            # SQLite file gets six writers.
            lane["memory_db"] = os.path.join(RIG, "state", f"memory.{tag}.db")
            lane["clock_state"] = os.path.join(RIG, "state", f"clock.{tag}.json")
        else:
            lane["fixture_port"] = 8900 + i
            lane["cdp_port"] = 29400 + i
        reg[tag] = lane
        print(f"{tag:8} owner_ref={ref} " + (
            f"memory={os.path.basename(lane['memory_db'])}" if kind == "voice"
            else f"fixture=:{lane['fixture_port']} cdp=:{lane['cdp_port']}"))
    save_registry(reg)
    print(f"\nregistry {REGISTRY}")
    return 0


def cmd_list() -> int:
    reg = load_registry()
    if not reg:
        print("no lanes provisioned")
        return 0
    for tag in sorted(reg):
        lane = reg[tag]
        counts = {}
        for status in ("queued", "running", "awaiting_confirm", "done", "failed"):
            cond = f'status="{status}" && owner_ref="{lane["owner_ref"]}"'
            got = req("GET", "/api/collections/jobs/records?filter="
                      + urllib.parse.quote(cond) + "&perPage=1")
            n = (got or {}).get("totalItems") or 0
            if n:
                counts[status] = n
        extra = (f"fixture=:{lane['fixture_port']} cdp=:{lane['cdp_port']}"
                 if lane["kind"] == "arm" else "")
        print(f"{tag:8} {lane['owner_ref']}  {extra}  jobs={counts or '{}'}")
    return 0


def cmd_clean(kind: str) -> int:
    """Cancel every unfinished job in these lanes.

    Not a delete: the rows are the evidence a run leaves behind and scoring
    reads them afterwards. But a queued browser job is not litter, it is an
    errand that fires later, so anything still live gets stopped.
    """
    reg = load_registry()
    n = 0
    for tag in sorted(reg):
        lane = reg[tag]
        if kind not in ("all", lane["kind"]):
            continue
        for status in ("queued", "running", "awaiting_confirm"):
            cond = f'status="{status}" && owner_ref="{lane["owner_ref"]}"'
            got = req("GET", "/api/collections/jobs/records?filter="
                      + urllib.parse.quote(cond) + "&perPage=200")
            for j in (got or {}).get("items") or []:
                req("PATCH", f"/api/collections/jobs/records/{j['id']}",
                    {"status": "cancelled",
                     "result": "lanes.py clean: stopped between runs"})
                n += 1
    print(f"cancelled {n} unfinished job(s)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["provision", "list", "clean"])
    ap.add_argument("kind", nargs="?", default="all")
    ap.add_argument("count", nargs="?", type=int, default=1)
    args = ap.parse_args()

    health = req("GET", "/api/health")
    if not health or health.get("code") != 200:
        sys.exit(f"backend {PB} is not answering — run: sh proof/local_rig.sh up")

    if args.command == "provision":
        return cmd_provision(args.kind, args.count)
    if args.command == "list":
        return cmd_list()
    return cmd_clean(args.kind)


if __name__ == "__main__":
    sys.exit(main())
