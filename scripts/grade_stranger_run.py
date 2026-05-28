"""
grade_stranger_run.py — independently grade a stranger run report against DONE.md.

Two-model agreement protocol (Rule 1 of BOOTSTRAP.md):
- Codex computer-use wrote the report (model A: implicit, the agent itself).
- This script asks a SECOND independent model (model B: DeepSeek V4 Flash on OpenRouter)
  to read the report against DONE.md and produce a verdict.
- If model B disagrees with the report's self-assessment, the run fails.
- If model B agrees with a pass verdict, the run passes.
- If model B says fail regardless, the run fails.

We do not use vision here. We read the structured report text against the structured DONE.md.
This is cheap (~$0.002 per grading) and deterministic in inputs.
"""

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path


GRADING_PROMPT = """You are an independent quality reviewer. Read the DONE.md spec and the stranger run REPORT below. Produce a JSON verdict with exactly these fields:

- "verdict": "pass" or "fail"
- "reasoning": one to three sentences explaining your decision
- "rough_edges": array of strings, each describing a specific rough edge found in the report (empty if none)
- "matches_done_bar": boolean, true only if the report describes an experience that meets every clause of DONE.md

The bar is the "trillion-dollar stranger" bar from DONE.md. A "pretty good" experience is a fail. Polish anywhere below excellent is a fail. Any rough edge mentioned by the stranger is grounds for fail.

You output ONLY the JSON object. No prose before or after.

=== DONE.md ===
{done_doc}

=== REPORT ===
{report}
"""


def call_openrouter(prompt: str) -> str:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY not set")
    body = json.dumps({
        "model": "deepseek/deepseek-chat-v4-flash",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 800,
        "temperature": 0.1,
    }).encode()
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://anticipy.ai",
            "X-Title": "Anticipy synthetic-stranger grader",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())
    return data["choices"][0]["message"]["content"].strip()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--report", required=True)
    p.add_argument("--done-doc", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()

    done_doc = Path(args.done_doc).read_text()
    report = Path(args.report).read_text()

    prompt = GRADING_PROMPT.format(done_doc=done_doc, report=report)

    try:
        raw = call_openrouter(prompt)
    except Exception as e:
        Path(args.output).write_text(json.dumps({
            "verdict": "fail",
            "reasoning": f"grader call failed: {e}",
            "rough_edges": ["grader_unavailable"],
            "matches_done_bar": False,
        }, indent=2))
        sys.exit(1)

    # Strip code fences if present
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    if raw.endswith("```"):
        raw = raw[:-3].strip()

    try:
        verdict = json.loads(raw)
    except json.JSONDecodeError:
        Path(args.output).write_text(json.dumps({
            "verdict": "fail",
            "reasoning": f"grader returned non-JSON: {raw[:200]}",
            "rough_edges": ["grader_invalid_response"],
            "matches_done_bar": False,
        }, indent=2))
        sys.exit(1)

    Path(args.output).write_text(json.dumps(verdict, indent=2))
    sys.exit(0 if verdict.get("verdict") == "pass" else 1)


if __name__ == "__main__":
    main()
