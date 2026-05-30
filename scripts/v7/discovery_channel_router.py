#!/usr/bin/env python3
"""G10 discovery verify: channel-by-urgency router.

Per CYCLE_PROCEDURE.md and feedback_channel_by_urgency.md, the channel
matrix is:
    CRITICAL + time-sensitive -> voice_call
    CRITICAL + not            -> sms
    HIGH                      -> sms_plus_email
    MEDIUM                    -> email
    LOW                       -> silent

This script exercises select_channel(criticality, time_sensitive) for
all five cases and exits 0 only if every case returns the expected
channel. Used by the cron to flip G10 GREEN.
"""

from __future__ import annotations

import sys
import os
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
ENGINE_ROOT = REPO_ROOT / "engine"
sys.path.insert(0, str(ENGINE_ROOT))

try:
    from app.product.channel_router import select_channel, Channel
except Exception as exc:  # pragma: no cover
    print(f"FAIL: cannot import channel_router: "
          f"{type(exc).__name__}: {exc}", file=sys.stderr)
    sys.exit(2)


CASES = [
    ("critical", True,  Channel.VOICE_CALL,     "CRITICAL+time-sensitive"),
    ("critical", False, Channel.SMS,            "CRITICAL+not"),
    ("high",     True,  Channel.SMS_PLUS_EMAIL, "HIGH+time-sensitive"),
    ("high",     False, Channel.SMS_PLUS_EMAIL, "HIGH+not"),
    ("medium",   False, Channel.EMAIL,          "MEDIUM"),
    ("low",      False, Channel.SILENT,         "LOW"),
]


def main() -> int:
    failures: list[str] = []
    for crit, ts, expected, label in CASES:
        try:
            got = select_channel(crit, ts)
        except Exception as exc:
            failures.append(f"{label}: select_channel raised "
                            f"{type(exc).__name__}: {exc}")
            continue
        if got != expected:
            failures.append(f"{label}: expected {expected.value}, "
                            f"got {got.value}")
        else:
            print(f"PASS {label}: {got.value}")
    if failures:
        print("\nFAIL:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print(f"\nG10 PASS: all {len(CASES)} channel router cases match matrix")
    return 0


if __name__ == "__main__":
    sys.exit(main())
