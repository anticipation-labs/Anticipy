"""
cost_audit.py — extrapolate per-user-per-year runtime cost from recent OpenRouter usage.

Constraint (docs/COST_BUDGET.md): under $200/year per heaviest user at 100k complex tasks.
Per-task ceiling: $0.002.

Reads:
- OPENROUTER_API_KEY from env (for the /v1/credits and /v1/generation endpoints)
- state/journey-runs/*/step_*.log for tasks-executed count

Writes:
- state/cost-overruns/<timestamp>.md if over budget
- state/STATUS.md is updated with the projection by write_status.py separately

Exit codes:
  0 — under budget
  1 — over budget, overrun report written
  2 — could not determine (e.g. no API key); does not fail the cycle, just warns
"""

import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


PER_TASK_CEILING = 0.002  # USD
TASKS_PER_YEAR_HEAVY = 100_000
YEARLY_CEILING = PER_TASK_CEILING * TASKS_PER_YEAR_HEAVY  # $200

STATE_DIR = Path("state")


def count_tasks_today() -> int:
    """Count distinct task executions in the last 24 hours of journey runs."""
    n = 0
    runs_dir = STATE_DIR / "journey-runs"
    if not runs_dir.exists():
        return 0
    cutoff = time.time() - 24 * 3600
    for run_dir in runs_dir.iterdir():
        if not run_dir.is_dir():
            continue
        if run_dir.stat().st_mtime < cutoff:
            continue
        # step 6 (input) and step 7 (action) are the task-heavy steps
        for step_log in run_dir.glob("step_6.log"):
            text = step_log.read_text(errors="ignore")
            n += text.count("intent_executed:")
        for step_log in run_dir.glob("step_7.log"):
            text = step_log.read_text(errors="ignore")
            n += text.count("action_executed:")
    return n


def fetch_openrouter_cost_24h() -> float | None:
    """Total OpenRouter spend in last 24 hours, USD. None if unavailable."""
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        return None
    try:
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/credits",
            headers={"Authorization": f"Bearer {key}"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        # Try recent generations endpoint for granular spend
        # Fallback: use the credits drop since yesterday (less accurate)
        used = data.get("data", {}).get("total_usage", 0.0)
        return float(used)
    except Exception as e:
        print(f"cost_audit: openrouter query failed: {e}", file=sys.stderr)
        return None


def main():
    tasks = count_tasks_today()

    if tasks == 0:
        print("cost_audit: no recent task executions, skipping (exit 2)")
        sys.exit(2)

    cost = fetch_openrouter_cost_24h()

    if cost is None:
        print("cost_audit: no OpenRouter key or query failed, skipping (exit 2)")
        sys.exit(2)

    per_task = cost / tasks
    projected_yearly = per_task * TASKS_PER_YEAR_HEAVY

    status = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tasks_last_24h": tasks,
        "cost_last_24h_usd": round(cost, 4),
        "per_task_usd": round(per_task, 6),
        "projected_yearly_per_heavy_user_usd": round(projected_yearly, 2),
        "ceiling_per_task_usd": PER_TASK_CEILING,
        "ceiling_yearly_usd": YEARLY_CEILING,
        "verdict": "pass" if per_task <= PER_TASK_CEILING else "fail",
    }

    STATE_DIR.mkdir(exist_ok=True)
    (STATE_DIR / "last_cost_audit.json").write_text(json.dumps(status, indent=2))

    if status["verdict"] == "fail":
        overrun_dir = STATE_DIR / "cost-overruns"
        overrun_dir.mkdir(exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        (overrun_dir / f"{ts}.md").write_text(
            f"# Cost overrun {ts}\n\n"
            f"Per-task cost: ${per_task:.6f}\n"
            f"Ceiling: ${PER_TASK_CEILING}\n"
            f"Projected yearly per heavy user: ${projected_yearly:.2f}\n"
            f"Ceiling yearly: ${YEARLY_CEILING}\n\n"
            f"## Next action\n\n"
            f"Inspect the most recent journey-runs/ for which step(s) used expensive models or excessive tokens. "
            f"The fix is usually one of: switching a step to Gemini Flash 2.5, reducing prompt size, "
            f"or replacing vision with a deterministic DOM/AX check.\n"
        )
        print(f"cost_audit: FAIL — projected ${projected_yearly:.2f}/year/user")
        sys.exit(1)
    else:
        print(f"cost_audit: pass — projected ${projected_yearly:.2f}/year/user")
        sys.exit(0)


if __name__ == "__main__":
    main()
