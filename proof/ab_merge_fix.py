"""Did the merge fix move Earls, or did the minute?

`second_scenario_proof` runs about 20-25% red on its own, and the failures are
time-correlated: whole windows go bad together. Comparing "5/5 yesterday" to
"4/5 today" therefore says nothing at all, and this repo has a written record
of two good fixes being wrongly condemned exactly that way.

So run BOTH versions ALTERNATELY, inside the same minutes, on the same model:
fix, baseline, fix, baseline. Upstream weather hits both arms equally, and what
is left is the change.

    OPENROUTER_API_KEY=... ANTICIPY_MODEL=google/gemini-2.5-flash \
        python3 proof/ab_merge_fix.py [pairs]
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TARGET = os.path.join(ROOT, "brain", "anticipy_core.py")
PROOF = os.path.join(HERE, "second_scenario_proof.py")

# The one line that differs between the two arms.
FIXED = "        if ratio <= 1 / 3 or len(gained) > len(erased):"
BASELINE = "        if ratio <= 1 / 3:"


def set_arm(fixed: bool) -> None:
    src = open(TARGET).read()
    want, other = (FIXED, BASELINE) if fixed else (BASELINE, FIXED)
    if want in src:
        return
    if other not in src:
        raise SystemExit("neither arm's line found — the code moved, fix this script")
    open(TARGET, "w").write(src.replace(other, want))


def run_once() -> bool:
    env = dict(os.environ, PYTHONPATH=ROOT)
    p = subprocess.run([sys.executable, PROOF], env=env,
                       capture_output=True, text=True, timeout=600)
    out = p.stdout + p.stderr
    if p.returncode != 0:
        why = [l for l in out.splitlines() if l.strip().startswith("FAIL")]
        print(f"        {why[0].strip()[:100] if why else 'failed'}")
    return p.returncode == 0


def main() -> int:
    pairs = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    if not os.environ.get("OPENROUTER_API_KEY"):
        print("SKIP — needs the real model")
        return 0
    print(f"model={os.environ.get('ANTICIPY_MODEL', '(default)')}   "
          f"{pairs} interleaved pairs\n")
    score = {"fix": 0, "baseline": 0}
    try:
        for i in range(pairs):
            for arm in ("fix", "baseline"):
                set_arm(arm == "fix")
                ok = run_once()
                score[arm] += ok
                print(f"  pair {i + 1}  {arm:<8} {'ok' if ok else 'FAILED'}")
    finally:
        set_arm(True)   # always leave the tree on the fix
    print(f"\n  WITH the fix : {score['fix']}/{pairs}")
    print(f"  baseline     : {score['baseline']}/{pairs}")
    if score["fix"] < score["baseline"]:
        print("\n  The fix looks WORSE on Earls. Do not ship it on dinner alone.")
    elif score["fix"] == score["baseline"]:
        print("\n  No difference on Earls — the fix is neutral here, and its "
              "case is dinner.")
    else:
        print("\n  The fix looks better here too.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
