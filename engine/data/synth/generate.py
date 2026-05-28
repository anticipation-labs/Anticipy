"""Phase 1 synth-data generator — DeepSeek V4 Flash via OpenRouter.

Uses the prompt templates in `prompts.py` to produce JSONL rows that
match the schema validated by `validate.py`. Writes incrementally to
the target file so a crash mid-run loses at most one example.

Usage:
  python -m engine.data.synth.generate utterance_in_context \\
    --n 100 --out engine/data/synth/utterance_in_context.jsonl
  python -m engine.data.synth.generate negative --n 100 --out ...
  python -m engine.data.synth.generate memory_resolution --n 100 --out ...

Cost-cap: stops if estimated cost exceeds OPENROUTER_SOFT_CAP_USD env
(default $5 per run).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT.parent / ".env.local")

sys.path.insert(0, str(ROOT))
from data.synth.prompts import (  # type: ignore  # noqa: E402
    UTTERANCE_IN_CONTEXT_SYSTEM,
    UTTERANCE_IN_CONTEXT_USER,
    MEMORY_RESOLUTION_SYSTEM,
    MEMORY_RESOLUTION_USER,
    NEGATIVE_SYSTEM,
    NEGATIVE_USER,
    DEFAULT_BOUNDARY_DISTRIBUTION,
)
from data.synth.validate import validate_row  # type: ignore  # noqa: E402

MODEL = "deepseek/deepseek-chat"  # OpenRouter routes this to DeepSeek-V3
ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_BATCH_SIZE = 10
PRICE_INPUT_PER_1K = 0.00027   # OpenRouter's DeepSeek-V3 input
PRICE_OUTPUT_PER_1K = 0.0011   # OpenRouter's DeepSeek-V3 output


def call_deepseek(system: str, user: str, max_tokens: int = 4000) -> tuple[str, dict]:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise SystemExit("OPENROUTER_API_KEY missing from env")
    r = httpx.post(
        ENDPOINT,
        json={
            "model": MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.9,
            "max_tokens": max_tokens,
        },
        headers={
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "https://www.anticipy.ai",
            "X-Title": "Anticipy synth-data generator",
            "Content-Type": "application/json",
        },
        timeout=90.0,
    )
    r.raise_for_status()
    data = r.json()
    text = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})
    return text, usage


def parse_jsonl_lines(text: str) -> list[dict]:
    """Take the raw model output and yield one parsed JSON object per
    line. Tolerates surrounding prose / fences.
    """
    out = []
    for raw in text.splitlines():
        raw = raw.strip()
        if not raw or raw.startswith("```") or raw.endswith("```"):
            continue
        try:
            obj = json.loads(raw)
            out.append(obj)
        except json.JSONDecodeError:
            # Try to extract a JSON object embedded in the line
            i, j = raw.find("{"), raw.rfind("}")
            if i >= 0 and j > i:
                try:
                    out.append(json.loads(raw[i : j + 1]))
                except json.JSONDecodeError:
                    pass
    return out


def estimate_cost(usage: dict) -> float:
    pi = usage.get("prompt_tokens", 0)
    po = usage.get("completion_tokens", 0)
    return (pi / 1000) * PRICE_INPUT_PER_1K + (po / 1000) * PRICE_OUTPUT_PER_1K


def generate(kind: str, n: int, out_path: Path, batch_size: int = DEFAULT_BATCH_SIZE) -> dict:
    if kind == "utterance_in_context":
        system = UTTERANCE_IN_CONTEXT_SYSTEM
        user_template = UTTERANCE_IN_CONTEXT_USER
        boundary_dist_str = json.dumps(DEFAULT_BOUNDARY_DISTRIBUTION, indent=2)
    elif kind == "memory_resolution":
        system = MEMORY_RESOLUTION_SYSTEM
        user_template = MEMORY_RESOLUTION_USER
    elif kind == "negative":
        system = NEGATIVE_SYSTEM
        user_template = NEGATIVE_USER
    else:
        raise SystemExit(f"unknown kind: {kind}")

    soft_cap = float(os.environ.get("OPENROUTER_SOFT_CAP_USD", "5.0") or "5.0")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    written = 0
    rejected = 0
    total_cost = 0.0
    next_id = 0
    with out_path.open("a", encoding="utf-8") as fh:
        while written < n:
            this_batch = min(batch_size, n - written)
            if kind == "utterance_in_context":
                user = user_template.format(n=this_batch, boundary_distribution=boundary_dist_str)
            elif kind == "memory_resolution":
                user = user_template.format(n=this_batch, ambiguous_pct=10)
            else:
                user = user_template.format(n=this_batch)
            try:
                text, usage = call_deepseek(system, user)
            except httpx.HTTPStatusError as e:
                print(f"[generate] HTTP error: {e}", file=sys.stderr)
                break
            cost = estimate_cost(usage)
            total_cost += cost
            if total_cost > soft_cap:
                print(f"[generate] hit soft cap ${soft_cap}; stopping (spent ~${total_cost:.4f})", file=sys.stderr)
                break

            rows = parse_jsonl_lines(text)
            sample_errs: list[str] = []
            for row in rows:
                if "id" not in row:
                    next_id += 1
                    row["id"] = f"gen_{int(time.time())}_{next_id}"
                if "kind" not in row:
                    row["kind"] = kind
                # Cheap auto-coerce: if the generator left expected_intent
                # missing, infer from label.
                if row.get("expected_label") in {"REFUSE", "STORE_AS_LATENT"}:
                    row.setdefault("expected_intent", None)
                if row.get("expected_label") != "COMMIT":
                    row["expected_intent"] = None  # force null for non-COMMIT
                row.setdefault("expected_memory_write", None)
                row.setdefault("turn_history", [])
                row.setdefault("user_memory", [])
                errs = validate_row(row, written)
                if errs:
                    if len(sample_errs) < 3:
                        sample_errs.append(errs[0])
                    rejected += 1
                    continue
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                fh.flush()
                written += 1
                if written >= n:
                    break
            if sample_errs:
                print(f"[generate] batch sample rejections: {sample_errs[:3]}", file=sys.stderr)

    return {
        "written": written,
        "rejected": rejected,
        "estimated_cost_usd": round(total_cost, 4),
        "out_path": str(out_path),
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("kind", choices=["utterance_in_context", "memory_resolution", "negative"])
    p.add_argument("--n", type=int, default=10)
    p.add_argument("--out", type=str, required=True)
    p.add_argument("--batch", type=int, default=DEFAULT_BATCH_SIZE)
    args = p.parse_args()
    out = generate(args.kind, args.n, Path(args.out), batch_size=args.batch)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
