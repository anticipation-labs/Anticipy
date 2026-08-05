"""Does asking "which line does this continue?" beat the timer on Omar's own day?

Ground truth: his 244 real logged lines, cut into continuous stretches wherever
he went quiet for more than 10 minutes. That criterion is deliberately NOT one
either arm uses — the timer arm keys on 45s and the link arm reads no clock at
all — so neither is being scored against its own rule.

Arm A, TIMER: production's rule, brain/segmenter.py:95 — a gap under
CONTINUE_S starts nothing new, a gap at or over it does. This is what is
running on his phone today.

Arm B, LINKS: the real triage call, live model, with the previous lines shown
numbered, exactly as brain/worker.py now does it. Conversations come out of
brain/links.py as connected components.

Reported the way the disentanglement literature reports it, so the numbers are
comparable to published work rather than invented here: how many conversations
each arm produces against the true count, how many true conversations survive
whole (exact match), and 1-to-1 overlap.

Run:  OPENROUTER_API_KEY=... ANTICIPY_MODEL=... python3 proof/score_links.py
      --limit N     score only the first N lines (cheap smoke run)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain.links import conversations            # noqa: E402
from brain.llm import LLM                        # noqa: E402
from brain.orchestrator import Brain             # noqa: E402
from brain.segmenter import CONTINUE_S           # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TRUE_GAP_S = 600          # the ground-truth criterion; used by neither arm
WINDOW = 40               # candidates shown, matching worker.LINK_WINDOW


def ts(s: str) -> float:
    return datetime.fromisoformat(
        s.replace(" ", "T").replace("Z", "+00:00")).timestamp()


def load_rows() -> list[dict]:
    rows = []
    for name in ("corpus_dev.json", "corpus_heldout.json"):
        rows += json.load(open(os.path.join(ROOT, "overnight", name)))
    rows.sort(key=lambda r: ts(r["created"]))
    return rows


def truth(rows) -> list[list[str]]:
    out, cur = [], [rows[0]]
    for prev, r in zip(rows, rows[1:]):
        if ts(r["created"]) - ts(prev["created"]) > TRUE_GAP_S:
            out.append(cur)
            cur = [r]
        else:
            cur.append(r)
    out.append(cur)
    return [[r["id"] for r in s] for s in out]


def timer_arm(rows) -> list[list[str]]:
    """Production's rule, applied to the same lines."""
    out, cur = [], [rows[0]]
    for prev, r in zip(rows, rows[1:]):
        if ts(r["created"]) - ts(prev["created"]) >= CONTINUE_S:
            out.append(cur)
            cur = [r]
        else:
            cur.append(r)
    out.append(cur)
    return [[r["id"] for r in s] for s in out]


def link_arm(rows, brain, log) -> list[list[str]]:
    """Ask the real triage call, one line at a time, in speech order."""
    lines = []
    asked = errors = 0
    for n, r in enumerate(rows):
        cands = [c for c in rows[max(0, n - WINDOW):n]]
        parent = r["id"]                       # self = starts something new
        if cands:
            shown = "\n".join(
                f"[{i}] {c['text'].strip()}" for i, c in enumerate(cands, 1))
            prompt = (f"{r['text']}\n(Recent lines, oldest first — say in "
                      f'"continues" which ONE this line carries on from, or 0 '
                      f"if it starts something new:\n{shown})")
            try:
                d = brain.triage(prompt, candidates=len(cands))
                asked += 1
                idx = d.continues
                if idx is not None and 1 <= idx <= len(cands):
                    parent = cands[idx - 1]["id"]
            except Exception as e:              # noqa: BLE001
                errors += 1
                print(f"  ! line {n}: {e}", file=sys.stderr)
        lines.append({"id": r["id"], "parent": parent,
                      "spoken_at": ts(r["created"])})
        if (n + 1) % 25 == 0:
            print(f"  {n+1}/{len(rows)} asked={asked} errors={errors}",
                  file=sys.stderr)
    log["asked"], log["errors"] = asked, errors
    log["links"] = {ln["id"]: ln["parent"] for ln in lines}
    return conversations(lines)


def score(pred: list[list[str]], gold: list[list[str]]) -> dict:
    P = [set(g) for g in pred]
    G = [set(g) for g in gold]
    n = sum(len(g) for g in G)
    exact = sum(1 for g in G if g in P)
    # 1-to-1 overlap: greedily pair each true conversation with its best
    # predicted match, each used once, and count the agreeing lines.
    used, overlap = set(), 0
    for g in sorted(G, key=len, reverse=True):
        best, bi = 0, None
        for i, p in enumerate(P):
            if i in used:
                continue
            hit = len(g & p)
            if hit > best:
                best, bi = hit, i
        if bi is not None:
            used.add(bi)
            overlap += best
    # How many true conversations got torn into more than one piece.
    split = 0
    for g in G:
        touching = sum(1 for p in P if g & p)
        if touching > 1:
            split += 1
    return {"conversations": len(P), "exact_match": exact,
            "one_to_one": round(overlap / n, 3) if n else 0.0,
            "true_conversations_split": split}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default=os.path.join(HERE, "score_links.json"))
    args = ap.parse_args()

    rows = load_rows()
    if args.limit:
        rows = rows[:args.limit]
    gold = truth(rows)

    llm = LLM()
    if not llm.live:
        print("need OPENROUTER_API_KEY")
        return 1
    brain = Brain(llm=llm)

    print(f"lines: {len(rows)}   true conversations: {len(gold)}")
    print(f"model: {os.environ.get('ANTICIPY_MODEL', '(default)')}\n")

    a = score(timer_arm(rows), gold)
    print(f"TIMER (production, {CONTINUE_S}s): {a}")

    log: dict = {}
    t0 = time.time()
    b = score(link_arm(rows, brain, log), gold)
    print(f"LINKS (live model):                 {b}")
    print(f"\nasked {log['asked']} times, {log['errors']} errors, "
          f"{time.time()-t0:.0f}s")

    json.dump({"lines": len(rows), "true_conversations": len(gold),
               "timer": a, "links": b,
               "model": os.environ.get("ANTICIPY_MODEL", ""),
               "asked": log["asked"], "errors": log["errors"],
               "link_map": log["links"]},
              open(args.out, "w"), indent=1)
    print(f"\nwrote {args.out}")

    better = (b["true_conversations_split"] < a["true_conversations_split"]
              and b["one_to_one"] >= a["one_to_one"])
    print("\nVERDICT:", "LINKS WIN" if better else "NOT BETTER — park it")
    return 0


if __name__ == "__main__":
    sys.exit(main())
