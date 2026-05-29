#!/usr/bin/env python3
"""G2 discovery verify: trivia fires.

Per CYCLE_PROCEDURE.md G2: inject a trivia phrase, the engine fires
the trivia cache lookup, the answer is correct, perceived audio
latency below 2 seconds.

This script picks one canonical trivia phrase, posts it via
/api/listen/inject, waits briefly, then reads /api/trivia/recent to
confirm a fire landed with low total_latency_ms.

Exit 0 only if a trivia fire is found within the last 5 seconds and
the answer text is non-empty.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
import urllib.error

ENGINE = os.environ.get("ANTICIPY_ENGINE", "http://127.0.0.1:8731")
PHRASE = os.environ.get(
    "ANTICIPY_TRIVIA_PHRASE",
    "wait, when did the Roman Empire fall",
)


def _get(path: str, timeout: float = 5.0) -> tuple[int, dict]:
    req = urllib.request.Request(ENGINE + path)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(
                resp.read().decode("utf-8", "replace"))
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


def main() -> int:
    print(f"discovery_trivia: engine={ENGINE}, phrase={PHRASE!r}")
    code, health = _get("/health")
    if code != 200:
        print(f"FAIL: engine not healthy ({code}): {health}", file=sys.stderr)
        return 2

    cutoff = time.time() - 0.5
    print("step 1: inject trivia phrase")
    t0 = time.time()
    code, resp = _post("/api/listen/inject", {
        "text": PHRASE,
        "speaker_count": 2,
    })
    inject_ms = (time.time() - t0) * 1000.0
    if code != 200:
        print(f"FAIL: inject {code}: {resp}", file=sys.stderr)
        return 2
    print(f"  inject status={code} in {inject_ms:.0f} ms; outcome="
          f"{resp.get('outcome')}")

    # Give cache+TTS spawn a moment
    time.sleep(0.6)

    print("step 2: read /api/trivia/recent")
    code, recent = _get("/api/trivia/recent")
    if code != 200:
        print(f"FAIL: trivia/recent {code}: {recent}", file=sys.stderr)
        return 2
    fires = recent.get("fires") or []
    if not fires:
        print("FAIL: no trivia fires", file=sys.stderr)
        return 1
    fresh = [f for f in fires if float(f.get("ts") or 0.0) >= cutoff]
    print(f"  total fires={len(fires)}, fresh={len(fresh)}")
    if not fresh:
        print("FAIL: no FRESH trivia fire from this run", file=sys.stderr)
        return 1
    fire = fresh[0]
    answer = fire.get("answer") or ""
    total_ms = float(fire.get("total_latency_ms") or 0.0)
    tts = fire.get("tts") or {}
    print(f"  answer={answer!r}")
    print(f"  total_latency_ms={total_ms}, tts={tts}")
    if not answer.strip():
        print("FAIL: empty answer", file=sys.stderr)
        return 1
    if total_ms > 2000.0:
        print(f"FAIL: latency {total_ms} ms exceeds 2000 ms ceiling",
              file=sys.stderr)
        return 1

    print(f"\nG2 PASS: trivia fired in {total_ms} ms with non-empty answer")
    return 0


if __name__ == "__main__":
    sys.exit(main())
