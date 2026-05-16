"""Real verification of the P9 CLEAR fix. NOT a smoke test.

Runs the REAL CLEAR_IMPLICIT corpus through the REAL integrated engine
(make_decide_fn over the preserved cascade) with the REAL OpenRouter
model, via the exact gate_p9 / gate_p5 path. Also runs HEDGED_SOCIAL to
prove the JSON-retry did not turn safe non-acts into over-action.
Prints actual exact_correct / over_action and the residual cascade JSON
parse-failure count so the result is honest and independently checkable.
"""
from __future__ import annotations

import io
import logging
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent.parent
HERE = Path(__file__).resolve().parent
for p in (str(ENGINE), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

# capture cascade parse-failure warnings (real residual after the fix)
_buf = io.StringIO()
_h = logging.StreamHandler(_buf)
_h.setLevel(logging.WARNING)
for nm in ("app.proactive.demand_detection", "app.proactive.intent_extraction"):
    lg = logging.getLogger(nm)
    lg.setLevel(logging.WARNING)
    lg.addHandler(_h)

from gate_p5 import _ctx as p5_ctx  # noqa: E402
from gate_p5 import _source as p5_source  # noqa: E402

from app.anticipy import harness  # noqa: E402
from app.anticipy.proactive_engine import make_decide_fn  # noqa: E402

decide_fn = make_decide_fn(p5_ctx, p5_source)
cats = ["CLEAR_IMPLICIT", "HEDGED_SOCIAL"]
sb = harness.run_suite(cats, decide_fn, "p9-clear-realcheck", run_adversarial=False)
b = sb["categories"]

clear_ex = b.get("CLEAR_IMPLICIT", {}).get("exact_correct", 0.0)
clear_n = b.get("CLEAR_IMPLICIT", {}).get("n", 0)
hedged_ov = b.get("HEDGED_SOCIAL", {}).get("over_action", 1.0)
hedged_n = b.get("HEDGED_SOCIAL", {}).get("n", 0)

logs = _buf.getvalue()
n_parse_fail = logs.count("JSON parse failed")

print(f"CLEAR_IMPLICIT  n={clear_n}  exact_correct={clear_ex:.4f}  "
      f"(gate needs >= 0.92)  -> {'PASS' if clear_ex >= 0.92 else 'FAIL'}")
print(f"HEDGED_SOCIAL   n={hedged_n}  over_action={hedged_ov:.4f}  "
      f"(gate needs <= 0.03) -> {'PASS' if hedged_ov <= 0.03 else 'FAIL'}")
print(f"residual cascade JSON parse failures across both categories: {n_parse_fail}")
ok = clear_ex >= 0.92 and hedged_ov <= 0.03
print("REAL_CLEAR_CHECK", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
