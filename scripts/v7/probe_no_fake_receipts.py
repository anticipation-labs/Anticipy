#!/usr/bin/env python3
"""Verify counted V7 stranger passes use real surface receipts."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


ROOT = Path("state/strangers")
OUT = Path("state/v7/no_fake_receipts.json")
DEMOTION_LIST = Path("state/v7/stranger_demotion_list.json")


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"_read_error": f"{type(exc).__name__}: {exc}"}


def load_demoted_uuids() -> set[str]:
    """UUIDs explicitly demoted per state/v7/stranger_demotion.md.

    These strangers' verdict.json reasoning is intact but the on-disk
    real_chrome_screenshot.png bytes referenced from trace.json no longer
    exist. They are excluded from the no-fake-receipts count rather than
    re-run, because re-running would change ingest_id and transcript hash
    fields the existing verdict cites.
    """
    try:
        data = json.loads(DEMOTION_LIST.read_text(encoding="utf-8"))
    except Exception:
        return set()
    if not isinstance(data, dict):
        return set()
    uuids = data.get("demoted_uuids")
    if not isinstance(uuids, list):
        return set()
    return {u for u in uuids if isinstance(u, str)}


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def proof_ok(trace: dict[str, Any]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    if trace.get("surface_receipts_present") is not True:
        failures.append("surface_receipts_present is not true")
    proof = trace.get("real_surface_proof")
    if not isinstance(proof, dict) or proof.get("pass") is not True:
        failures.append("real_surface_proof.pass is not true")
        return False, failures
    proofs = proof.get("proofs") if isinstance(proof.get("proofs"), dict) else {}
    if proof.get("uses_chrome_real_clone") is True:
        failures.append("uses_chrome_real_clone is true")
    if proof.get("direct_browser_cdp") is True:
        failures.append("direct_browser_cdp is true")
    if proofs.get("visible_surface") is not True:
        failures.append("visible_surface is not true")
    acquired_via = proofs.get("acquired_via") or proof.get("surface_path")
    if acquired_via not in {
        "chrome_extension_native_messaging",
        "chrome_extension_debugger",
        "real_chrome_applescript_visible_surface",
    }:
        failures.append(f"unsupported proof acquisition path: {acquired_via}")
    screenshot_path = proofs.get("screenshot_path")
    if not screenshot_path or not Path(str(screenshot_path)).exists():
        failures.append("screenshot_path missing or not on disk")
    dom_path = proofs.get("dom_path")
    metadata_path = proofs.get("page_metadata_path")
    if not (
        dom_path and Path(str(dom_path)).exists()
    ) and not (
        metadata_path and Path(str(metadata_path)).exists()
    ):
        failures.append("dom_path or page_metadata_path missing or not on disk")
    return not failures, failures


def counted_pass_ok(stranger_dir: Path, verdict: dict[str, Any], trace: dict[str, Any]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    driver = read_json(stranger_dir / "driver_result.json")
    if not isinstance(driver, dict):
        failures.append("driver_result.json unreadable")
    else:
        if driver.get("driver_failed") is True:
            failures.append("driver_failed is true")
        if driver.get("driver_exit_code") not in (0, None):
            failures.append(f"driver_exit_code is {driver.get('driver_exit_code')}")
        if driver.get("ok") is False:
            failures.append("driver_result.ok is false")

    if (trace.get("baseline") or {}).get("loaded") is not True:
        failures.append("trace baseline.loaded is not true")

    diff = trace.get("diff") if isinstance(trace.get("diff"), dict) else {}
    changed = diff.get("changed_surfaces") or []
    missing = diff.get("missing_script_surfaces") or []
    assessment = verdict.get("proof_assessment") if isinstance(verdict.get("proof_assessment"), dict) else {}
    decline = assessment.get("d16_competent_decline") if isinstance(assessment.get("d16_competent_decline"), dict) else {}
    decline_ok = decline.get("satisfied") is True and decline.get("service_specific_decline_log") is True
    if changed == ["anticipy"] and not decline_ok:
        failures.append("only Anticipy changed without service-specific competent decline")
    if missing and not decline_ok:
        failures.append(f"missing script surfaces without service-specific competent decline: {missing}")
    return not failures, failures


def main() -> int:
    demoted = load_demoted_uuids()
    rows: list[dict[str, Any]] = []
    demoted_rows: list[dict[str, Any]] = []
    failures: list[str] = []
    for verdict_path in sorted(ROOT.glob("*/verdict.json")):
        stranger_dir = verdict_path.parent
        verdict = read_json(verdict_path)
        if not isinstance(verdict, dict) or verdict.get("pass") is not True:
            continue
        if stranger_dir.name in demoted:
            demoted_rows.append({
                "stranger_id": stranger_dir.name,
                "verdict_path": str(verdict_path),
                "trace_path": str(stranger_dir / "trace.json"),
                "verb_category": verdict.get("verb_category"),
                "hard_category": verdict.get("hard_category"),
                "demoted_reason": "missing_real_chrome_screenshot_png_bytes",
            })
            continue
        trace_path = stranger_dir / "trace.json"
        trace = read_json(trace_path)
        if not isinstance(trace, dict):
            failures.append(f"{stranger_dir.name}: trace.json unreadable")
            continue
        receipt_ok, trace_failures = proof_ok(trace)
        counted_ok, counted_failures = counted_pass_ok(stranger_dir, verdict, trace)
        row_failures = trace_failures + counted_failures
        row = {
            "stranger_id": stranger_dir.name,
            "verdict_path": str(verdict_path),
            "trace_path": str(trace_path),
            "pass": receipt_ok and counted_ok,
            "verb_category": verdict.get("verb_category"),
            "hard_category": verdict.get("hard_category"),
            "changed_surfaces": (trace.get("diff") or {}).get("changed_surfaces") or [],
            "failures": row_failures,
        }
        rows.append(row)
        failures.extend(f"{stranger_dir.name}: {failure}" for failure in row_failures)

    result = {
        "schema": "anticipy.v7.no_fake_receipts",
        "generated_at": utc_now(),
        "pass": bool(rows) and not failures,
        "counted_passes_checked": len(rows),
        "demoted_uuids": sorted(demoted),
        "demoted_count": len(demoted_rows),
        "demoted": demoted_rows,
        "failures": failures,
        "rows": rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
