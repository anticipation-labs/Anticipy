#!/usr/bin/env bash
# Run the whole local engine over one builder-visible day and write a replayable trace.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$REPO/engine/.venv/bin/python"

cd "$REPO"
mkdir -p logs/trace logs realdays/raw

"$PY" - "$@" <<'PY'
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request

REPO = Path.cwd()
sys.path.insert(0, str(REPO / "engine"))

from anticipy_engine.capture.transcribe import is_audio_file, transcribe_audio

BASE = os.environ.get("ANTICIPY_ENGINE_BASE", "http://127.0.0.1:8787")
LAP = os.environ.get("AUTOPILOT_LAP") or dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
TRACE = REPO / "logs" / "trace" / f"{LAP}.jsonl"
LAST = REPO / "logs" / "last_realday.json"


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def write_step(action: str, target: str, input_summary: str, result: str, **extra: object) -> None:
    row = {
        "ts": now(),
        "lap": LAP,
        "phase": "test",
        "actor": "realday_harness",
        "action": action,
        "target": target,
        "input_summary": input_summary,
        "result": result,
        "proof_ref": str(LAST.relative_to(REPO)) if LAST.exists() else "",
        "tokens": 0,
        "cost_usd": 0.0,
    }
    row.update(extra)
    with TRACE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, sort_keys=True) + "\n")


def http(method: str, path: str, body: dict | None = None, timeout: int = 180) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw) if raw else {}


def choose_day(argv: list[str]) -> tuple[str, list[str], bool, dict]:
    if argv:
        p = Path(argv[0]).expanduser()
        if not p.is_absolute():
            p = REPO / p
        if is_audio_file(p):
            transcript = transcribe_audio(p)
            return p.stem, transcript.lines, False, {"kind": "audio", **transcript.metadata}
        text = p.read_text(encoding="utf-8")
        return p.stem, [ln.strip() for ln in text.splitlines() if ln.strip()], False, {"kind": "text", "path": str(p)}

    raw = sorted((REPO / "realdays" / "raw").glob("*"))
    readable = [p for p in raw if p.is_file() and not is_audio_file(p)]
    if readable:
        p = readable[0]
        text = p.read_text(encoding="utf-8")
        return p.stem, [ln.strip() for ln in text.splitlines() if ln.strip()], False, {"kind": "text", "path": str(p)}

    audio = [p for p in raw if p.is_file() and is_audio_file(p)]
    if audio:
        p = audio[0]
        transcript = transcribe_audio(p)
        return p.stem, transcript.lines, False, {"kind": "audio", **transcript.metadata}

    return (
        "setup-smoke-sample",
        ["The weather is nice today. This setup smoke line should stay silent."],
        True,
        {"kind": "synthetic_setup_sample"},
    )


def main() -> int:
    TRACE.parent.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    day_id, lines, synthetic, source = choose_day(sys.argv[1:])
    write_step("select_day", "realdays/raw", day_id, "ok", synthetic_setup_sample=synthetic, source=source)

    try:
        health = http("GET", "/health", timeout=5)
    except Exception as e:
        write_step("health", BASE + "/health", "", f"fail: {type(e).__name__}: {e}")
        return 2
    write_step("health", BASE + "/health", "", "ok", response=health)

    decisions: dict[str, int] = {}
    rows: list[dict] = []
    for idx, line in enumerate(lines, start=1):
        try:
            out = http("POST", "/event", {"text": line, "source": "app"}, timeout=240)
            decision = str(out.get("decision", "unknown"))
            decisions[decision] = decisions.get(decision, 0) + 1
            rows.append({"line": idx, "decision": decision, "response": out})
            write_step("post_event", BASE + "/event", line[:180], "ok", decision=decision, response=out)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            write_step("post_event", BASE + "/event", line[:180], f"fail: HTTP {e.code}", body=body[:500])
            return 3
        except Exception as e:
            write_step("post_event", BASE + "/event", line[:180], f"fail: {type(e).__name__}: {e}")
            return 3

    try:
        glassbox = http("GET", "/glassbox?limit=80", timeout=10)
    except Exception as e:
        glassbox = {"error": f"{type(e).__name__}: {e}"}
    try:
        scorecard = http("GET", "/scorecard", timeout=10)
    except Exception as e:
        scorecard = {"error": f"{type(e).__name__}: {e}"}

    summary = {
        "lap": LAP,
        "realday_id": day_id,
        "synthetic_setup_sample": synthetic,
        "line_count": len(lines),
        "source": source,
        "decisions": decisions,
        "events": rows,
        "glassbox_tail": glassbox,
        "scorecard": scorecard,
        "wall_seconds": round(time.perf_counter() - start, 3),
        "trace": str(TRACE.relative_to(REPO)),
    }
    LAST.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_step("write_summary", str(LAST.relative_to(REPO)), day_id, "ok", summary=summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


raise SystemExit(main())
PY
