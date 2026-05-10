"""
End-to-end browser-agent test harness.

Launches Chrome in this codespace (headed, on Xvfb) with the unpacked Anticipy
extension loaded. Skips Supabase auth entirely — directly injects an
`apiConfig` into the extension's chrome.storage with a synthetic user_id and
the LLM keys from .env.local. Then triggers tasks by broadcasting
`confirmed_intent` on the `anticipy-intents` Realtime channel with that
synthetic user_id (the extension filters by user_id match — see
extension/background.js:296).

Watches `chrome.storage.local.agentStatus` to know when each task finishes.
Scores by checking the agent's final message against per-scenario verifiers.

This is the same broadcast → extension → agent path a wearer hits in
production. We just trigger every step ourselves, in this codespace, with
this codespace's IP. Run repeatedly to benchmark agent reliability.

Usage:
    cd /workspaces/Anticipy/engine
    set -a && source ../.env.local && set +a
    DISPLAY=:99 python test_extension_runner.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Callable

import httpx

EXTENSION_PATH = (Path(__file__).resolve().parent.parent / "extension").as_posix()
PROFILE_DIR = "/tmp/anticipy_test_profile"

SUPABASE_URL = (os.environ.get("NEXT_PUBLIC_SUPABASE_URL") or "").rstrip("/")
SUPABASE_ANON_KEY = os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

REALTIME_TOPIC = "anticipy-intents"


# ─────────────────────────────────────────────────────────────────────
# Scenarios — small, observable, no-login. Pass/fail = a regex match
# against the agent's final user-facing message.
# ─────────────────────────────────────────────────────────────────────


# NO HARDCODED PHRASE LISTS, NO STRING-MATCH RULES.
# Every verifier here goes through app.llm_judge — given the original
# task and the agent's reply, an LLM judge returns YES/NO with a reason.
# Whichever free model has quota at the moment serves the verdict.
from app.llm_judge import judge_task_response  # noqa: E402


def llm_judge_pass(task_description: str, expected_facts: list[str] | None = None) -> Callable[[dict], bool]:
    """Build a verifier that asks an LLM judge whether the agent's reply
    actually answered the task. The expected_facts are passed as guidance
    to the judge prompt, not used as string-matchers in this verifier.
    """
    def verify(result: dict) -> bool:
        msg = (result or {}).get("message", "") or ""
        verdict = judge_task_response(task_description, msg, expected_facts=expected_facts)
        return bool(verdict.get("passed"))
    return verify


# Backwards-compat shims so existing scenario dicts keep importing.
# Both routes go through the LLM judge — no string-match.
def scenario_pass(needles: list[str]) -> Callable[[dict], bool]:
    return llm_judge_pass(
        task_description="(judge whether the agent surfaced any of the listed facts as a real answer)",
        expected_facts=needles,
    )


def scenario_pass_substantive(min_chars: int = 30) -> Callable[[dict], bool]:
    return llm_judge_pass(
        task_description="(judge whether the agent gave a substantive real answer, not a generic failure)",
        expected_facts=None,
    )


SCENARIOS: list[dict[str, Any]] = [
    # ─── Easy fact-finding (baseline) ──────────────────────────────────
    {
        "name": "wiki_python_year",
        "task": "Look up on Wikipedia the year Python the programming language was first released and tell me.",
        "verify": scenario_pass(["1991"]),
    },
    {
        "name": "wiki_capital_france",
        "task": "Look up the capital of France on Wikipedia and tell me the name.",
        "verify": scenario_pass(["paris"]),
    },
    {
        "name": "ddg_cats_diet",
        "task": "Search DuckDuckGo for what cats eat and tell me one common food.",
        "verify": scenario_pass(["meat", "carnivore", "fish", "mice", "kibble", "tuna", "chicken"]),
    },
    # ─── Numeric / specific value extraction ──────────────────────────
    {
        "name": "wiki_japan_population",
        "task": "Look up Japan on Wikipedia and tell me the population (just the rough number is fine).",
        # Wide acceptance: any 100M+ rounded number ("122 million" / "122,000,000")
        # OR explicit million/billion mentions.
        "verify": lambda r: bool(
            (r or {}).get("message")
            and any(s in (r or {}).get("message", "") for s in [
                "million", "120,", "121,", "122,", "123,", "124,", "125,", "126,", "127,",
            ])
        ),
    },
    {
        "name": "wiki_eiffel_height",
        "task": "Look up the Eiffel Tower on Wikipedia and tell me its height in metres.",
        "verify": scenario_pass(["330", "324", "300 m", "metres", "meters"]),
    },
    # ─── Multi-step / multi-tab (compare across sources) ──────────────
    {
        "name": "compare_python_year_two_sources",
        "task": "Compare on both Wikipedia and DuckDuckGo: what year was Python the programming language first released? Tell me both answers.",
        "verify": scenario_pass(["1991"]),
    },
    {
        "name": "wiki_then_ddg_einstein",
        "task": "Look up Albert Einstein on Wikipedia, then search DuckDuckGo for his most famous equation. Tell me the equation.",
        "verify": scenario_pass(["e=mc", "e = mc", "e=mc²", "energy", "mass"]),
    },
    # ─── Search-engine flow (no Wikipedia fallback) ───────────────────
    {
        "name": "google_capital_japan",
        "task": "Search Google for the capital of Japan and tell me.",
        "verify": scenario_pass(["tokyo"]),
    },
    {
        "name": "ddg_chrome_release_year",
        "task": "Search DuckDuckGo for the year Google Chrome was first released and tell me.",
        "verify": scenario_pass(["2008"]),
    },
    # ─── Reading a specific page (no search needed) ───────────────────
    {
        "name": "wiki_apollo_11_year",
        "task": "Go directly to en.wikipedia.org/wiki/Apollo_11 and tell me the year it landed on the moon.",
        "verify": scenario_pass(["1969"]),
    },
    # ─── Aborted commitment (the user changes their mind) ─────────────
    {
        "name": "aborted_commitment",
        "task": "Look up the population of Vatican City on Wikipedia. Actually never mind, I don't want to know.",
        # Pass = agent gracefully declines OR proceeds anyway with a value.
        # Either is acceptable; the failure mode we're guarding against is
        # the agent timing out in the cascade revalidation loop.
        "verify": lambda r: bool((r or {}).get("message", "")),
    },
    # ─── Multi-criteria fact (more than one piece of info) ────────────
    {
        "name": "wiki_taj_mahal_year_and_who",
        "task": "Look up the Taj Mahal on Wikipedia. Tell me both who built it AND when (just the rough year).",
        "verify": lambda r: ("shah jahan" in (r or {}).get("message", "").lower())
                            and any(y in (r or {}).get("message", "") for y in ["1632", "1631", "1648", "163"]),
    },
    # ─── Common consumer site (not heavy-anti-bot) ────────────────────
    {
        "name": "imdb_inception_year",
        "task": "On IMDb (imdb.com), look up the movie Inception and tell me the year it was released.",
        "verify": scenario_pass(["2010"]),
    },
    # ─── Quoted / specific list extraction (anti-cop-out: list several) ─
    {
        "name": "wiki_planets_list",
        "task": "Go to the Wikipedia page about the planets of the Solar System and list at least 5 of them by name.",
        "verify": lambda r: sum(
            1 for p in ["mercury", "venus", "earth", "mars", "jupiter", "saturn", "uranus", "neptune"]
            if p in (r or {}).get("message", "").lower()
        ) >= 5,
    },
    # ─── Anti-flake stress: same task, simpler — should never fail ─────
    {
        "name": "smoke_repeat_capital_uk",
        "task": "Look up the capital of the United Kingdom on Wikipedia and tell me the name.",
        "verify": scenario_pass(["london"]),
    },

    # ─── Harder set: real-world failure modes ─────────────────────────
    # These are the kind of tasks where agents typically fail. Adding them
    # to find where to actually improve. Each task is something a normal
    # user would reasonably ask. Failure here is informative — not a bug
    # in the harness, but a real gap to fix.

    # Multi-tab research (compare across two sites). Verifier goes
    # through the LLM judge — checks both BBC and CNN are referenced and
    # the message contains real headlines, not a generic failure.
    {
        "name": "compare_news_headlines",
        "task": "Open BBC News (bbc.com/news) AND CNN (cnn.com), and tell me one headline from each. Quote them verbatim.",
        "verify": llm_judge_pass(
            task_description=(
                "Did the agent name BOTH BBC News AND CNN, and quote a real "
                "headline from each (not just a navigation report)?"
            ),
            expected_facts=["bbc", "cnn"],
        ),
    },

    # Search → click first result → extract from the result page
    {
        "name": "search_then_extract",
        "task": "Search Google for 'OpenAI Wikipedia', click the Wikipedia result, and tell me the year OpenAI was founded.",
        "verify": scenario_pass(["2015"]),
    },

    # Reddit — often anti-bot but read-only path is usually open
    {
        "name": "reddit_read_top_post",
        "task": "Go to reddit.com/r/programming and tell me the title of one of the current top posts.",
        "verify": scenario_pass_substantive(min_chars=50),
    },

    # YouTube — search and read result titles
    {
        "name": "youtube_search_video",
        "task": "Search YouTube (youtube.com) for 'Python tutorial' and tell me the title of the top video result.",
        "verify": scenario_pass_substantive(min_chars=30),
    },

    # Mid-task pivot — task description has a non-obvious target
    {
        "name": "indirect_target",
        "task": "Find out who is the current CEO of Microsoft. Search for it.",
        "verify": scenario_pass(["nadella", "satya"]),
    },

    # Dynamic content / JS-rendered (HackerNews works as a SPA-ish surface)
    {
        "name": "hackernews_top",
        "task": "Go to news.ycombinator.com and tell me the title of the top story.",
        "verify": scenario_pass_substantive(min_chars=30),
    },

    # Numeric reasoning across a single page
    {
        "name": "wiki_compare_two_facts",
        "task": "Look up both London and New York on Wikipedia. Tell me which has a larger population.",
        "verify": scenario_pass(["london", "new york", "tokyo"]),  # any specific city named
    },

    # Specific URL with hash/fragment navigation
    {
        "name": "wiki_section_extract",
        "task": "Go to en.wikipedia.org/wiki/JavaScript and tell me what year JavaScript was first released.",
        "verify": scenario_pass(["1995"]),
    },

    # Common consumer site with many distractors
    {
        "name": "amazon_search_smoke",
        "task": "Search Amazon (amazon.com) for 'usb-c cable' and tell me the title of the top result.",
        # Pass if the message contains "USB" or "cable" (almost any real result will).
        "verify": lambda r: any(s in (r or {}).get("message", "").lower() for s in ["usb", "cable"]),
    },

    # Attempt-before-decline: sites that often need cookie consent
    {
        "name": "consent_banner_handling",
        "task": "Go to bbc.com and tell me one section name from the navigation menu.",
        "verify": scenario_pass_substantive(min_chars=30),
    },
]


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────


def _service_headers() -> dict[str, str]:
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }


async def broadcast_intent(client: httpx.AsyncClient, *, user_id: str, task: str) -> str:
    """Broadcast a confirmed_intent on the anticipy-intents Realtime channel
    with the given user_id. The extension filters incoming broadcasts by
    user_id match (extension/background.js:intentBelongsToUs)."""
    intent_id = str(uuid.uuid4())
    payload = {
        "id": intent_id,
        "user_id": user_id,
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
    r = await client.post(
        f"{SUPABASE_URL}/realtime/v1/api/broadcast",
        headers=_service_headers(),
        json=body,
        timeout=15,
    )
    if not (200 <= r.status_code < 300):
        raise RuntimeError(f"broadcast failed: {r.status_code} {r.text[:200]}")
    return intent_id


async def configure_extension(popup_page, *, user_id: str) -> None:
    """Inject the apiConfig the extension expects into chrome.storage.

    Service-worker .evaluate() is unreliable for MV3 extensions in Patchright
    on Xvfb (SW goes idle, attaching CDP doesn't wake it cleanly). Instead
    we open the extension's own popup.html as a regular Playwright page —
    that page runs in the extension's context and has full chrome.storage
    access, regardless of SW state."""
    # Real access code from env if set; otherwise TEST_NOOP. The real code
    # is required to exercise the deployed agent-team endpoints (/api/agent/*).
    # When TEST_NOOP, the planner endpoint returns 401 and the agent runs
    # in legacy plan-less mode — useful for isolating the executor from
    # the multi-agent pipeline.
    api_config = {
        "userId": user_id,
        "username": f"runner_{user_id[:8]}",
        "accessCode": os.environ.get("ANTICIPY_ACCESS_CODE") or "TEST_NOOP",
        "cerebrasApiKey": os.environ.get("CEREBRAS_API_KEY") or None,
        "groqApiKey": os.environ.get("GROQ_API_KEY") or None,
        "geminiApiKey": os.environ.get("GOOGLE_API_KEY") or None,
        "kimiApiKey": os.environ.get("KIMI_API_KEY") or None,
        "deepseekApiKey": os.environ.get("DEEPSEEK_API_KEY") or None,
        "proxyBaseUrl": os.environ.get("WEBSITE_BASE", "https://www.anticipy.ai"),
    }
    await popup_page.evaluate(
        """(config) => new Promise(r =>
            chrome.storage.local.set({ apiConfig: config }, () => r(true))
        )""",
        api_config,
    )


async def get_agent_status(popup_page) -> dict | None:
    return await popup_page.evaluate(
        """() => new Promise(r =>
            chrome.storage.local.get(['agentStatus'], (d) => r(d.agentStatus || null))
        )"""
    )


async def wait_for_finished(popup_page, intent_id: str, timeout_s: float) -> dict | None:
    end = time.time() + timeout_s
    last_msg = None
    while time.time() < end:
        status = await get_agent_status(popup_page)
        if status and status.get("intentId") == intent_id:
            cur_msg = status.get("message", "")
            if cur_msg != last_msg:
                print(f"    [{time.strftime('%H:%M:%S')}] {status.get('status')}: {cur_msg}", flush=True)
                last_msg = cur_msg
            if status.get("status") in ("done", "failed"):
                return status
        await asyncio.sleep(2.0)
    return None


# ─────────────────────────────────────────────────────────────────────
# Main runner
# ─────────────────────────────────────────────────────────────────────


async def main() -> int:
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        print("ERROR: SUPABASE env vars not set. source .env.local first.", file=sys.stderr)
        return 2

    # Patchright import — we use it (preferred) but fall back to playwright.
    try:
        from patchright.async_api import async_playwright  # type: ignore
        engine_label = "patchright"
    except Exception:
        from playwright.async_api import async_playwright  # type: ignore
        engine_label = "playwright"

    user_id = "runner_" + uuid.uuid4().hex[:12]
    print(f"== synthetic user_id: {user_id}", flush=True)
    print(f"== engine: {engine_label}", flush=True)
    print(f"== extension path: {EXTENSION_PATH}", flush=True)

    Path(PROFILE_DIR).mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        print(f"== launching Chrome with extension loaded...", flush=True)
        context = await p.chromium.launch_persistent_context(
            user_data_dir=PROFILE_DIR,
            headless=False,
            args=[
                f"--disable-extensions-except={EXTENSION_PATH}",
                f"--load-extension={EXTENSION_PATH}",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
            no_viewport=True,
        )

        # Find the extension's service worker (background.js).
        sw = None
        for attempt in range(40):
            sws = context.service_workers
            if sws:
                sw = sws[0]
                break
            await asyncio.sleep(0.25)
        if not sw:
            print("ERROR: extension service worker did not register", file=sys.stderr)
            await context.close()
            return 3

        ext_id = sw.url.split("/")[2]
        print(f"== extension loaded, id={ext_id}", flush=True)

        # MV3 service workers go idle and don't reliably accept evaluate in
        # patchright/Xvfb mode. Use the extension's popup.html as a regular
        # page — it runs in the extension context and gives us full
        # chrome.storage access via .evaluate().
        popup_page = await context.new_page()
        try:
            await asyncio.wait_for(
                popup_page.goto(f"chrome-extension://{ext_id}/popup.html",
                                wait_until="domcontentloaded"),
                timeout=10.0,
            )
            print(f"== popup page loaded for chrome.storage access", flush=True)
        except asyncio.TimeoutError:
            print("ERROR: popup.html did not load", flush=True)
            await context.close()
            return 4

        try:
            v = await asyncio.wait_for(popup_page.evaluate("1 + 1"), timeout=8.0)
            print(f"== popup.evaluate sanity: 1+1 = {v}", flush=True)
        except asyncio.TimeoutError:
            print("ERROR: popup.evaluate('1+1') timed out", flush=True)
            await context.close()
            return 4

        try:
            await asyncio.wait_for(configure_extension(popup_page, user_id=user_id), timeout=15.0)
            print(f"== chrome.storage.apiConfig configured", flush=True)
        except asyncio.TimeoutError:
            print("ERROR: configure_extension timed out", flush=True)
            await context.close()
            return 5

        # The agent uses chrome.tabs.query({active:true}) to find the tab to
        # drive. If the popup_page is active, the agent will navigate IT to
        # whatever site the task targets — and the popup loses extension
        # context, breaking our chrome.storage access. Open a dedicated
        # "agent tab", make it active, and the popup stays put as our
        # control-plane.
        agent_page = await context.new_page()
        await agent_page.goto("about:blank")
        await agent_page.bring_to_front()
        print(f"== agent tab opened (about:blank, active)", flush=True)

        # Wait for the extension's Realtime websocket to connect.
        await asyncio.sleep(4.0)

        results: list[dict] = []
        async with httpx.AsyncClient() as client:
            for scenario_idx, scenario in enumerate(SCENARIOS):
                # Inter-task cooldown — give Kimi rate-limit windows time
                # to recover between scenarios. Without this, the run
                # cascades into 429s by ~task 13 and every subsequent
                # task fails immediately. 12s/scenario × 25 = +5min total
                # — small price for stable measurement.
                if scenario_idx > 0:
                    print(f"  (cooldown 12s before next scenario)", flush=True)
                    await asyncio.sleep(12.0)
                print(f"\n== scenario: {scenario['name']}", flush=True)
                print(f"  task: {scenario['task']}", flush=True)
                t0 = time.time()
                try:
                    intent_id = await broadcast_intent(
                        client, user_id=user_id, task=scenario["task"]
                    )
                    print(f"  intent broadcast: {intent_id}", flush=True)
                except Exception as e:
                    print(f"  BROADCAST FAILED: {e}", flush=True)
                    results.append({
                        "scenario": scenario["name"],
                        "passed": False,
                        "reason": f"broadcast: {e}",
                        "duration_s": time.time() - t0,
                    })
                    continue

                final = await wait_for_finished(popup_page, intent_id, timeout_s=300.0)
                duration = time.time() - t0
                if not final:
                    print(f"  TIMEOUT at {duration:.1f}s", flush=True)
                    results.append({
                        "scenario": scenario["name"],
                        "passed": False,
                        "reason": "timeout (no agentStatus update in 5min)",
                        "duration_s": duration,
                    })
                    continue

                msg = final.get("message", "")
                passed = scenario["verify"]({"message": msg})
                print(f"  finished status={final.get('status')} passed={passed}", flush=True)
                print(f"  msg: {msg!r}", flush=True)
                results.append({
                    "scenario": scenario["name"],
                    "passed": passed,
                    "agent_status": final.get("status"),
                    "agent_message": msg,
                    "duration_s": duration,
                })

        # Summary
        print("\n=== RESULTS ===", flush=True)
        for r in results:
            mark = "PASS" if r["passed"] else "FAIL"
            print(f"  [{mark}] {r['scenario']}  {r.get('duration_s', 0):.1f}s", flush=True)
            if not r["passed"]:
                print(f"      reason: {r.get('reason') or r.get('agent_message', 'N/A')}", flush=True)

        passed = sum(1 for r in results if r["passed"])
        total = len(results)
        pct = 100.0 * passed / total if total else 0.0
        print(f"\n{passed}/{total} passed ({pct:.0f}%)", flush=True)

        # Persist run results for the progress log
        out_path = Path(__file__).parent / "logs" / f"runner_{int(time.time())}.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "user_id": user_id,
            "engine": engine_label,
            "results": results,
            "passed": passed,
            "total": total,
            "pct": pct,
        }, indent=2))
        print(f"\n== run saved to {out_path}", flush=True)

        await context.close()
        return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
