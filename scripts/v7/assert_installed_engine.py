#!/usr/bin/env python3
"""Fail unless 127.0.0.1:8731 is served by the installed Anticipy app."""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.request


PORT = "8731"
EXPECTED_PREFIX = "/Applications/Anticipy.app/Contents/MacOS/anticipy-engine"


def _run(cmd: list[str]) -> str:
    return subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT).strip()


def main() -> int:
    try:
        pids = _run(["lsof", "-tiTCP:" + PORT, "-sTCP:LISTEN"]).splitlines()
    except subprocess.CalledProcessError as exc:
        print(f"no listener on 127.0.0.1:{PORT}: {exc.output}", file=sys.stderr)
        return 1
    if len(pids) != 1:
        print(f"expected one listener on {PORT}, found {pids}", file=sys.stderr)
        return 1

    pid = pids[0].strip()
    command = _run(["ps", "-p", pid, "-o", "command="])
    command_token = (command.split() or [""])[0]
    if command_token != EXPECTED_PREFIX:
        print(
            "port 8731 is not the installed user-device engine; "
            f"pid={pid} command={command!r}",
            file=sys.stderr,
        )
        return 1

    with urllib.request.urlopen("http://127.0.0.1:8731/health", timeout=5) as resp:
        health = json.loads(resp.read().decode("utf-8"))
    if health.get("ok") is not True:
        print(f"installed engine health is not ok: {health}", file=sys.stderr)
        return 1
    if int(health.get("pid") or -1) != int(pid):
        print(f"health pid does not match lsof pid: pid={pid} health={health}", file=sys.stderr)
        return 1
    if int(health.get("port") or -1) != int(PORT):
        print(f"health port does not match {PORT}: {health}", file=sys.stderr)
        return 1
    if health.get("service") != "anticipy-local-engine":
        print(f"unexpected health service: {health}", file=sys.stderr)
        return 1
    if health.get("version") != "product-3":
        print(f"unexpected health version: {health}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "ok": True,
                "port": 8731,
                "pid": int(pid),
                "command": command,
                "command_token": command_token,
                "health": health,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
