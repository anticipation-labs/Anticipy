"""
spec_from_failure.py — Read a journey.sh failure log, produce a precise spec for the active agent.

The spec includes:
- Which step failed
- Exact verifier output that failed
- The relevant doc references (JOURNEY.md, RISK_TIERS.md, REFERENCE_RESOLUTION.md, BRAND.md)
- Suggested change locations in the codebase (not forced, agent decides)
- Verification criteria to re-check after the change
- An explicit "do not declare done until the verifier passes 10 consecutive runs" reminder

Usage:
    python3 scripts/spec_from_failure.py --log <path> --out state/work/next.md
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path


STEP_TO_DOCS = {
    1: ["docs/JOURNEY.md", "docs/BRAND.md", "docs/ARCHITECTURE.md"],
    2: ["docs/JOURNEY.md", "docs/ARCHITECTURE.md"],
    3: ["docs/JOURNEY.md", "docs/ARCHITECTURE.md"],
    4: ["docs/JOURNEY.md", "docs/ARCHITECTURE.md", "docs/BRAND.md"],
    5: ["docs/JOURNEY.md", "docs/REFERENCE_RESOLUTION.md", "docs/BRAND.md"],
    6: ["docs/JOURNEY.md", "docs/INPUTS.md", "docs/REFERENCE_RESOLUTION.md"],
    7: ["docs/JOURNEY.md", "docs/RISK_TIERS.md", "docs/REFERENCE_RESOLUTION.md"],
}

STEP_NAMES = {
    1: "Web front door",
    2: "Signup",
    3: "Download",
    4: "Install and launch",
    5: "Onboarding (dossier build)",
    6: "Input pipeline",
    7: "Action execution",
}


def parse_failed_step(log_text: str) -> int | None:
    """Find the failed step number in the journey log."""
    # journey.sh prints lines like "Step 4 FAILED (exit ...)"
    m = re.search(r"Step (\d) FAILED", log_text)
    if m:
        return int(m.group(1))
    # fallback: read state/journey-runs/*/failed_step.txt
    runs = sorted(Path("state/journey-runs").glob("*/failed_step.txt"))
    if runs:
        try:
            n = int(runs[-1].read_text().strip())
            if n > 0:
                return n
        except Exception:
            pass
    return None


def extract_step_log(log_text: str, step: int) -> str:
    """Pull the last 50 lines of relevant log for the failed step."""
    runs = sorted(Path("state/journey-runs").glob("*"))
    if not runs:
        return "(no run dir found)"
    latest = runs[-1]
    step_log = latest / f"step_{step}.log"
    if not step_log.exists():
        return "(step log missing)"
    lines = step_log.read_text().splitlines()
    return "\n".join(lines[-50:])


def write_spec(step: int, journey_log: str, step_log: str, out_path: str) -> None:
    docs = STEP_TO_DOCS.get(step, [])
    name = STEP_NAMES.get(step, "Unknown")

    spec = f"""# Work spec — generated from journey failure

Cycle generated: {os.environ.get("CYCLE", "unknown")}
Failed step: **{step} — {name}**

## What the verifier saw

```
{step_log}
```

## Read first (in this order)

{chr(10).join(f"- `{d}`" for d in docs)}
- `AGENTS.md` (rules, frozen paths, model picks)
- `verifier/steps/step{step}_*.py` (the exact verifier code that failed — read it to understand the contract)

## What you do

1. Open the verifier file at `verifier/steps/step{step}_*.py`. Read it line by line until you understand the exact assertion that failed.
2. Find the code in the product that should satisfy that assertion. Read it.
3. If the assertion's expected behavior is wrong (the verifier itself has a bug), STOP. Verifier changes require Omar approval via `state/decisions/queue.md`. Write the decision item and pick the closest workaround in the meantime.
4. If the product code is wrong, fix it. Stay inside non-frozen paths unless the issue is genuinely in a frozen path (see Rule 3 in `BOOTSTRAP.md` for the verifier-first procedure).
5. After implementing, run `bash scripts/journey.sh` locally. Confirm the step passes.
6. Run it 9 more times in a row. If any of those fails, you have not actually fixed it — flicker means the fix is incomplete.
7. Commit with message: `step{step}: <one-line description of the fix>`. Do not declare done in a comment, a status file, or a chat. The loop will decide done.

## Do not

- Add new dependencies without checking the cost budget in `docs/COST_BUDGET.md`.
- Touch frozen paths without writing a verifier first.
- Use any model not on the allowlist in `AGENTS.md`.
- Use em-dashes anywhere.
- Mark the step as fixed via a state file write — the loop reads journey.sh exit code, nothing else.

## When you're stuck after 90 minutes

Write a `state/decisions/queue.md` item with your best read of the problem, two candidate fixes with their tradeoffs, and your default pick. Execute the default. Keep moving.
"""

    Path(out_path).write_text(spec)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--log", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()

    log_text = Path(args.log).read_text() if Path(args.log).exists() else ""
    step = parse_failed_step(log_text)
    if step is None:
        Path(args.out).write_text(
            "# Work spec\n\nJourney exited non-zero but no step number was identified. "
            "Inspect `state/journey-runs/` directly and write the spec manually.\n"
        )
        sys.exit(0)
    step_log = extract_step_log(log_text, step)
    write_spec(step, log_text, step_log, args.out)


if __name__ == "__main__":
    main()
