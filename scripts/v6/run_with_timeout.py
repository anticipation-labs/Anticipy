#!/usr/bin/env python3
"""Run a command with a hard wall-clock timeout and kill its process group."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: run_with_timeout.py SECONDS COMMAND [ARG...]", file=sys.stderr)
        return 64
    try:
        seconds = float(sys.argv[1])
    except ValueError:
        print(f"invalid timeout: {sys.argv[1]}", file=sys.stderr)
        return 64
    command = sys.argv[2:]
    proc = subprocess.Popen(command, start_new_session=True)
    try:
        return proc.wait(timeout=seconds)
    except subprocess.TimeoutExpired:
        print(
            f"timeout after {seconds:g}s: {' '.join(command)}",
            file=sys.stderr,
            flush=True,
        )
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        deadline = time.time() + 5
        while time.time() < deadline:
            if proc.poll() is not None:
                return 124
            time.sleep(0.1)
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait()
        return 124


if __name__ == "__main__":
    raise SystemExit(main())
