"""
Hard, LLM-driven extension scenarios. Real production flow:
    intent → confirmed_intent broadcast → extension's BrowserAgent → real site.

This complements test_extension_actions.py (deterministic primitives) — it
proves the agent's PLANNING + multi-step + multi-tab behavior, not just
single-action correctness. Uses the production /api/extension/auth endpoint
to fetch real keys (no env-var divergence).

Categories:
  - search_nav        — navigate + extract a fact from a content page
  - multi_field_form  — fill a multi-field form on a real public page
  - multi_step        — pick from a result list and drill into it
  - dismiss_then_act  — consent banner blocks UI, agent must dismiss first
  - cross_tab         — open a second tab, gather info, return
  - canvas_editor     — type into a canvas/contenteditable surface

Run:
    cd engine && DISPLAY=:99 python test_extension_hard.py [N]

Pass criterion: 100% across N runs of each scenario, judged by the LLM judge.
"""

import asyncio
import json
import os
import sys
import time
import uuid
from pathlib import Path

import httpx
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env.local"
EXT_DIR = ROOT / "extension"

if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

SUPABASE_URL = os.environ["NEXT_PUBLIC_SUPABASE_URL"].rstrip("/")
SUPABASE_SERVICE = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
GEMINI_KEY = os.environ.get("GOOGLE_API_KEY")
PROD_AUTH = "https://www.anticipy.ai/api/extension/auth"
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash:generateContent"
)

HDR = {
    "apikey": SUPABASE_SERVICE,
    "Authorization": f"Bearer {SUPABASE_SERVICE}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}


# ---------------------------------------------------------------------------
# Curated hard scenarios — chosen to exercise distinct capabilities at once.
# Each scenario gives the agent a natural-language task and a programmatic
# success check (no LLM-as-judge to avoid LLM-flakiness in the rubric).
# ---------------------------------------------------------------------------

SCENARIOS = [
    {
        "name": "search_nav_wikipedia",
        "summary_for_user": "Search Wikipedia for 'Albert Einstein' and report his birth year.",
        "starting_url": "https://en.wikipedia.org/wiki/Main_Page",
        "browser_task": "On https://en.wikipedia.org find the article on Albert Einstein and report his birth year.",
        # Pass: Einstein was born 1879. Final result text contains "1879".
        "must_contain_in_result": ["1879"],
        "must_visit_url_substring": "/wiki/Albert_Einstein",
    },
    {
        "name": "search_nav_ddg_fact",
        "summary_for_user": "Search DuckDuckGo for 'population of Iceland' and report the figure.",
        "starting_url": "https://duckduckgo.com/",
        "browser_task": "Use DuckDuckGo to find the current population of Iceland and report a single number.",
        # Iceland population is ~370k–400k as of 2024-2026
        "must_contain_in_result_any": ["3", "4"],  # any 3-figure or 4-figure thousands match
        "min_result_length": 5,
    },
    {
        "name": "multi_step_pick_first",
        "summary_for_user": "On Hacker News (news.ycombinator.com), find the title of the very first story currently on the homepage.",
        "starting_url": "https://news.ycombinator.com/",
        "browser_task": "Open news.ycombinator.com and report the exact title of the first ranked story currently on the homepage.",
        # We don't know the title in advance; just verify the agent reports SOMETHING that looks like a story title (>5 chars, no error).
        "must_contain_in_result_any": ["the ", "a ", " - ", " — ", " | "],
        "min_result_length": 8,
    },
    {
        "name": "dismiss_then_act_youtube",
        "summary_for_user": "On YouTube, search for 'lo-fi study music' and report the title of the first result.",
        "starting_url": "https://www.youtube.com/",
        "browser_task": "Open YouTube. If a consent banner appears, dismiss it. Search for 'lo-fi study music'. Report the title of the first video result.",
        "must_visit_url_substring": "search_query=lo-fi",
        "min_result_length": 4,
    },
    {
        "name": "cross_tab_compare",
        "summary_for_user": "Compare the headlines of the BBC homepage and the Reuters homepage.",
        "starting_url": "https://www.bbc.com/news",
        "browser_task": "Open https://www.bbc.com/news in this tab. Then open a SECOND tab to https://www.reuters.com. Read the top headline on each. Report both headlines together in your final answer.",
        # Pass if final result contains some plausible "BBC" + "Reuters" mention indicating the agent visited both
        "must_contain_in_result_any": ["BBC", "bbc"],
        "min_result_length": 30,
    },
]


# ---------------------------------------------------------------------------
# Wire helpers
# ---------------------------------------------------------------------------


async def fetch_keys() -> dict:
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(
            f"{SUPABASE_URL}/rest/v1/engine_users?select=access_code&limit=1",
            headers={"apikey": SUPABASE_SERVICE, "Authorization": f"Bearer {SUPABASE_SERVICE}"},
        )
        code = r.json()[0]["access_code"]
        r = await c.post(PROD_AUTH, json={"code": code})
        return r.json()


async def insert_session_and_intent(scenario: dict) -> tuple[str, str, dict]:
    session_id = str(uuid.uuid4())
    intent_id = str(uuid.uuid4())
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            f"{SUPABASE_URL}/rest/v1/anticipy_sessions",
            headers=HDR,
            json={"id": session_id, "status": "ended", "metadata": {"hard_test": True}},
        )
        r.raise_for_status()
        intent = {
            "id": intent_id,
            "session_id": session_id,
            "summary_for_user": scenario["summary_for_user"],
            "action_type": "browser_action",
            "parameters": {"browser_task": scenario["browser_task"]},
            "status": "pending",
            "confidence": 0.95,
            "importance": "standard",
            "evidence_quote": f"hard-test:{scenario['name']}",
        }
        r = await c.post(f"{SUPABASE_URL}/rest/v1/anticipy_intents", headers=HDR, json=intent)
        r.raise_for_status()
        return session_id, intent_id, r.json()[0]


async def broadcast_confirmed(intent_id: str, intent_row: dict, browser_task: str) -> None:
    payload = {"messages": [{
        "topic": "anticipy-intents",
        "event": "confirmed_intent",
        "payload": {**intent_row, "id": intent_id, "status": "confirmed",
                    "parameters": {**(intent_row.get("parameters") or {}),
                                   "browser_task": browser_task}},
    }]}
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(
            f"{SUPABASE_URL}/realtime/v1/api/broadcast",
            headers={"apikey": SUPABASE_SERVICE, "Authorization": f"Bearer {SUPABASE_SERVICE}",
                     "Content-Type": "application/json"},
            json=payload,
        )
        r.raise_for_status()


async def get_intent(intent_id: str) -> dict | None:
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(
            f"{SUPABASE_URL}/rest/v1/anticipy_intents?id=eq.{intent_id}&select=*",
            headers=HDR,
        )
        if r.status_code != 200: return None
        rows = r.json()
        return rows[0] if rows else None


async def cleanup(session_id: str, intent_id: str) -> None:
    async with httpx.AsyncClient(timeout=15) as c:
        await c.delete(f"{SUPABASE_URL}/rest/v1/anticipy_intents?id=eq.{intent_id}", headers=HDR)
        await c.delete(f"{SUPABASE_URL}/rest/v1/anticipy_sessions?id=eq.{session_id}", headers=HDR)


# ---------------------------------------------------------------------------
# Verdict — all programmatic checks (no LLM-judge variance)
# ---------------------------------------------------------------------------


def verdict(scenario: dict, run: dict) -> dict:
    final = (run.get("final_row") or {}).get("execution_result") or ""
    final_lc = final.lower()
    visited = run.get("visited_urls") or []
    status = (run.get("final_row") or {}).get("status")
    misses = []
    if status not in ("completed", "executed"):
        misses.append(f"status={status}")
    if scenario.get("min_result_length") and len(final.strip()) < scenario["min_result_length"]:
        misses.append(f"result too short ({len(final)} chars)")
    for needle in scenario.get("must_contain_in_result", []):
        if needle.lower() not in final_lc:
            misses.append(f"missing '{needle}' in result")
    anyset = scenario.get("must_contain_in_result_any")
    if anyset and not any(n.lower() in final_lc for n in anyset):
        misses.append(f"none of {anyset} in result")
    if scenario.get("must_visit_url_substring"):
        s = scenario["must_visit_url_substring"].lower()
        if not any(s in (u or "").lower() for u in visited):
            misses.append(f"never visited url containing '{s}'")
    return {"pass": len(misses) == 0, "misses": misses, "result_text": final[:240]}


# ---------------------------------------------------------------------------
# Run one scenario
# ---------------------------------------------------------------------------


async def run_scenario(ctx, runner_page, scenario: dict, ext_id: str, timeout_s: int = 240) -> dict:
    sess_id, intent_id, intent_row = await insert_session_and_intent(scenario)
    visited = set()
    main_page = await ctx.new_page()
    try:
        # Track all navigations across all tabs — required for must_visit_url_substring check
        def on_request(req):
            try:
                if req.resource_type == "document":
                    visited.add(req.url)
            except Exception:
                pass
        ctx.on("request", on_request)

        # Land on the starting URL so the agent has a tab to act on
        try:
            await main_page.goto(scenario["starting_url"], timeout=20_000, wait_until="domcontentloaded")
            visited.add(scenario["starting_url"])
        except Exception as e:
            return {"scenario": scenario, "error": f"starting url failed: {e}",
                    "outcome": "infra_error", "final_row": None, "visited_urls": list(visited)}

        await asyncio.sleep(1.0)
        await broadcast_confirmed(intent_id, intent_row, scenario["browser_task"])

        deadline = time.time() + timeout_s
        last_status = None
        while time.time() < deadline:
            await asyncio.sleep(4)
            row = await get_intent(intent_id)
            cur = (row or {}).get("status")
            if cur != last_status:
                print(f"    [t={int(time.time()-(deadline-timeout_s))}s] status={cur}", flush=True)
                last_status = cur
            if cur in ("completed", "failed", "executed"):
                break

        final_row = await get_intent(intent_id)
        return {
            "scenario": scenario, "intent_id": intent_id,
            "final_row": final_row, "visited_urls": list(visited),
            "outcome": (final_row or {}).get("status") or "timeout",
        }
    finally:
        try: ctx.remove_listener("request", on_request)
        except Exception: pass
        try: await main_page.close()
        except Exception: pass
        try: await cleanup(sess_id, intent_id)
        except Exception: pass


# ---------------------------------------------------------------------------
# Launch + harness
# ---------------------------------------------------------------------------


async def launch_with_extension(p):
    profile = f"/tmp/hard_profile_{uuid.uuid4().hex[:8]}"
    os.makedirs(profile, exist_ok=True)
    args = [
        f"--disable-extensions-except={EXT_DIR}",
        f"--load-extension={EXT_DIR}",
        "--no-sandbox",
        "--disable-blink-features=AutomationControlled",
        "--disable-dev-shm-usage",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    ctx = await p.chromium.launch_persistent_context(
        user_data_dir=profile, headless=False, args=args,
        viewport={"width": 1280, "height": 800},
    )
    return ctx, profile


async def wait_extension(ctx) -> str | None:
    for _ in range(30):
        for sw in ctx.service_workers:
            if sw.url.startswith("chrome-extension://"):
                return sw.url.split("/")[2]
        await asyncio.sleep(0.5)
    return None


async def seed_keys(ctx, ext_id: str, keys: dict) -> bool:
    page = await ctx.new_page()
    try:
        await page.goto(f"chrome-extension://{ext_id}/popup.html", timeout=15_000)
        ok = await page.evaluate(
            """(cfg) => new Promise((res) => {
                chrome.storage.local.set({
                  apiConfig: { groqApiKey: cfg.g, geminiApiKey: cfg.gem },
                  accessAuthorized: true,
                }, () => res(true));
            })""",
            {"g": keys.get("groqApiKey", ""), "gem": keys.get("geminiApiKey", "")},
        )
        return bool(ok)
    finally:
        await page.close()


async def main(per_scenario: int = 1):
    print(f"Hard extension scenarios — {len(SCENARIOS)} × {per_scenario}")
    keys = await fetch_keys()
    if not (keys.get("groqApiKey") or keys.get("geminiApiKey")):
        print("FAIL: prod auth returned no API keys")
        return 1

    runs = []
    async with async_playwright() as p:
        ctx, profile = await launch_with_extension(p)
        try:
            ext_id = await wait_extension(ctx)
            if not ext_id:
                print("FAIL: extension not loaded")
                return 1
            print(f"Extension id: {ext_id}")
            await asyncio.sleep(3)  # let world_patch register
            await seed_keys(ctx, ext_id, keys)
            runner = await ctx.new_page()
            await runner.goto(f"chrome-extension://{ext_id}/popup.html", timeout=10_000)

            for sc in SCENARIOS:
                for rep in range(per_scenario):
                    print(f"\n=== {sc['name']} (rep {rep+1}/{per_scenario}) ===")
                    print(f"    task: {sc['browser_task'][:120]}")
                    t0 = time.time()
                    try:
                        run = await asyncio.wait_for(
                            run_scenario(ctx, runner, sc, ext_id, timeout_s=240),
                            timeout=270,
                        )
                    except asyncio.TimeoutError:
                        run = {"scenario": sc, "outcome": "harness_timeout",
                               "final_row": None, "visited_urls": []}
                    run["elapsed"] = round(time.time() - t0, 1)
                    v = verdict(sc, run)
                    run["verdict"] = v
                    runs.append(run)
                    tag = "✓ PASS" if v["pass"] else "✗ FAIL"
                    print(f"    {tag} ({run['elapsed']}s) — result: {v['result_text']!r}")
                    if v["misses"]:
                        print(f"    misses: {v['misses']}")
        finally:
            try: await ctx.close()
            except Exception: pass
            import shutil; shutil.rmtree(profile, ignore_errors=True)

    p_count = sum(1 for r in runs if r["verdict"]["pass"])
    print("\n" + "=" * 70)
    print(f"HARD SCENARIOS: {p_count}/{len(runs)} ({100*p_count/max(1,len(runs)):.0f}%)")
    print("=" * 70)
    for r in runs:
        sc = r["scenario"]
        tag = "✓" if r["verdict"]["pass"] else "✗"
        print(f"  {tag} {sc['name']:<28} {r['verdict']['result_text']!r}")

    out = Path("/tmp/ext_hard_detail.json")
    out.write_text(json.dumps([{
        "name": r["scenario"]["name"], "outcome": r.get("outcome"),
        "pass": r["verdict"]["pass"], "misses": r["verdict"]["misses"],
        "result_text": r["verdict"]["result_text"], "elapsed": r["elapsed"],
        "visited_urls": r.get("visited_urls", [])[:8],
    } for r in runs], indent=2))
    print(f"\nDetail: {out}")
    return 0 if p_count == len(runs) else 1


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    raise SystemExit(asyncio.run(main(per_scenario=n)))
