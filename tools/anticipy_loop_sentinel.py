#!/usr/bin/env python3
"""Anticipy loop sentinel helper.

Pure-stdlib Python utility. Called by tools/anticipy_loop_sentinel.sh to
parse messy text outputs, do JSON math, write the per-iteration verdict
file, and track consecutive RED counters.

The sentinel itself NEVER restarts processes, never kills agents, never
modifies engine state. This helper only reads, parses, and writes JSON
under state/orchestrator/. Decisions live with the operator.

CLI surface (one subcommand per iteration step):
  parse-cost-stats <stdout-file>             prints GREEN|RED + evidence
  parse-trivia    <stdout-file>              prints GREEN|RED + evidence
  parse-channel-router <stdout-file>         prints GREEN|RED + evidence
  parse-recovery  <stdout-file>              prints GREEN|RED + evidence
  parse-health    <stdout-file> <engine-pid> prints GREEN|RED + evidence
  z001-age        <runs-dir>                 prints age in seconds, or -1
  write-verdict   <state-dir> <gates-json> <z001-age-seconds>
                                             writes SENTINEL_LATEST.json
                                             writes SENTINEL_ALERT.json on any RED
                                             writes SENTINEL_STOP.json on 3 consecutive RED
                                             prints overall verdict

Exit code is always 0 unless an internal exception fires.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Tuple


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except FileNotFoundError:
        return ""


def parse_trivia_output(text: str) -> Tuple[str, str]:
    """discovery_trivia.py prints 'G2 PASS: trivia fired in <n> ms ...'.

    GREEN if PASS line present AND latency below 500 ms.
    """
    if not text.strip():
        return "RED", "empty output from discovery_trivia"
    pass_match = re.search(r"G2 PASS: trivia fired in ([0-9.]+) ms", text)
    if not pass_match:
        first_err = next(
            (line for line in text.splitlines() if "FAIL" in line or "Error" in line),
            text.strip().splitlines()[-1] if text.strip().splitlines() else "no PASS line",
        )
        return "RED", f"no G2 PASS line; tail={first_err[:160]}"
    ms = float(pass_match.group(1))
    if ms > 500.0:
        return "RED", f"latency {ms:.2f} ms exceeds 500 ms ceiling"
    return "GREEN", f"{ms:.2f} ms"


def parse_channel_router_output(text: str) -> Tuple[str, str]:
    """discovery_channel_router.py prints 'G10 PASS: all 6 channel router cases match matrix'."""
    if not text.strip():
        return "RED", "empty output from discovery_channel_router"
    if "G10 PASS" not in text:
        passes = len(re.findall(r"^PASS ", text, re.MULTILINE))
        fails = len(re.findall(r"^FAIL ", text, re.MULTILINE))
        return "RED", f"no G10 PASS line; pass={passes} fail={fails}"
    cases = re.findall(r"^PASS ", text, re.MULTILINE)
    return "GREEN", f"{len(cases)}/6"


def parse_cost_stats(text: str) -> Tuple[str, str]:
    """/api/cost/stats payload. G11 is GREEN as long as p95 cost is below
    the per-task hard cap and the endpoint responded with ok=true."""
    if not text.strip():
        return "RED", "empty body from /api/cost/stats"
    try:
        body = json.loads(text)
    except json.JSONDecodeError as exc:
        return "RED", f"invalid JSON from /api/cost/stats: {exc}"
    if not body.get("ok"):
        return "RED", f"cost stats ok=false body={text[:120]}"
    stats = body.get("stats", {}) or {}
    p95 = float(stats.get("p95_cost_usd", 0.0) or 0.0)
    hard_cap = float(stats.get("per_task_hard_cap_usd", 0.005) or 0.005)
    if p95 > hard_cap:
        return "RED", f"p95={p95:.6f} exceeds hard_cap={hard_cap}"
    return "GREEN", f"p95={p95}"


def parse_recovery(text: str) -> Tuple[str, str]:
    """/api/recovery/test payload. G12 GREEN when ok=true, sms_body_len in
    [40, 160] (single SMS), and an sms_body string is present."""
    if not text.strip():
        return "RED", "empty body from /api/recovery/test"
    try:
        body = json.loads(text)
    except json.JSONDecodeError as exc:
        return "RED", f"invalid JSON from /api/recovery/test: {exc}"
    if not body.get("ok"):
        return "RED", f"recovery ok=false body={text[:120]}"
    sms_body = body.get("sms_body") or ""
    sms_len = int(body.get("sms_body_len", 0) or 0)
    if not sms_body:
        return "RED", "recovery returned empty sms_body"
    if sms_len < 20 or sms_len > 160:
        return "RED", f"sms_body_len {sms_len} outside [20,160]"
    return "GREEN", f"{sms_len} char SMS"


def parse_health(text: str, engine_pid: str) -> Tuple[str, str]:
    """/health endpoint plus a quick ps lookup. RED if curl produced no
    body or ok=false. PID + etime added as evidence when discoverable."""
    if not text.strip():
        return "RED", "engine /health returned empty body (curl failed?)"
    try:
        body = json.loads(text)
    except json.JSONDecodeError as exc:
        return "RED", f"invalid JSON from /health: {exc}"
    if not body.get("ok"):
        return "RED", f"engine /health ok=false body={text[:120]}"
    pid = body.get("pid") or engine_pid or ""
    etime = ""
    if pid:
        try:
            import subprocess

            out = subprocess.run(
                ["ps", "-p", str(pid), "-o", "etime="],
                capture_output=True,
                text=True,
                timeout=3,
            )
            etime = out.stdout.strip()
        except Exception:
            etime = ""
    return "GREEN", f"pid {pid} etime {etime or 'unknown'}"


def z001_newest_age_seconds(runs_dir: str) -> int:
    """Return seconds since the newest z001 result.json mtime, or -1 if
    no result.json under the dir."""
    root = Path(runs_dir)
    if not root.exists():
        return -1
    newest = -1.0
    for child in root.iterdir():
        if not child.is_dir():
            continue
        result = child / "result.json"
        if result.exists():
            mtime = result.stat().st_mtime
            if mtime > newest:
                newest = mtime
    if newest < 0:
        return -1
    return int(time.time() - newest)


def write_verdict(state_dir: str, gates_path: str, z001_age_seconds: int) -> str:
    """Write SENTINEL_LATEST.json, SENTINEL_ALERT.json (on RED), and
    SENTINEL_STOP.json (on 3 consecutive RED). Returns overall verdict."""
    state = Path(state_dir)
    state.mkdir(parents=True, exist_ok=True)
    with open(gates_path, "r", encoding="utf-8") as fh:
        gates = json.load(fh)
    overall = "GREEN"
    failures = []
    for name, info in gates.items():
        if info.get("status") != "GREEN":
            overall = "RED"
            failures.append({"gate": name, "evidence": info.get("evidence", "")})
    latest_path = state / "SENTINEL_LATEST.json"
    prev_green = 0
    prev_red = 0
    if latest_path.exists():
        try:
            prev = json.loads(latest_path.read_text())
            prev_green = int(prev.get("consecutive_green_iterations", 0) or 0)
            prev_red = int(prev.get("consecutive_red_iterations", 0) or 0)
        except Exception:
            prev_green = 0
            prev_red = 0
    if overall == "GREEN":
        cons_green = prev_green + 1
        cons_red = 0
    else:
        cons_green = 0
        cons_red = prev_red + 1
    payload = {
        "last_check_ts": _utcnow_iso(),
        "verdict": overall,
        "gates": gates,
        "consecutive_green_iterations": cons_green,
        "consecutive_red_iterations": cons_red,
        "z001_age_seconds": z001_age_seconds,
    }
    tmp = latest_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True))
    os.replace(tmp, latest_path)
    alert_path = state / "SENTINEL_ALERT.json"
    if overall == "RED":
        alert = {
            "alert_ts": _utcnow_iso(),
            "failures": failures,
            "consecutive_red_iterations": cons_red,
            "suggested_action": (
                "Investigate the first RED gate listed. Common causes: engine "
                "process died, port 8731 not listening, OpenRouter 402, or an "
                "agent commit broke a /api route. Run "
                "tools/anticipy_agent_completion_verifier.sh against the last "
                "claimed-good commit to confirm baseline."
            ),
        }
        alert_path.write_text(json.dumps(alert, indent=2, sort_keys=True))
    else:
        try:
            if alert_path.exists():
                alert_path.unlink()
        except Exception:
            pass
    stop_path = state / "SENTINEL_STOP.json"
    if cons_red >= 3:
        stop = {
            "stop_ts": _utcnow_iso(),
            "consecutive_red_iterations": cons_red,
            "failures": failures,
            "halt_recommendation": (
                "3 consecutive RED iterations. Pause all parallel agents until "
                "operator intervenes. The sentinel does NOT restart anything; "
                "operator must inspect SENTINEL_ALERT.json, fix the engine or "
                "revert the offending commit, then delete this file to clear "
                "the halt flag."
            ),
        }
        stop_path.write_text(json.dumps(stop, indent=2, sort_keys=True))
    else:
        try:
            if stop_path.exists():
                stop_path.unlink()
        except Exception:
            pass
    return overall


def check_consecutive_red(state_dir: str) -> int:
    latest = Path(state_dir) / "SENTINEL_LATEST.json"
    if not latest.exists():
        return 0
    try:
        data = json.loads(latest.read_text())
        return int(data.get("consecutive_red_iterations", 0) or 0)
    except Exception:
        return 0


def should_alert(state_dir: str) -> bool:
    return (Path(state_dir) / "SENTINEL_ALERT.json").exists()


_COMMANDS = {
    "parse-trivia": lambda args: parse_trivia_output(_read(args[0])),
    "parse-channel-router": lambda args: parse_channel_router_output(_read(args[0])),
    "parse-cost-stats": lambda args: parse_cost_stats(_read(args[0])),
    "parse-recovery": lambda args: parse_recovery(_read(args[0])),
    "parse-health": lambda args: parse_health(_read(args[0]), args[1] if len(args) > 1 else ""),
}


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: anticipy_loop_sentinel.py <command> [args]", file=sys.stderr)
        return 2
    cmd = argv[1]
    args = argv[2:]
    if cmd in _COMMANDS:
        status, evidence = _COMMANDS[cmd](args)
        print(json.dumps({"status": status, "evidence": evidence}))
        return 0
    if cmd == "z001-age":
        if not args:
            print("usage: anticipy_loop_sentinel.py z001-age <runs-dir>", file=sys.stderr)
            return 2
        print(z001_newest_age_seconds(args[0]))
        return 0
    if cmd == "write-verdict":
        if len(args) < 3:
            print(
                "usage: anticipy_loop_sentinel.py write-verdict <state-dir> <gates-json> <z001-age-s>",
                file=sys.stderr,
            )
            return 2
        verdict = write_verdict(args[0], args[1], int(args[2]))
        print(verdict)
        return 0
    if cmd == "check-consecutive-red":
        print(check_consecutive_red(args[0] if args else "state/orchestrator"))
        return 0
    if cmd == "should-alert":
        print("yes" if should_alert(args[0] if args else "state/orchestrator") else "no")
        return 0
    print(f"unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
