#!/usr/bin/env python3
"""browser_eval.py — the un-gameable browser scoreboard (PLAN §7, build-step S1).

Modelled on `engine/scripts/_webvoyager_slice.py` (drive the real agent loop via
`POST /agent/run` against the engine on :8787) + `final/tests/context_eval.py`
(a table of cases, each graded by an INDEPENDENT functional checker, printed as a
PASS/FAIL scorecard). It is the browser analogue of context_eval: the measurement
we build the hands toward.

The load-bearing invariant (PLAN §7.1): **no task grades the agent's own "done."**
Every task under `final/tests/browser/tasks/<id>/` ships a `checker.py` that
independently re-reads the result — the server's echo / the backend's `/last`
record / a fresh fetch of the canonical page — never the model's self-report.

Three real-world FORM+ACTION tasks:
  (A) httpbin_form  — fill+submit httpbin's form; assert the planted nonce is in
                       the server's echoed JSON (real submit round-trips it).
  (B) local_form    — fill+submit a grader-owned form; assert the backend's /last
                       record matches exactly (the gold-standard independent read).
  (C) wiki_search   — search + click-through; assert the answer contains the
                       ground-truth fact AND the agent actually reached the article.

Reports:  pass-rate · $/task (+ $/successful-task) · steps · tier-mix
          (frontier% = SMART-model share, vision%, region%, replay%).

Run (LIVE — engine on :8787 with the extension connected; a build agent must NOT
do this while contending for the one real tab):
    engine/.venv/bin/python engine/scripts/browser_eval.py [--out scorecard.json]

Dry structural self-test (NO engine, NO Chrome — proves the harness + every
checker + the scorecard math, and that each checker PASSES a good result and
FAILS a faked one):
    engine/.venv/bin/python engine/scripts/browser_eval.py --selftest
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import yaml

ENGINE = os.environ.get("ANTICIPY_ENGINE_URL", "http://127.0.0.1:8787")
TASKS_DIR = Path(__file__).resolve().parents[2] / "final" / "tests" / "browser" / "tasks"


# ───────────────────────────── plumbing ─────────────────────────────

def default_http_get(url: str, timeout: float = 20.0) -> str:
    """The checkers' independent re-read primitive (overridable per-task/ctx)."""
    req = urllib.request.Request(url, headers={"User-Agent": "anticipy-browser-eval/1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def _post(path: str, body: dict, timeout: float = 900.0) -> dict:
    req = urllib.request.Request(ENGINE + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _get(path: str, timeout: float = 20.0) -> dict:
    with urllib.request.urlopen(ENGINE + path, timeout=timeout) as r:
        return json.loads(r.read())


def load_tasks() -> list[dict]:
    """Discover every `tasks/<id>/` bundle: parse spec.yaml, import checker.py."""
    tasks: list[dict] = []
    for d in sorted(p for p in TASKS_DIR.iterdir() if p.is_dir()):
        spec_path, checker_path = d / "spec.yaml", d / "checker.py"
        if not (spec_path.exists() and checker_path.exists()):
            continue
        spec = yaml.safe_load(spec_path.read_text()) or {}
        mod_name = f"browser_task_{d.name}"
        mspec = importlib.util.spec_from_file_location(mod_name, checker_path)
        module = importlib.util.module_from_spec(mspec)
        mspec.loader.exec_module(module)  # type: ignore[union-attr]
        tasks.append({"id": spec.get("id", d.name), "dir": d, "spec": spec, "module": module})
    return tasks


def make_ctx(task: dict) -> dict:
    """Per-task context: a fresh nonce + the re-read primitive; `setup()` may add
    a live backend handle (e.g. the local form server)."""
    ctx = {"nonce": uuid.uuid4().hex[:8], "http_get": default_http_get, "env": dict(os.environ)}
    setup = getattr(task["module"], "setup", None)
    if callable(setup):
        setup(ctx)
    return ctx


def resolve_start_url(task: dict, ctx: dict) -> str:
    fn = getattr(task["module"], "start_url", None)
    if callable(fn):
        return fn(ctx)
    raw = str(task["spec"].get("start_url") or "")
    return raw.replace("{NONCE}", ctx["nonce"])


def resolve_task_text(task: dict, ctx: dict) -> str:
    return str(task["spec"].get("task") or "").replace("{NONCE}", ctx["nonce"]).strip()


# ─────────────────────────── scorecard math ───────────────────────────

def summarize(rows: list[dict]) -> dict:
    """pass-rate · $/task · $/successful-task · steps · tier-mix. Pure function so
    the selftest can prove the aggregation without an engine."""
    n = len(rows) or 1
    oks = [r for r in rows if r.get("ok")]

    def avg(key: str, source: list[dict]) -> float:
        vals = [(r.get("metrics") or {}).get(key, 0) or 0 for r in source]
        return round(sum(vals) / max(1, len(source)), 4)

    total_cost = sum((r.get("metrics") or {}).get("est_cost_usd", 0) or 0 for r in rows)
    replay = [r for r in rows if (r.get("metrics") or {}).get("replayed")]
    return {
        "tasks": len(rows),
        "passed": len(oks),
        "pass_pct": round(100.0 * len(oks) / n, 1),
        "avg_cost_usd": round(total_cost / n, 4),
        "cost_per_success_usd": round(total_cost / len(oks), 4) if oks else None,
        "avg_steps": avg("steps", rows),
        "tier_mix": {
            "frontier_pct": avg("frontier_pct", rows),   # T3 SMART-model share
            "vision_pct": avg("vision_pct", rows),
            "region_pct": avg("region_pct", rows),
            "replay_pct": round(100.0 * len(replay) / n, 1),
        },
    }


def print_scorecard(rows: list[dict], summary: dict) -> None:
    print("=" * 72)
    for r in rows:
        v = "PASS" if r.get("ok") else "FAIL"
        m = r.get("metrics") or {}
        print(f"[{v}] {r['id']:<14} ${m.get('est_cost_usd', 0):.4f}  "
              f"{m.get('steps', 0)}st  front={m.get('frontier_pct', 0)}%  "
              f"| {r.get('detail', '')[:70]}")
    print("=" * 72)
    tm = summary["tier_mix"]
    print(f"SCORE: {summary['passed']}/{summary['tasks']}  ({summary['pass_pct']}%)   "
          f"$/task={summary['avg_cost_usd']}  $/pass={summary['cost_per_success_usd']}  "
          f"steps={summary['avg_steps']}")
    print(f"TIER-MIX: frontier={tm['frontier_pct']}%  vision={tm['vision_pct']}%  "
          f"region={tm['region_pct']}%  replay={tm['replay_pct']}%")
    print("=" * 72)


# ───────────────────────────── live lane ─────────────────────────────

def _wait_engine(tries: int = 40) -> bool:
    for _ in range(tries):
        try:
            if _get("/health").get("ok") or True:  # any 200 is enough
                return True
        except Exception:
            pass
        time.sleep(0.25)
    return False


def _wait_connected(want: bool, tries: int = 80) -> bool:
    for _ in range(tries):
        try:
            if _get("/ws/state").get("connected") == want:
                return True
        except Exception:
            pass
        time.sleep(0.25)
    return False


def run_live(out_path: str | None) -> int:
    tasks = load_tasks()
    print(f"BROWSER EVAL — {len(tasks)} real-world FORM+ACTION tasks, functional checkers\n"
          f"engine={ENGINE}")
    if not _wait_engine():
        print("FAIL: engine not reachable on", ENGINE)
        return 2
    try:
        _post("/ws/reload", {}, timeout=20)
    except Exception:
        pass
    _wait_connected(False, 40)
    if not _wait_connected(True):
        print("FAIL: extension not connected (load the unpacked extension + keep the tab open)")
        return 2

    rows: list[dict] = []
    for task in tasks:
        ctx = make_ctx(task)
        start_url, text = resolve_start_url(task, ctx), resolve_task_text(task, ctx)
        max_steps = int(task["spec"].get("max_steps", 12))
        print(f"\n=== {task['id']} ===\n  URL : {start_url}\n  TASK: {text[:120]}")
        try:
            _post("/agent/reset", {}, timeout=30)          # cold slate between tasks
        except Exception:
            pass
        try:
            result = _post("/agent/run", {"task": text, "start_url": start_url,
                                          "max_steps": max_steps, "judge": True})
        except Exception as e:
            result = {"answer": None, "metrics": {}, "error": f"run error: {e}"}
        try:
            ok, detail = task["module"].check(result, ctx)
        except Exception as e:
            ok, detail = False, f"checker error: {type(e).__name__}: {e}"
        finally:
            td = getattr(task["module"], "teardown", None)
            if callable(td):
                td(ctx)
        rows.append({"id": task["id"], "ok": bool(ok), "detail": detail,
                     "metrics": result.get("metrics") or {}, "answer": result.get("answer")})
        print(f"  -> {'PASS' if ok else 'FAIL'}: {detail}")

    summary = summarize(rows)
    print_scorecard(rows, summary)
    if out_path:
        Path(out_path).write_text(json.dumps({"summary": summary, "rows": rows}, indent=2))
        print("wrote", out_path)
    return 0


# ─────────────────────────── selftest lane ───────────────────────────

def run_selftest() -> int:
    """Structural proof — no engine, no Chrome. For every task: the checker must
    PASS a good synthetic result and FAIL a faked one; then the scorecard math is
    exercised. This is the isolated unit test that guards the harness itself."""
    tasks = load_tasks()
    print(f"BROWSER EVAL — STRUCTURAL SELF-TEST ({len(tasks)} tasks, no engine)\n" + "=" * 66)
    if len(tasks) < 3:
        print(f"FAIL: expected >=3 task bundles, found {len(tasks)}")
        return 1
    failures: list[str] = []
    synth_rows: list[dict] = []
    for task in tasks:
        mod = task["module"]
        for name in ("check", "synth_pass", "synth_fail"):
            if not callable(getattr(mod, name, None)):
                failures.append(f"{task['id']}: missing {name}()")
        if failures:
            continue
        # PASS fixture must pass.
        ctx = make_ctx(task)
        try:
            good = mod.synth_pass(ctx)
            ok_g, det_g = mod.check(good, ctx)
        finally:
            _teardown(mod, ctx)
        if not ok_g:
            failures.append(f"{task['id']}: synth_pass was rejected ({det_g})")
        else:
            print(f"[ok]   {task['id']:<14} synth_pass -> PASS  ({det_g[:48]})")
        # FAIL fixture must fail — this is the anti-cheat proof (a lying result is caught).
        ctx2 = make_ctx(task)
        try:
            bad = mod.synth_fail(ctx2)
            ok_b, det_b = mod.check(bad, ctx2)
        finally:
            _teardown(mod, ctx2)
        if ok_b:
            failures.append(f"{task['id']}: synth_fail was (wrongly) accepted")
        else:
            print(f"[ok]   {task['id']:<14} synth_fail -> FAIL  ({det_b[:48]})")
        synth_rows.append({"id": task["id"], "ok": True, "detail": det_g,
                           "metrics": good.get("metrics") or {}})

    # scorecard math sanity
    s = summarize(synth_rows + [{"id": "x", "ok": False, "detail": "", "metrics": {"est_cost_usd": 0.02, "steps": 3}}])
    checks = [
        (s["tasks"] == len(synth_rows) + 1, "tasks count"),
        (s["passed"] == len(synth_rows), "passed count"),
        (0.0 <= s["pass_pct"] <= 100.0, "pass_pct range"),
        (s["cost_per_success_usd"] is not None, "cost_per_success computed"),
        ("frontier_pct" in s["tier_mix"], "tier_mix present"),
    ]
    for good, label in checks:
        if not good:
            failures.append(f"scorecard: {label} wrong ({s})")
        else:
            print(f"[ok]   scorecard      {label}")

    print("=" * 66)
    if failures:
        for f in failures:
            print("FAIL:", f)
        print(f"SELFTEST RED — {len(failures)} failure(s)")
        return 1
    print(f"SELFTEST GREEN — {len(tasks)} checkers distinguish real success from faked; scorecard sound")
    return 0


def _teardown(mod, ctx: dict) -> None:
    td = getattr(mod, "teardown", None)
    if callable(td):
        try:
            td(ctx)
        except Exception:
            pass


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest", action="store_true",
                    help="structural proof only; no engine, no Chrome")
    ap.add_argument("--out", help="write the scorecard JSON to this path (live lane)")
    args = ap.parse_args()
    if args.selftest:
        return run_selftest()
    return run_live(args.out)


if __name__ == "__main__":
    sys.exit(main())
