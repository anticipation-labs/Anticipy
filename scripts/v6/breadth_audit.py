#!/usr/bin/env python3
"""Audit V6 stranger breadth from state/strangers."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any
from uuid import UUID


STATE = Path("state")
STRANGERS = STATE / "strangers"
DEMOTION_LIST = STATE / "v7" / "stranger_demotion_list.json"
HARD = {
    "canvas",
    "canvas-based design tools",
    "canvas_design",
    "crm",
    "crm/enterprise saas",
    "e-commerce",
    "ecommerce",
    "commerce",
    "native",
    "native mac apps",
    "ambient",
    "ambient-only intents",
}


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_demoted_uuids() -> set[str]:
    """Load the list of stranger UUIDs that should not count toward
    successful_interactions because their on-disk proof is incomplete.

    See state/v7/stranger_demotion.md for the rationale.
    """
    data = read_json(DEMOTION_LIST)
    if not isinstance(data, dict):
        return set()
    uuids = data.get("demoted_uuids")
    if not isinstance(uuids, list):
        return set()
    return {u for u in uuids if isinstance(u, str)}


def verdict_pass(v: Any) -> bool:
    return bool(isinstance(v, dict) and (v.get("pass") is True or v.get("verdict") == "pass"))


def verified_pass(stranger_dir: Path, verdict: Any) -> tuple[bool, list[str]]:
    failures: list[str] = []
    if not verdict_pass(verdict):
        failures.append("verdict is not pass")
        return False, failures

    driver = read_json(stranger_dir / "driver_result.json")
    if not isinstance(driver, dict):
        failures.append("driver_result.json missing or unreadable")
    else:
        if driver.get("driver_failed") is True:
            failures.append("driver_failed is true")
        if driver.get("driver_exit_code") not in (0, None):
            failures.append(f"driver_exit_code is {driver.get('driver_exit_code')}")
        if driver.get("ok") is False:
            failures.append("driver_result.ok is false")

    trace = read_json(stranger_dir / "trace.json")
    if not isinstance(trace, dict):
        failures.append("trace.json missing or unreadable")
        return False, failures
    if (trace.get("baseline") or {}).get("loaded") is not True:
        failures.append("trace baseline was not loaded")
    if trace.get("surface_receipts_present") is not True:
        failures.append("surface_receipts_present is not true")

    diff = trace.get("diff") if isinstance(trace.get("diff"), dict) else {}
    changed = diff.get("changed_surfaces") or []
    missing = diff.get("missing_script_surfaces") or []
    proof_assessment = verdict.get("proof_assessment") if isinstance(verdict, dict) else None
    competent_decline = (
        proof_assessment.get("d16_competent_decline")
        if isinstance(proof_assessment, dict)
        else None
    )
    if competent_decline is None and isinstance(verdict, dict):
        competent_decline = verdict.get("d16_competent_decline")
    decline_ok = isinstance(competent_decline, dict) and competent_decline.get("satisfied") is True
    service_decline = (
        isinstance(competent_decline, dict)
        and (
            competent_decline.get("service_specific_decline_log") is True
            or competent_decline.get("service_specific_log_present") is True
        )
    )
    if missing and not (decline_ok and service_decline):
        failures.append(f"missing script surfaces without service-specific competent decline: {missing}")
    if changed == ["anticipy"] and not (decline_ok and service_decline):
        failures.append("only Anticipy changed without service-specific competent decline")

    return not failures, failures


def is_uuid(value: str) -> bool:
    try:
        UUID(value)
    except ValueError:
        return False
    return True


def is_generated_stranger_dir(stranger_dir: Path, persona: Any, script: Any) -> bool:
    if not is_uuid(stranger_dir.name):
        return False
    if not isinstance(persona, dict) or not isinstance(script, dict):
        return False
    persona_uuid = persona.get("uuid")
    script_persona_uuid = script.get("persona_uuid")
    return persona_uuid == stranger_dir.name and script_persona_uuid == stranger_dir.name


def category_from(stranger_dir: Path, persona: Any, script: Any, verdict: Any) -> str:
    for obj in (verdict, script, persona):
        if isinstance(obj, dict):
            for key in ("verb_category", "category", "primary_category", "hard_category_focus"):
                value = obj.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip().lower()
    return stranger_dir.name


def hard_from(persona: Any, verdict: Any, category: str) -> str:
    values: list[str] = [category]
    for obj in (persona, verdict):
        if isinstance(obj, dict):
            for key in ("hard_category", "hard_category_focus"):
                value = obj.get(key)
                if isinstance(value, str):
                    values.append(value.lower())
    for value in values:
        for hard in HARD:
            if hard in value:
                if "canvas" in hard:
                    return "canvas"
                if "crm" in hard:
                    return "crm"
                if "commerce" in hard or "e-commerce" in hard or "ecommerce" in hard:
                    return "e-commerce"
                if "native" in hard:
                    return "native"
                if "ambient" in hard:
                    return "ambient"
    return ""


def collect() -> dict:
    demoted = load_demoted_uuids()
    rows = []
    for d in sorted(STRANGERS.glob("*"), key=lambda p: p.stat().st_mtime if p.exists() else 0):
        if not d.is_dir():
            continue
        persona = read_json(d / "persona.json")
        script = read_json(d / "script.json")
        if not is_generated_stranger_dir(d, persona, script):
            continue
        verdict = read_json(d / "verdict.json")
        category = category_from(d, persona, script, verdict)
        hard = hard_from(persona, verdict, category)
        verified, verify_failures = verified_pass(d, verdict)
        if d.name in demoted:
            verified = False
            verify_failures = list(verify_failures) + [
                "demoted_v7_20_missing_screenshot_bytes"
            ]
        rows.append({
            "uuid": d.name,
            "pass": verdict_pass(verdict),
            "verified_pass": verified,
            "verification_failures": verify_failures,
            "demoted": d.name in demoted,
            "category": category,
            "hard_category": hard,
            "has_trace": (d / "trace.json").exists(),
            "has_verdict": (d / "verdict.json").exists(),
        })
    passing = [r for r in rows if r["verified_pass"]]
    cats = Counter(r["category"] for r in passing if r["category"])
    hard = Counter(r["hard_category"] for r in passing if r["hard_category"])
    latest20 = rows[-20:]
    return {
        "total_interactions": len(rows),
        "successful_interactions": len(passing),
        "demoted_uuids": sorted(demoted),
        "demoted_count": len([r for r in rows if r["demoted"]]),
        "verb_categories": sorted(cats),
        "verb_category_count": len(cats),
        "hard_categories": sorted(hard),
        "hard_category_count": len(hard),
        "last20_count": len(latest20),
        "last20_failures": [r["uuid"] for r in latest20 if not r["verified_pass"]],
        "rows": rows[-50:],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write-status", action="store_true")
    ap.add_argument("--min-success", type=int, default=0)
    ap.add_argument("--min-verb-categories", type=int, default=0)
    ap.add_argument("--min-hard-categories", type=int, default=0)
    args = ap.parse_args()
    result = collect()
    STATE.mkdir(exist_ok=True)
    (STATE / "stranger_breadth.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    if args.write_status:
        print(json.dumps(result, indent=2))
    ok = (
        result["successful_interactions"] >= args.min_success
        and result["verb_category_count"] >= args.min_verb_categories
        and result["hard_category_count"] >= args.min_hard_categories
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
