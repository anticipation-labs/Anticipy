#!/usr/bin/env python
"""Spend governance: record per-lap model spend, answer budget questions.

  spend.py record --lap LAP [--build-json f] [--judge-json f] [--extra-usd x]
  spend.py remaining            -> prints remaining week budget (float)
  spend.py check --kind build|judge  -> exit 0 if envelope allows another lap

Build/judge JSONs are claude CLI result envelopes (last event of stream-json or the
--output-format json object) carrying total_cost_usd. Subscription runs report 0.0 —
still recorded so the trail is complete. Week = ISO week, resets Monday UTC.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CSV_PATH = REPO / "logs/factory/spend.csv"
BUDGET = REPO / "factory/config/budget.json"
COLS = ["lap", "ts_utc", "iso_week", "build_usd", "judge_usd", "extra_usd", "total_usd"]


def budget() -> dict:
    return json.loads(BUDGET.read_text(encoding="utf-8"))


def cost_from(path: str | None) -> float:
    if not path:
        return 0.0
    p = Path(path)
    if not p.exists():
        return 0.0
    text = p.read_text(encoding="utf-8").strip()
    # stream-json: scan lines for the result envelope; plain json: single object
    candidates = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        candidates.append(obj)
    for obj in reversed(candidates):
        for key in ("total_cost_usd", "cost_usd", "total_cost"):
            if isinstance(obj, dict) and key in obj:
                try:
                    return float(obj[key])
                except Exception:
                    pass
    return 0.0


def iso_week(ts: dt.datetime | None = None) -> str:
    ts = ts or dt.datetime.now(dt.timezone.utc)
    y, w, _ = ts.isocalendar()
    return f"{y}-W{w:02d}"


def week_spent() -> float:
    if not CSV_PATH.exists():
        return 0.0
    wk = iso_week()
    total = 0.0
    with CSV_PATH.open() as f:
        for row in csv.DictReader(f):
            if row.get("iso_week") == wk:
                try:
                    total += float(row.get("total_usd", 0) or 0)
                except Exception:
                    pass
    return total


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    rec = sub.add_parser("record")
    rec.add_argument("--lap", required=True)
    rec.add_argument("--build-json", default="")
    rec.add_argument("--judge-json", default="")
    rec.add_argument("--extra-usd", type=float, default=0.0)
    sub.add_parser("remaining")
    chk = sub.add_parser("check")
    chk.add_argument("--kind", required=True, choices=["build", "judge"])
    args = ap.parse_args()

    b = budget()
    if args.cmd == "record":
        bu, ju = cost_from(args.build_json), cost_from(args.judge_json)
        total = bu + ju + args.extra_usd
        CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
        new = not CSV_PATH.exists()
        with CSV_PATH.open("a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLS)
            if new:
                w.writeheader()
            w.writerow({"lap": args.lap,
                        "ts_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                        "iso_week": iso_week(), "build_usd": round(bu, 4),
                        "judge_usd": round(ju, 4), "extra_usd": round(args.extra_usd, 4),
                        "total_usd": round(total, 4)})
        print(json.dumps({"lap": args.lap, "recorded_usd": round(total, 4),
                          "week_spent": round(week_spent(), 4)}))
        return 0

    remaining = float(b["week_usd"]) - week_spent()
    if args.cmd == "remaining":
        print(f"{remaining:.2f}")
        return 0

    # check
    reserve = float(b["week_usd"]) * float(b.get("reserve_for_judge_pct", 25)) / 100.0
    if args.kind == "build":
        ok = remaining - reserve >= float(b.get("per_lap_build_usd", 5.0))
    else:
        ok = remaining >= float(b.get("per_lap_judge_usd", 2.0))
    print("OK" if ok else "EXHAUSTED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
