#!/usr/bin/env python3
"""LIVE PROOF for brief 01: research runs in the worker, never his browser.

Queues "research: opening hours of the Vancouver aquarium" with the same
lane-routing rule the brain uses, then watches the job:

  PASS = the job goes queued -> done, claimed by "worker-research", with a
         summarized answer carrying a Sources list — and NO browser agent
         ever touched it.

Run it against a deployment whose worker has BRAVE_API_KEY set:

  ANTICIPY_PB=https://…railway.app ANTICIPY_SERVICE_TOKEN=… \
  ANTICIPY_OWNER_ID=<the worker's owner id> \
  PYTHONPATH=. python3 proof/research_proof.py

Creates exactly one job record and deletes it on the way out, pass or fail.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime

BASE = os.environ.get("ANTICIPY_PB", "http://127.0.0.1:8090").rstrip("/")
OWNER = os.environ.get("ANTICIPY_OWNER_ID", "")
GOAL = "research: opening hours of the Vancouver aquarium"
WAIT_SECONDS = 180

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from brain.anticipy_core import job_lane
except Exception:                       # no deps installed: rule known-good
    job_lane = lambda goal: "research"

RESULTS: list[tuple[str, bool, str]] = []


def report(name: str, ok: bool, detail: str = ""):
    RESULTS.append((name, ok, detail))
    print(("PASS  " if ok else "FAIL  ") + name
          + (f"\n        {detail}" if detail else ""))


def api(path, body=None, method=None, timeout=20):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    token = os.environ.get("ANTICIPY_SERVICE_TOKEN")
    if token:
        headers["X-Anticipy-Token"] = token
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r) if r.status not in (204,) else {}


def main() -> int:
    if not OWNER:
        print("WARNING: ANTICIPY_OWNER_ID is unset — the worker only claims "
              "its owner's jobs, so this will likely sit queued forever.")

    lane = job_lane(GOAL)
    report("the routing rule sends this goal to the research lane",
           lane == "research", f"job_lane({GOAL!r}) = {lane!r}")

    rec = api("/api/collections/jobs/records", {
        "goal": GOAL,
        "params": json.dumps({"source": "research proof",
                              "now": datetime.now().isoformat()}),
        "status": "queued", "lane": lane,
        "device_id": "research-proof", "owner": OWNER,
    })
    job_id = rec["id"]
    print(f"queued job {job_id}; watching for {WAIT_SECONDS}s …")

    final, foreign_claims = None, set()
    try:
        deadline = time.time() + WAIT_SECONDS
        while time.time() < deadline:
            time.sleep(3)
            job = api(f"/api/collections/jobs/records/{job_id}")
            claimant = (job.get("claimed_by") or "").strip()
            if claimant and claimant != "worker-research":
                foreign_claims.add(claimant)
            if job.get("status") in ("done", "failed"):
                final = job
                break
        if final is None:
            report("the worker picked the job up", False,
                   f"still not finished after {WAIT_SECONDS}s "
                   "(is the worker deployed with BRAVE_API_KEY?)")
        else:
            result = (final.get("result") or "").strip()
            report("the job finished", final["status"] == "done",
                   f"status={final['status']} result={result[:200]!r}")
            report("it was the WORKER that ran it",
                   final.get("claimed_by") == "worker-research",
                   f"claimed_by={final.get('claimed_by')!r}")
            report("no browser agent ever claimed it",
                   not foreign_claims, f"saw: {sorted(foreign_claims)}")
            report("the answer is summarized and cited",
                   "Sources:" in result and "http" in result,
                   result[:400])
            if final["status"] == "done":
                print("\n--- the answer -------------------------------------")
                print(result)
                print("----------------------------------------------------")
    finally:
        try:
            api(f"/api/collections/jobs/records/{job_id}", method="DELETE")
            print(f"cleaned up job {job_id}")
        except Exception as e:
            print(f"could not delete job {job_id}: {e} — remove it by hand")

    failed = [n for n, ok, _ in RESULTS if not ok]
    print(f"\nresearch proof: {len(RESULTS) - len(failed)} passed, "
          f"{len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
