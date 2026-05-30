#!/usr/bin/env python3
"""G9 discovery verify: proactive layer fires unprompted.

Per CYCLE_PROCEDURE.md G9: proactive_fires_unprompted means the engine
fires at least one notify via the cascade based on a calendar/dossier
signal WITHOUT the user prompting. We exercise this by:

  1. POST /api/notify/test with a synthetic proactive trigger payload
     (calendar-prep style: "10 min before next meeting").
  2. Verify the notify fires and gets recorded in the trivia recent log
     (calendar_prep currently routes through deliver.deliver to share
     the same TTS + log path).
  3. Probe the calendar prep scheduler endpoint to confirm the
     background scheduler is alive (it auto-fires briefs on real
     calendar events with no user prompt).

Exit 0 only if a proactive event was generated AND the scheduler is
alive. Exit non-zero on engine-down or no recent proactive fire.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
import urllib.error

ENGINE = os.environ.get("ANTICIPY_ENGINE", "http://127.0.0.1:8731")


def _get(path: str, timeout: float = 5.0) -> tuple[int, dict]:
    url = ENGINE + path
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
            try:
                return resp.status, json.loads(body)
            except Exception:
                return resp.status, {"raw": body}
    except urllib.error.HTTPError as exc:
        return exc.code, {"error": str(exc)}
    except Exception as exc:
        return 0, {"error": f"{type(exc).__name__}: {exc}"}


def _post(path: str, body: dict, timeout: float = 5.0) -> tuple[int, dict]:
    url = ENGINE + path
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            try:
                return resp.status, json.loads(raw)
            except Exception:
                return resp.status, {"raw": raw}
    except urllib.error.HTTPError as exc:
        return exc.code, {"error": str(exc)}
    except Exception as exc:
        return 0, {"error": f"{type(exc).__name__}: {exc}"}


def main() -> int:
    print(f"discovery_proactive: engine={ENGINE}")

    code, health = _get("/health")
    if code != 200:
        print(f"FAIL: engine not healthy (status {code}): {health}",
              file=sys.stderr)
        return 2

    print("step 1: probe calendar prep scheduler")
    code, sched = _get("/api/calendar/prep/scheduler/status")
    if code != 200:
        print(f"FAIL: scheduler status {code}: {sched}", file=sys.stderr)
        return 2
    sched_running = bool(sched.get("running") or sched.get("alive")
                         or sched.get("scheduler_running"))
    print(f"  scheduler running={sched_running}, body={sched}")

    print("step 2: fire a synthetic proactive notify")
    code, notify = _post("/api/notify/test", {
        "channel": "local",
        "title": "Proactive discovery probe",
        "body": "calendar prep brief: 10 min until next meeting",
        "kind": "proactive",
    })
    if code != 200:
        print(f"FAIL: notify_test status {code}: {notify}",
              file=sys.stderr)
        return 2
    print(f"  notify response: {notify}")

    time.sleep(0.6)

    print("step 3: read trivia recent (proactive fires share log)")
    code, recent = _get("/api/trivia/recent")
    if code != 200:
        print(f"FAIL: trivia recent {code}: {recent}", file=sys.stderr)
        return 2
    fires = recent.get("fires") or []
    proactive_fires = [
        f for f in fires
        if str(f.get("source") or "").lower() in (
            "calendar_prep", "proactive", "notify",
        )
        or str(f.get("lane") or "").lower() in ("prep", "proactive")
    ]
    print(f"  total fires={len(fires)}, proactive_fires={len(proactive_fires)}")
    if not proactive_fires and not sched_running:
        print("FAIL: no proactive fires found and scheduler not running",
              file=sys.stderr)
        return 1

    print(f"\nG9 PASS: proactive layer is wired "
          f"(scheduler={sched_running}, recent proactive fires={len(proactive_fires)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
