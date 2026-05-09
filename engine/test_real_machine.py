"""Real-machine end-to-end test: drives YOUR Chrome with YOUR extension via
Supabase Realtime broadcasts, polls engine_trajectories for the result.

WHY: Patchright in this codespace is unreliable on broadcast reception.
The legitimate test is YOUR real Chrome on YOUR real machine with the
extension installed and signed in, listening on anticipy-intents. This
codespace orchestrates:

  1. Insert/Broadcast a confirmed_intent on anticipy-intents (your user_id)
  2. YOUR extension picks it up, runs through the multi-agent pipeline
     (planner+executor+verifier+critic+reflector hitting /api/agent/*),
     completes the task in YOUR Chrome with YOUR cookies and YOUR IP
  3. The agent POSTs a trajectory to /api/engine/trajectory at end-of-task
  4. We poll engine_trajectories for the matching intent_id row, score it,
     repeat for each scenario

PRE-FLIGHT (do these on your machine):
  - Pull the latest main (so your extension/agent.js has the new
    agent-team integration): `git pull`
  - Open Chrome
  - Install /workspaces/Anticipy/extension as an unpacked extension
    (chrome://extensions → Developer mode → Load unpacked → pick the dir),
    or RELOAD the extension if already installed (the reload arrow on
    the extension card)
  - Click the Anticipy icon → enter access code: 77c04c26 → Connect
  - Pin the extension; the SW must be alive while the test runs
  - Don't actively type during the test — the agent drives a tab; let it work

THEN in this codespace:
  cd /workspaces/Anticipy/engine
  set -a && source ../.env.local && set +a
  python test_real_machine.py
  # or for a single scenario:
  python test_real_machine.py --scenario wiki_python_year
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import uuid
from typing import Any

import httpx

# Re-use the scenarios + verifier helpers from the Patchright harness.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_extension_runner import (  # noqa: E402
    SCENARIOS as EASY_SCENARIOS,
    REALTIME_TOPIC,
    SUPABASE_URL,
    SUPABASE_SERVICE_ROLE_KEY,
    llm_judge_pass,
    scenario_pass,
    _service_headers,
)


# ─── HARD scenarios — actual capability tests, not "open a website" ──
# Each is multi-step, action-on-page, and exercises a different facet
# of the agent. Some need YOUR auth (Gmail, Amazon, Google Calendar, X);
# those rely on your real Chrome session — that's the point.
#
# Verifiers go through the LLM judge (app.llm_judge). The judge sees the
# original task and the agent's outcome message; it returns YES/NO based
# on whether the message reflects a real attempt + meaningful answer.
# No string-match.

HARD_SCENARIOS: list[dict[str, Any]] = [
    {
        "name": "anticipy_waitlist_signup",
        "task": (
            "Go to anticipy.ai, find the waitlist sign-up form (probably on "
            "the home page or /waitlist), and sign up with the email "
            "test+browser-agent@anticipy.ai and the name 'Browser Agent Test'. "
            "Tell me whether the signup confirmed."
        ),
        "verify": llm_judge_pass(
            task_description=(
                "Did the agent SUBMIT the Anticipy waitlist form and observe a "
                "confirmation? It should report something like 'signed up' or "
                "'thanks for joining' — NOT just 'I navigated to the page'."
            ),
            expected_facts=["signed up", "thanks", "confirmation", "joined", "added to waitlist"],
        ),
    },
    {
        "name": "gmail_draft_compose",
        "task": (
            "Open Gmail (mail.google.com), start composing a NEW email to "
            "omarkebrahim@gmail.com, subject 'Anticipy agent test', body "
            "'This was drafted by the browser agent.' Save it as a draft "
            "(do NOT send). Tell me the draft was saved."
        ),
        "verify": llm_judge_pass(
            task_description=(
                "Did the agent OPEN a Gmail compose window, type the subject + "
                "body, and SAVE the draft (or observe it auto-saved)? Required "
                "evidence: the agent reports the draft was saved/created — not "
                "just 'I navigated to Gmail'."
            ),
            expected_facts=["draft saved", "draft created", "saved as draft", "draft in"],
        ),
    },
    {
        "name": "amazon_monitor_search",
        "task": (
            "On Amazon, search for a 32-inch 4K monitor under $200 with at "
            "least 4 stars. From the results, tell me the brand, current "
            "price, and star rating of the top result that matches."
        ),
        "verify": llm_judge_pass(
            task_description=(
                "Did the agent return a SPECIFIC monitor — naming brand, price "
                "(under $200), and star rating (>=4)? Generic 'I searched' "
                "without product specifics is a fail."
            ),
            expected_facts=["LG", "Samsung", "Dell", "Acer", "AOC", "ASUS", "$", "stars", "rating"],
        ),
    },
    {
        "name": "compare_news_bbc_techcrunch",
        "task": (
            "Open BBC News (bbc.com/news) AND TechCrunch (techcrunch.com), "
            "and tell me the lead headline from EACH site, quoted verbatim. "
            "Both sites must be named in your answer."
        ),
        "verify": llm_judge_pass(
            task_description=(
                "Did the agent name BOTH BBC News and TechCrunch and quote a "
                "headline from each? Multi-tab planning + extraction. "
                "If only one site is covered, fail."
            ),
            expected_facts=["bbc", "techcrunch"],
        ),
    },
    {
        "name": "hn_top_comment_extract",
        "task": (
            "Go to news.ycombinator.com, find the top story (highest points), "
            "click into its comments page, and tell me one of the top-level "
            "comments verbatim. Include the commenter's username."
        ),
        "verify": llm_judge_pass(
            task_description=(
                "Did the agent navigate INTO the comments page (not just the "
                "story title) and quote a real comment with username? Must "
                "include actual comment text — username alone is not enough."
            ),
            expected_facts=["comment", "wrote", "said", "user", "@"],
        ),
    },
    {
        "name": "reddit_thread_3_comments",
        "task": (
            "Go to reddit.com/r/programming, find the current top post, click "
            "into it, and tell me 3 of the top comments. Just the comment "
            "text — not a summary."
        ),
        "verify": llm_judge_pass(
            task_description=(
                "Did the agent return 3 distinct comments from a Reddit thread, "
                "verbatim? Summaries don't count — needs actual comment text. "
                "If fewer than 3 or just summaries, fail."
            ),
            expected_facts=["comment", "1.", "2.", "3."],
        ),
    },
    {
        "name": "amazon_product_page_read",
        "task": (
            "On Amazon, find the product page for the 'Logitech MX Master 3S' "
            "mouse and tell me the current price and the number of customer "
            "reviews. (Don't add to cart — just report the info.)"
        ),
        "verify": llm_judge_pass(
            task_description=(
                "Did the agent return Logitech MX Master 3S price and review "
                "count? Must include $ amount AND review count number."
            ),
            expected_facts=["MX Master 3S", "$", "reviews", "ratings"],
        ),
    },
    {
        "name": "github_search_top_repo",
        "task": (
            "On github.com, search for 'browser agent' and tell me the top "
            "repository's full name, star count, and the first paragraph of "
            "its README."
        ),
        "verify": llm_judge_pass(
            task_description=(
                "Did the agent name a specific GitHub repo (org/name shape), "
                "include a star count number, and quote a README paragraph? "
                "Generic 'I searched GitHub' is a fail."
            ),
            expected_facts=["github.com/", "stars", "README", "/"],
        ),
    },
    {
        "name": "google_calendar_today_read",
        "task": (
            "Open Google Calendar (calendar.google.com) and tell me what "
            "events I have on TODAY. Just read the schedule — don't add or "
            "modify anything."
        ),
        "verify": llm_judge_pass(
            task_description=(
                "Did the agent read events from Google Calendar for today? "
                "Either it lists specific events with names/times, or it "
                "reports 'no events scheduled today'. Either is acceptable. "
                "What's NOT acceptable: 'I navigated to Calendar but couldn't "
                "see' — that's a failure."
            ),
            expected_facts=["meeting", "event", "scheduled", "no events", "free", "calendar"],
        ),
    },
    {
        "name": "x_public_search",
        "task": (
            "Open x.com (Twitter), search for 'browser agent', and tell me "
            "the author handle (@username) and the like count of the top "
            "tweet from the results."
        ),
        "verify": llm_judge_pass(
            task_description=(
                "Did the agent return a specific @handle and a like count "
                "number from X/Twitter? Generic 'I searched' is a fail."
            ),
            expected_facts=["@", "likes", "like"],
        ),
    },
]


# Combined scenario list — easy first, hard second. By default we run
# all 35; --hard-only runs just the 10 hard ones.
SCENARIOS: list[dict[str, Any]] = list(EASY_SCENARIOS) + HARD_SCENARIOS


# ─── Real-machine config ─────────────────────────────────────────────


# Omar's actual user_id (engine_users where access_code='77c04c26').
DEFAULT_USER_ID = "cc3fb754-6c7b-46da-bce7-dfa127a576d2"
DEFAULT_ACCESS_CODE = "77c04c26"
USER_ID = os.environ.get("ANTICIPY_USER_ID") or DEFAULT_USER_ID
ACCESS_CODE = os.environ.get("ANTICIPY_ACCESS_CODE") or DEFAULT_ACCESS_CODE


# ─── Broadcast + trajectory polling ──────────────────────────────────


async def broadcast_real_intent(
    client: httpx.AsyncClient,
    *,
    intent_id: str,
    task: str,
) -> None:
    """Broadcast on anticipy-intents with the configured user_id. Same
    payload shape as /api/engine/confirm produces."""
    payload = {
        "id": intent_id,
        "user_id": USER_ID,
        "summary_for_user": task,
        "action_type": "browser_action",
        "evidence_quote": "",
        "importance": "standard",
        "confidence": 0.9,
        "parameters": {},
        "status": "confirmed",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
    }
    body = {
        "messages": [
            {
                "topic": REALTIME_TOPIC,
                "event": "confirmed_intent",
                "payload": payload,
            }
        ]
    }
    resp = await client.post(
        f"{SUPABASE_URL}/realtime/v1/api/broadcast",
        headers=_service_headers(),
        json=body,
        timeout=15.0,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"broadcast failed: {resp.status_code} {resp.text[:200]}")


async def wait_for_trajectory(
    client: httpx.AsyncClient,
    *,
    intent_id: str,
    timeout_s: float,
    poll_every_s: float = 4.0,
) -> dict[str, Any] | None:
    """Poll engine_trajectories until a row with this intent_id appears or
    timeout. Service-role read bypasses RLS."""
    deadline = time.time() + timeout_s
    last_log = 0.0
    started = time.time()
    while time.time() < deadline:
        url = (
            f"{SUPABASE_URL}/rest/v1/engine_trajectories"
            f"?intent_id=eq.{intent_id}&select=*&limit=1"
        )
        try:
            resp = await client.get(url, headers=_service_headers(), timeout=10.0)
            if resp.status_code == 200:
                rows = resp.json()
                if rows:
                    return rows[0]
        except (httpx.TimeoutException, httpx.NetworkError):
            pass
        if time.time() - last_log > 30:
            elapsed = int(time.time() - started)
            print(f"    ... still waiting ({elapsed}s elapsed)", flush=True)
            last_log = time.time()
        await asyncio.sleep(poll_every_s)
    return None


# ─── Pre-flight ──────────────────────────────────────────────────────


async def preflight(client: httpx.AsyncClient) -> tuple[bool, str]:
    """Confirm the user exists and the agent-team routes are live."""
    # 1. user lookup
    url = (
        f"{SUPABASE_URL}/rest/v1/engine_users"
        f"?id=eq.{USER_ID}&select=id,access_code&limit=1"
    )
    try:
        resp = await client.get(url, headers=_service_headers(), timeout=10.0)
        if resp.status_code != 200 or not resp.json():
            return False, f"user_id {USER_ID} not in engine_users"
        if resp.json()[0]["access_code"] != ACCESS_CODE:
            return False, f"access_code mismatch for user_id {USER_ID}"
    except Exception as e:
        return False, f"engine_users lookup failed: {e}"

    # 2. /api/agent/plan reachability (auth handshake)
    try:
        resp = await client.post(
            "https://www.anticipy.ai/api/agent/plan",
            headers={
                "Content-Type": "application/json",
                "X-Anticipy-Code": ACCESS_CODE,
            },
            json={"task": "ping"},
            timeout=30,
        )
        if resp.status_code not in (200, 400):
            return False, f"/api/agent/plan returned {resp.status_code}"
    except Exception as e:
        return False, f"/api/agent/plan unreachable: {e}"

    return True, "ok"


# ─── LLM judge for verdicts ──────────────────────────────────────────


def judge_outcome(scenario: dict, trajectory: dict | None) -> tuple[bool, str]:
    """Use the existing per-scenario verifier (which itself wraps the LLM
    judge in app.llm_judge for non-trivial scenarios)."""
    if trajectory is None:
        return False, "NO TRAJECTORY (timed out — extension did not POST one)"
    msg = trajectory.get("outcome_message") or ""
    outcome = trajectory.get("outcome") or "unknown"
    try:
        verifier = scenario["verify"]
        passed = bool(verifier({"message": msg}))
        return passed, f"outcome={outcome} | message: {msg[:240]}"
    except Exception as e:
        return False, f"verifier raised: {e} | message: {msg[:240]}"


# ─── Main ────────────────────────────────────────────────────────────


async def main(
    scenario_filter: str | None = None,
    per_task_timeout_s: float = 360.0,
) -> int:
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        print("ERROR: SUPABASE env vars not set. source .env.local first.",
              file=sys.stderr)
        return 2

    print("=== Anticipy real-machine end-to-end test ===", flush=True)
    print(f"User ID:     {USER_ID}", flush=True)
    print(f"Access code: {ACCESS_CODE[:4]}...{ACCESS_CODE[-2:]}", flush=True)
    print(f"Endpoints:   https://www.anticipy.ai/api/agent/*", flush=True)

    async with httpx.AsyncClient() as client:
        ok, reason = await preflight(client)
        if not ok:
            print(f"\nPRE-FLIGHT FAILED: {reason}", flush=True)
            return 3
        print("Pre-flight OK\n", flush=True)
        print("(Make sure your Chrome is open with the Anticipy extension "
              "signed in.)", flush=True)
        print("(Pull latest main first: cd ~/Anticipy && git pull, then "
              "reload the extension in chrome://extensions.)", flush=True)

        scenarios = SCENARIOS
        if scenario_filter:
            scenarios = [s for s in SCENARIOS if scenario_filter in s["name"]]
            if not scenarios:
                print(f"No scenarios match filter '{scenario_filter}'", flush=True)
                return 4

        print(f"\nRunning {len(scenarios)} scenario(s)", flush=True)
        results: list[dict] = []

        for scenario in scenarios:
            intent_id = str(uuid.uuid4())
            print(f"\n== {scenario['name']} (intent {intent_id[:8]}…)", flush=True)
            print(f"   task: {scenario['task']}", flush=True)
            t0 = time.time()
            try:
                await broadcast_real_intent(
                    client, intent_id=intent_id, task=scenario["task"]
                )
            except Exception as e:
                print(f"   FAIL — broadcast: {e}", flush=True)
                results.append({
                    "scenario": scenario["name"],
                    "passed": False,
                    "reason": f"broadcast: {e}",
                    "duration_s": 0,
                })
                continue

            print(f"   broadcast sent — waiting for trajectory "
                  f"(≤{int(per_task_timeout_s)}s)...", flush=True)
            row = await wait_for_trajectory(
                client,
                intent_id=intent_id,
                timeout_s=per_task_timeout_s,
            )
            duration = time.time() - t0
            passed, detail = judge_outcome(scenario, row)
            mark = "PASS" if passed else "FAIL"
            print(f"   [{mark}] {duration:.1f}s — {detail[:240]}", flush=True)
            results.append({
                "scenario": scenario["name"],
                "passed": passed,
                "duration_s": duration,
                "detail": detail,
                "intent_id": intent_id,
                "trajectory_id": (row or {}).get("id"),
                "outcome": (row or {}).get("outcome"),
                "total_steps": (row or {}).get("total_steps"),
            })

        # Summary
        print("\n=== RESULTS ===", flush=True)
        for r in results:
            mark = "PASS" if r["passed"] else "FAIL"
            steps = r.get("total_steps")
            outcome = r.get("outcome") or "?"
            steps_str = f" steps={steps}" if steps is not None else ""
            print(f"  [{mark}] {r['scenario']}  {r.get('duration_s', 0):.1f}s "
                  f"outcome={outcome}{steps_str}", flush=True)
        passed_n = sum(1 for r in results if r["passed"])
        total = len(results)
        pct = 100.0 * passed_n / total if total else 0.0
        print(f"\n{passed_n}/{total} passed ({pct:.0f}%)", flush=True)

        # Persist
        out_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "logs",
            f"real_machine_{int(time.time())}.json",
        )
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w") as f:
            json.dump({
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "user_id": USER_ID,
                "access_code_prefix": ACCESS_CODE[:4] + "...",
                "results": results,
                "passed": passed_n,
                "total": total,
                "pct": pct,
            }, f, indent=2)
        print(f"\nLog: {out_path}", flush=True)

        return 0 if passed_n == total else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", help="Substring filter on scenario name "
                        "(e.g. 'wiki', 'compare', 'gmail', 'amazon')")
    parser.add_argument("--hard-only", action="store_true",
                        help="Run only the 10 hard scenarios (real action, "
                        "multi-step, some auth-walled)")
    parser.add_argument("--easy-only", action="store_true",
                        help="Run only the 25 easy scenarios (read-only "
                        "fact-finding)")
    parser.add_argument("--timeout", type=float, default=360.0,
                        help="Per-task timeout seconds (default 360 = 6 min)")
    args = parser.parse_args()

    if args.hard_only:
        # Override the scenario filter to match only HARD scenarios by name.
        hard_names = {s["name"] for s in HARD_SCENARIOS}
        # Hack: stash the set on the module so main() can look it up via
        # the existing filter mechanism. Simpler: scope via filter to a
        # known unique substring per hard scenario — they all happen to
        # not collide with easy names; just use a sentinel approach.
        # Cleanest: rebind SCENARIOS module-global to HARD_SCENARIOS.
        SCENARIOS = HARD_SCENARIOS  # noqa: F811 — rebind for main()'s view
    elif args.easy_only:
        SCENARIOS = EASY_SCENARIOS  # noqa: F811

    sys.exit(asyncio.run(main(args.scenario, args.timeout)))
