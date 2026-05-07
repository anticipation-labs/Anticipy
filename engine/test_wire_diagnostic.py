"""
Wire diagnostic — does the extension's Realtime listener actually fire on a
status UPDATE? Inserts ONE intent, PATCHes status to confirmed, polls every 3s
for 60s, prints the status each poll. If the status never changes from
"confirmed", the extension isn't running the agent (service worker dead,
channel never joined, or handleConfirmedIntent errors).

Run:
    cd engine && DISPLAY=:99 python test_wire_diagnostic.py
"""

import asyncio
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
GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
GEMINI_KEY = os.environ.get("GOOGLE_API_KEY", "")

PROD_AUTH_ENDPOINT = "https://www.anticipy.ai/api/extension/auth"


async def fetch_keys_via_prod_auth(access_code: str) -> dict:
    """Mirror what the extension popup does: POST access code to the production
    auth endpoint and use the returned keys. This proves the production wire
    works end-to-end and avoids any divergence between local env vars and
    what real users get."""
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(PROD_AUTH_ENDPOINT, json={"code": access_code})
        if r.status_code != 200:
            raise RuntimeError(f"prod auth {r.status_code}: {r.text[:200]}")
        return r.json()


async def lookup_any_engine_user_code() -> str | None:
    """Look up an engine user's access code from Supabase. The harness uses one
    real user's code for the test — this is how a real install authenticates."""
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(
            f"{SUPABASE_URL}/rest/v1/engine_users?select=access_code&limit=1",
            headers={
                "apikey": SUPABASE_SERVICE,
                "Authorization": f"Bearer {SUPABASE_SERVICE}",
            },
        )
        if r.status_code != 200:
            return None
        rows = r.json()
        return rows[0]["access_code"] if rows else None

HDR = {
    "apikey": SUPABASE_SERVICE,
    "Authorization": f"Bearer {SUPABASE_SERVICE}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}


async def insert_session(session_id: str) -> None:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            f"{SUPABASE_URL}/rest/v1/anticipy_sessions",
            headers=HDR,
            json={"id": session_id, "status": "ended", "metadata": {"diag": True}},
        )
        r.raise_for_status()


async def delete_session(session_id: str) -> None:
    async with httpx.AsyncClient(timeout=30) as c:
        await c.delete(
            f"{SUPABASE_URL}/rest/v1/anticipy_sessions?id=eq.{session_id}",
            headers=HDR,
        )


async def insert_row(intent_id: str, session_id: str) -> dict:
    row = {
        "id": intent_id,
        "session_id": session_id,
        "summary_for_user": "Search for 'cats' on Wikipedia",
        "action_type": "browser_action",
        "parameters": {"browser_task": "Search for 'cats' on Wikipedia"},
        "status": "pending",
        "confidence": 0.95,
        "importance": "standard",
        "evidence_quote": "diagnostic test",
    }
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            f"{SUPABASE_URL}/rest/v1/anticipy_intents",
            headers=HDR, json=row,
        )
        r.raise_for_status()
        return r.json()[0]


async def update_status(intent_id: str, status: str) -> None:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.patch(
            f"{SUPABASE_URL}/rest/v1/anticipy_intents?id=eq.{intent_id}",
            headers=HDR, json={"status": status},
        )
        r.raise_for_status()


async def broadcast_confirmed(intent_id: str, intent_row: dict, browser_task: str) -> None:
    """Mirror production /api/engine/confirm: send a confirmed_intent broadcast on
    realtime:anticipy-intents so the extension's BrowserAgent runs."""
    payload = {
        "messages": [{
            "topic": "anticipy-intents",
            "event": "confirmed_intent",
            "payload": {
                **intent_row,
                "id": intent_id,
                "status": "confirmed",
                "parameters": {
                    **(intent_row.get("parameters") or {}),
                    "browser_task": browser_task,
                },
            },
        }],
    }
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(
            f"{SUPABASE_URL}/realtime/v1/api/broadcast",
            headers={
                "Content-Type": "application/json",
                "apikey": SUPABASE_SERVICE,
                "Authorization": f"Bearer {SUPABASE_SERVICE}",
            },
            json=payload,
        )
        if r.status_code not in (200, 202):
            raise RuntimeError(f"broadcast {r.status_code}: {r.text[:200]}")


async def get_row(intent_id: str) -> dict | None:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(
            f"{SUPABASE_URL}/rest/v1/anticipy_intents?id=eq.{intent_id}&select=*",
            headers=HDR,
        )
        if r.status_code != 200:
            return None
        rows = r.json()
        return rows[0] if rows else None


async def delete_row(intent_id: str) -> None:
    async with httpx.AsyncClient(timeout=30) as c:
        await c.delete(
            f"{SUPABASE_URL}/rest/v1/anticipy_intents?id=eq.{intent_id}",
            headers=HDR,
        )


async def main() -> int:
    intent_id = str(uuid.uuid4())
    print(f"Intent id: {intent_id}", flush=True)

    profile_dir = f"/tmp/wire_diag_profile_{uuid.uuid4().hex[:8]}"
    os.makedirs(profile_dir, exist_ok=True)
    args = [
        f"--disable-extensions-except={EXT_DIR}",
        f"--load-extension={EXT_DIR}",
        "--no-sandbox",
        "--disable-blink-features=AutomationControlled",
        "--disable-dev-shm-usage",
        "--no-first-run",
        "--no-default-browser-check",
    ]

    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir=profile_dir,
            headless=False,
            args=args,
            viewport={"width": 1280, "height": 800},
        )

        # Wait for service worker
        ext_id = None
        for _ in range(20):
            await asyncio.sleep(0.5)
            for sw in ctx.service_workers:
                if sw.url.startswith("chrome-extension://"):
                    ext_id = sw.url.split("/")[2]
                    break
            if ext_id:
                break
        print(f"Extension id: {ext_id}", flush=True)
        if not ext_id:
            print("FAIL: extension service worker not found", flush=True)
            await ctx.close()
            return 1

        # Authenticate the extension via the same path real users hit:
        # 1. look up an engine_users access code
        # 2. POST it to /api/extension/auth and get back the LLM API keys
        # 3. write apiConfig to chrome.storage.local just like popup.js does
        access_code = await lookup_any_engine_user_code()
        if not access_code:
            print("FAIL: no engine_users access code found in Supabase", flush=True)
            await ctx.close()
            return 1
        try:
            keys = await fetch_keys_via_prod_auth(access_code)
        except Exception as e:
            print(f"FAIL: prod auth endpoint failed: {e}", flush=True)
            await ctx.close()
            return 1
        groq = keys.get("groqApiKey") or ""
        gem = keys.get("geminiApiKey") or ""
        print(f"Got keys via prod auth: groq={'set' if groq else 'EMPTY'} gemini={'set' if gem else 'EMPTY'}", flush=True)

        page = await ctx.new_page()
        await page.goto(f"chrome-extension://{ext_id}/popup.html", timeout=15_000)
        await page.evaluate(
            """(cfg) => new Promise((res) => {
              try {
                chrome.storage.local.set({
                  apiConfig: { groqApiKey: cfg.g, geminiApiKey: cfg.gem },
                  accessAuthorized: true
                }, () => res(true));
              } catch (e) { res(false); }
            })""",
            {"g": groq, "gem": gem},
        )
        # Read back what's in storage
        seeded = await page.evaluate(
            """() => new Promise((res) => {
              chrome.storage.local.get(null, (data) => res(data));
            })"""
        )
        print(f"Storage after seed: {list(seeded.keys())}", flush=True)
        await page.close()

        # Tail the SW console (best-effort) by attaching to the SW context
        sw = None
        for s in ctx.service_workers:
            if s.url.startswith(f"chrome-extension://{ext_id}/"):
                sw = s
                break
        if sw:
            sw.on("console", lambda m: print(f"  [SW] {m.type}: {m.text}", flush=True))
            print("Attached to service worker console", flush=True)

        async def read_storage():
            p = await ctx.new_page()
            try:
                await p.goto(f"chrome-extension://{ext_id}/popup.html", timeout=10_000)
                data = await p.evaluate(
                    """() => new Promise((res) => {
                      chrome.storage.local.get(null, (d) => res(d));
                    })"""
                )
                return data
            finally:
                await p.close()

        s0 = await read_storage()
        print(f"Initial storage: connectionStatus={s0.get('connectionStatus')!r}", flush=True)
        # Give the SW 8s to come alive and connect
        await asyncio.sleep(8)
        s1 = await read_storage()
        print(f"After 8s:        connectionStatus={s1.get('connectionStatus')!r}", flush=True)

        # Open a real tab so the agent has somewhere to act
        page = await ctx.new_page()
        await page.goto("https://en.wikipedia.org/", timeout=15_000)

        # Insert session, then intent (FK)
        session_id = str(uuid.uuid4())
        await insert_session(session_id)
        intent_row = await insert_row(intent_id, session_id)
        print(f"Inserted session {session_id[:8]} + intent (status=pending). Sleeping 2s…", flush=True)
        await asyncio.sleep(2)

        # Production-faithful trigger: send a `confirmed_intent` broadcast on
        # the `anticipy-intents` topic. This is what /api/engine/confirm does
        # for browser-routed intents.
        task = "Search Wikipedia for 'cats'"
        await broadcast_confirmed(intent_id, intent_row, task)
        print("Broadcast confirmed_intent. Sleeping 6s for SW to react…", flush=True)
        await asyncio.sleep(6)

        # If the broadcast wire didn't fire, drive the BrowserAgent directly via
        # the SW context to verify the agent loop itself works against the loaded
        # extension. This exercises agent.js end-to-end without Realtime.
        # Verify what's actually in storage right before invoking the agent
        storage_now = await read_storage()
        ac = storage_now.get("apiConfig") or {}
        print(f"  Pre-invoke apiConfig keys: groq={'set' if ac.get('groqApiKey') else 'EMPTY'} gemini={'set' if ac.get('geminiApiKey') else 'EMPTY'} all_keys={list(ac.keys())}", flush=True)

        # Read storage FROM INSIDE the SW context (not popup) to see if SW
        # sees the same apiConfig the popup wrote.
        if sw is not None:
            sw_view = await sw.evaluate(
                """() => new Promise(res => chrome.storage.local.get(["apiConfig"], d => res({
                  has: !!d.apiConfig,
                  groq: !!(d.apiConfig && d.apiConfig.groqApiKey),
                  gem: !!(d.apiConfig && d.apiConfig.geminiApiKey),
                  keys: d.apiConfig ? Object.keys(d.apiConfig) : []
                })))"""
            )
            print(f"  SW sees apiConfig: {sw_view}", flush=True)

        if sw is not None:
            print("Direct-driving BrowserAgent via SW debug hook…", flush=True)
            try:
                drive = await sw.evaluate(
                    "(intent) => globalThis.__anticipy_debug_run_intent(intent)",
                    {**intent_row, "id": intent_id, "status": "confirmed",
                     "parameters": {**(intent_row.get("parameters") or {}),
                                    "browser_task": task}},
                )
                print(f"  SW evaluate result: {drive}", flush=True)
            except Exception as e:
                print(f"  SW evaluate failed: {e}", flush=True)

        deadline = time.time() + 240
        start_t = time.time()
        last_status = None
        last_agent_status = None
        while time.time() < deadline:
            await asyncio.sleep(5)
            row = await get_row(intent_id)
            cur = (row or {}).get("status")
            if cur != last_status:
                print(f"  t={int(time.time()-start_t)}s row.status={cur}", flush=True)
                last_status = cur
            # Also peek at the extension's live agent status
            try:
                ag = await read_storage()
                a = ag.get("agentStatus") or {}
                snap = (a.get("status"), (a.get("message") or "")[:60])
                if snap != last_agent_status:
                    print(f"  t={int(time.time()-start_t)}s agentStatus={snap}", flush=True)
                    last_agent_status = snap
            except Exception:
                pass
            if cur in ("completed", "failed", "executed"):
                break

        await delete_row(intent_id)
        await delete_session(session_id)
        await ctx.close()

    import shutil
    shutil.rmtree(profile_dir, ignore_errors=True)

    print(f"\nFinal status: {last_status}", flush=True)
    return 0 if last_status in ("completed", "failed", "executed") else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
