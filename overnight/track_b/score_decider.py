"""Track B — the SCORER (the boss). Reads the human key, runs the decider, reports honest numbers.

Three numbers, kept separate (per the directive):
  1. caught the real promises   = recall on true ACT/ASK (did it avoid silencing a real commitment)
  2. stayed silent on the noise = SILENT precision AND recall (when it's quiet, is it right; and did
     it stay quiet on the vents)
  3. THE CARDINAL ONE           = false-action count = (true SILENT predicted ACT). HARD GATE ~0.
Reported on TRAIN and HELD-OUT separately. LAW #4: `self_prove()` feeds known predictions against a
known mini-key and checks the math catches a planted false-action before any real score is trusted.
LAW #3: the decider does not import this; this reads the key the decider never sees.

Run: PYTHONPATH=engine:overnight/track_b python overnight/track_b/score_decider.py
"""
from __future__ import annotations

import asyncio
import json
import os

from anticipy_engine.core.env import load_local_env

load_local_env()

import decider as D
from anticipy_engine.core.gateway import PROVIDER_OPENROUTER, ModelGateway


def _metrics(pairs):
    """pairs = list of (true, pred). Return the three-number readout."""
    commit = [(t, p) for t, p in pairs if t in ("ACT", "ASK")]
    caught = sum(1 for t, p in commit if p in ("ACT", "ASK"))
    exact_commit = sum(1 for t, p in commit if t == p)
    sil_true = [(t, p) for t, p in pairs if t == "SILENT"]
    sil_pred = [(t, p) for t, p in pairs if p == "SILENT"]
    sil_recall = sum(1 for t, p in sil_true if p == "SILENT")
    sil_prec = sum(1 for t, p in sil_pred if t == "SILENT")
    false_action = sum(1 for t, p in pairs if t == "SILENT" and p == "ACT")     # CARDINAL
    over_ask = sum(1 for t, p in pairs if t == "SILENT" and p == "ASK")          # annoying, not fatal
    return {
        "n": len(pairs),
        "caught_commitments": f"{caught}/{len(commit)}" + (f" = {caught/len(commit):.2f}" if commit else ""),
        "exact_on_commitments": f"{exact_commit}/{len(commit)}" if commit else "0/0",
        "silent_recall": f"{sil_recall}/{len(sil_true)}" + (f" = {sil_recall/len(sil_true):.2f}" if sil_true else ""),
        "silent_precision": f"{sil_prec}/{len(sil_pred)}" + (f" = {sil_prec/len(sil_pred):.2f}" if sil_pred else ""),
        "FALSE_ACTION_cardinal": false_action,
        "over_ask_on_silent": over_ask,
    }


def self_prove() -> bool:
    """Plant known predictions against a known mini-key; the math MUST report 1 false-action."""
    mini = [("ACT", "ACT"),       # caught
            ("ACT", "SILENT"),    # missed a promise
            ("ASK", "ASK"),       # caught
            ("SILENT", "SILENT"), # correct quiet
            ("SILENT", "ACT"),    # <-- THE planted false-action (cardinal); must be counted
            ("SILENT", "ASK")]    # over-ask
    m = _metrics(mini)
    ok = (m["FALSE_ACTION_cardinal"] == 1 and m["over_ask_on_silent"] == 1
          and m["caught_commitments"].startswith("2/3"))
    print(f"  self-prove metrics: false_action={m['FALSE_ACTION_cardinal']} (must be 1), "
          f"over_ask={m['over_ask_on_silent']} (must be 1), caught={m['caught_commitments']}")
    print(f"  SCORER {'TRUSTWORTHY (counts a planted false-action)' if ok else 'BROKEN'}")
    return ok


async def main():
    print("=== Track B: self-prove the scorer before trusting any number (LAW #4) ===")
    if not self_prove():
        print("SCORER BROKEN -> refusing to score."); return

    key = [json.loads(l) for l in open("overnight/track_b/answer_key.jsonl") if l.strip()]
    gw = ModelGateway(provider=PROVIDER_OPENROUTER,
                      cheap_model=os.environ.get("ANTICIPY_MODEL_CHEAP", "google/gemini-3.1-flash-lite"),
                      smart_model=os.environ.get("ANTICIPY_MODEL_SMART", "google/gemini-3.5-flash"))
    print(f"\n=== running the decider over {len(key)} lines (cheap model, temp 0) ===")
    rows = []
    for r in key:
        pred = await D.decide(r["line"], gw=gw)
        rows.append({**r, "pred": pred})
        if r["label"] == "SILENT" and pred == "ACT":   # surface every cardinal violation immediately
            print(f"  !! FALSE-ACTION on SILENT: {r['line']!r} -> {pred}")

    for split in ("train", "heldout", "ALL"):
        sub = rows if split == "ALL" else [r for r in rows if r["split"] == split]
        pairs = [(r["label"], r["pred"]) for r in sub]
        m = _metrics(pairs)
        print(f"\n--- {split.upper()} (n={m['n']}) ---")
        print(f"  caught real commitments (ACT/ASK recall): {m['caught_commitments']}  "
              f"(exact: {m['exact_on_commitments']})")
        print(f"  stayed silent on noise: recall {m['silent_recall']} | precision {m['silent_precision']}")
        print(f"  CARDINAL false-action (SILENT->ACT): {m['FALSE_ACTION_cardinal']}   [hard gate ~0]")
        print(f"  over-ask on SILENT (annoying, not fatal): {m['over_ask_on_silent']}")

    # full miss/violation ledger for the report
    miss = [r for r in rows if (r["label"] in ("ACT", "ASK") and r["pred"] == "SILENT")
            or (r["label"] == "SILENT" and r["pred"] in ("ACT", "ASK"))]
    print(f"\n=== disagreements ({len(miss)}) ===")
    for r in miss:
        tag = "FALSE-ACTION" if (r["label"] == "SILENT" and r["pred"] == "ACT") else \
              ("over-ask" if r["label"] == "SILENT" else "missed")
        nl = " [nearline]" if r["nearline"] else ""
        print(f"  {tag:<12} true={r['label']:<6} pred={r['pred']:<6} {r['line']!r}{nl}")
    open("overnight/track_b/results.json", "w").write(json.dumps(rows, indent=2))
    print("\n  -> overnight/track_b/results.json")


if __name__ == "__main__":
    asyncio.run(main())
