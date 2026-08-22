#!/usr/bin/env python3
"""Which model should triage run on? Accuracy and cost, on the same lines.

    python proof/ambient/model_bakeoff.py --sample 150
    python proof/ambient/model_bakeoff.py --models google/gemini-2.5-flash-lite,x-ai/grok-4-fast
    python proof/ambient/model_bakeoff.py --sample 300 --json out.json

WHY THIS EXISTS. Triage is 57% of what an ambient decision costs, and on
2026-08-21 it was running on google/gemini-3.7-flash, where OpenRouter reports
`Reasoning is mandatory for this endpoint and cannot be disabled` — so 133 of
every 182 output tokens were hidden thinking, billed at the output rate. The
Gemini-direct path in brain/llm.py has always set thinkingBudget to 0, with a
comment explaining exactly why; the OpenRouter path never got the same
treatment, because nothing measured it.

Swapping the model is the biggest lever available, and it is also the most
dangerous thing to do on a hunch: a triage model that is 5x cheaper and quietly
worse at hearing "we have not booked anything for half term" is not a saving,
it is the product failing silently and cheaply. So this measures both, on the
same corpus lines, against the same gold labels.

WHAT IT MEASURES, and it is deliberately NOT the full pipeline. This calls
triage and nothing else: no worker, no PocketBase, no memory, no segmentation.
That isolates the one decision the model is responsible for, runs in minutes
instead of hours, and costs a few cents. The winner still has to be confirmed
end to end afterwards — proof/ambient/fanout.py is what does that.

THE TWO ERRORS ARE NOT EQUAL, and the scoring says so out loud:

  false ping  gold "ignore" and the model wants to act or ask. It reached the
              owner over nothing. Trust does not come back.
  miss        gold "act"/"ask" and the model saw no errand at all — no
              decision AND no goal. One lost convenience.

A goal WITHOUT an act verdict is not a miss: brain/anticipy_core.py queues a
non-consequential errand unheld and stamps the row "ignore", which the owner
experiences as quiet work. proof/ambient/score.py calls that the `quiet` lane
and accepts it for a gold "act". This file uses the same rule so the two
scorecards cannot disagree.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import random
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)

from brain.orchestrator import TRIAGE_SYSTEM  # noqa: E402  the prompt under test
from brain.llm import now_line, where_line     # noqa: E402  the same grounding

URL = "https://openrouter.ai/api/v1/chat/completions"

# Candidates worth the call. Every one of these has to answer with parseable
# JSON on the first try to be usable at all — a model that needs the retry path
# costs double and is disqualified on cost before accuracy is even considered.
DEFAULT_MODELS = [
    "google/gemini-3.7-flash",          # incumbent, mandatory reasoning
    "google/gemini-2.5-flash",
    "google/gemini-2.5-flash-lite",
    "openai/gpt-4.1-mini",
    "openai/gpt-4o-mini",
    "deepseek/deepseek-chat",
    "x-ai/grok-4-fast",
    "qwen/qwen3-235b-a22b",
]


def env_value(name: str) -> str:
    for line in open(os.path.join(REPO, ".env.local")):
        if line.startswith(name + "="):
            return line.split("=", 1)[1].strip().strip('"\'')
    return ""


def extract_json(text: str):
    """The same tolerance orchestrator._extract_json has: models fence things."""
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.S)
    start = t.find("{")
    if start < 0:
        raise ValueError("no object")
    depth = 0
    for i, ch in enumerate(t[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(t[start:i + 1])
    raise ValueError("unbalanced")


def lane_for(decision: str, goal) -> str:
    """What the owner would experience, by proof/ambient/score.py's rule."""
    goal = (goal or "")
    goal = goal.strip() if isinstance(goal, str) else ""
    if decision == "ask":
        return "spoke"
    if decision == "act":
        return "desk"
    if goal:
        return "quiet"
    return "silent"


ACCEPTABLE = {
    "ignore": {"silent", "quiet"},
    "act": {"quiet", "desk", "spoke"},
    "ask": {"spoke"},
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=os.path.join(HERE, "corpus.big.json"))
    ap.add_argument("--models", default=",".join(DEFAULT_MODELS))
    ap.add_argument("--sample", type=int, default=150)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    key = os.environ.get("OPENROUTER_API_KEY") or env_value("OPENROUTER_API_KEY")
    if not key:
        raise SystemExit("no OPENROUTER_API_KEY")

    corpus = json.load(open(args.corpus))
    # Stratified on the gold label, because the two error rates are computed
    # over different denominators and a random draw would under-sample `ask`
    # (73 of 1000) into meaninglessness.
    random.seed(args.seed)
    by_gold = collections.defaultdict(list)
    for c in corpus:
        by_gold[c["gold"]].append(c)
    share = {"ignore": 0.40, "act": 0.45, "ask": 0.15}
    sample = []
    for gold, frac in share.items():
        want = min(int(args.sample * frac), len(by_gold[gold]))
        sample += random.sample(by_gold[gold], want)
    random.shuffle(sample)
    print(f"{len(sample)} lines: " + ", ".join(
        f"{k}={sum(1 for c in sample if c['gold'] == k)}" for k in ("ignore", "act", "ask")))

    # The same grounding llm.py adds, so the prompt under test is the real one.
    where = where_line(None)
    system = f"{now_line(None)}\n\n{TRIAGE_SYSTEM}"
    if where:
        system = f"{where}\n{system}"

    hdr = {"Authorization": f"Bearer {key}", "Content-Type": "application/json",
           "HTTP-Referer": "https://anticipy.ai", "X-Title": "Anticipy"}
    lock = threading.Lock()
    results = {}

    def one(model, item):
        body = {"model": model, "temperature": 0.0, "seed": 11,
                "usage": {"include": True},
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": item["text"]}]}
        for attempt in range(3):
            try:
                r = httpx.post(URL, headers=hdr, json=body, timeout=120)
                d = r.json()
                if "choices" not in d:
                    msg = str((d.get("error") or {}).get("message"))[:80]
                    if attempt == 2:
                        return {"id": item["id"], "error": msg}
                    time.sleep(2 + attempt * 3)
                    continue
                u = d.get("usage") or {}
                txt = d["choices"][0]["message"]["content"] or ""
                try:
                    raw = extract_json(txt)
                    parsed = True
                except Exception:
                    raw, parsed = {}, False
                det = u.get("completion_tokens_details") or {}
                return {
                    "id": item["id"], "gold": item["gold"],
                    "decision": raw.get("decision", "ignore"),
                    "goal": raw.get("goal"),
                    "parsed": parsed,
                    "cost": u.get("cost") or 0.0,
                    "in": u.get("prompt_tokens") or 0,
                    "out": u.get("completion_tokens") or 0,
                    "think": det.get("reasoning_tokens") or 0,
                }
            except Exception as e:
                if attempt == 2:
                    return {"id": item["id"], "error": str(e)[:80]}
                time.sleep(2 + attempt * 3)
        return {"id": item["id"], "error": "gave up"}

    models = [m for m in args.models.split(",") if m.strip()]
    for model in models:
        t0 = time.time()
        rows = []
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            for row in pool.map(lambda it: one(model, it), sample):
                rows.append(row)
        ok = [r for r in rows if "error" not in r]
        errs = len(rows) - len(ok)
        if not ok:
            print(f"\n{model}: every call failed ({rows[0].get('error')})")
            results[model] = {"unusable": rows[0].get("error")}
            continue
        gold_of = {c["id"]: c for c in sample}
        fp = miss = 0
        n_ign = n_err = 0
        right = 0
        for r in ok:
            gold = gold_of[r["id"]]["gold"]
            lane = lane_for(r["decision"], r["goal"])
            hit = lane in ACCEPTABLE[gold]
            right += hit
            if gold == "ignore":
                n_ign += 1
                if lane in ("desk", "spoke"):
                    fp += 1
            else:
                n_err += 1
                if lane == "silent":
                    miss += 1
        cost = sum(r["cost"] for r in ok)
        results[model] = {
            "n": len(ok), "errors": errs,
            "unparsed": sum(1 for r in ok if not r["parsed"]),
            "false_ping_pct": round(100 * fp / max(n_ign, 1), 1),
            "miss_pct": round(100 * miss / max(n_err, 1), 1),
            "accuracy_pct": round(100 * right / len(ok), 1),
            "cost_per_line": round(cost / len(ok), 6),
            "in_tok": round(sum(r["in"] for r in ok) / len(ok)),
            "out_tok": round(sum(r["out"] for r in ok) / len(ok)),
            "think_tok": round(sum(r["think"] for r in ok) / len(ok)),
            "secs": round(time.time() - t0),
        }
        r = results[model]
        print(f"\n{model}")
        print(f"   accuracy {r['accuracy_pct']:5.1f}%   false pings {r['false_ping_pct']:5.1f}%"
              f"   misses {r['miss_pct']:5.1f}%")
        print(f"   {r['cost_per_line']:.6f}/line   in {r['in_tok']} out {r['out_tok']}"
              f" (think {r['think_tok']})   {r['secs']}s   unparsed {r['unparsed']}  errors {r['errors']}")

    usable = {m: r for m, r in results.items() if "unusable" not in r}
    if usable:
        base = results.get("google/gemini-3.7-flash", {})
        print("\n" + "=" * 78)
        print(f"{'model':34}{'acc':>7}{'fping':>7}{'miss':>7}{'$/line':>10}{'vs now':>9}")
        for m, r in sorted(usable.items(), key=lambda kv: kv[1]["cost_per_line"]):
            ratio = (base.get("cost_per_line", 0) / r["cost_per_line"]) if r["cost_per_line"] else 0
            print(f"{m:34}{r['accuracy_pct']:6.1f}%{r['false_ping_pct']:6.1f}%"
                  f"{r['miss_pct']:6.1f}%{r['cost_per_line']:10.6f}{ratio:8.1f}x")
    if args.json:
        json.dump(results, open(args.json, "w"), indent=1)
        print(f"\nwritten to {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
