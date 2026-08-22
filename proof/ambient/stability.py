#!/usr/bin/env python3
"""Across N rounds of the same corpus, which lines are SETTLED and which flip?

    python proof/ambient/stability.py proof/ambient/rounds/k*/results.jsonl

A single pass cannot tell a capability boundary from a coin flip, and the two
need completely different responses. A line that misses every time is a gap in
what the brain can hear — worth changing a prompt over. A line that lands four
times out of eight is variance, and "fixing" it by tuning against one run is
how a prompt gets overfitted to noise.

Measured 2026-08-21 before this existed: fourteen lines that missed in one
round were re-pushed and five were caught the second time. That is a third of
an apparent failure list that was never a failure list.

Output is per-line: how often each utterance landed in an acceptable lane, so
the corpus splits into ALWAYS RIGHT / ALWAYS WRONG / UNSTABLE. Only the middle
group is a defect list. The last is a variance budget.
"""
from __future__ import annotations

import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

ACCEPTABLE = {
    "ignore": {"silent", "quiet"},
    "act": {"quiet", "desk", "spoke"},
    "ask": {"spoke"},
}


def own_said(r) -> list:
    said = r.get("said") or []
    said = [{"text": s} if isinstance(s, str) else s for s in said]
    if (r.get("decision") or "") in ("act", "ask"):
        return said
    goal = (r.get("goal") or "").strip().lower()
    if not goal:
        return []
    return [s for s in said if (s.get("goal") or "").strip().lower() == goal]


def lane_of(r) -> str:
    """Identical to proof/ambient/score.py:lane_of — the two must not drift."""
    decision = r.get("decision") or ""
    goal = (r.get("goal") or "").strip()
    if own_said(r) or decision == "ask":
        return "spoke"
    if decision == "act":
        return "desk"
    if goal or (r.get("jobs") or []):
        return "quiet"
    return "silent"


def main() -> int:
    paths = sys.argv[1:]
    if not paths:
        print(__doc__)
        return 2
    corpus = {c["id"]: c for c in
              json.load(open(os.path.join(HERE, "corpus.big.json")))}

    seen = collections.defaultdict(list)   # id -> [True/False per round]
    for path in paths:
        for line in open(path):
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            c = corpus.get(r.get("id"))
            if not c or not (r.get("decision") or "").strip():
                continue
            seen[r["id"]].append(lane_of(r) in ACCEPTABLE[c["gold"]])

    repeated = {k: v for k, v in seen.items() if len(v) >= 2}
    always_right = [k for k, v in repeated.items() if all(v)]
    always_wrong = [k for k, v in repeated.items() if not any(v)]
    unstable = {k: v for k, v in repeated.items() if any(v) and not all(v)}

    n = len(repeated)
    print(f"{len(paths)} rounds, {sum(len(v) for v in seen.values())} decisions, "
          f"{n} utterances answered at least twice\n")
    print(f"  ALWAYS RIGHT  {len(always_right):5}  ({100*len(always_right)/n:.1f}%)")
    print(f"  ALWAYS WRONG  {len(always_wrong):5}  ({100*len(always_wrong)/n:.1f}%)"
          f"   <- the real defect list")
    print(f"  UNSTABLE      {len(unstable):5}  ({100*len(unstable)/n:.1f}%)"
          f"   <- variance, not a bug to chase")

    # A settled failure is worth reading; a coin flip is not.
    by_reg = collections.Counter(corpus[k]["register"] for k in always_wrong)
    by_fam = collections.Counter(corpus[k].get("family") or "-" for k in always_wrong)
    by_gold = collections.Counter(corpus[k]["gold"] for k in always_wrong)
    print(f"\nALWAYS WRONG by gold : {dict(by_gold)}")
    print(f"ALWAYS WRONG by register:")
    for reg, cnt in by_reg.most_common():
        total = sum(1 for k in repeated if corpus[k]["register"] == reg)
        print(f"   {reg:16} {cnt:4} of {total:4}  ({100*cnt/max(total,1):.0f}%)")
    print(f"\nALWAYS WRONG top families:")
    for fam, cnt in by_fam.most_common(8):
        print(f"   {fam:20} {cnt}")

    if unstable:
        rate = sum(sum(v) / len(v) for v in unstable.values()) / len(unstable)
        print(f"\nunstable lines land correctly {100*rate:.0f}% of the time on average")
        print("first 10, with their per-round record:")
        for k in list(unstable)[:10]:
            hits = "".join("." if x else "x" for x in unstable[k])
            print(f"   {k:10} {hits:10} {corpus[k]['text'][:58]}")

    out = os.path.join(HERE, "stability.json")
    json.dump({"always_right": sorted(always_right),
               "always_wrong": sorted(always_wrong),
               "unstable": {k: v for k, v in unstable.items()}},
              open(out, "w"), indent=1)
    print(f"\nwritten to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
