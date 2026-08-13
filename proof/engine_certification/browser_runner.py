from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from proof import day_zero_20 as browser_rig


def _norm(value: Any) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(value).lower()))


def _job_blob(job: dict[str, Any]) -> str:
    params = job.get("params") if isinstance(job.get("params"), dict) else {}
    return " ".join([
        str(job.get("goal") or ""),
        str(params.get("source") or ""),
        str(params.get("update") or ""),
    ])


def _score(spec: dict[str, Any], job: dict[str, Any]) -> int:
    blob = _norm(_job_blob(job))
    score = 0
    for field in spec.get("fields") or []:
        value = _norm(field.get("value"))
        if value and value in blob:
            score += max(1, len(value.split()))
    return score


def _pair(specs: list[dict[str, Any]], jobs: list[dict[str, Any]]) \
        -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Pair multiple independent jobs without assuming model output order."""
    unused = list(jobs)
    pairs = []
    for spec in specs:
        if not unused:
            break
        best = max(range(len(unused)), key=lambda index: _score(spec, unused[index]))
        pairs.append((spec, unused.pop(best)))
    return pairs


def prepare(cases_path: Path, oracle_path: Path, brain_results_path: Path,
            limit: int | None = None, start: int = 0) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    cases_doc = json.loads(cases_path.read_text())
    oracle_doc = json.loads(oracle_path.read_text())
    brain_doc = json.loads(brain_results_path.read_text())
    rows = {row["id"]: row for row in brain_doc["rows"]}
    oracles = {item["id"]: item for item in oracle_doc["oracles"]}
    prepared: list[dict[str, Any]] = []
    preflight: list[dict[str, Any]] = []

    for case in cases_doc["cases"]:
        oracle = oracles[case["id"]]
        expected = int(oracle["expected_jobs"])
        if expected == 0:
            continue
        row = rows.get(case["id"])
        # A cohort brain file may intentionally cover only part of the 500
        # stories. Unrun stories are outside this browser cohort; a story that
        # actually ran and failed is a preflight failure.
        if row is None:
            continue
        if not row.get("passed"):
            preflight.append({
                "scenario": case["id"], "ok": False,
                "note": "brain stage did not pass; browser action correctly withheld",
            })
            continue
        jobs = row.get("jobs") or []
        specs = case.get("browser_tasks") or ([case["browser"]] if case.get("browser") else [])
        if len(jobs) != expected or len(specs) != expected:
            preflight.append({
                "scenario": case["id"], "ok": False,
                "note": f"chain mismatch: {len(jobs)} brain jobs, {len(specs)} site tasks, expected {expected}",
            })
            continue
        for sequence, (spec, job) in enumerate(_pair(specs, jobs), 1):
            params = job.get("params") if isinstance(job.get("params"), dict) else {}
            goal = str(job.get("goal") or "").strip()
            source = str(params.get("source") or "").strip()
            task = goal
            if source and _norm(source) not in _norm(task):
                task += f"\nContext from what was heard: {source}"
            slug = f"{case['id']}-action-{sequence}"
            prepared.append({
                "slug": slug,
                "title": f"{spec['title']} · {case['id']}",
                "task": task,
                "authority_text": source or goal,
                # Product evidence, never hidden oracle: the concise model
                # goal plus the exact source retained on the brain job.
                "approved_scope": source or goal,
                # Critical hidden-oracle invariant: expected field values are
                # used by the site verifier, never copied into workflow facts.
                "agent_facts": {},
                "fields": [
                    {**field, "required": field.get("required", True)}
                    for field in spec.get("fields") or []
                ],
                "layout_seed": spec.get("layout_seed"),
                "mutations": spec.get("mutations") or [],
                "source_case": case["id"],
            })
    end = None if limit is None else start + limit
    return prepared[start:end], preflight, cases_doc


def run(cases_path: Path, oracle_path: Path, brain_results_path: Path,
        results_path: Path, limit: int | None = None,
        headless: bool = False, start: int = 0) -> dict[str, Any]:
    cases, preflight, cases_doc = prepare(
        cases_path, oracle_path, brain_results_path, limit, start)
    if not cases:
        summary = {
            "candidate": cases_doc["candidate"],
            "seed_hex": cases_doc["seed_hex"],
            "passed": 0, "total": len(preflight), "results": preflight,
        }
    else:
        summary = browser_rig.run_cases(cases, results_path, headless=headless)
        summary["candidate"] = cases_doc["candidate"]
        summary["seed_hex"] = cases_doc["seed_hex"]
        summary["start"] = start
        if preflight:
            summary["results"] = preflight + summary["results"]
            summary["total"] += len(preflight)
    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.write_text(json.dumps(summary, indent=2) + "\n")
    return summary
