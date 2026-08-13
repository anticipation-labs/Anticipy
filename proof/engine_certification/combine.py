from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _same_candidate(document: dict[str, Any], cases: dict[str, Any], path: Path) -> None:
    if document.get("candidate") != cases.get("candidate"):
        raise ValueError(f"{path}: candidate fingerprint does not match cases")
    if document.get("seed_hex") != cases.get("seed_hex"):
        raise ValueError(f"{path}: hidden seed does not match cases")
    if document.get("complete") is not True:
        raise ValueError(f"{path}: cohort is not complete")


def combine_brain(cases_path: Path, inputs: list[Path], output: Path) -> dict[str, Any]:
    cases = _load(cases_path)
    expected = {case["id"] for case in cases["cases"]}
    rows: dict[str, dict[str, Any]] = {}
    for path in inputs:
        document = _load(path)
        _same_candidate(document, cases, path)
        for row in document.get("rows") or []:
            case_id = row.get("id")
            if case_id in rows:
                raise ValueError(f"duplicate brain story: {case_id}")
            rows[case_id] = row
    missing, extra = expected - rows.keys(), rows.keys() - expected
    if missing or extra:
        raise ValueError(
            f"brain coverage mismatch: missing={len(missing)} extra={len(extra)}")
    ordered = sorted(rows.values(), key=lambda row: int(row["n"]))
    summary = {
        "candidate": cases["candidate"], "seed_hex": cases["seed_hex"],
        "total": len(ordered),
        "passed": sum(bool(row.get("passed")) for row in ordered),
        "failed": sum(not bool(row.get("passed")) for row in ordered),
        "complete": True, "cohorts": [str(path) for path in inputs],
        "rows": ordered,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def combine_browser(cases_path: Path, inputs: list[Path], output: Path) -> dict[str, Any]:
    cases = _load(cases_path)
    expected = {
        f"{case['id']}-action-{index}"
        for case in cases["cases"]
        for index, _ in enumerate(case.get("browser_tasks") or [], 1)
    }
    results: dict[str, dict[str, Any]] = {}
    models, transports = set(), set()
    for path in inputs:
        document = _load(path)
        _same_candidate(document, cases, path)
        models.add(str(document.get("model") or ""))
        transports.add(str(document.get("model_transport") or ""))
        for row in document.get("results") or []:
            scenario = row.get("scenario")
            if scenario in results:
                raise ValueError(f"duplicate browser action: {scenario}")
            results[scenario] = row
    missing, extra = expected - results.keys(), results.keys() - expected
    if missing or extra:
        raise ValueError(
            f"browser coverage mismatch: missing={len(missing)} extra={len(extra)}")
    ordered = [results[scenario] for scenario in sorted(results)]
    summary = {
        "candidate": cases["candidate"], "seed_hex": cases["seed_hex"],
        "model": sorted(models), "model_transport": sorted(transports),
        "total": len(ordered),
        "passed": sum(bool(row.get("ok")) for row in ordered),
        "failed": sum(not bool(row.get("ok")) for row in ordered),
        "complete": True, "cohorts": [str(path) for path in inputs],
        "results": ordered,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Combine complete hidden-oracle certification cohorts")
    parser.add_argument("kind", choices=("brain", "browser"))
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    combine = combine_brain if args.kind == "brain" else combine_browser
    summary = combine(args.cases, args.inputs, args.output)
    print(f"combined {args.kind}: {summary['passed']}/{summary['total']} passed")
    raise SystemExit(0 if summary["passed"] == summary["total"] else 1)


if __name__ == "__main__":
    main()
