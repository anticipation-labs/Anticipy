"""Track B bonus — grade the EXISTING SHIPPED decider (the real triage + harm-line) on the SAME key.

This is NOT unverified code: it runs the actual production decision path
(`proactive/triage.py` + `proactive/harm.py`) deterministically (zero model calls) and scores it
with the SAME self-proven scorer + the SAME human key the Track B decider was graded on. It answers
the question that matters most: does the engine that exists today pass the cardinal gate, or does it
act on vents/wishes? Mapping (the real loop): triage drops it -> SILENT; else harm-line detrimental
-> ASK, reversible -> ACT.

Run: PYTHONPATH=engine:overnight/track_b python overnight/track_b/score_existing_engine.py
"""
from __future__ import annotations

import json

from anticipy_engine.proactive.harm import HarmLine
from anticipy_engine.proactive.triage import Triage
from score_decider import _metrics   # reuse the SELF-PROVEN scorer math (separate from any builder)


def existing_decide(line: str) -> str:
    """The real shipped path, mapped to ACT/ASK/SILENT. Deterministic; no model."""
    if not Triage(gateway=None).actionable(line):
        return "SILENT"                       # the bouncer dropped it
    v = HarmLine().assess(line, ctx={})
    return "ASK" if v.detrimental else "ACT"   # harm-line: binding -> ask, reversible -> act


def main():
    key = [json.loads(l) for l in open("overnight/track_b/answer_key.jsonl") if l.strip()]
    rows = [{**r, "pred": existing_decide(r["line"])} for r in key]
    pairs = [(r["label"], r["pred"]) for r in rows]
    m = _metrics(pairs)
    print("=== EXISTING engine (triage + harm-line), graded on the SAME 60-line key ===")
    print(f"  caught real commitments (ACT/ASK recall): {m['caught_commitments']}")
    print(f"  stayed silent on noise: recall {m['silent_recall']} | precision {m['silent_precision']}")
    print(f"  CARDINAL false-action (SILENT->ACT): {m['FALSE_ACTION_cardinal']}   [hard gate ~0]")
    print(f"  over-ask on SILENT: {m['over_ask_on_silent']}")
    fa = [r for r in rows if r["label"] == "SILENT" and r["pred"] == "ACT"]
    oa = [r for r in rows if r["label"] == "SILENT" and r["pred"] == "ASK"]
    print(f"\n  FALSE-ACTIONS on vents/wishes ({len(fa)}) — the catastrophic ones:")
    for r in fa:
        print(f"    SILENT->ACT  {r['line']!r}")
    print(f"\n  over-asks on noise ({len(oa)}):")
    for r in oa:
        print(f"    SILENT->ASK  {r['line']!r}")
    open("overnight/track_b/results_existing.json", "w").write(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
