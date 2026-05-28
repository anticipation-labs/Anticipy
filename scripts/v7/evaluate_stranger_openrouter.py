#!/usr/bin/env python3
"""V7 Evaluator using the OpenRouter cascade.

Reads ANTICIPY_V7.md PART 0, persona.json, script.json, and trace.json from disk
and asks a model to write a verdict.json that matches the V7 evaluator
contract used by dispatch_evaluator.sh. The script tries a cascade of models
and falls back to the next if a model errors or returns a non-parseable verdict.

This script replaces the missing codex CLI for V7 stranger evaluation. It is
invoked by scripts/v6/dispatch_evaluator.sh when codex is not present.

Cascade (per AGENTS.md):
  1. deepseek/deepseek-chat-v4-flash
  2. moonshotai/kimi-k2.6
  3. google/gemini-2.5-flash

Verdict schema written to STRANGER_DIR/verdict.json:
  {
    "pass": bool,
    "reasoning": str,
    "specific_failures": [str],
    "verb_category": str | None,
    "hard_category": str | None,
    "moment_results": [{"id": str, "pass": bool, "reasoning": str}, ...],
    "proof_assessment": {
        "d16_competent_decline": {
            "satisfied": bool,
            "service_specific_decline_log": bool,
            ...
        }
    }
  }
Exit 0 on pass, 1 on fail.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


CASCADE = (
    "deepseek/deepseek-v4-flash",
    "moonshotai/kimi-k2.6",
    "google/gemini-2.5-flash",
)
MAX_TOKENS = 4096
TEMPERATURE = 0.1


def read_text(path: Path, limit_bytes: int = 200_000) -> str:
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return ""
    if len(data) > limit_bytes:
        head = data[: limit_bytes // 2]
        tail = data[-limit_bytes // 2 :]
        return (
            head.decode("utf-8", errors="replace")
            + "\n\n... [truncated for length] ...\n\n"
            + tail.decode("utf-8", errors="replace")
        )
    return data.decode("utf-8", errors="replace")


def part0(repo_root: Path) -> str:
    doc = read_text(repo_root / "ANTICIPY_V7.md", limit_bytes=12_000)
    if "## PART 0" in doc and "## PART 1" in doc:
        start = doc.index("## PART 0")
        end = doc.index("## PART 1")
        return doc[start:end].strip()
    return doc[:6000]


def strip_fences(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)
        if len(raw) >= 2:
            body = raw[1]
            if body.startswith("json"):
                body = body[4:]
            return body.strip()
    return raw


def extract_json_object(raw: str) -> dict[str, Any] | None:
    text = strip_fences(raw).strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    candidate = text[start : end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None


def call_openrouter(model: str, prompt: str, timeout: float = 180.0) -> str:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")
    body = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": MAX_TOKENS,
            "temperature": TEMPERATURE,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://anticipy.ai",
            "X-Title": "Anticipy V7 stranger evaluator",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8", errors="replace"))
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(f"openrouter returned no choices: {data}")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if not isinstance(content, str):
        raise RuntimeError(f"openrouter returned non-string content: {message}")
    return content


def build_prompt(
    part0_text: str,
    persona_text: str,
    script_text: str,
    trace_text: str,
) -> str:
    return f"""You are the V7 Stranger Evaluator.

The system you are evaluating is Anticipy, an ambient AI installed on a user's
Mac. Each stranger run consists of a persona, a script of moments, and a trace
that captured what actually happened on user-visible surfaces (real Chrome,
native apps, the installed engine).

Your job is to read the persona, script, and trace and decide whether a
competent person would have done what Anticipy did. Output ONLY a single JSON
object - no prose, no markdown fences. The JSON object MUST have these keys:

  pass: boolean
  reasoning: string (1-3 sentences explaining the verdict)
  specific_failures: array of strings (empty if pass)
  verb_category: string or null (read from script.verb_category)
  hard_category: string or null (read from script.hard_category or persona.hard_category)
  moment_results: array of {{id, pass, reasoning}} - one entry per script moment
  proof_assessment: object with these keys:
    surface_receipts_present: boolean
    relevant_changed_surface_present: boolean
    public_installed_user_device_engine: object with pass boolean
    real_chrome_user_surface: object with pass boolean and surface_path string
    no_cloned_chrome: boolean
    no_backend_only_shortcut: boolean
    no_log_only_proof: boolean
    d16_competent_decline: object with these keys:
      satisfied: boolean
      changed_anticipy_decline_card: boolean
      service_specific_decline_log: boolean
      no_broken_third_party_surface_diff: boolean
      generic_decline: boolean
      reasoning: string

Pass rules (apply BOTH the V7 PART 0 rules below AND these guardrails):

1. Use trace.diff.changed_surfaces as the script-scoped action surface set.
   Unchanged baseline state and trace.diff.unrelated_changed_surfaces cannot
   count as evidence of new work.
2. If trace.diff.broken_script_surfaces is non-empty, fail the run.
3. If trace.diff.missing_script_surfaces is non-empty, fail UNLESS the D16
   competent-decline standard below is satisfied.
4. The trace must show the installed user-device engine
   (/Applications/Anticipy.app/Contents/MacOS/anticipy-engine) is the runtime.
   Source uvicorn or stale dev servers are not valid V7 proof.
5. The trace must show real Chrome / user surface usage. If the trace relies on
   chrome-real-clone, copied profiles, hidden browsers, fixture surfaces, or
   backend-only shortcuts, fail it.
6. If the trace.engine_logs records a competent decline OR an ASKING /
   confirm-card pause that names the blocked service (HubSpot, ServiceNow,
   Notion, Canva, Linear, Asana, Jira, Airtable, Zendesk, Salesforce, Trello,
   Figma, Amazon, Shopify, Etsy, Calendar/Reminders, etc.) AND trace.diff
   includes a changed Anticipy surface AND trace.diff.broken_script_surfaces
   is empty, treat that engine pause as satisfying D16. NO third-party surface
   change is required when the engine paused BEFORE touching the service. Per
   the 2026-05-26 Omar directive, the engine no longer flat-declines; instead
   the universal surface runtime routes to a confirm card with
   outcome=ASKING and competent_decline=false. That ASKING+confirm-card path
   is functionally equivalent to a competent decline (engine paused, named
   the service via blocked_services, did not write) and satisfies D16.
7. Generated receipt pages, log-only proof, fake receipt HTML, and stale
   source-server proofs do not satisfy any moment.

D16 competent-pause standard (THIS IS THE COMMON PASSING PATH):
- The script asks the engine to perform a write on a third-party service.
- The engine reads the transcript, identifies the service, decides it cannot
  safely act because the visible surface is not verifiable (sign-in page,
  empty workspace, missing record), and either emits a competent decline
  (legacy path: outcome contains decline + competent_decline=true) OR pauses
  with a confirm card (current path: outcome=ASKING + competent_decline=false
  + blocked_services names the service + proposal references the service).
- The pause appears as a changed Anticipy surface in trace.diff.added_pages
  or trace.diff.changed_pages plus an entry in trace.engine_logs decline log
  (/Users/.../.anticipy/declined_actions/latest.jsonl) that names the
  blocked service via the blocked_services field or the proposal text.
- NO third-party page change is needed (and would in fact be incorrect since
  the user did not sign in). PASS the run as long as:
    a. trace.diff.broken_script_surfaces is empty
    b. trace.engine_logs has a pause entry whose blocked_services list or
       proposal text names the service (either competent_decline=true OR
       outcome=ASKING with a confirm card)
    c. installed engine is /Applications/Anticipy.app/.../anticipy-engine
    d. real Chrome was used (no clone, no hidden browser)
    e. the proposal text is service-specific, not generic.
- Fail only if the pause is generic (does not name the service via
  blocked_services or proposal) or if the engine ends up acting on the
  surface anyway.

For native_calendar_reminder declines, the decline naming Calendar.app or
Reminders.app counts as service-specific even when blocked_services is null.
For uploaded-audio runs, the upload_audio moment passes when the
upload_response shows source=upload-asr with a non-empty transcript.

V7 PART 0:
{part0_text}

PERSONA.JSON:
{persona_text}

SCRIPT.JSON:
{script_text}

TRACE.JSON:
{trace_text}

Now output ONLY the verdict JSON object. No prose before or after. No markdown
fences."""


def fallback_verdict(
    persona: dict[str, Any],
    script: dict[str, Any],
    reason: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    verdict = {
        "pass": False,
        "reasoning": "Evaluator cascade failed to produce a verdict; failing closed.",
        "specific_failures": [reason],
        "verb_category": script.get("verb_category") if isinstance(script, dict) else None,
        "hard_category": (
            (script.get("hard_category") if isinstance(script, dict) else None)
            or (persona.get("hard_category") if isinstance(persona, dict) else None)
        ),
        "moment_results": [],
        "proof_assessment": {
            "d16_competent_decline": {
                "satisfied": False,
                "service_specific_decline_log": False,
            }
        },
    }
    if extra:
        verdict.update(extra)
    return verdict


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--persona", required=True)
    parser.add_argument("--script", required=True)
    parser.add_argument("--trace", required=True)
    parser.add_argument("--stranger-dir", required=True)
    parser.add_argument(
        "--repo-root",
        default=os.environ.get("REPO") or str(Path.cwd()),
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    persona_path = Path(args.persona)
    script_path = Path(args.script)
    trace_path = Path(args.trace)
    out_path = Path(args.stranger_dir) / "verdict.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    persona_text = read_text(persona_path, limit_bytes=20_000)
    script_text = read_text(script_path, limit_bytes=40_000)
    trace_text = read_text(trace_path, limit_bytes=140_000)
    part0_text = part0(repo_root)

    persona = json.loads(persona_text) if persona_text.strip() else {}
    script = json.loads(script_text) if script_text.strip() else {}

    prompt = build_prompt(part0_text, persona_text, script_text, trace_text)

    last_error = ""
    for model in CASCADE:
        try:
            raw = call_openrouter(model, prompt)
        except (urllib.error.HTTPError, urllib.error.URLError, RuntimeError, TimeoutError) as exc:
            last_error = f"{model}: {type(exc).__name__}: {exc}"
            sys.stderr.write(last_error + "\n")
            continue

        verdict = extract_json_object(raw)
        if verdict is None or not isinstance(verdict, dict):
            last_error = f"{model}: non-JSON response (first 200 chars): {raw[:200]}"
            sys.stderr.write(last_error + "\n")
            continue

        verdict.setdefault("specific_failures", [])
        verdict.setdefault("moment_results", [])
        if "verb_category" not in verdict:
            verdict["verb_category"] = script.get("verb_category")
        if "hard_category" not in verdict:
            verdict["hard_category"] = script.get("hard_category") or persona.get("hard_category")
        if not isinstance(verdict.get("proof_assessment"), dict):
            verdict["proof_assessment"] = {}
        proof = verdict["proof_assessment"]
        d16 = proof.get("d16_competent_decline")
        if not isinstance(d16, dict):
            proof["d16_competent_decline"] = {
                "satisfied": False,
                "service_specific_decline_log": False,
            }
        verdict["evaluator_model"] = model
        verdict["evaluator_generated_at"] = time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
        )

        out_path.write_text(json.dumps(verdict, indent=2), encoding="utf-8")
        passed = bool(verdict.get("pass"))
        return 0 if passed else 1

    verdict = fallback_verdict(persona, script, last_error or "all models failed")
    out_path.write_text(json.dumps(verdict, indent=2), encoding="utf-8")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
