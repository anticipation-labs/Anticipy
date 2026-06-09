#!/usr/bin/env python
"""SOLE writer of logs/factory/product_scoreboard.csv and logs/factory/RATCHET.json.

The builder never writes these. Inputs are machine outputs only:
  logs/factory/laps/<LAP>/metrics.json       (persona_score.py)
  logs/factory/laps/<LAP>/gate_results.json  (verify_gate.sh)
  logs/factory/laps/<LAP>/manifest.json      (builder pre-registration)
  logs/factory/laps/<LAP>/judge.json         (optional judge verdict summary)

A lap COUNTS (resets the treadmill) iff guards hold AND (primary metric moved beyond
epsilon OR a phase gate closed). The ratchet only advances on kept laps.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SB = REPO / "logs/factory/product_scoreboard.csv"
RATCHET = REPO / "logs/factory/RATCHET.json"

# direction: +1 means higher is better
METRIC_DIRECTION = {
    "catch_rate": 1, "catch_rate_worst": 1, "correct_action_rate": 1,
    "e2e_completion_rate": 1, "memory_recall_worst": 1, "owner_day_pass": 1,
    "false_action_count": -1, "silent_harm_count": -1,
    "interrupt_cost": -1, "interrupt_cost_worst": -1,
}

COLUMNS = ["lap", "ts_utc", "target_version", "target_sha", "suite_hash", "phase",
           "lap_type", "intended_metric", "builder_commit", "gates_passed", "gate_closed",
           "catch_rate", "catch_rate_worst", "correct_action_rate", "false_action_count",
           "silent_harm_count", "interrupt_cost", "interrupt_cost_worst",
           "e2e_completion_rate", "memory_recall_worst", "worst_persona", "personas_run",
           "metric_moved", "delta", "judge_verdict", "kept", "treadmill_count",
           "budget_mode", "spend_total_usd", "wall_seconds", "notes"]


def parse_target() -> dict:
    text = (REPO / "factory/TARGET.md").read_text(encoding="utf-8")
    out = {}
    m = re.search(r"^# TARGET v(\S+)", text, re.M)
    out["version"] = m.group(1) if m else "?"
    for key in ("current_phase", "primary_metric", "eval_tier", "budget_week_usd"):
        m = re.search(rf"^{key}:\s*(.+)$", text, re.M)
        out[key] = m.group(1).strip() if m else ""
    out["sha"] = hashlib.sha256(text.encode()).hexdigest()[:12]
    return out


def suite_hash() -> str:
    h = hashlib.sha256()
    bank = REPO / "factory/personas/dev"
    for p in sorted(bank.rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(bank)).encode())
            h.update(p.read_bytes())
    return h.hexdigest()[:12]


def load(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default if default is not None else {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lap", required=True)
    ap.add_argument("--kept", default="false", choices=["true", "false"])
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    lap_dir = REPO / "logs/factory/laps" / args.lap
    metrics_all = load(lap_dir / "metrics.json")
    agg = metrics_all.get("aggregate", {}) if metrics_all else {}
    gates = load(lap_dir / "gate_results.json")
    manifest = load(lap_dir / "manifest.json")
    judge = load(lap_dir / "judge.json")
    target = parse_target()
    ratchet = load(RATCHET, {"best": {}, "treadmill_count": 0,
                             "last_movement_lap": "", "spend_since_movement": 0.0,
                             "phases_closed": {}})
    ratchet.setdefault("phases_closed", {})
    budget = load(REPO / "factory/config/budget.json", {"epsilon_noise": 0.02})
    eps = float(budget.get("epsilon_noise", 0.02))

    primary = target.get("primary_metric") or "catch_rate_worst"
    direction = METRIC_DIRECTION.get(primary, 1)
    current = agg.get(primary)
    best = ratchet["best"].get(primary)
    moved, delta = "none", ""
    if current is not None:
        if best is None:
            moved, delta = primary, f"{current:+.4f} (first measurement)"
        else:
            d = (current - best) * direction
            if d > eps:
                moved, delta = primary, f"{(current - best):+.4f}"

    phase = target.get("current_phase", "")
    gate_passed_now = bool(gates.get("phase_gate_passed"))
    # Closing a phase counts as progress ONCE — the first lap that closes it.
    # A gate that keeps passing on later laps is status, not movement.
    first_closure = gate_passed_now and phase not in ratchet["phases_closed"]
    gate_closed = first_closure
    guards_ok = (agg.get("silent_harm_count", 0) == 0) if agg else True
    kept = args.kept == "true"
    counts = kept and guards_ok and (moved != "none" or first_closure)

    new_treadmill = 0 if counts else int(ratchet.get("treadmill_count", 0)) + 1
    spend_total = float(gates.get("spend_total_usd", 0.0) or 0.0)

    row = {
        "lap": args.lap,
        "ts_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "target_version": target.get("version", "?"),
        "target_sha": target.get("sha", ""),
        "suite_hash": suite_hash(),
        "phase": target.get("current_phase", ""),
        "lap_type": manifest.get("lap_type", "build"),
        "intended_metric": manifest.get("intended_metric", ""),
        "builder_commit": gates.get("builder_commit", ""),
        "gates_passed": gates.get("all_scans_passed", ""),
        "gate_closed": gate_closed,
        "catch_rate": agg.get("catch_rate", ""),
        "catch_rate_worst": agg.get("catch_rate_worst", ""),
        "correct_action_rate": agg.get("correct_action_rate", ""),
        "false_action_count": agg.get("false_action_count", ""),
        "silent_harm_count": agg.get("silent_harm_count", ""),
        "interrupt_cost": agg.get("interrupt_cost", ""),
        "interrupt_cost_worst": agg.get("interrupt_cost_worst", ""),
        "e2e_completion_rate": agg.get("e2e_completion_rate", ""),
        "memory_recall_worst": agg.get("memory_recall_worst", ""),
        "worst_persona": agg.get("worst_persona", ""),
        "personas_run": agg.get("personas_run", ""),
        "metric_moved": moved,
        "delta": delta,
        "judge_verdict": judge.get("verdict", "NA"),
        "kept": kept,
        "treadmill_count": new_treadmill,
        "budget_mode": gates.get("budget_mode", "FULL"),
        "spend_total_usd": spend_total,
        "wall_seconds": gates.get("wall_seconds", ""),
        "notes": (manifest.get("hypothesis", "") or "")[:400].replace("\n", " "),
    }

    if args.dry_run:
        print(json.dumps({"row": row, "counts": counts, "would_update_ratchet": kept}, indent=2))
        return 0

    SB.parent.mkdir(parents=True, exist_ok=True)
    new_file = not SB.exists()
    with SB.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        if new_file:
            w.writeheader()
        w.writerow(row)

    if kept:
        for k, d in METRIC_DIRECTION.items():
            v = agg.get(k)
            if v is None or v == "":
                continue
            b = ratchet["best"].get(k)
            if b is None or (v - b) * d > 0:
                ratchet["best"][k] = v
        if first_closure:
            ratchet["phases_closed"][phase] = args.lap
    ratchet["treadmill_count"] = new_treadmill
    if counts:
        ratchet["last_movement_lap"] = args.lap
        ratchet["spend_since_movement"] = 0.0
    else:
        ratchet["spend_since_movement"] = float(ratchet.get("spend_since_movement", 0.0)) + spend_total
    RATCHET.write_text(json.dumps(ratchet, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(json.dumps({"lap": args.lap, "metric_moved": moved, "delta": delta,
                      "gate_closed": gate_closed, "counts": counts,
                      "treadmill_count": new_treadmill}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
