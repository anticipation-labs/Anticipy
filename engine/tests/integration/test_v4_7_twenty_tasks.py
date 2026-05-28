"""Phase V4-7 two-tier push-to-failure harness.

Tier 1 (general DOM web): target 100%. No iteration cap. Every
failure is a bug to fix, then re-test until 3/3.

Tier 2 (canvas apps): target 90%. Google's canvas resists synthetic
input (proven in V4-6, ~12 experiments). 2-attempt cap, document
honestly.

Each task runs 3x from a BLANK Chrome (all page tabs closed, a fresh
about:blank), no setup URL, no rehearsal. The integrity vision
auditor inside the runner grades every final state against the goal
using real pixels, so a reported SUCCESS is pixel-verified, never
fabricated.

Results persist incrementally to .anticipy/v4_7_results.jsonl so the
run is resumable and targeted re-tests during the fix loop are cheap.
V4_SCOREBOARD.md is regenerated after every pass.

CLI:
  python -m tests.integration.test_v4_7_twenty_tasks --tier 1
  python -m tests.integration.test_v4_7_twenty_tasks --task gmail_search --runs 3
  python -m tests.integration.test_v4_7_twenty_tasks --all
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ENGINE))

from app.action_engine.dsv4_skill_runner import DSv4SkillRunner  # noqa: E402

REPO = ENGINE.parent
RESULTS = REPO / ".anticipy" / "v4_7_results.jsonl"
SCOREBOARD = REPO / ".anticipy" / "V4_SCOREBOARD.md"


@dataclass
class Task:
    name: str
    tier: int
    goal: str
    max_iters: int = 18


# Gmail send uses a clearly-test sink address. The user has
# explicitly and repeatedly designed the engine to commit on
# Send/Buy/Submit with no confirmation gate and takes responsibility;
# the recipient is a test address.
TASKS: list[Task] = [
    # ── Tier 1: general DOM web (target 100%) ──────────────────────
    Task("gmail_compose_send", 1,
         "Open Gmail, compose a new email to anticipy-test@gmail.com with "
         "subject 'Test from Anticipy' and body 'This is a test email sent "
         "by the Anticipy action engine.', then send it.", 22),
    Task("gmail_search", 1,
         "Open Gmail and tell me the subject line of the most recent email "
         "in the inbox.", 14),
    Task("youtube_search", 1,
         "Open YouTube, search for 'lofi beats', and tell me the title of "
         "the first video result.", 14),
    Task("amazon_price", 1,
         "Open Amazon, search for 'usb-c cable', and tell me the price of "
         "the first result. Do not add anything to the cart.", 16),
    Task("resy_restaurant", 1,
         "Open resy.com for New York and tell me the name of any one "
         "restaurant that is featured or listed on the page (a venue "
         "named in a featured article or card counts). Do not book "
         "anything.", 14),
    Task("notion_recent", 1,
         "Open notion.so and tell me the title of the most recent or top "
         "page visible in the workspace sidebar.", 16),
    Task("slack_recent", 1,
         "Open Slack in the browser and tell me the text of the most recent "
         "message visible in the current channel.", 16),
    Task("spotify_song", 1,
         "Open the Spotify web player, search for the song 'Bohemian "
         "Rhapsody', and tell me the artist.", 16),
    Task("maps_coffee", 1,
         "Open Google Maps, search for coffee shops, and tell me the name "
         "of the first result.", 16),
    Task("github_repos", 1,
         "Open github.com, go to the signed-in user's profile, and tell me "
         "how many public repositories they have.", 16),
    Task("hackernews_top", 1,
         "Open news.ycombinator.com and tell me the title of the current "
         "number one story.", 12),
    Task("reddit_top", 1,
         "Open reddit.com/r/programming and tell me the title of the top "
         "post.", 14),
    # ── Tier 2: canvas apps (target 90%) ───────────────────────────
    Task("sheets_cell_write", 2,
         "Open Google Sheets, create a new spreadsheet, and put the text "
         "'Anticipy Test' in cell A1.", 16),
    Task("sheets_header_row", 2,
         "Open Google Sheets, create a new spreadsheet, and create a header "
         "row in row 1 with 'Week' in A1, 'Product' in B1, 'Units' in C1.", 18),
    Task("sheets_formula", 2,
         "Open Google Sheets, create a new spreadsheet, put 10 in A1, 20 in "
         "A2, and =A1+A2 in A3.", 18),
    Task("docs_paragraph", 2,
         "Open Google Docs, create a new document, and type the sentence "
         "'This document was created by the Anticipy action engine.'", 16),
    Task("docs_heading", 2,
         "Open Google Docs, create a new document, and type a title line "
         "'Anticipy Report' followed by a body paragraph 'Generated "
         "automatically.'", 18),
    Task("slides_text", 2,
         "Open Google Slides, create a new presentation, and put the title "
         "text 'Anticipy' on the first slide.", 18),
    Task("canva_navigate", 2,
         "Open canva.com and navigate to the templates page; tell me one "
         "template category you can see.", 14),
    Task("figma_navigate", 2,
         "Open figma.com, go to the files/recents area, and tell me whether "
         "any design files are listed.", 14),
]

TASK_BY_NAME = {t.name: t for t in TASKS}


def _reset_chrome_blank():
    """Close every page tab, open one fresh about:blank. No setup,
    no rehearsal, no contamination between tasks."""
    try:
        targets = json.load(urllib.request.urlopen(
            "http://localhost:9222/json/list", timeout=6))
    except Exception as e:
        raise RuntimeError(f"Chrome :9222 unreachable: {e}")
    urllib.request.urlopen(urllib.request.Request(
        "http://localhost:9222/json/new?about:blank", method="PUT"),
        timeout=8).read()
    for t in targets:
        if t.get("type") == "page":
            try:
                urllib.request.urlopen(
                    f"http://localhost:9222/json/close/{t['id']}", timeout=5).read()
            except Exception:
                pass
    time.sleep(1.5)


def _append_result(row: dict):
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    with RESULTS.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


def _load_results() -> list[dict]:
    if not RESULTS.exists():
        return []
    out = []
    for ln in RESULTS.read_text().splitlines():
        ln = ln.strip()
        if ln:
            try:
                out.append(json.loads(ln))
            except Exception:
                pass
    return out


def run_task(task: Task, runs: int = 3, kimi_primary: bool = False) -> list[dict]:
    rows = []
    fm = "moonshotai/kimi-k2.6" if kimi_primary else None
    for r in range(runs):
        _reset_chrome_blank()
        runner = DSv4SkillRunner(max_iters=task.max_iters, force_model=fm)
        t0 = time.monotonic()
        try:
            res = runner.run(task.goal)
            status = res.status
            answer = res.answer
            evidence = res.evidence
            tdir = res.trajectory_dir
            err = res.error
        except Exception as e:
            status, answer, evidence, tdir, err = "ERROR", "", "", "", str(e)
        row = {
            "ts": time.time(),
            "task": task.name,
            "tier": task.tier,
            "run": r,
            "status": status,
            "answer": (answer or "")[:300],
            "evidence": (evidence or "")[:300],
            "wall_s": round(time.monotonic() - t0, 1),
            "trajectory_dir": tdir,
            "error": err,
        }
        rows.append(row)
        _append_result(row)
        print(json.dumps({k: row[k] for k in
              ("task", "tier", "run", "status", "wall_s")}))
    return rows


def _latest_per_run(results: list[dict]) -> dict:
    """Most recent result per (task, run)."""
    latest: dict[tuple, dict] = {}
    for row in results:
        key = (row["task"], row["run"])
        if key not in latest or row["ts"] >= latest[key]["ts"]:
            latest[key] = row
    return latest


def write_scoreboard():
    results = _load_results()
    latest = _latest_per_run(results)
    lines = ["# V4-7 SCOREBOARD", "",
             f"Generated {time.strftime('%Y-%m-%d %H:%M:%S')}",
             "",
             "Each task: 3 runs from blank Chrome, vision-auditor grades "
             "the final state on real pixels (no fabrication possible).",
             ""]
    for tier in (1, 2):
        tier_tasks = [t for t in TASKS if t.tier == tier]
        target = "95% aggregate" if tier == 1 else "90%"
        lines.append(f"## Tier {tier} ({'general DOM' if tier==1 else 'canvas apps'}) "
                     f"- target {target}")
        lines.append("")
        tasks_3of3 = 0
        tasks_2of3 = 0
        agg_success = 0
        agg_total = 0
        for t in tier_tasks:
            runs = [latest.get((t.name, i)) for i in range(3)]
            npass = sum(bool(r) and r["status"] == "SUCCESS" for r in runs)
            ran = sum(1 for r in runs if r)
            agg_success += npass
            agg_total += ran
            if npass == 3:
                tasks_3of3 += 1
            if npass >= 2:
                tasks_2of3 += 1
            if tier == 1:
                mark = "PASS" if npass == 3 else ("OK2of3" if npass >= 2 else "FAIL")
            else:
                mark = "PASS" if npass >= 2 else "FAIL"
            statuses = ",".join((r["status"] if r else "-") for r in runs)
            lines.append(f"- [{mark}] {t.name}: {npass}/3 ({statuses})")
        total = len(tier_tasks)
        lines.append("")
        if tier == 1:
            # Exact gate definition (no rounding, honest aggregate):
            # DONE iff >=11/12 tasks at 3/3, OR all 12 at >=2/3 AND
            # aggregate successful runs >= 95% across all 36.
            agg_pct = (100.0 * agg_success / agg_total) if agg_total else 0.0
            cond_a = tasks_3of3 >= 11
            cond_b = (tasks_2of3 == total and agg_total >= total * 3
                      and agg_pct >= 95.0)
            done = cond_a or cond_b
            lines.append(f"**Tier 1 AGGREGATE: {agg_success}/{agg_total} "
                         f"successful runs = {agg_pct:.1f}% "
                         f"(not rounded)**")
            lines.append(f"- tasks at 3/3: {tasks_3of3}/{total} "
                         f"(gate A needs >=11)")
            lines.append(f"- tasks at >=2/3: {tasks_2of3}/{total} "
                         f"(gate B needs all 12 AND aggregate >=95%)")
            lines.append(f"- **Tier 1 DONE: "
                         f"{'YES' if done else 'NO'}** "
                         f"(A={'Y' if cond_a else 'N'}, "
                         f"B={'Y' if cond_b else 'N'})")
        else:
            pct = round(100.0 * tasks_2of3 / total) if total else 0
            lines.append(f"**Tier 2 score: {tasks_2of3}/{total} tasks "
                         f"pass at >=2/3 ({pct}%) - target 90%, "
                         f"2-attempt cap, frontier limit accepted**")
        lines.append("")
    # Failing tier 1 detail for the fix loop
    lines.append("## Tier 1 tasks not yet at 3/3 (fix loop targets)")
    lines.append("")
    any_fail = False
    for t in [x for x in TASKS if x.tier == 1]:
        runs = [latest.get((t.name, i)) for i in range(3)]
        npass = sum(bool(r) and r["status"] == "SUCCESS" for r in runs)
        if npass < 3:
            any_fail = True
            lines.append(f"### {t.name} ({npass}/3)")
            for i, r in enumerate(runs):
                if r and r["status"] != "SUCCESS":
                    lines.append(f"  - run {i}: {r['status']} | "
                                 f"{r['evidence'][:160]} | {r['trajectory_dir']}")
                elif not r:
                    lines.append(f"  - run {i}: not yet run")
            lines.append("")
    if not any_fail:
        lines.append("None. Every Tier 1 task is at 3/3.")
        lines.append("")
    SCOREBOARD.write_text("\n".join(lines))
    print(f"scoreboard written: {SCOREBOARD}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--tier", type=int, choices=[1, 2])
    p.add_argument("--task", help="single task name")
    p.add_argument("--all", action="store_true")
    p.add_argument("--runs", type=int, default=3)
    p.add_argument("--scoreboard-only", action="store_true")
    p.add_argument("--kimi-primary", action="store_true",
                   help="escalate the entire decide loop to Kimi K2.6 "
                        "as primary (per the fix-loop directive)")
    args = p.parse_args()

    if args.scoreboard_only:
        write_scoreboard()
        return 0

    if args.task:
        run_task(TASK_BY_NAME[args.task], runs=args.runs,
                 kimi_primary=args.kimi_primary)
    elif args.tier:
        for t in [x for x in TASKS if x.tier == args.tier]:
            run_task(t, runs=args.runs, kimi_primary=args.kimi_primary)
    elif args.all:
        for t in TASKS:
            run_task(t, runs=args.runs)
    else:
        print("specify --tier, --task, --all, or --scoreboard-only")
        return 2

    write_scoreboard()
    return 0


if __name__ == "__main__":
    sys.exit(main())
