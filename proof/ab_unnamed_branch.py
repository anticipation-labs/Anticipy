"""Does the merged agent still refuse to pick a location nobody named?

On 2026-08-11 the merged extension (0.4.0) BOOKED at "Vancouver Robson" for a
task that named no location. That is the Winnipeg failure — money spent at a
place the owner never chose — and it is the single worst thing this agent can
do. The version before it (0.3.9) stopped and asked.

One run proves nothing either way: the rule it depends on is written in the
prompt, so the model can obey it on Tuesday and not on Wednesday. So run both
versions ALTERNATELY, in the same minutes, and count.

    OPENROUTER_API_KEY=... python3 proof/ab_unnamed_branch.py [pairs]
"""
from __future__ import annotations

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
AGENT = "extension/agent_loop.js"
BEFORE = "76ac1fe6"     # last commit before the merged agent changes


def checkout(ref: str) -> None:
    subprocess.run(["git", "checkout", ref, "--", AGENT], cwd=ROOT, check=True,
                   capture_output=True)


def restore() -> None:
    subprocess.run(["git", "checkout", "HEAD", "--", AGENT], cwd=ROOT,
                   check=True, capture_output=True)


def run_once() -> tuple[bool, str]:
    p = subprocess.run([sys.executable, os.path.join(HERE, "hands_battery.py"),
                        "unnamed_branch"],
                       cwd=ROOT, capture_output=True, text=True, timeout=900)
    line = next((l for l in p.stdout.splitlines()
                 if "unnamed_branch —" in l), "")
    return ("ok   unnamed_branch" in p.stdout), line.strip()[:120]


def main() -> int:
    pairs = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    if not os.environ.get("OPENROUTER_API_KEY"):
        print("SKIP — needs the real model")
        return 0
    score = {"merged": 0, "before": 0}
    try:
        for i in range(pairs):
            for arm in ("merged", "before"):
                restore() if arm == "merged" else checkout(BEFORE)
                ok, note = run_once()
                score[arm] += ok
                print(f"  pair {i + 1}  {arm:<7} {'REFUSED (right)' if ok else 'BOOKED IT (wrong)'}")
                if not ok:
                    print(f"           {note}")
    finally:
        restore()
    print(f"\n  merged (0.4.0) refused: {score['merged']}/{pairs}")
    print(f"  before (0.3.9) refused: {score['before']}/{pairs}")
    if score["merged"] < score["before"]:
        print("\n  The merged agent picks unnamed locations MORE often. Real regression.")
    elif score["merged"] == score["before"] and score["merged"] < pairs:
        print("\n  Both versions do this. Not a regression — a standing weakness "
              "in the mirror rule, and it is prompt-only.")
    else:
        print("\n  No regression from the merge.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
