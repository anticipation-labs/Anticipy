"""
export_training_corpus.py — pull the proactive_training_corpus view, transform
to JSONL, and write to engine/data/training_corpus.jsonl.

Output schema (one JSON object per line):
  {
    "intent_id":          "<uuid>",
    "created_at":         "<iso8601>",
    "input": {
      "transcript_window": "<conversation that produced the intent>",
      "system_prompt":     "<the intent-extraction system prompt currently in production>",
      "memory_context":    ["<retrieved memory hint>", ...],         // best-effort, may be []
      "preference_context":["<retrieved preference hint>", ...],     // best-effort, may be []
      "local_time":        "<intent created_at in user's tz>",
      "timezone":          "<user tz, defaults to UTC>"
    },
    "ground_truth_intent": {       // when the user accepted/executed
      "action_type":    "...",
      "summary":        "...",
      "evidence_quote": "...",
      "parameters":     {...},
      "importance":     "standard|important|...",
      "confidence":     0.0-1.0,
      "executed":       true|false
    } | null,
    "negative_examples": [         // when the user rejected/failed
      { ... same shape ... }
    ],
    "labels": {
      "gate_verdict":     "confirmed|rejected|executed|failed|auto_proceeded",
      "signal_kind":      "accept|reject|edit|auto_proceed" | null,
      "signal_reasoning": "<one-sentence why-summary>" | null,
      "executed_outcome": { "executed": bool, "action_status": "...", "action_result": {...} }
    }
  }

Privacy + access control:
  - Reads with SUPABASE_SERVICE_ROLE_KEY only. The view itself revokes anon
    and authenticated. Without service role this script cannot pull data.
  - This script must be invoked by an OPERATOR explicitly. It is NOT wired
    into any cron, hook, or background process. There is no `--auto` flag.
  - The output file is gitignored (engine/data/training_corpus.jsonl).
    Confirm `git status` does not show it before pushing anything.
  - Real user transcripts may be present. Treat the file like a database
    dump: encrypt at rest if shared, never paste into shared docs.

Run:
  cd engine
  export $(grep -v '^#' ../.env.local | xargs)
  python data/export_training_corpus.py
  python data/export_training_corpus.py --limit 500
  python data/export_training_corpus.py --out /tmp/corpus.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parent.parent.parent
ENV_FILE = ROOT / ".env.local"
DEFAULT_OUT = Path(__file__).resolve().parent / "training_corpus.jsonl"

if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

SUPABASE_URL = os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

if not SUPABASE_URL or not SUPABASE_SERVICE:
    print(
        "ERROR: NEXT_PUBLIC_SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set "
        "(load .env.local first).",
        file=sys.stderr,
    )
    sys.exit(2)

HDR = {
    "apikey": SUPABASE_SERVICE,
    "Authorization": f"Bearer {SUPABASE_SERVICE}",
    "Content-Type": "application/json",
}

# We embed a snapshot of the production system prompt so each training row is
# self-contained — a future fine-tuning job can replay the exact (input,
# expected_output) pair without reaching back into the codebase. Re-export
# whenever the prompt changes.
SYSTEM_PROMPT_SNAPSHOT = (
    "You are an ambient intelligence assistant that listens to real conversations "
    "and extracts ONLY genuinely actionable items the user needs to do LATER. "
    "Filter conversational back-and-forth, delegations to other people, retracted "
    "conditionals, status queries, and future-tense pleasantries. Capture only "
    "future actions the wearer themselves committed to. Honest confidence: 0.9+ "
    "only when the action is unambiguous and clearly the user's to do. Anything "
    "conversational, hypothetical, or unclear gets <0.65. The full live prompt "
    "(with worked rules and slot taxonomy) lives in src/lib/intent-prompt.ts; "
    "this is a stable summary suitable for fine-tuning input."
)


def fetch_corpus(limit: int | None) -> list[dict[str, Any]]:
    """Pull rows from the proactive_training_corpus view via PostgREST.

    Service-role only — the view revokes anon/authenticated.
    """
    url = f"{SUPABASE_URL}/rest/v1/proactive_training_corpus?select=*&order=created_at.asc"
    if limit is not None and limit > 0:
        url += f"&limit={int(limit)}"
    with httpx.Client(timeout=60) as c:
        r = c.get(url, headers=HDR)
        if r.status_code != 200:
            print(
                f"ERROR: corpus fetch {r.status_code}: {r.text[:300]}", file=sys.stderr
            )
            sys.exit(3)
        rows = r.json()
        if not isinstance(rows, list):
            print(f"ERROR: unexpected response shape: {type(rows)}", file=sys.stderr)
            sys.exit(3)
        return rows


# Lightweight redaction pass on transcript_window. The view filters out test
# users; we additionally scrub anything that obviously looks like an email,
# phone, credit card, or long digit run from the transcript before the row
# leaves the database. This is defense-in-depth — the goal of the corpus is
# to learn intent EXTRACTION patterns, not to memorize user PII.
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(r"(?<!\d)(\+?\d[\d\s().-]{7,}\d)(?!\d)")
LONG_DIGIT_RE = re.compile(r"\b\d{12,}\b")


def redact(text: str) -> str:
    if not text:
        return ""
    text = EMAIL_RE.sub("[EMAIL]", text)
    text = PHONE_RE.sub("[PHONE]", text)
    text = LONG_DIGIT_RE.sub("[NUMBER]", text)
    return text


def to_intent_payload(intent_json: dict[str, Any], outcome: dict[str, Any]) -> dict[str, Any]:
    return {
        "action_type":    intent_json.get("action_type"),
        "summary":        redact(intent_json.get("summary") or ""),
        "evidence_quote": redact(intent_json.get("evidence_quote") or ""),
        "parameters":     intent_json.get("parameters") or {},
        "importance":     intent_json.get("importance"),
        "confidence":     intent_json.get("confidence"),
        "executed":       bool(outcome.get("executed")),
    }


# Status -> sign of the example. Generic mapping (we do not hardcode action
# categories): a TERMINAL "confirmed/executed/auto_proceeded" gate is positive
# evidence the system was right to extract the intent; "rejected/failed" is
# negative evidence the wearer (or the world) did not want this.
POSITIVE_VERDICTS = {"confirmed", "executed", "auto_proceeded"}
NEGATIVE_VERDICTS = {"rejected", "failed"}


def transform(row: dict[str, Any]) -> dict[str, Any]:
    intent_json = row.get("extracted_intent_json") or {}
    outcome = row.get("executed_outcome") or {}
    verdict = row.get("gate_verdict") or ""
    payload = to_intent_payload(intent_json, outcome)

    if verdict in POSITIVE_VERDICTS:
        ground_truth = payload
        negatives: list[dict[str, Any]] = []
    elif verdict in NEGATIVE_VERDICTS:
        ground_truth = None
        negatives = [payload]
    else:
        # Defensive — view should have filtered these.
        ground_truth = None
        negatives = []

    return {
        "intent_id":  row.get("intent_id"),
        "created_at": row.get("created_at"),
        "input": {
            "transcript_window":  redact(row.get("transcript_window") or ""),
            "system_prompt":      SYSTEM_PROMPT_SNAPSHOT,
            "memory_context":     [],
            "preference_context": [],
            "local_time":         row.get("created_at"),
            "timezone":           "UTC",
        },
        "ground_truth_intent": ground_truth,
        "negative_examples":   negatives,
        "labels": {
            "gate_verdict":      verdict,
            "signal_kind":       row.get("signal_kind"),
            "signal_reasoning":  row.get("signal_reasoning"),
            "executed_outcome":  outcome,
        },
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help="Output JSONL path (gitignored). Default: engine/data/training_corpus.jsonl",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Cap rows (for sampling). Default: all rows from the view.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print row count + a redacted sample, write nothing.",
    )
    args = p.parse_args()

    print(
        f"Fetching from {SUPABASE_URL}/rest/v1/proactive_training_corpus "
        f"(limit={args.limit or 'all'})...",
        flush=True,
    )
    rows = fetch_corpus(args.limit)
    print(f"  fetched {len(rows)} rows", flush=True)

    transformed = [transform(r) for r in rows]
    pos = sum(1 for t in transformed if t["ground_truth_intent"] is not None)
    neg = sum(1 for t in transformed if t["negative_examples"])
    drop = sum(1 for t in transformed if t["ground_truth_intent"] is None and not t["negative_examples"])

    print(
        f"  transformed: {pos} positive, {neg} negative, {drop} dropped",
        flush=True,
    )

    if args.dry_run:
        if transformed:
            print("\nSample row (redacted, truncated):", flush=True)
            sample = dict(transformed[0])
            tw = sample["input"]["transcript_window"]
            sample["input"]["transcript_window"] = (tw[:200] + "...") if len(tw) > 200 else tw
            print(json.dumps(sample, indent=2, default=str)[:1500], flush=True)
        return 0

    out_path: Path = args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        for t in transformed:
            f.write(json.dumps(t, default=str) + "\n")
    print(f"\nWrote {len(transformed)} rows to {out_path}", flush=True)
    print(
        "Reminder: this file is gitignored. Do NOT commit, share over chat, "
        "or upload to cloud storage without encryption.",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
