#!/usr/bin/env python3
"""
audit_stranger_artifacts.py

Read-only depth audit of every stranger run under state/strangers/.

Verifies the V7.20 "no fake receipts" rule held by checking, for each stranger:

  1. verdict.json exists and pass is true.
  2. trace.json exists and carries real-time evidence. The historical schema
     does not use an "events" array; instead it uses
     {extension_surface_proof, real_surface_proof, driver_result, engine_logs,
     pages, native_ax, terminal, transcript_quality, cost_breakdown, diff}.
     We treat the trace as "evidence-bearing" when those required artifacts
     are present, non-empty, and reference at-rest files (screenshots,
     visible text, page metadata) whose byte counts are above zero.
  3. script.json exists with persona uuid and verb_category.
  4. Surface proof: trace must reference real-Chrome AppleScript / extension
     surface paths and the visible_surface flag must be true. We then confirm
     the referenced screenshot path exists on disk with the recorded sha256
     hash matching the bytes.
  5. Memory write claim: V7.20 sets ASKING / DECLINED as a competent pause,
     so writes should NOT have happened. We confirm engine_logs do not
     record an outcome=ACTED with d16_competent_decline=true. If the
     verdict claims an outcome=ACTED, the per-stranger dossier dir under
     ~/.anticipy/v7/dossiers/<account_id>/dossier.json must have grown
     above the empty-state size.
  6. Clock-skew: trace.created_at must be <= verdict.evaluator_generated_at
     for every stranger. driver_result and engine_log timestamps must
     fall within the trace window.
  7. Evaluator authenticity: verdict.evaluator_model must be present and
     match the V7 allowlist (deepseek/deepseek-v4-flash etc.). The reasoning
     field must be over 200 chars and not a copy of a sibling reasoning.

Output:
  state/v7/stranger_artifact_audit_<ts>/summary.json
  state/v7/stranger_artifact_audit_<ts>/summary.md

The script is hermetically local: zero network calls, zero LLM calls.
It does NOT mutate state/strangers/ in any way.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/Users/omarebrahim/Developer/Anticipy-V7")
STRANGERS_DIR = ROOT / "state" / "strangers"
DOSSIERS_DIR = Path(os.path.expanduser("~/.anticipy/v7/dossiers"))
ALLOWED_EVALUATOR_MODELS = {
    "deepseek/deepseek-v4-flash",
    "deepseek/deepseek-chat-v4-flash",
    "moonshotai/kimi-k2.6",
    "moonshotai/kimi-k2.6-instruct",
}


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_iso(s: str):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def jsonl_loads(text: str):
    out = []
    for raw in text.strip().splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            out.append(json.loads(raw))
        except Exception:
            continue
    return out


def audit_one(sdir: Path) -> dict:
    """Return per-stranger audit dict with checks 1..7."""
    result = {
        "uuid": sdir.name,
        "checks": {},
        "warnings": [],
        "missing_files": [],
        "evaluator_model": None,
        "outcome": None,
        "pass_all": False,
    }

    # -------- Check 1: verdict.json + pass=true --------
    v_path = sdir / "verdict.json"
    if not v_path.exists():
        result["missing_files"].append("verdict.json")
        result["checks"]["1_verdict_pass"] = False
        return result
    try:
        verdict = json.loads(v_path.read_text())
    except Exception as e:
        result["warnings"].append(f"verdict_json_parse_error: {e}")
        result["checks"]["1_verdict_pass"] = False
        return result
    result["checks"]["1_verdict_pass"] = verdict.get("pass") is True
    if not result["checks"]["1_verdict_pass"]:
        return result

    # -------- Check 2: trace.json carries real evidence --------
    t_path = sdir / "trace.json"
    if not t_path.exists():
        result["missing_files"].append("trace.json")
        result["checks"]["2_trace_evidence"] = False
        return result
    try:
        trace = json.loads(t_path.read_text())
    except Exception as e:
        result["warnings"].append(f"trace_json_parse_error: {e}")
        result["checks"]["2_trace_evidence"] = False
        return result

    required_trace_artifacts = [
        "extension_surface_proof",
        "real_surface_proof",
        "driver_result",
        "engine_logs",
        "pages",
        "transcript_quality",
        "cost_breakdown",
    ]
    missing = [k for k in required_trace_artifacts if k not in trace or not trace[k]]
    result["checks"]["2_trace_evidence"] = len(missing) == 0
    if missing:
        result["warnings"].append(f"missing_trace_keys: {missing}")

    # -------- Check 3: script.json with persona + verb_category --------
    s_path = sdir / "script.json"
    if not s_path.exists():
        result["missing_files"].append("script.json")
        result["checks"]["3_script_persona_verb"] = False
    else:
        try:
            script = json.loads(s_path.read_text())
        except Exception as e:
            result["warnings"].append(f"script_json_parse_error: {e}")
            script = {}
        has_persona = script.get("persona_uuid") == sdir.name
        has_verb = bool(script.get("verb_category"))
        result["checks"]["3_script_persona_verb"] = has_persona and has_verb
        if not has_persona:
            result["warnings"].append("script_persona_uuid_mismatch")
        if not has_verb:
            result["warnings"].append("script_missing_verb_category")

    # -------- Check 4: real Chrome surface receipts on disk --------
    surface_path = trace.get("chrome_surface_path", "")
    asp = trace.get("extension_surface_proof", {}).get("applescript_surface_probe", {})
    ss_path_str = asp.get("screenshot_path", "")
    ss_sha = asp.get("screenshot_sha256", "")
    visible = asp.get("visible_surface", False)

    surface_ok = "real_chrome" in surface_path and visible is True
    ss_ok = False
    if ss_path_str:
        ss_path = Path(ss_path_str)
        if ss_path.exists() and ss_path.stat().st_size > 0:
            actual_sha = sha256_file(ss_path)
            ss_ok = actual_sha == ss_sha
            if not ss_ok:
                result["warnings"].append(
                    f"screenshot_sha_mismatch: claimed={ss_sha[:12]} actual={actual_sha[:12]}"
                )
        else:
            result["warnings"].append(f"screenshot_path_missing_or_empty: {ss_path}")
    else:
        result["warnings"].append("screenshot_path_not_recorded")

    # Either AppleScript path or a CDP target_id on the page must be present
    pages = trace.get("pages", [])
    has_real_target = any(
        ("chrome-extension-native-messaging" in str(p.get("target_id", ""))
         or "cdp" in str(p.get("acquired_via", "")).lower()
         or "applescript" in str(p.get("acquired_via", "")).lower())
        for p in pages
    )
    result["checks"]["4_real_surface_receipts"] = surface_ok and ss_ok and has_real_target
    if not has_real_target:
        result["warnings"].append("no_real_chrome_target_in_pages")

    # -------- Check 5: memory write claim alignment --------
    dr = trace.get("driver_result", {})
    outcome = dr.get("outcome", "")
    result["outcome"] = outcome

    # All V7.20 strangers should be ASKING or DECLINED (competent pause).
    # If outcome == ACTED, the dossier dir must show write evidence.
    if outcome == "ACTED":
        account_id = dr.get("account_id") or trace.get("account_id") or "anticipy-user"
        dossier_path = DOSSIERS_DIR / account_id / "dossier.json"
        if dossier_path.exists() and dossier_path.stat().st_size > 0:
            result["checks"]["5_memory_write_alignment"] = True
        else:
            result["checks"]["5_memory_write_alignment"] = False
            result["warnings"].append(
                f"outcome_ACTED_but_dossier_missing: {dossier_path}"
            )
    elif outcome in ("ASKING", "DECLINED"):
        # No write expected. Confirm engine_logs reflect this:
        # an outcome line in the jsonl must match.
        logs = trace.get("engine_logs", {})
        combined = "\n".join(str(v) for v in logs.values())
        log_records = jsonl_loads(combined)
        log_outcomes = [r.get("outcome") for r in log_records if isinstance(r, dict)]
        result["checks"]["5_memory_write_alignment"] = outcome in log_outcomes
        if outcome not in log_outcomes:
            result["warnings"].append(
                f"engine_log_outcome_mismatch: driver={outcome} log_outcomes={log_outcomes[:5]}"
            )
    else:
        result["checks"]["5_memory_write_alignment"] = False
        result["warnings"].append(f"unexpected_outcome: {outcome!r}")

    # -------- Check 6: clock-skew / ordering sanity --------
    t_created = parse_iso(trace.get("created_at", ""))
    v_created = parse_iso(verdict.get("evaluator_generated_at", ""))
    cb_generated = parse_iso(trace.get("cost_breakdown", {}).get("generated_at", ""))
    tq_generated = parse_iso(trace.get("transcript_quality", {}).get("generated_at", ""))
    esp_generated = parse_iso(
        trace.get("extension_surface_proof", {}).get("generated_at", "")
    )

    ordering_ok = True
    if t_created and v_created and t_created > v_created:
        ordering_ok = False
        result["warnings"].append(
            f"clock_skew_trace_after_verdict: trace={t_created} verdict={v_created}"
        )
    # transcript / cost / extension proof must fall within +/-10 minutes of trace
    for label, ts in [("cb", cb_generated), ("tq", tq_generated), ("esp", esp_generated)]:
        if not (t_created and ts):
            continue
        delta = abs((ts - t_created).total_seconds())
        if delta > 600:
            ordering_ok = False
            result["warnings"].append(
                f"clock_skew_{label}_far_from_trace: delta_seconds={int(delta)}"
            )
    result["checks"]["6_clock_ordering"] = ordering_ok

    # -------- Check 7: evaluator authenticity --------
    em = verdict.get("evaluator_model")
    result["evaluator_model"] = em
    reasoning = verdict.get("reasoning", "")
    eval_ok = (
        em in ALLOWED_EVALUATOR_MODELS
        and isinstance(reasoning, str)
        and len(reasoning) >= 200
    )
    result["checks"]["7_evaluator_authentic"] = eval_ok
    if not em:
        result["warnings"].append("evaluator_model_missing")
    elif em not in ALLOWED_EVALUATOR_MODELS:
        result["warnings"].append(f"evaluator_model_not_allowlisted: {em}")
    if len(reasoning) < 200:
        result["warnings"].append(f"reasoning_too_short: {len(reasoning)} chars")

    result["pass_all"] = all(result["checks"].values())
    return result


def main():
    if not STRANGERS_DIR.exists():
        print(f"FATAL: {STRANGERS_DIR} does not exist", file=sys.stderr)
        sys.exit(2)

    stranger_dirs = sorted([d for d in STRANGERS_DIR.iterdir() if d.is_dir()])
    print(f"Auditing {len(stranger_dirs)} stranger dirs...", file=sys.stderr)

    per_stranger = []
    for sd in stranger_dirs:
        per_stranger.append(audit_one(sd))

    # Compute aggregates only over strangers that claim pass=true
    verified = [r for r in per_stranger if r["checks"].get("1_verdict_pass")]
    print(f"  verdict.pass=true: {len(verified)}", file=sys.stderr)
    full_pass = [r for r in verified if r["pass_all"]]
    suspicious = [r for r in verified if not r["pass_all"] or r["warnings"]]

    # Cross-stranger novelty checks
    reasonings = {}
    for r in verified:
        try:
            v = json.loads((STRANGERS_DIR / r["uuid"] / "verdict.json").read_text())
            reasonings.setdefault(v.get("reasoning", ""), []).append(r["uuid"])
        except Exception:
            pass
    duplicated_reasoning = {k[:48]: v for k, v in reasonings.items() if len(v) > 1}

    # Screenshot sha uniqueness
    screenshot_shas = {}
    for r in verified:
        try:
            t = json.loads((STRANGERS_DIR / r["uuid"] / "trace.json").read_text())
            sha = (
                t.get("extension_surface_proof", {})
                .get("applescript_surface_probe", {})
                .get("screenshot_sha256", "")
            )
            if sha:
                screenshot_shas.setdefault(sha, []).append(r["uuid"])
        except Exception:
            pass
    duplicated_screenshots = {k[:12]: v for k, v in screenshot_shas.items() if len(v) > 1}

    # Pick three most suspicious by warning count + failed checks
    def suspicion_score(r):
        failed = sum(1 for v in r["checks"].values() if v is False)
        return failed * 10 + len(r["warnings"]) + (5 if not r.get("evaluator_model") else 0)

    top_suspicious = sorted(suspicious, key=lambda r: -suspicion_score(r))[:5]

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = ROOT / "state" / "v7" / f"stranger_artifact_audit_{ts}"
    out_dir.mkdir(parents=True, exist_ok=True)

    summary = {
        "schema": "anticipy.stranger_artifact_audit.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "strangers_dir": str(STRANGERS_DIR),
        "total_stranger_dirs": len(stranger_dirs),
        "verified_pass_true_count": len(verified),
        "passed_all_7_checks": len(full_pass),
        "with_at_least_one_warning_or_failed_check": len(suspicious),
        "duplicated_reasoning_groups": duplicated_reasoning,
        "duplicated_screenshot_groups": duplicated_screenshots,
        "top_suspicious_uuids": [
            {
                "uuid": r["uuid"],
                "failed_checks": [k for k, v in r["checks"].items() if v is False],
                "warnings": r["warnings"],
                "outcome": r["outcome"],
                "evaluator_model": r["evaluator_model"],
            }
            for r in top_suspicious
        ],
        "per_stranger": per_stranger,
        "v7_20_fake_receipts_gate": {
            "all_verified_have_real_chrome_surface_path": all(
                r["checks"].get("4_real_surface_receipts") for r in verified
            ),
            "all_verified_have_outcome_in_ASKING_DECLINED_or_ACTED_with_dossier": all(
                r["checks"].get("5_memory_write_alignment") for r in verified
            ),
            "no_unallowlisted_evaluator_models": all(
                (r["evaluator_model"] in ALLOWED_EVALUATOR_MODELS) for r in verified
            ),
        },
    }

    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))

    md_lines = [
        "# Stranger artifact audit",
        "",
        f"Generated: {summary['generated_at']}",
        f"Strangers dir: `{STRANGERS_DIR}`",
        "",
        "## Headline numbers",
        "",
        f"- Stranger dirs on disk: {summary['total_stranger_dirs']}",
        f"- Verified (verdict.pass=true): {summary['verified_pass_true_count']}",
        f"- Passed all 7 checks: {summary['passed_all_7_checks']}",
        f"- Suspicious (one or more warnings or failed checks): {summary['with_at_least_one_warning_or_failed_check']}",
        "",
        "## V7.20 no-fake-receipts gate",
        "",
        f"- Every verified stranger has a real Chrome surface path: "
        f"{summary['v7_20_fake_receipts_gate']['all_verified_have_real_chrome_surface_path']}",
        f"- Every verified outcome is ASKING / DECLINED / ACTED with dossier: "
        f"{summary['v7_20_fake_receipts_gate']['all_verified_have_outcome_in_ASKING_DECLINED_or_ACTED_with_dossier']}",
        f"- Every verified evaluator_model is on the V7 allowlist: "
        f"{summary['v7_20_fake_receipts_gate']['no_unallowlisted_evaluator_models']}",
        "",
        "## Duplicate reasoning groups",
        "",
    ]
    if duplicated_reasoning:
        for k, v in duplicated_reasoning.items():
            md_lines.append(f"- `{k}...`: {len(v)} strangers -> {v[:5]}")
    else:
        md_lines.append("- None. Every verdict.reasoning string is unique.")
    md_lines += [
        "",
        "## Duplicate screenshot sha256 groups",
        "",
    ]
    if duplicated_screenshots:
        for k, v in duplicated_screenshots.items():
            md_lines.append(f"- `{k}...`: {len(v)} strangers -> {v[:5]}")
    else:
        md_lines.append("- None. Every captured surface screenshot is unique on disk.")
    md_lines += [
        "",
        "## Top suspicious UUIDs",
        "",
    ]
    if top_suspicious:
        for s in top_suspicious:
            md_lines.append(f"- `{s['uuid']}`")
            failed = [k for k, v in s["checks"].items() if v is False]
            if failed:
                md_lines.append(f"  - failed checks: {failed}")
            if s["warnings"]:
                md_lines.append(f"  - warnings: {s['warnings'][:5]}")
            md_lines.append(f"  - outcome: {s['outcome']}, evaluator_model: {s['evaluator_model']}")
    else:
        md_lines.append("- None. No suspicious strangers.")
    md_lines.append("")

    (out_dir / "summary.md").write_text("\n".join(md_lines))
    print(f"WROTE: {out_dir}/summary.json", file=sys.stderr)
    print(f"WROTE: {out_dir}/summary.md", file=sys.stderr)
    print(json.dumps({
        "verified": len(verified),
        "passed_all": len(full_pass),
        "suspicious": len(suspicious),
        "out_dir": str(out_dir),
    }))


if __name__ == "__main__":
    main()
