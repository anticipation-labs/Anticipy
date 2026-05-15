"""Held-out cascade eval — runs the cascade against the SYNTH data
(utterance_in_context_v2 + negative) which the cascade's few-shot
prompt has NEVER seen. This is the real generalization measurement.

The cascade still uses gold_standard.jsonl as its few-shot exemplars,
so v2/negative are out-of-distribution for it.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT.parent / ".env.local")

from app.proactive.demand_detection import DemandDetector  # noqa: E402
from app.proactive.hedge_filter import HedgeFilter  # noqa: E402
from app.proactive.intent_extraction import IntentExtractor  # noqa: E402
from app.proactive.pipeline import PodAPipeline  # noqa: E402

HOLDOUT_FILES = [
    ROOT / "data" / "synth" / "utterance_in_context_v2.jsonl",
    ROOT / "data" / "synth" / "negative.jsonl",
]


def load_rows(path: Path) -> list[dict]:
    rows = []
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return rows


async def main() -> int:
    pipeline = PodAPipeline(
        demand_detector=DemandDetector(),
        hedge_filter=HedgeFilter(backend="cascade", fewshot_count=8),
        intent_extractor=IntentExtractor(),
    )

    all_rows: list[dict] = []
    for f in HOLDOUT_FILES:
        if f.exists():
            all_rows.extend(load_rows(f))

    print(f"== Held-out cascade eval, n={len(all_rows)} (DeepSeek-generated; cascade few-shot is gold_standard.jsonl) ==\n")

    by_label_total: dict[str, int] = {}
    by_label_hits: dict[str, int] = {}
    by_tag_total: dict[str, int] = {}
    by_tag_hits: dict[str, int] = {}

    hits = 0
    for i, row in enumerate(all_rows, 1):
        ctx_lines = []
        for t in row.get("turn_history", []):
            ctx_lines.append(f"{t['speaker'].capitalize()}: {t['text']}")
        ctx = "\n".join(ctx_lines) if ctx_lines else None

        result = await pipeline.from_text(
            utterance=row["utterance"],
            user_id="holdout",
            context_transcript=ctx,
        )
        actual = result.hedge.decision if result.hedge else "REFUSE"
        expected = row["expected_label"]
        match = actual == expected
        if match:
            hits += 1
        tag = row.get("boundary_tag", "unknown")
        by_label_total[expected] = by_label_total.get(expected, 0) + 1
        by_tag_total[tag] = by_tag_total.get(tag, 0) + 1
        if match:
            by_label_hits[expected] = by_label_hits.get(expected, 0) + 1
            by_tag_hits[tag] = by_tag_hits.get(tag, 0) + 1
        sym = "✓" if match else "✗"
        print(f"[{i:2d}/{len(all_rows)}] {sym} {tag:14s} expected={expected:16s} actual={actual:16s} {row['utterance'][:60]}")

    print()
    print(f"== SUMMARY: {hits}/{len(all_rows)} ({100*hits/max(len(all_rows),1):.1f}%) ==")
    print()
    print("By expected_label:")
    for lbl in sorted(by_label_total):
        h = by_label_hits.get(lbl, 0)
        t = by_label_total[lbl]
        print(f"  {lbl:18s}  {h}/{t}  {100*h/max(t,1):.0f}%")
    print()
    print("By boundary_tag:")
    for tag in sorted(by_tag_total):
        h = by_tag_hits.get(tag, 0)
        t = by_tag_total[tag]
        print(f"  {tag:14s}  {h}/{t}  {100*h/max(t,1):.0f}%")
    return 0 if hits >= len(all_rows) * 0.85 else 1  # 85% holdout floor


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
