"""Track A harness — many FRESH laps, each proven against the real calendar.

Per lap: pull a NEW request (generator) -> worker creates a real event -> judge reads the real
calendar and confirms it. The harness coordinates; worker and judge never import each other. The
judge is self-proved (real+fake) before ANY lap is trusted. After the run it keeps a few events
visible as morning proof and deletes the rest (cleanup), logging every real id either way.

Run: PYTHONPATH=engine:overnight/track_a python overnight/track_a/run_laps.py [n_laps]
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import sys
import time
from datetime import datetime

from anticipy_engine.core.env import load_local_env

load_local_env()

import generate_request as gen
import judge as J
import worker as W
from arcadepy import Arcade


def _delete(event_id: str) -> bool:
    try:
        Arcade(api_key=os.environ["ARCADE_API_KEY"]).tools.execute(
            tool_name="GoogleCalendar.DeleteEvent", user_id=os.environ["ARCADE_USER_ID"],
            input={"event_id": event_id})
        return True
    except Exception:
        return False


async def main(n: int) -> dict:
    print("=== Track A: self-prove the judge before trusting any lap (LAW #4) ===")
    if not J.self_prove():
        print("JUDGE BROKEN -> refusing to run laps."); return {"aborted": "judge_broken"}

    rng = random.Random(time.time_ns())   # fresh, non-memorizable sequence each run
    rows, asks_seen = [], set()
    print(f"\n=== Track A: {n} fresh laps (each a NEW request, proven against the real calendar) ===")
    for i in range(n):
        req = gen.fresh_request(rng)
        ask = req["ask"]
        dup = ask in asks_seen            # honesty: track if a request ever repeats
        asks_seen.add(ask)
        now = datetime.now().astimezone()
        claim = await W.do(ask, now)      # builder
        verdict = J.confirm(claim)        # boss reads reality
        ev = (verdict.get("evidence") or {})
        rows.append({"lap": i + 1, "ask": ask, "duplicate_ask": dup, "worker_status": claim["status"],
                     "event_id": claim.get("event_id"), "summary": claim.get("summary"),
                     "start": claim.get("start_datetime"), "pass": verdict["pass"],
                     "reason": verdict["reason"], "htmlLink": ev.get("htmlLink"),
                     "worker_error": claim.get("error")})
        mark = "PASS" if verdict["pass"] else "FAIL"
        print(f"  [{mark}] lap {i+1:>2}  {ask[:54]:<54}  id={claim.get('event_id') or '-'}")
        if not verdict["pass"]:
            print(f"         reason: {verdict['reason']}  worker_err={claim.get('error')}")

    passes = [r for r in rows if r["pass"]]
    distinct_passed = len({r["ask"] for r in passes})
    # cleanup: keep the last 3 PASSED events visible as morning proof; delete the rest
    keep = {r["event_id"] for r in passes[-3:]}
    deleted, kept = [], []
    for r in rows:
        eid = r["event_id"]
        if not eid:
            continue
        if eid in keep:
            kept.append(eid)
        elif _delete(eid):
            deleted.append(eid)
    summary = {
        "laps": n, "passed": len(passes), "failed": n - len(passes),
        "distinct_requests": len(asks_seen), "distinct_passed": distinct_passed,
        "any_duplicate_ask": any(r["duplicate_ask"] for r in rows),
        "kept_visible_ids": kept, "deleted_ids": deleted, "rows": rows,
    }
    print(f"\n  RESULT: {len(passes)}/{n} fresh laps passed, all {distinct_passed} were DISTINCT requests.")
    print(f"  kept {len(kept)} events visible as proof, cleaned up {len(deleted)}.")
    out = "overnight/track_a/results.json"
    open(out, "w").write(json.dumps(summary, indent=2))
    print(f"  -> {out}")
    return summary


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    asyncio.run(main(n))
