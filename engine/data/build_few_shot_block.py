"""
build_few_shot_block.py — pick 8 strong positive + 4 strong negative examples
from training_corpus.jsonl and emit a single FEW_SHOT prompt block to be
injected into the intent-extraction system prompt.

Selection heuristic (generic — no hardcoded action_type categories):
  POSITIVES (gate_verdict in {confirmed, executed, auto_proceeded}):
    - Prefer rows whose `executed=true` (the action actually ran) — strongest signal.
    - Prefer rows with non-empty parameters (richer slot-filling exemplar).
    - Prefer `confidence` >= 0.7 (the model was sure and was right).
    - Diversity: cap one per action_type so the block doesn't pile on a single skill.
  NEGATIVES (gate_verdict in {rejected, failed}):
    - Prefer rows where signal_kind == 'reject' (explicit user no), then 'failed'.
    - Prefer rows with a non-empty signal_reasoning (we have a one-liner WHY).
    - Diversity: cap one per action_type.

Output:
  - engine/data/few_shot_block.txt   (gitignored)

The block is plain text, designed to be appended to the intent-prompt
system message. The format is illustrative, not enforced — the LLM treats
the examples as soft guidance.

Run:
  cd engine
  python data/build_few_shot_block.py
  python data/build_few_shot_block.py --positives 8 --negatives 4
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent
CORPUS = DATA_DIR / "training_corpus.jsonl"
OUT = DATA_DIR / "few_shot_block.txt"


def load_corpus(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        print(
            f"ERROR: {path} not found. Run export_training_corpus.py first.",
            file=sys.stderr,
        )
        sys.exit(2)
    rows: list[dict[str, Any]] = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def positive_score(row: dict[str, Any]) -> tuple[int, float, int]:
    g = row.get("ground_truth_intent") or {}
    if not g:
        return (-1, 0.0, 0)
    executed = 1 if g.get("executed") else 0
    confidence = float(g.get("confidence") or 0.0)
    param_richness = len(g.get("parameters") or {})
    return (executed, confidence, param_richness)


def negative_score(row: dict[str, Any]) -> tuple[int, int]:
    labels = row.get("labels") or {}
    has_reasoning = 1 if (labels.get("signal_reasoning") or "").strip() else 0
    explicit_reject = 1 if labels.get("signal_kind") == "reject" else 0
    return (explicit_reject, has_reasoning)


def pick_diverse(
    rows: list[dict[str, Any]],
    score_fn,
    n: int,
    extract_intent,
) -> list[dict[str, Any]]:
    sorted_rows = sorted(rows, key=score_fn, reverse=True)
    seen: set[str] = set()
    picks: list[dict[str, Any]] = []
    # First pass: one per action_type
    for r in sorted_rows:
        if len(picks) >= n:
            break
        intent = extract_intent(r)
        if not intent:
            continue
        at = (intent.get("action_type") or "").strip().lower()
        if at and at in seen:
            continue
        seen.add(at)
        picks.append(r)
    # Second pass: fill remainder regardless of duplicate action_types
    if len(picks) < n:
        for r in sorted_rows:
            if r in picks or len(picks) >= n:
                continue
            if extract_intent(r):
                picks.append(r)
    return picks


def render_positive(row: dict[str, Any], idx: int) -> str:
    g = row["ground_truth_intent"] or {}
    transcript = (row.get("input") or {}).get("transcript_window") or ""
    reasoning = (row.get("labels") or {}).get("signal_reasoning") or ""
    params = json.dumps(g.get("parameters") or {}, ensure_ascii=False)
    parts = [
        f"POSITIVE EXAMPLE {idx} — wearer accepted/executed this intent:",
        f"  Transcript: \"{transcript[:240]}\"",
        f"  Extract:    action_type={g.get('action_type')!s} | "
        f"summary={g.get('summary')!s} | "
        f"importance={g.get('importance')!s} | "
        f"confidence={g.get('confidence')}",
        f"  Parameters: {params}",
    ]
    if reasoning:
        parts.append(f"  Why it worked: {reasoning}")
    return "\n".join(parts)


def render_negative(row: dict[str, Any], idx: int) -> str:
    n = (row.get("negative_examples") or [{}])[0]
    transcript = (row.get("input") or {}).get("transcript_window") or ""
    labels = row.get("labels") or {}
    reasoning = labels.get("signal_reasoning") or ""
    verdict = labels.get("gate_verdict") or ""
    parts = [
        f"NEGATIVE EXAMPLE {idx} — wearer rejected or this failed (do NOT extract similarly):",
        f"  Transcript: \"{transcript[:240]}\"",
        f"  Extracted (rejected): action_type={n.get('action_type')!s} | summary={n.get('summary')!s}",
        f"  Verdict:    {verdict}",
    ]
    if reasoning:
        parts.append(f"  Why it failed: {reasoning}")
    return "\n".join(parts)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--positives", type=int, default=8)
    p.add_argument("--negatives", type=int, default=4)
    p.add_argument("--corpus", type=Path, default=CORPUS)
    p.add_argument("--out", type=Path, default=OUT)
    args = p.parse_args()

    rows = load_corpus(args.corpus)
    pos_rows = [r for r in rows if r.get("ground_truth_intent")]
    neg_rows = [r for r in rows if r.get("negative_examples")]
    print(
        f"corpus: {len(rows)} rows ({len(pos_rows)} positive, {len(neg_rows)} negative)",
        flush=True,
    )

    pos_picks = pick_diverse(
        pos_rows,
        positive_score,
        args.positives,
        extract_intent=lambda r: r.get("ground_truth_intent"),
    )
    neg_picks = pick_diverse(
        neg_rows,
        negative_score,
        args.negatives,
        extract_intent=lambda r: (r.get("negative_examples") or [None])[0],
    )

    print(f"  picked: {len(pos_picks)} positives, {len(neg_picks)} negatives", flush=True)
    if not pos_picks and not neg_picks:
        print("ERROR: nothing to render — corpus is empty", file=sys.stderr)
        return 3

    header = (
        "LEARNED-FROM-DATA EXAMPLES — patterns from real wearer accept/reject signal. "
        "Treat them as illustrative anchors. Do not memorize wording; generalize the pattern.\n"
    )
    blocks: list[str] = [header]
    for i, r in enumerate(pos_picks, 1):
        blocks.append(render_positive(r, i))
        blocks.append("")
    for i, r in enumerate(neg_picks, 1):
        blocks.append(render_negative(r, i))
        blocks.append("")

    text = "\n".join(blocks).rstrip() + "\n"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text)
    print(f"wrote {args.out} ({len(text)} chars)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
