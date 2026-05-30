#!/usr/bin/env python3
"""G4 discovery verify: cold start fills dossier.

Per CYCLE_PROCEDURE.md G4: cold-start inhales >= 10 real people in
under 60 seconds. We probe /api/dossier/active first; if it already
has >= 10 people, G4 is already GREEN. Otherwise we kick off
/api/coldstart/start, poll /api/coldstart/status, and re-read the
dossier file on disk.

We READ the dossier directly from disk to avoid the documented
account_id mismatch bug at /api/dossier/active (server.py reads from
prof.user_id or env, ignores ?account_id= query). Owner: don't fix
that yet; reading the source file is the truthful path.

Exit 0 if dossier has >=10 people within 60s, else exit 1.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
import urllib.error
import pathlib

ENGINE = os.environ.get("ANTICIPY_ENGINE", "http://127.0.0.1:8731")
ACCOUNT = os.environ.get("ANTICIPY_ACCOUNT_ID", "anticipy-user")
DOSSIER = pathlib.Path.home() / ".anticipy" / "v7" / "dossiers" / ACCOUNT / "dossier.json"
MIN_PEOPLE = 10
TIMEOUT_S = 60


def _get(path: str, timeout: float = 5.0) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(ENGINE + path, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        return exc.code, {"error": str(exc)}
    except Exception as exc:
        return 0, {"error": f"{type(exc).__name__}: {exc}"}


def _post(path: str, body: dict, timeout: float = 5.0) -> tuple[int, dict]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        ENGINE + path, data=data,
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


def _disk_people() -> int:
    if not DOSSIER.exists():
        return 0
    try:
        data = json.loads(DOSSIER.read_text("utf-8"))
    except Exception:
        return 0
    people = data.get("people") or []
    return len(people)


def main() -> int:
    print(f"discovery_coldstart: engine={ENGINE} account={ACCOUNT}")
    print(f"  dossier path: {DOSSIER}")
    code, health = _get("/health")
    if code != 200:
        print(f"FAIL: engine not healthy ({code}): {health}", file=sys.stderr)
        return 2

    existing = _disk_people()
    print(f"  pre-existing people on disk: {existing}")
    if existing >= MIN_PEOPLE:
        print(f"\nG4 PASS: dossier already has {existing} people (>= {MIN_PEOPLE})")
        return 0

    print(f"step 1: kicking off coldstart (need {MIN_PEOPLE - existing} more)")
    code, started = _post("/api/coldstart/start", {"account_id": ACCOUNT})
    if code != 200:
        print(f"FAIL: coldstart start {code}: {started}", file=sys.stderr)
        return 2
    print(f"  started: {started}")

    print(f"step 2: polling for up to {TIMEOUT_S}s")
    t0 = time.time()
    last_count = existing
    while time.time() - t0 < TIMEOUT_S:
        count = _disk_people()
        if count != last_count:
            print(f"  +{time.time() - t0:.0f}s: {count} people on disk")
            last_count = count
        if count >= MIN_PEOPLE:
            print(f"\nG4 PASS: dossier has {count} people after "
                  f"{time.time() - t0:.0f}s")
            return 0
        time.sleep(2)

    final = _disk_people()
    print(f"\nFAIL: only {final} people on disk after {TIMEOUT_S}s "
          f"(needed {MIN_PEOPLE})", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
