"""Schema + sanity validator for engine/data/synth/*.jsonl.

Pure stdlib (no deps). Run before training and after every generator
batch. Catches malformed JSON, missing fields, label/intent mismatches,
non-substring evidence quotes, and other corner cases that would
silently poison a fine-tune.

Usage:
    python engine/data/synth/validate.py engine/data/synth/gold_standard.jsonl
    python engine/data/synth/validate.py engine/data/synth/utterance_in_context.jsonl
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

VALID_LABELS = {"COMMIT", "STORE_AS_LATENT", "REFUSE"}
VALID_BOUNDARY_TAGS = {
    "sarcasm",
    "hedging",
    "abandonment",
    "third_party",
    "past_tense",
    "conditional",
    "joke",
    "brainstorm",
    "real_action",
    "multi_turn",
}
VALID_MEMORY_KINDS = {
    "preference",
    "aversion",
    "contact",
    "habit",
    "recurrence",
    "trajectory",
    "sentiment_fact",
}
VALID_ACTION_CATEGORIES = {
    "book_reservation",
    "send_email",
    "schedule_event",
    "reorder",
    "post_message",
    "draft_proposal",
    "set_reminder",
    "navigate_to",
    "log_expense",
    "queue_song",
    "create_issue",
    "update_contact",
    "file_expense",
    "fact_lookup",
}

REQUIRED_TOP_LEVEL = (
    "id",
    "kind",
    "turn_history",
    "utterance",
    "user_memory",
    "expected_label",
    "expected_reason",
    "expected_intent",
    "expected_memory_write",
    "boundary_tag",
)


def validate_row(row: dict[str, Any], idx: int) -> list[str]:
    """Return a list of human-readable errors. Empty list = valid."""
    errs: list[str] = []

    for k in REQUIRED_TOP_LEVEL:
        if k not in row:
            errs.append(f"row {idx}: missing field '{k}'")
    if errs:
        return errs  # Bail early; downstream checks assume fields exist.

    if not isinstance(row["id"], str) or not row["id"]:
        errs.append(f"row {idx}: id must be a non-empty string")

    if not isinstance(row["utterance"], str) or not row["utterance"].strip():
        errs.append(f"row {idx}: utterance must be a non-empty string")

    if row["expected_label"] not in VALID_LABELS:
        errs.append(
            f"row {idx}: expected_label '{row['expected_label']}' "
            f"not in {sorted(VALID_LABELS)}"
        )

    if row["boundary_tag"] not in VALID_BOUNDARY_TAGS:
        errs.append(
            f"row {idx}: boundary_tag '{row['boundary_tag']}' "
            f"not in {sorted(VALID_BOUNDARY_TAGS)}"
        )

    if not isinstance(row["turn_history"], list):
        errs.append(f"row {idx}: turn_history must be a list")
    else:
        for ti, t in enumerate(row["turn_history"]):
            if not isinstance(t, dict) or "speaker" not in t or "text" not in t:
                errs.append(
                    f"row {idx}: turn_history[{ti}] missing speaker/text"
                )

    if not isinstance(row["user_memory"], list):
        errs.append(f"row {idx}: user_memory must be a list")
    else:
        for mi, m in enumerate(row["user_memory"]):
            if not isinstance(m, dict):
                errs.append(f"row {idx}: user_memory[{mi}] must be an object")
                continue
            if m.get("kind") not in VALID_MEMORY_KINDS:
                errs.append(
                    f"row {idx}: user_memory[{mi}].kind '{m.get('kind')}' "
                    f"not in {sorted(VALID_MEMORY_KINDS)}"
                )

    label = row["expected_label"]
    intent = row["expected_intent"]
    if label == "COMMIT":
        if intent is None:
            errs.append(f"row {idx}: COMMIT requires non-null expected_intent")
        elif not isinstance(intent, dict):
            errs.append(f"row {idx}: expected_intent must be an object")
        else:
            ac = intent.get("action_category")
            if ac not in VALID_ACTION_CATEGORIES:
                errs.append(
                    f"row {idx}: action_category '{ac}' not in "
                    f"{sorted(VALID_ACTION_CATEGORIES)}"
                )
            for k in ("slots", "needs_memory", "needs_inference"):
                if k not in intent:
                    errs.append(
                        f"row {idx}: expected_intent missing '{k}'"
                    )
    elif intent is not None:
        errs.append(
            f"row {idx}: expected_intent must be null when label != COMMIT "
            f"(label={label})"
        )

    mem_write = row["expected_memory_write"]
    if mem_write is not None:
        if not isinstance(mem_write, dict):
            errs.append(
                f"row {idx}: expected_memory_write must be an object or null"
            )
        else:
            if mem_write.get("kind") not in VALID_MEMORY_KINDS:
                errs.append(
                    f"row {idx}: expected_memory_write.kind '{mem_write.get('kind')}' "
                    f"not in {sorted(VALID_MEMORY_KINDS)}"
                )
            ev = mem_write.get("evidence_quote", "")
            if ev and ev not in row["utterance"]:
                errs.append(
                    f"row {idx}: evidence_quote '{ev[:50]}...' is not a "
                    f"substring of utterance"
                )

    return errs


def validate_file(path: Path) -> int:
    """Returns exit code: 0 = all valid, 1 = any errors."""
    if not path.exists():
        print(f"ERROR: {path} does not exist", file=sys.stderr)
        return 1

    n_rows = 0
    n_errs = 0
    label_counts: dict[str, int] = {}
    tag_counts: dict[str, int] = {}

    with path.open() as f:
        for idx, raw in enumerate(f):
            raw = raw.strip()
            if not raw:
                continue
            try:
                row = json.loads(raw)
            except json.JSONDecodeError as e:
                print(f"row {idx}: JSON parse error: {e}", file=sys.stderr)
                n_errs += 1
                continue

            errs = validate_row(row, idx)
            for e in errs:
                print(e, file=sys.stderr)
            n_errs += len(errs)
            n_rows += 1

            label_counts[row.get("expected_label", "?")] = (
                label_counts.get(row.get("expected_label", "?"), 0) + 1
            )
            tag_counts[row.get("boundary_tag", "?")] = (
                tag_counts.get(row.get("boundary_tag", "?"), 0) + 1
            )

    print(f"\n{path}:", file=sys.stderr)
    print(f"  rows: {n_rows}", file=sys.stderr)
    print(f"  errors: {n_errs}", file=sys.stderr)
    print(f"  by label: {label_counts}", file=sys.stderr)
    print(f"  by boundary_tag: {tag_counts}", file=sys.stderr)

    return 0 if n_errs == 0 else 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python validate.py <path1.jsonl> [path2.jsonl ...]", file=sys.stderr)
        sys.exit(2)
    rc = 0
    for arg in sys.argv[1:]:
        if validate_file(Path(arg)):
            rc = 1
    sys.exit(rc)
