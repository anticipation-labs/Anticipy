"""End-to-end Pod A cascade test against the 17 gold-standard fixtures.

Per Rule 13 of the v-final-prototype master prompt: no claim of done
without a passing end-to-end test. This is that test.

Two modes:
  TEXT mode   — feeds the JSONL utterance directly into PodAPipeline.from_text.
                Validates the LLM cascade (Stage 1 → 1.5 → 2). Fast.
  AUDIO mode  — feeds the WAV via PodAPipeline.from_wav (ASR → cascade).
                Validates the full pipeline including Parakeet ASR.

Usage:
    cd engine
    source .venv/bin/activate
    python -m pytest tests/test_proactive_pipeline.py -v
    python tests/test_proactive_pipeline.py text   # quick TEXT mode
    python tests/test_proactive_pipeline.py audio  # full AUDIO mode

Pass criterion: 14/17 minimum (the master-prompt floor for Stage 1.5
without the QLoRA adapter — the adapter brings it to 30+/32 on the
full set).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

# Ensure engine/ is on sys.path so `app.proactive...` imports resolve
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT.parent / ".env.local")

from app.proactive.demand_detection import DemandDetector  # noqa: E402
from app.proactive.hedge_filter import HedgeFilter  # noqa: E402
from app.proactive.intent_extraction import IntentExtractor  # noqa: E402
from app.proactive.pipeline import PodAPipeline  # noqa: E402

GOLD_PATH = ROOT / "data" / "synth" / "gold_standard.jsonl"
WAV_DIR = ROOT / "tests" / "fixtures" / "gold_standard"
PASS_THRESHOLD = 14  # of 17


def load_gold_rows() -> list[dict]:
    rows: list[dict] = []
    with GOLD_PATH.open() as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


async def run_text_mode(pipeline: PodAPipeline, rows: list[dict]) -> list[dict]:
    """Run each row's utterance through the cascade. Returns one verdict
    per row.
    """
    verdicts: list[dict] = []
    for i, row in enumerate(rows, 1):
        # Multi-turn rows have prior context in turn_history
        ctx_lines = []
        for t in row.get("turn_history", []):
            ctx_lines.append(f"{t['speaker'].capitalize()}: {t['text']}")
        ctx = "\n".join(ctx_lines) if ctx_lines else None

        # Memory summary (compact representation of user_memory)
        mem_lines = []
        for m in row.get("user_memory", []):
            mem_lines.append(f"- {m['kind']}: {m.get('key', '')} = {m.get('value', '')}")
        mem = "\n".join(mem_lines) if mem_lines else None

        result = await pipeline.from_text(
            utterance=row["utterance"],
            user_id="goldtest",
            source="typed",
            context_transcript=ctx,
            context_memory=mem,
        )

        # The pipeline writes nothing for "not actionable" Stage 1
        # decisions; for our gold tests, treat that as REFUSE-equivalent
        # since none of the gold rows are pure-noise.
        actual = (
            result.hedge.decision
            if result.hedge is not None
            else "REFUSE"  # Stage 1 dropped it
        )
        expected = row["expected_label"]
        verdict = {
            "id": row["id"],
            "boundary_tag": row.get("boundary_tag"),
            "utterance": row["utterance"][:80],
            "expected": expected,
            "actual": actual,
            "match": actual == expected,
            "demand_actionable": result.demand.actionable if result.demand else None,
            "hedge_reason": result.hedge.reason if result.hedge else None,
            "intent_action": result.intent.action_category if result.intent else None,
        }
        verdicts.append(verdict)
        # Print per-row progress so a failing batch is debuggable inline
        sym = "PASS" if verdict["match"] else "FAIL"
        print(
            f"[{i:2d}/{len(rows)}] {sym}  {row['id']:6s} {row['boundary_tag']:14s} "
            f"expected={expected:16s} actual={actual:16s}  {row['utterance'][:60]}"
        )
        if not verdict["match"]:
            print(f"           hedge_reason: {verdict['hedge_reason']}")
    return verdicts


async def run_audio_mode(pipeline: PodAPipeline, rows: list[dict]) -> list[dict]:
    """Run each row through the WAV path (ASR → cascade)."""
    verdicts: list[dict] = []
    for i, row in enumerate(rows, 1):
        wav = WAV_DIR / f"{row['id']}.wav"
        if not wav.exists():
            print(f"[{i:2d}/{len(rows)}] SKIP   {row['id']} — WAV missing at {wav}")
            verdicts.append(
                {"id": row["id"], "expected": row["expected_label"], "actual": "SKIP", "match": False}
            )
            continue
        result = await pipeline.from_wav(path=wav, user_id="goldtest", source="mac_mic")
        actual = result.hedge.decision if result.hedge is not None else "REFUSE"
        expected = row["expected_label"]
        verdicts.append(
            {
                "id": row["id"],
                "expected": expected,
                "actual": actual,
                "match": actual == expected,
                "asr_text": result.utterance,
                "hedge_reason": result.hedge.reason if result.hedge else None,
            }
        )
        sym = "PASS" if actual == expected else "FAIL"
        print(
            f"[{i:2d}/{len(rows)}] {sym}  {row['id']:6s} expected={expected:16s} "
            f"actual={actual:16s}  asr={result.utterance[:60]}"
        )
    return verdicts


def summarize(verdicts: list[dict]) -> dict:
    n = len(verdicts)
    hits = sum(1 for v in verdicts if v["match"])
    by_tag: dict[str, list[bool]] = {}
    for v in verdicts:
        tag = v.get("boundary_tag", "unknown")
        by_tag.setdefault(tag, []).append(v["match"])
    summary = {
        "total": n,
        "hits": hits,
        "rate": hits / n if n else 0.0,
        "passes_threshold": hits >= PASS_THRESHOLD,
        "by_boundary_tag": {
            t: f"{sum(b)}/{len(b)}" for t, b in sorted(by_tag.items())
        },
    }
    return summary


async def main(mode: str) -> int:
    rows = load_gold_rows()
    pipeline = PodAPipeline(
        demand_detector=DemandDetector(),
        hedge_filter=HedgeFilter(backend="cascade", fewshot_count=8),
        intent_extractor=IntentExtractor(),
        # supabase=None — we don't publish during tests
    )
    print(f"== Pod A cascade test, MODE={mode}, rows={len(rows)} ==\n")
    if mode == "audio":
        verdicts = await run_audio_mode(pipeline, rows)
    else:
        verdicts = await run_text_mode(pipeline, rows)
    summary = summarize(verdicts)
    print()
    print("== SUMMARY ==")
    print(json.dumps(summary, indent=2))
    return 0 if summary["passes_threshold"] else 1


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "text"
    if mode not in {"text", "audio"}:
        print(f"usage: {sys.argv[0]} [text|audio]", file=sys.stderr)
        sys.exit(2)
    sys.exit(asyncio.run(main(mode)))
