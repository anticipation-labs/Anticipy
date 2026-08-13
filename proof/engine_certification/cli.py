from __future__ import annotations

import argparse
from pathlib import Path

from .brain_runner import run as run_brain
from .browser_runner import run as run_browser
from .generator import generate


def main() -> None:
    parser = argparse.ArgumentParser(description="Anticipy hidden-oracle engine certification")
    parser.add_argument("command", choices=("generate", "brain", "browser"))
    parser.add_argument("--count", type=int, default=500)
    parser.add_argument("--seed", type=lambda value: int(value, 0))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--start", type=int, default=0,
                        help="zero-based story/action offset for reproducible cohorts")
    parser.add_argument("--cases", type=Path, default=Path("work/engine-cert/cases.json"))
    parser.add_argument("--oracle", type=Path, default=Path("work/engine-cert/oracle.json"))
    parser.add_argument("--results", type=Path, default=Path("work/engine-cert/brain-results.json"))
    parser.add_argument("--brain-results", type=Path, default=Path("work/engine-cert/brain-results.json"))
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()
    if args.command == "generate":
        info = generate(args.count, args.cases, args.oracle, args.seed)
        print(f"generated {args.count} hidden-oracle stories · seed={info['seed_hex']} · candidate={info['candidate']['candidate_sha256']}")
        return
    if args.command == "browser":
        summary = run_browser(args.cases, args.oracle, args.brain_results,
                              args.results, args.limit, args.headless, args.start)
        print(f"browser certification: {summary['passed']}/{summary['total']} passed; results={args.results}")
        raise SystemExit(0 if summary["passed"] == summary["total"] else 1)
    summary = run_brain(args.cases, args.oracle, args.results, args.limit, args.start)
    print(f"brain certification: {summary['passed']}/{summary['total']} passed; results={args.results}")
    raise SystemExit(0 if summary["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
