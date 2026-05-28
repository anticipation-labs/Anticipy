"""The generated test harness. Engine agnostic: it takes a decision
function and a list of categories, runs the fixed corpus, and produces a
direction aware honest scoreboard via the grader. With no categories it
runs clean and empty, which is the P0 resource gate.

Concurrency is bounded so the suite stays inside the declared 2 GB
resource envelope: the model calls are blocking I/O, a small thread pool
overlaps their latency without growing the working set.
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional

from app.anticipy import grader, platform_adapter, taxonomy

DecideFn = Callable[[dict], dict]

# Each decision is several blocking network calls (addressee, demand,
# hedge, intent, plus reparse/retry). The work is pure I/O wait, not
# CPU or memory, so high concurrency stays far inside the 2 GB envelope
# (a thread blocked on a socket costs a small stack, nothing else) and
# is the only thing that keeps the 590 case P5 suite tractable at the
# observed model latency. Verified bounded by the resource gate.
_MAX_WORKERS = 24


def run_category(category: str, decide_fn: DecideFn, n: Optional[int] = None) -> list[dict]:
    cases = taxonomy.generate(category, n)
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        fut_map = {pool.submit(decide_fn, case): case for case in cases}
        for fut in as_completed(fut_map):
            case = fut_map[fut]
            try:
                actual = fut.result()
            except Exception as e:
                actual = {"decision": "IGNORE", "error": f"decide raised: {e}"}
            results.append({"case": case, "actual": actual})
    return results


def run_suite(
    categories: list[str],
    decide_fn: Optional[DecideFn],
    phase_tag: str,
    run_adversarial: bool = False,
    counts: Optional[dict] = None,
) -> dict:
    """Run the given categories and write the honest scoreboard. With an
    empty category list this returns a clean empty scoreboard, which is
    the P0 gate that proves the harness executes within the resource cap.
    """
    started = time.time()
    scoreboard: dict = {
        "phase": phase_tag,
        "started_iso": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(started)),
        "categories": {},
        "all_pass": True,
        "empty_run": len(categories) == 0,
    }

    correct_pool: list[dict] = []
    for category in categories:
        spec = taxonomy.ALL_SPECS[category]
        n = (counts or {}).get(category)
        results = run_category(category, decide_fn, n) if decide_fn else []
        block = grader.grade_category(category, spec.grading, results) if results else {
            "category": category, "n": 0, "pass": False, "note": "no decide_fn",
        }
        scoreboard["categories"][category] = block
        if not block.get("pass"):
            scoreboard["all_pass"] = False
        # collect CORRECT graded items for the adversarial backstop, using
        # the real per category acceptance set (never a pseudo token)
        for r in results:
            d = r["actual"].get("decision")
            accept = taxonomy.accept_set(r["case"].get("category", ""), r["case"].get("variant"))
            if accept and d in accept:
                correct_pool.append(r)

    if run_adversarial and correct_pool:
        scoreboard["adversarial"] = grader.adversarial_check(correct_pool)
        if not scoreboard["adversarial"]["pass"]:
            scoreboard["all_pass"] = False

    scoreboard["elapsed_s"] = round(time.time() - started, 2)
    out_dir = platform_adapter.data_dir() / "scoreboards"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{phase_tag}.json").write_text(json.dumps(scoreboard, indent=2))
    return scoreboard


def format_scoreboard(scoreboard: dict) -> str:
    lines = [f"== SCOREBOARD {scoreboard['phase']} =="]
    if scoreboard.get("empty_run"):
        lines.append("empty run: harness executed with zero categories (resource gate)")
    for cat, b in scoreboard.get("categories", {}).items():
        if "exact_correct" in b:
            lines.append(
                f"{cat:26s} n={b['n']:4d} exact={b['exact_correct']:.3f} "
                f"over={b['over_action']:.3f} under={b['under_action']:.3f} "
                f"silentACT={b.get('silent_act', 0)} pass={b['pass']}"
            )
        elif "present_act_rate" in b:
            lines.append(
                f"{cat:26s} n={b['n']:4d} present_ACT={b['present_act_rate']:.3f} "
                f"absent_all_ASK={b['absent_all_ask']} pass={b['pass']}"
            )
        else:
            lines.append(f"{cat:26s} n={b.get('n', 0):4d} pass={b.get('pass')} {b.get('note', '')}")
    if "adversarial" in scoreboard:
        a = scoreboard["adversarial"]
        lines.append(f"adversarial: sampled={a['sampled']} flagged={a['flagged']} rate={a['flag_rate']:.3f} pass={a['pass']}")
    lines.append(f"ALL_PASS={scoreboard['all_pass']} elapsed={scoreboard.get('elapsed_s')}s")
    return "\n".join(lines)
