#!/usr/bin/env python3
"""Run the maintained content, authorship, approval and delivery contracts.

The August 4 inline rig is retired: it assumed a missing authorship verdict
licensed action, inferred dictation from fluency, and omitted today's effect
schema. Its untouched HEAD baseline fails 17 assertions then raises TypeError
on _queue_job(touches=...). Those obsolete expectations must not weaken the
current fail-closed authorship floor or restore the deleted word classifier.

Real contextual model and whole-worker evidence is separate, in
research/overnight-2026-09-07/ambient-context-repair.md. This command proves
wiring and failure behavior only, never live model accuracy or phone delivery.
"""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if __name__ == "__main__":
    raise SystemExit(subprocess.call([sys.executable, "-m", "pytest", "-q",
        "tests/test_read_into_a_machine.py", "tests/test_owes.py",
        "tests/test_no_verdict_is_below_the_floor.py",
        "tests/test_pending_question_delivery.py",
        "tests/test_phone_revocation_notification_boundary.py"], cwd=ROOT))
