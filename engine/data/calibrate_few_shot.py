"""
calibrate_few_shot.py — measure the impact of the learned-from-data few-shot
block on intent extraction quality.

Approach:
  - Pick N stratified scenarios from engine/data/proactive_e2e.jsonl (default 30).
  - For each scenario, call Gemini 2.5 Flash directly with the SAME intent-
    extraction system prompt the production analyze route uses, in two
    variants:
      A) baseline:  no few-shot block
      B) few-shot:  the block from engine/data/few_shot_block.txt appended
  - Score with the same Gemini judge used by test_master_benchmark.py
    (matched / missed / fp / spurious counts).
  - Report before/after pass-rate, precision, recall, and the lift.

This bypasses the Next.js server so we can run calibration purely offline.
The system prompt is mirrored from src/lib/intent-prompt.ts; if the
production prompt changes, re-export it.

Run:
  cd engine
  export $(grep -v '^#' ../.env.local | xargs)
  python data/calibrate_few_shot.py            # 30 stratified
  python data/calibrate_few_shot.py 60         # 60 stratified
  python data/calibrate_few_shot.py 30 --few-shot-only   # only run B
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent.parent
ENV_FILE = ROOT / ".env.local"
DATA_DIR = Path(__file__).resolve().parent
DATASET = DATA_DIR / "proactive_e2e.jsonl"
FEW_SHOT_PATH = DATA_DIR / "few_shot_block.txt"

if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

GEMINI_KEY = os.environ.get("GOOGLE_API_KEY", "")
if not GEMINI_KEY:
    print("ERROR: GOOGLE_API_KEY missing", file=sys.stderr)
    sys.exit(2)

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash:generateContent"
)


# Mirror of the production system prompt body. Keep this in sync with
# src/lib/intent-prompt.ts if the live prompt is materially edited. The
# calibration measures the LIFT from adding examples, so a small rendering
# drift between mirror and live is acceptable; we hold both A and B against
# the same mirror.
SYSTEM_PROMPT = """You are an ambient intelligence assistant that listens to real conversations and extracts ONLY genuinely actionable items the user needs to do LATER.

Extract every real task, appointment, reminder, deadline, thing to buy, call to make, follow-up, bill to pay, health instruction, proposal to send, or meeting to schedule that the user must do AFTER this conversation ends.

CRITICAL FILTER — Do NOT flag any of the following as actionable items:
- Conversational back-and-forth or questions between speakers
- Instructions being CARRIED OUT during the conversation itself
- Clarifications, status checks, or confirmations of present state
- Hypotheticals, "what ifs", or things being merely discussed
- Future-tense pleasantries ("we should grab coffee sometime")
- Conditionals that get retracted in-conversation
- Delegations to other named people (those are tasks for them, not the wearer)
- Status queries ("did I X?", "have I done Y?")
- Stale conditionals (clock-time triggers already past with no confirmation)

DIRECT AGENT COMMANDS ARE INTENTS — when the wearer speaks an imperative aimed at the assistant ("search Wikipedia for X", "find me Y on Amazon"), capture it.

NEGATION PROPAGATES — if a sentence contains "don't", "hold off", "wait", "not yet", "skip", or "never mind" near a verb, suppress that verb and any chained downstream actions.

PARTIAL RETRACTION — when the wearer lists items then scratches some, emit only the survivors.

Default to FILTERING borderline conversational items. A false positive is much worse than missing a borderline item.

Return JSON:
{
  "reasoning": "brief analysis",
  "intents": [
    {
      "action_type": "snake_case_name",
      "confidence": 0.0-1.0,
      "importance": "critical|important|standard|low",
      "summary_for_user": "one clear sentence",
      "evidence_quote": "exact triggering quote",
      "parameters": {},
      "required_slots": ["..."],
      "missing_slots": ["..."],
      "clarification_question": ""
    }
  ]
}

Use confidence honestly: 0.9+ only when unambiguous. Anything conversational, hypothetical, or unclear gets <0.65 and will be filtered out.
If the conversation is purely casual or contains no real future actions: { "reasoning": "...", "intents": [] }"""


JUDGE_SYSTEM = """You judge whether a proactive intent-extraction system did the right thing.

You see:
- The conversation transcript
- The list of EXPECTED intents (ground truth)
- The list of NOISE items (system should NOT extract these)
- The list of EXTRACTED intents (what the system produced)
- An OPTIONAL expected_clarification

For EACH expected intent, decide if it has a clear match in extracted (ignoring phrasing).
For EACH noise item, decide if extracted contains anything corresponding (a false positive).
For EACH extracted intent that doesn't correspond to any expected OR noise item, count it as 'spurious'.
A clarifying QUESTION extracted is GOOD when expected_clarification is present.

Return JSON:
{
  "matched_expected": <int>,
  "missed_expected": <int>,
  "false_positives_on_noise": <int>,
  "spurious_extra": <int>,
  "clarification_asked": <bool>
}

Match by INTENT, not exact wording. Quantity matters.
Delegations to other people the system extracted as wearer-actions are false positives on noise.
"""


def load_dataset(limit: int, stratified: bool = True) -> list[dict]:
    rows: list[dict] = []
    with DATASET.open() as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    if not stratified:
        return rows[:limit]
    by_cat: dict[str, list[dict]] = {}
    for r in rows:
        c = r.get("category") or r.get("pattern_id") or "uncategorized"
        by_cat.setdefault(c, []).append(r)
    cats = sorted(by_cat.keys())
    picked: list[dict] = []
    idx = 0
    while len(picked) < limit:
        progressed = False
        for c in cats:
            if idx < len(by_cat[c]):
                picked.append(by_cat[c][idx])
                progressed = True
                if len(picked) >= limit:
                    break
        if not progressed:
            break
        idx += 1
    return picked[:limit]


async def call_gemini_extract(
    transcript: list[str], system: str, max_retries: int = 3
) -> list[str]:
    """Invoke Gemini 2.5 Flash with the given system prompt against the
    transcript. Returns the extracted summaries (the same field the judge
    reads from anticipy_intents.summary_for_user)."""
    user_msg = (
        "\n".join(transcript)
        + "\n\n---\nCurrent local time: 2026-05-08 14:00 (UTC)\n"
        "Recent actions: None yet.\n\n"
        "Extract ONLY genuine future actions the user needs to take. "
        "Skip conversational back-and-forth. Reason briefly, then output JSON."
    )
    body = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user_msg}]}],
        "generationConfig": {
            "temperature": 0.0,
            "maxOutputTokens": 4096,
            "responseMimeType": "application/json",
        },
    }
    last_err: str | None = None
    for _ in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=60) as c:
                r = await c.post(f"{GEMINI_URL}?key={GEMINI_KEY}", json=body)
                if r.status_code != 200:
                    last_err = f"extract {r.status_code}: {r.text[:200]}"
                    await asyncio.sleep(2)
                    continue
                txt = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                t = txt.strip()
                if t.startswith("```"):
                    t = t.split("\n", 1)[1] if "\n" in t else t
                    if t.endswith("```"):
                        t = t.rsplit("```", 1)[0]
                try:
                    parsed = json.loads(t)
                except json.JSONDecodeError:
                    s, e = txt.find("{"), txt.rfind("}")
                    if s >= 0 and e > s:
                        parsed = json.loads(txt[s : e + 1])
                    else:
                        raise
                intents = parsed.get("intents") or []
                # Filter low-confidence as the production route would
                summaries = [
                    i.get("summary_for_user") or ""
                    for i in intents
                    if float(i.get("confidence") or 0.0) >= 0.65
                ]
                return summaries
        except Exception as e:
            last_err = f"extract: {type(e).__name__}: {e}"
            await asyncio.sleep(2)
    print(f"    [extract ERROR] {last_err}", flush=True)
    return []


async def judge(
    transcript: list[str],
    expected: list[str],
    noise: list[str],
    extracted: list[str],
    clarif: str | None,
) -> dict:
    payload = {
        "transcript": "\n".join(transcript),
        "expected_intents": expected,
        "noise_should_NOT_act_on": noise,
        "extracted_intents": extracted,
    }
    if clarif:
        payload["expected_clarification"] = clarif
    body = {
        "system_instruction": {"parts": [{"text": JUDGE_SYSTEM}]},
        "contents": [{"role": "user", "parts": [{"text": json.dumps(payload, indent=2)}]}],
        "generationConfig": {
            "temperature": 0.0,
            "maxOutputTokens": 4096,
            "responseMimeType": "application/json",
        },
    }
    for _ in range(3):
        try:
            async with httpx.AsyncClient(timeout=60) as c:
                r = await c.post(f"{GEMINI_URL}?key={GEMINI_KEY}", json=body)
                if r.status_code != 200:
                    await asyncio.sleep(2)
                    continue
                txt = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                t = txt.strip()
                if t.startswith("```"):
                    t = t.split("\n", 1)[1] if "\n" in t else t
                    if t.endswith("```"):
                        t = t.rsplit("```", 1)[0]
                try:
                    return json.loads(t)
                except json.JSONDecodeError:
                    s, e = txt.find("{"), txt.rfind("}")
                    if s >= 0 and e > s:
                        return json.loads(txt[s : e + 1])
                    raise
        except Exception:
            await asyncio.sleep(2)
    return {
        "matched_expected": 0,
        "missed_expected": len(expected),
        "false_positives_on_noise": 0,
        "spurious_extra": 0,
        "error": "judge failed",
    }


def score(scenario: dict, judgment: dict) -> dict:
    expected_n = len(scenario["expected_intents"])
    matched = judgment.get("matched_expected", 0)
    missed = judgment.get("missed_expected", 0)
    fp = judgment.get("false_positives_on_noise", 0)
    spurious = judgment.get("spurious_extra", 0)
    pp = matched + fp + spurious
    precision = (matched / pp) if pp else (1.0 if expected_n == 0 else 0.0)
    recall = (matched / expected_n) if expected_n else (1.0 if (fp + spurious) == 0 else 0.0)
    passed = (missed == 0) and (fp == 0) and (spurious == 0)
    return {
        "expected_n": expected_n,
        "matched": matched,
        "missed": missed,
        "fp": fp,
        "spurious": spurious,
        "precision": precision,
        "recall": recall,
        "passed": passed,
    }


async def run_variant(
    scenarios: list[dict], system: str, label: str, concurrency: int = 6
) -> list[dict]:
    sem = asyncio.Semaphore(concurrency)
    out: list[dict | None] = [None] * len(scenarios)

    async def go(idx: int, sc: dict) -> None:
        async with sem:
            extracted = await call_gemini_extract(sc["transcript"], system)
            j = await judge(
                sc["transcript"],
                sc["expected_intents"],
                sc["noise_should_NOT_act_on"],
                extracted,
                sc.get("expected_clarification"),
            )
            s = score(sc, j)
            out[idx] = {
                "scenario": sc["name"],
                "category": sc.get("category") or sc.get("pattern_id") or "uncategorized",
                "extracted": extracted,
                "expected_n": s["expected_n"],
                "matched": s["matched"],
                "missed": s["missed"],
                "fp": s["fp"],
                "spurious": s["spurious"],
                "passed": s["passed"],
                "precision": s["precision"],
                "recall": s["recall"],
            }
            tag = "PASS" if s["passed"] else "FAIL"
            print(
                f"  [{label}] {sc['name'][:40]:<40} {tag} "
                f"m={s['matched']}/{s['expected_n']} "
                f"miss={s['missed']} fp={s['fp']} sp={s['spurious']}",
                flush=True,
            )

    await asyncio.gather(*[go(i, sc) for i, sc in enumerate(scenarios)])
    return [r for r in out if r is not None]


def summarize(label: str, results: list[dict]) -> dict:
    n = len(results) or 1
    passed = sum(1 for r in results if r["passed"])
    total_matched = sum(r["matched"] for r in results)
    total_expected = sum(r["expected_n"] for r in results)
    total_fp = sum(r["fp"] for r in results)
    total_spurious = sum(r["spurious"] for r in results)
    total_missed = sum(r["missed"] for r in results)
    avg_p = sum(r["precision"] for r in results) / n
    avg_r = sum(r["recall"] for r in results) / n
    summary = {
        "label": label,
        "n": n,
        "pass_rate": passed / n,
        "passed": passed,
        "missed": total_missed,
        "fp": total_fp,
        "spurious": total_spurious,
        "matched": total_matched,
        "expected_total": total_expected,
        "avg_precision": avg_p,
        "avg_recall": avg_r,
    }
    return summary


def print_summary(s: dict) -> None:
    print(
        f"\n  {s['label']:<14} pass={s['passed']}/{s['n']} ({100 * s['pass_rate']:.0f}%) "
        f"matched={s['matched']}/{s['expected_total']} miss={s['missed']} "
        f"fp={s['fp']} sp={s['spurious']} "
        f"P={s['avg_precision']:.2f} R={s['avg_recall']:.2f}"
    )


async def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("limit", type=int, nargs="?", default=30)
    p.add_argument("--baseline-only", action="store_true")
    p.add_argument("--few-shot-only", action="store_true")
    p.add_argument("--out", type=Path, default=Path("/tmp/calibration_result.json"))
    args = p.parse_args()

    scenarios = load_dataset(args.limit, stratified=True)
    print(f"Calibration: {len(scenarios)} stratified scenarios from {DATASET}", flush=True)

    if not FEW_SHOT_PATH.exists():
        print(
            f"ERROR: {FEW_SHOT_PATH} not found. Run build_few_shot_block.py first.",
            file=sys.stderr,
        )
        return 2
    few_shot_text = FEW_SHOT_PATH.read_text().strip()
    fs_system = SYSTEM_PROMPT + "\n\n" + few_shot_text
    print(f"  few-shot block: {len(few_shot_text)} chars", flush=True)

    t0 = time.time()
    a_summary: dict | None = None
    b_summary: dict | None = None
    a_results: list[dict] = []
    b_results: list[dict] = []

    if not args.few_shot_only:
        print("\n[A] BASELINE (no few-shot block)", flush=True)
        a_results = await run_variant(scenarios, SYSTEM_PROMPT, "A_base")
        a_summary = summarize("A_base", a_results)
        print_summary(a_summary)

    if not args.baseline_only:
        print("\n[B] WITH few-shot block", flush=True)
        b_results = await run_variant(scenarios, fs_system, "B_fs")
        b_summary = summarize("B_fs", b_results)
        print_summary(b_summary)

    print(f"\n  total elapsed: {time.time() - t0:.1f}s")

    if a_summary and b_summary:
        delta_pass = b_summary["pass_rate"] - a_summary["pass_rate"]
        delta_p = b_summary["avg_precision"] - a_summary["avg_precision"]
        delta_r = b_summary["avg_recall"] - a_summary["avg_recall"]
        print("\n  Lift (B - A):")
        print(
            f"    pass_rate:  {a_summary['pass_rate']*100:>5.1f}%  "
            f"-> {b_summary['pass_rate']*100:>5.1f}%   "
            f"({'+'  if delta_pass >= 0 else ''}{delta_pass*100:.1f} pts)"
        )
        print(
            f"    precision:  {a_summary['avg_precision']:.3f}  "
            f"-> {b_summary['avg_precision']:.3f}   "
            f"({'+'  if delta_p >= 0 else ''}{delta_p:.3f})"
        )
        print(
            f"    recall:     {a_summary['avg_recall']:.3f}  "
            f"-> {b_summary['avg_recall']:.3f}   "
            f"({'+'  if delta_r >= 0 else ''}{delta_r:.3f})"
        )

    args.out.write_text(
        json.dumps(
            {
                "n": len(scenarios),
                "baseline": a_summary,
                "few_shot": b_summary,
                "baseline_results": a_results,
                "few_shot_results": b_results,
            },
            indent=2,
            default=str,
        )
    )
    print(f"\n  detail: {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
