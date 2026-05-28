"""P11 final honest scoreboard. The build's last model spend.

Runs the full ENGINE_CORE corpus through the FINAL integrated engine
(the exact gate_p9 path: gate_p5 _ctx/_source + make_decide_fn, with
the JSON-retry wrapper and the first-party deepseek provider pin in
place) and prints the REAL per-category exact / over-action /
under-action / silent-ACT plus the adversarial flag rate, and the
measured per-decision cost from the ledger delta of THIS run alone.
No thresholds, no booleans: the honest numbers for the handoff doc.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent.parent
HERE = Path(__file__).resolve().parent
for p in (str(ENGINE), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

from gate_p5 import _ctx as p5_ctx  # noqa: E402
from gate_p5 import _source as p5_source  # noqa: E402
from app.anticipy import harness, platform_adapter  # noqa: E402
from app.anticipy.proactive_engine import make_decide_fn  # noqa: E402

ENGINE_CORE = [
    "EXPLICIT_COMMAND", "CLEAR_IMPLICIT", "DIRECT_USER_COMMAND",
    "BOSS_DIRECTED", "HEDGED_SOCIAL", "AMBIGUOUS_ADDRESSEE",
    "SARCASM_AND_NEGATION", "PURE_AMBIENT_NEGATIVE",
    "REFERENCE_RESOLUTION", "MULTI_SPEAKER_CROSSTALK",
    "NEVERMIND_RECONCILIATION",
]


def _ledger():
    p = platform_adapter.data_dir() / "model_calls.jsonl"
    n = 0
    cost = 0.0
    if p.exists():
        for ln in p.read_text().splitlines():
            try:
                d = json.loads(ln)
            except Exception:
                continue
            n += 1
            cost += float(d.get("cost_usd", 0) or 0)
    return n, cost


n0, c0 = _ledger()
t0 = time.time()
decide_fn = make_decide_fn(p5_ctx, p5_source)
sb = harness.run_suite(ENGINE_CORE, decide_fn, "p11-final-scoreboard",
                       run_adversarial=True)
elapsed = time.time() - t0
n1, c1 = _ledger()
b = sb["categories"]

total_cases = 0
print("CATEGORY                       n   exact   over   under  silentACT")
for cat in ENGINE_CORE:
    c = b.get(cat, {})
    nn = c.get("n", 0)
    total_cases += nn
    print(f"{cat:30s} {nn:3d}  {c.get('exact_correct',0.0):.3f}  "
          f"{c.get('over_action',0.0):.3f}  {c.get('under_action',0.0):.3f}  "
          f"{c.get('silent_act',0)}")
adv = sb.get("adversarial", {})
print(f"adversarial: flag_rate={adv.get('flag_rate','?')} pass={adv.get('pass','?')}")

calls = n1 - n0
cost = c1 - c0
decisions = total_cases
print(f"RUN: cases={total_cases} elapsed={elapsed:.0f}s model_calls={calls} "
      f"cost_usd={cost:.4f}")
if decisions:
    print(f"PER_DECISION: calls={calls/decisions:.2f} cost_usd={cost/decisions:.6f}")
print("FINAL_SCOREBOARD_DONE")
