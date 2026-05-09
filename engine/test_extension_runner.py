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


def scenario_pass(needles: list[str]) -> Callable[[dict], bool]:
    """Build a verifier that requires AT LEAST ONE of the needles in the
    agent's final message (case-insensitive)."""
    lows = [n.lower() for n in needles]

    def verify(result: dict) -> bool:
        msg = (result or {}).get("message", "") or ""
        msg = msg.lower()
        return any(n in msg for n in lows)

    return verify


SCENARIOS: list[dict[str, Any]] = [
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
    api_config = {
        "userId": user_id,
        "username": f"runner_{user_id[:8]}",
        "accessCode": "TEST_NOOP",
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
            for scenario in SCENARIOS:
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
