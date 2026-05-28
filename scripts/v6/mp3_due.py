#!/usr/bin/env python3
"""Decide whether the held-out MP3 evaluation is due."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path


SIX_HOURS_SECONDS = 6 * 60 * 60


def newest_verdict(mp3_eval_dir: Path) -> Path | None:
    if not mp3_eval_dir.exists():
        return None
    verdicts = [path for path in mp3_eval_dir.rglob("verdict.json") if path.is_file()]
    if not verdicts:
        return None
    return max(verdicts, key=lambda path: path.stat().st_mtime)


def read_eval_cycle(verdict: Path | None) -> int | None:
    if verdict is None:
        return None
    cycle_file = verdict.parent / "cycle.json"
    if not cycle_file.exists():
        return None
    try:
        data = json.loads(cycle_file.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    cycle = data.get("cycle")
    return cycle if isinstance(cycle, int) else None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Return JSON describing whether the held-out MP3 eval is due."
    )
    parser.add_argument("--cycle", type=int, required=True)
    parser.add_argument("--state-dir", default="state")
    parser.add_argument("--max-age-seconds", type=int, default=SIX_HOURS_SECONDS)
    args = parser.parse_args()

    state_dir = Path(args.state_dir)
    verdict = newest_verdict(state_dir / "mp3_eval")
    last_eval_cycle = read_eval_cycle(verdict)

    result: dict[str, object] = {
        "cycle": args.cycle,
        "due": False,
        "reason": "recent_mp3_eval",
    }

    if args.cycle > 0 and args.cycle % 10 == 0:
        result.update({"due": True, "reason": "cycle_multiple_of_10"})
    elif verdict is None:
        result.update({"due": True, "reason": "no_prior_mp3_eval"})
    else:
        age_seconds = max(0, int(time.time() - verdict.stat().st_mtime))
        result.update(
            {
                "last_verdict": str(verdict),
                "last_age_seconds": age_seconds,
                "max_age_seconds": args.max_age_seconds,
            }
        )
        if last_eval_cycle is not None:
            result["last_eval_cycle"] = last_eval_cycle
        if (
            last_eval_cycle is not None
            and args.cycle // 10 > last_eval_cycle // 10
        ):
            result.update({"due": True, "reason": "cycle_cadence_elapsed"})
        elif age_seconds >= args.max_age_seconds:
            result.update({"due": True, "reason": "older_than_6_hours"})

    print(json.dumps(result, sort_keys=True))
    return 0 if result["due"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
