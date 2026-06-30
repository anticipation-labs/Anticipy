#!/usr/bin/env python3
"""Browser-agent benchmark harness — the "measure from day one" scorecard.

Runs a task set through the LIVE engine (/agent/run with the read-back judge) and aggregates the
Year-0 metrics we committed to tracking: success%, $/task, steps, vision_pct (DOM-first health),
frontier_pct (% of model calls on the SMART model), and human-intervention rate.

This is the SAME general agent for every task — no per-site code. Point it at a JSON task file or
use the built-in default set (two brand-new scrape sites + Wikipedia) for the generic proof.

  engine/.venv/bin/python engine/scripts/browser_bench.py [tasks.json] [--out scorecard.json]

Each task: {"task": "...", "start_url": "https://...", "max_steps": 14}
The engine must be running on 127.0.0.1:8787 with the extension connected.
"""
import json
import sys
import time
import urllib.request

ENGINE = "http://127.0.0.1:8787"

# Default set: deliberately spans THREE brand-new sites the agent has never been told about, with
# different shapes (quotes list, book catalogue + price, encyclopedia article) — proof of generality.
DEFAULT_TASKS = [
    {"task": "What is the very first quote shown on this page, and who is it attributed to?",
     "start_url": "https://quotes.toscrape.com/", "max_steps": 8},
    {"task": "Go to the 'humor' tag page, then tell me the author of the first quote listed there.",
     "start_url": "https://quotes.toscrape.com/", "max_steps": 14},
    {"task": "What is the title and price of the first book shown on this page?",
     "start_url": "https://books.toscrape.com/", "max_steps": 10},
    {"task": "Open the 'Travel' category and tell me how many books are listed in it.",
     "start_url": "https://books.toscrape.com/", "max_steps": 14},
    {"task": "What is this article's subject, and what was the first web browser, who created it, and in what year?",
     "start_url": "https://en.wikipedia.org/wiki/Web_browser", "max_steps": 10},
]


def reset_state() -> bool:
    """Clean-slate the browser (cookies + per-origin storage) between tasks so a prior task's saved
    state (cart, login, form) cannot contaminate the next — honest, deterministic cold-start."""
    try:
        req = urllib.request.Request(f"{ENGINE}/agent/reset", data=b"{}",
                                     headers={"Content-Type": "application/json"})
        r = json.load(urllib.request.urlopen(req, timeout=30))
        return bool(r.get("ok"))
    except Exception:
        return False


def run_one(t: dict) -> dict:
    body = json.dumps({
        "task": t["task"], "start_url": t.get("start_url"),
        "max_steps": t.get("max_steps", 14), "judge": True,
    }).encode()
    req = urllib.request.Request(f"{ENGINE}/agent/run", data=body,
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    # Long multi-page tasks (40 steps of pagination) can run several minutes; a too-tight client
    # timeout aborts a task that is still legitimately working AND crashes the whole bench before the
    # scorecard is written. Generous ceiling + a caught timeout that records as an (unsuccessful) row.
    try:
        r = json.load(urllib.request.urlopen(req, timeout=900))
    except Exception as e:
        r = {"answer": None, "task_succeeded": False, "needs_human": True,
             "judgment": {"reason": f"client error/timeout: {e}"}, "metrics": {}}
    r["_wall_s"] = round(time.time() - t0, 1)
    return r


def main() -> int:
    args = [a for a in sys.argv[1:]]
    out_path = None
    if "--out" in args:
        i = args.index("--out")
        out_path = args[i + 1]
        del args[i:i + 2]
    # Inter-task settle. These are INDEPENDENT tasks; real usage invokes them discretely, not as a
    # zero-gap burst into one reused tab (which races the previous task's tab teardown/regroup and
    # makes an observe catch a half-loaded DOM). A short gap models discrete invocation; it does not
    # change any single task's difficulty.
    gap_s = 6.0
    if "--gap" in args:
        i = args.index("--gap")
        gap_s = float(args[i + 1])
        del args[i:i + 2]
    tasks = json.load(open(args[0])) if args else DEFAULT_TASKS

    rows = []
    n_ok = n_human = 0
    sum_cost = sum_steps = sum_vis = sum_front = sum_region = 0.0
    n_metric = 0
    print(f"\nBROWSER BENCH — {len(tasks)} tasks, same general agent, no per-site code\n" + "=" * 72)
    for k, t in enumerate(tasks, 1):
        if k > 1 and gap_s > 0:
            time.sleep(gap_s)
        reset_state()  # clean slate before EACH task (incl. the first) so no stale cross-run state leaks
        r = run_one(t)
        m = r.get("metrics", {}) or {}
        j = r.get("judgment", {}) or {}
        ok = bool(r.get("task_succeeded"))
        human = bool(r.get("needs_human"))
        n_ok += ok
        n_human += human
        if "est_cost_usd" in m:
            sum_cost += m.get("est_cost_usd", 0.0)
            sum_steps += m.get("steps", 0)
            sum_vis += m.get("vision_pct", 0.0)
            sum_region += m.get("region_pct", 0.0)
            sum_front += m.get("frontier_pct", 0.0)
            n_metric += 1
        rows.append({"task": t["task"], "url": t.get("start_url"), "answer": r.get("answer"),
                     "success": ok, "needs_human": human, "judge_reason": j.get("reason"),
                     "metrics": m, "wall_s": r.get("_wall_s")})
        verdict = "PASS" if ok else ("HUMAN" if human else "FAIL")
        print(f"[{k}/{len(tasks)}] {verdict:5s} vis={m.get('vision_pct'):>5}% "
              f"rgn={m.get('region_pct'):>5}% front={m.get('frontier_pct'):>5}% ${m.get('est_cost_usd'):.4f} "
              f"{m.get('steps')}st {r.get('_wall_s')}s | {t['task'][:48]}")
        print(f"        -> {str(r.get('answer'))[:90]}")

    nt = len(tasks)
    nm = max(1, n_metric)
    summary = {
        "tasks": nt,
        "success_pct": round(100.0 * n_ok / nt, 1),
        "human_intervention_pct": round(100.0 * n_human / nt, 1),
        "avg_cost_usd": round(sum_cost / nm, 4),
        "avg_steps": round(sum_steps / nm, 1),
        "avg_vision_pct": round(sum_vis / nm, 1),
        "avg_region_pct": round(sum_region / nm, 1),
        "avg_frontier_pct": round(sum_front / nm, 1),
    }
    print("=" * 72)
    print("SCORECARD:", json.dumps(summary))
    print("=" * 72)
    if out_path:
        json.dump({"summary": summary, "rows": rows}, open(out_path, "w"), indent=2)
        print("wrote", out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
