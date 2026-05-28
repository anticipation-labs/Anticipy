"""
write_status.py — writes state/STATUS.md after each cycle.

Format (frozen, do not change without Omar approval):
- Cycle number, UTC timestamp
- Journey: pass/fail (which step if fail)
- Stranger run: pass/fail/skipped (link to video if applicable)
- Cost audit: pass/fail (current $/year/user projection)
- Changes this cycle (read from git log of the cycle window)
- Next intended action
- Blockers (decision-queue items pending)
"""

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def latest_run_dir(base: str) -> Path | None:
    p = Path(base)
    if not p.exists():
        return None
    runs = sorted([d for d in p.iterdir() if d.is_dir()])
    return runs[-1] if runs else None


def journey_status() -> tuple[str, str]:
    d = latest_run_dir("state/journey-runs")
    if not d:
        return "unknown", "no journey runs yet"
    failed = (d / "failed_step.txt").read_text().strip() if (d / "failed_step.txt").exists() else "?"
    if failed == "0":
        return "pass", "all 7 steps green"
    return "fail", f"step {failed} failed (see {d}/step_{failed}.log)"


def stranger_status() -> tuple[str, str]:
    d = latest_run_dir("state/stranger-runs")
    if not d:
        return "skipped", "no stranger run this cycle"
    verdict_file = d / "verdict.json"
    if not verdict_file.exists():
        return "fail", f"no verdict written for {d.name}"
    try:
        v = json.loads(verdict_file.read_text())
    except Exception:
        return "fail", f"verdict.json unreadable for {d.name}"
    return v.get("verdict", "fail"), v.get("reasoning", "")


def cost_status() -> tuple[str, str]:
    p = Path("state/last_cost_audit.json")
    if not p.exists():
        return "skipped", "no audit this cycle"
    try:
        v = json.loads(p.read_text())
    except Exception:
        return "fail", "audit file unreadable"
    return v.get("verdict", "skipped"), f"${v.get('projected_yearly_per_heavy_user_usd', '?')}/year/user projected"


def recent_commits() -> str:
    try:
        out = subprocess.check_output(
            ["git", "log", "--since=2 hours ago", "--pretty=format:- %s"],
            text=True,
        )
    except subprocess.CalledProcessError:
        return "(git unavailable)"
    return out.strip() or "(no commits this cycle)"


def pending_decisions() -> str:
    q = Path("state/decisions/queue.md")
    if not q.exists():
        return "(none)"
    content = q.read_text().strip()
    return content if content else "(none)"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--cycle", required=True)
    args = p.parse_args()

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    jv, jr = journey_status()
    sv, sr = stranger_status()
    cv, cr = cost_status()

    out = f"""# Anticipy autonomous loop — status

Last update: {ts}
Cycle: {args.cycle}

## Journey
**{jv.upper()}** — {jr}

## Synthetic stranger run
**{sv.upper()}** — {sr}

## Cost audit
**{cv.upper()}** — {cr}

## Changes this cycle
{recent_commits()}

## Pending decisions (defaults executing, override anytime)
{pending_decisions()}

---
*Read this file when you want. The loop continues without your input. Override decisions by editing `state/decisions/queue.md`.*
"""
    Path("state/STATUS.md").write_text(out)


if __name__ == "__main__":
    main()
