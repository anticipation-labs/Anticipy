"""P0 gate. Runs the five P0 checks and reports one PASS/FAIL.

  portability  nothing environmental outside platform_adapter
  durable      start, journal, hard kill, resume, verify across processes
  resource     the harness runs empty under the 2 GB cap
  logger       the trajectory logger round trips a portable record
  seams        every typed seam interface imports and type checks

Each runs as its own process so env and rlimit isolation is clean.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENGINE = HERE.parent.parent
PYBIN = str(ENGINE / ".venv" / "bin" / "python")

GATES = [
    ("portability", "gate_portability.py", "PORTABILITY: clean"),
    ("durable", "gate_durable.py", "DURABLE_GATE_PASS"),
    ("resource", "gate_resource.py", "RESOURCE_GATE_PASS"),
    ("logger", "gate_logger.py", "LOGGER_GATE_PASS"),
    ("seams", "gate_seams.py", "SEAMS_GATE_PASS"),
]


def main() -> int:
    results = []
    for name, script, marker in GATES:
        t0 = time.time()
        proc = subprocess.run([PYBIN, str(HERE / script)], cwd=str(ENGINE), capture_output=True, text=True)
        out = proc.stdout
        passed = proc.returncode == 0 and marker in out
        results.append((name, passed))
        print(f"\n----- {name} ({time.time() - t0:.1f}s, rc={proc.returncode}) -----")
        print(out.strip())
        if proc.stderr.strip():
            print(f"[{name} stderr] {proc.stderr.strip()[:600]}")

    print("\n===== P0 GATE SUMMARY =====")
    for name, passed in results:
        print(f"  {name:12s} {'PASS' if passed else 'FAIL'}")
    all_pass = all(p for _, p in results)
    print(f"P0_GATE {'PASS' if all_pass else 'FAIL'}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
