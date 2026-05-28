"""
Extension torture test — loads the unpacked Anticipy extension into headed
Chromium via Playwright, drives intents through the real Supabase Realtime
wire, and judges completion with an LLM.

Same hardening philosophy as test_torture_proactive.py:
- Generate adversarial scenarios via LLM
- Drive the production wire (no test-only side channels)
- LLM-as-judge per scenario
- Generic-only — no keyword tables, no per-site code

Run:
    cd engine && DISPLAY=:99 python test_torture_extension.py [N]

N = scenarios per category (default 1). 9 categories.
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
SUPABASE_ANON = os.environ["NEXT_PUBLIC_SUPABASE_ANON_KEY"]
SUPABASE_SERVICE = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
GEMINI_KEY = os.environ.get("GOOGLE_API_KEY")
GROQ_KEY = os.environ.get("GROQ_API_KEY")
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash:generateContent"
)


# ---------------------------------------------------------------------------
# Gemini helpers
# ---------------------------------------------------------------------------

async def _gemini_json(system: str, user: str, max_tokens: int = 4096) -> dict:
    payload = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": max_tokens,
            "responseMimeType": "application/json",
        },
    }
    async with httpx.AsyncClient(timeout=120) as c:
        for attempt in range(3):
            r = await c.post(f"{GEMINI_URL}?key={GEMINI_KEY}", json=payload)
            if r.status_code == 200:
                try:
                    txt = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                    return json.loads(txt)
                except Exception:
                    if attempt == 2:
                        raise
                    await asyncio.sleep(2)
            else:
                if attempt == 2:
                    raise RuntimeError(f"gemini {r.status_code}: {r.text[:200]}")
                await asyncio.sleep(2)
    raise RuntimeError("gemini exhausted retries")


# ---------------------------------------------------------------------------
# Supabase helpers (REST)
# ---------------------------------------------------------------------------

def _service_headers() -> dict:
    return {
        "apikey": SUPABASE_SERVICE,
        "Authorization": f"Bearer {SUPABASE_SERVICE}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


async def _supabase_insert_intent(intent: dict) -> dict:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            f"{SUPABASE_URL}/rest/v1/anticipy_intents",
            headers=_service_headers(),
            json=intent,
        )
        if r.status_code not in (200, 201):
            raise RuntimeError(f"insert {r.status_code}: {r.text[:300]}")
        return r.json()[0]


async def _supabase_update_status(intent_id: str, status: str) -> None:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.patch(
            f"{SUPABASE_URL}/rest/v1/anticipy_intents?id=eq.{intent_id}",
            headers=_service_headers(),
            json={"status": status},
        )
        if r.status_code not in (200, 204):
            raise RuntimeError(f"update {r.status_code}: {r.text[:300]}")


async def _supabase_get_intent(intent_id: str) -> dict | None:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(
            f"{SUPABASE_URL}/rest/v1/anticipy_intents?id=eq.{intent_id}&select=*",
            headers=_service_headers(),
        )
        if r.status_code != 200:
            return None
        rows = r.json()
        return rows[0] if rows else None


async def _supabase_delete_intent(intent_id: str) -> None:
    async with httpx.AsyncClient(timeout=30) as c:
        await c.delete(
            f"{SUPABASE_URL}/rest/v1/anticipy_intents?id=eq.{intent_id}",
            headers=_service_headers(),
        )


# ---------------------------------------------------------------------------
# Scenario generation
# ---------------------------------------------------------------------------

CATEGORIES = [
    "canvas_editor",
    "webgl_or_map",
    "shadow_dom",
    "multi_field_form",
    "autocomplete",
    "lazy_load",
    "login_wall",
    "multi_step",
    "ambiguous_goal",
]

GEN_SYSTEM = """You generate ONE adversarial test for the Anticipy Chrome extension's browser agent.

The extension runs inside the user's real Chrome on a public website. The user \
never types — the task is delivered as an "intent" the user just confirmed. \
The agent receives:
  summary_for_user: short natural-language statement of the task
  action_type: short verb-noun like "search_google", "fill_form", "edit_doc"
  parameters: structured args the agent should use

Return ONE JSON object:
{
  "category": "<exact category from list>",
  "summary_for_user": "<the natural-language goal>",
  "action_type": "<short verb-noun>",
  "parameters": { ...structured args needed... },
  "starting_url": "<real public URL the extension should be navigated to first>",
  "success_criteria": "<concrete check on the page state or extension's final message>",
  "fail_modes": ["...", "..."],
  "expected_capability": "<one of: force_type, canvas_type, pierce_query, canvas_pointer, generic_click_type, scroll_then_extract, graceful_decline>"
}

CRITICAL
- starting_url must be reachable today, free, no login required, no payment.
- The task must be POSSIBLE in a real browser — don't ask for things that need 2FA or a logged-in session.
- For login_wall pick a site that intentionally blocks: success = the agent declines cleanly without faking.
- For canvas_editor pick a public template URL or a Sheets demo doc that's editable / view-only.
- For webgl_or_map pick openstreetmap.org / google maps / a 3D viewer.
- For shadow_dom pick a site with web components — youtube.com, salesforce.com help, ionicframework.com.
"""

GEN_USER = "Generate an adversarial scenario for category: {category}"


async def _generate_scenario(category: str) -> dict:
    s = await _gemini_json(GEN_SYSTEM, GEN_USER.format(category=category), max_tokens=2048)
    s.setdefault("category", category)
    return s


# ---------------------------------------------------------------------------
# Run one scenario
# ---------------------------------------------------------------------------

TEST_USER_ID = f"torture_{uuid.uuid4().hex[:8]}"


async def _run_scenario(scenario: dict, page, timeout_s: int = 180) -> dict:
    intent_id = str(uuid.uuid4())
    row = {
        "id": intent_id,
        "session_id": str(uuid.uuid4()),
        "summary_for_user": scenario.get("summary_for_user", "")[:300],
        "action_type": scenario.get("action_type", "browser_action"),
        "parameters": scenario.get("parameters", {}),
        "status": "pending",
        "confidence": 0.95,
        "importance": "standard",
        "evidence_quote": f"torture-test:{TEST_USER_ID}",
    }

    print(f"  Inserting intent {intent_id[:8]}…", flush=True)
    try:
        await _supabase_insert_intent(row)
    except Exception as e:
        return {"scenario": scenario, "error": f"insert failed: {e}", "outcome": "infra_error"}

    # Navigate to the starting URL so the extension's content script + active tab
    # are aligned. Without this, agent's first action (chrome.tabs.update) does
    # the navigation, which is fine — but pointing first lets the warm content
    # script fire faster.
    start_url = scenario.get("starting_url", "https://www.google.com/")
    try:
        await page.goto(start_url, timeout=20_000, wait_until="domcontentloaded")
    except Exception:
        pass  # extension can navigate itself

    await asyncio.sleep(1.0)

    # Trigger the agent: PATCH status to confirmed
    print("  Confirming intent (UPDATE→confirmed)…", flush=True)
    try:
        await _supabase_update_status(intent_id, "confirmed")
    except Exception as e:
        await _supabase_delete_intent(intent_id)
        return {"scenario": scenario, "error": f"update failed: {e}", "outcome": "infra_error"}

    # Poll for terminal status
    print("  Waiting for extension to finish…", flush=True)
    final = None
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        await asyncio.sleep(3)
        row = await _supabase_get_intent(intent_id)
        if not row:
            continue
        status = row.get("status", "")
        if status in ("completed", "failed", "error"):
            final = row
            break

    if final is None:
        # Timeout — capture whatever the row looks like now
        final = await _supabase_get_intent(intent_id) or {}
        final["__timeout__"] = True

    # Cleanup
    try:
        await _supabase_delete_intent(intent_id)
    except Exception:
        pass

    return {
        "scenario": scenario,
        "intent_id": intent_id,
        "final_row": final,
        "outcome": (
            "completed" if final.get("status") == "completed" else
            "failed" if final.get("status") == "failed" else
            "timeout" if final.get("__timeout__") else
            "unknown"
        ),
    }


# ---------------------------------------------------------------------------
# Judge
# ---------------------------------------------------------------------------

JUDGE_SYSTEM = """You are an impartial judge for the Anticipy extension's browser agent.

You see ONE scenario and the final intent row state (status, result_message, errors).

Return JSON:
{ "verdict": "pass" | "partial" | "fail",
  "reason": "<one sentence>",
  "missing": "<what's missing if not pass, else empty>" }

Rules:
- pass: status==completed AND the result_message clearly addresses success_criteria.
- For login_wall category: pass if status==failed AND the message cleanly identifies a login wall (no fake success).
- partial: most of the goal addressed but at least one explicit field missing.
- fail: status timed out, status=error, hallucinated values, claim-of-success that doesn't match success_criteria.
- Never invent. Don't penalize verbose. Only penalize wrong / missing / fake.
"""


async def _judge(run: dict) -> dict:
    s = run["scenario"]
    f = run.get("final_row") or {}
    payload = {
        "category": s.get("category"),
        "summary_for_user": s.get("summary_for_user"),
        "success_criteria": s.get("success_criteria"),
        "fail_modes": s.get("fail_modes", []),
        "intent_status": f.get("status"),
        "result_message": f.get("result_message") or f.get("message") or "",
        "errors": f.get("error_message") or "",
        "outcome": run["outcome"],
    }
    return await _gemini_json(JUDGE_SYSTEM, json.dumps(payload, indent=2), max_tokens=512)


# ---------------------------------------------------------------------------
# Extension launch
# ---------------------------------------------------------------------------

async def _launch_with_extension(playwright_inst):
    """Launch persistent context with the unpacked Anticipy extension loaded.
    Returns (context, page)."""
    profile_dir = f"/tmp/torture_ext_profile_{uuid.uuid4().hex[:8]}"
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

    ctx = await playwright_inst.chromium.launch_persistent_context(
        user_data_dir=profile_dir,
        headless=False,
        args=args,
        viewport={"width": 1280, "height": 800},
    )

    # Pre-seed API keys in the extension's storage so its agent has a working
    # apiConfig without needing to go through the popup auth flow.
    await _seed_extension_keys(ctx)

    pages = ctx.pages
    page = pages[0] if pages else await ctx.new_page()
    return ctx, page, profile_dir


async def _seed_extension_keys(ctx) -> None:
    """Drop GROQ + GEMINI keys into chrome.storage.local for the extension.
    Done by opening any extension page (popup or background SW) and calling
    chrome.storage.local.set in its context."""
    # Wait briefly for the service worker to register
    await asyncio.sleep(2)

    # Find the extension ID from the loaded service worker URL
    ext_id = None
    for sw in ctx.service_workers:
        url = sw.url
        if url.startswith("chrome-extension://"):
            ext_id = url.split("/")[2]
            break
    if not ext_id:
        # Some Playwright/Chromium versions register lazily — wait + retry
        for _ in range(8):
            await asyncio.sleep(1)
            for sw in ctx.service_workers:
                url = sw.url
                if url.startswith("chrome-extension://"):
                    ext_id = url.split("/")[2]
                    break
            if ext_id:
                break
    if not ext_id:
        print("  WARN: could not find extension service worker; skipping key seeding")
        return

    # Open the extension's popup.html (it has chrome API access) and inject keys
    page = await ctx.new_page()
    try:
        await page.goto(f"chrome-extension://{ext_id}/popup.html", timeout=15_000)
        await page.evaluate(
            """
            (cfg) => new Promise((res) => {
              try {
                chrome.storage.local.set({
                  apiConfig: { groqApiKey: cfg.groq, geminiApiKey: cfg.gemini },
                  accessAuthorized: true,
                }, () => res(true));
              } catch (e) { res(false); }
            })
            """,
            {"groq": GROQ_KEY or "", "gemini": GEMINI_KEY or ""},
        )
        print(f"  Seeded API keys in extension {ext_id[:12]}…")
    except Exception as e:
        print(f"  WARN: could not seed keys: {e}")
    finally:
        await page.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main(per_category: int = 1) -> int:
    print(f"Generating {per_category * len(CATEGORIES)} scenarios…", flush=True)
    scenarios: list[dict] = []
    for cat in CATEGORIES:
        for _ in range(per_category):
            try:
                s = await _generate_scenario(cat)
                scenarios.append(s)
                print(f"  [{cat}] {s.get('summary_for_user','')[:80]}", flush=True)
            except Exception as e:
                print(f"  [{cat}] generation failed: {e}", flush=True)

    print(f"\nLaunching Chrome with extension loaded…\n", flush=True)
    runs: list[dict] = []
    profile_dir = None
    async with async_playwright() as p:
        ctx, page, profile_dir = await _launch_with_extension(p)
        try:
            for i, sc in enumerate(scenarios, 1):
                print(f"\n=== {i}/{len(scenarios)} [{sc.get('category')}] {sc.get('summary_for_user','')[:90]} ===", flush=True)
                run = await _run_scenario(sc, page)
                try:
                    verdict = await _judge(run)
                except Exception as e:
                    verdict = {"verdict": "fail", "reason": f"judge error: {e}"}
                run["verdict"] = verdict
                runs.append(run)
                v = verdict.get("verdict", "fail")
                print(f"  → {v.upper()}: {verdict.get('reason','')[:120]}", flush=True)
        finally:
            try:
                await ctx.close()
            except Exception:
                pass
            if profile_dir and os.path.isdir(profile_dir):
                import shutil
                shutil.rmtree(profile_dir, ignore_errors=True)

    # Aggregate
    by_cat: dict[str, dict] = {}
    for r in runs:
        c = r["scenario"].get("category", "?")
        v = r.get("verdict", {}).get("verdict", "fail")
        d = by_cat.setdefault(c, {"pass": 0, "partial": 0, "fail": 0, "total": 0})
        d[v if v in ("pass", "partial", "fail") else "fail"] += 1
        d["total"] += 1

    print("\n" + "=" * 70)
    print("EXTENSION TORTURE — RESULTS BY CATEGORY")
    print("=" * 70)
    tp = tpa = tf = 0
    for c, d in sorted(by_cat.items()):
        tp += d["pass"]; tpa += d["partial"]; tf += d["fail"]
        print(f"  {c:22s}  pass={d['pass']:>2}  partial={d['partial']:>2}  fail={d['fail']:>2}  /{d['total']}")
    grand = tp + tpa + tf
    pct = 100.0 * tp / grand if grand else 0.0
    print("-" * 70)
    print(f"  TOTAL: pass={tp}  partial={tpa}  fail={tf}  ({pct:.1f}% strict pass)")

    out = Path("/tmp/torture_extension_detail.json")
    out.write_text(json.dumps(
        [{
            "category": r["scenario"].get("category"),
            "summary": r["scenario"].get("summary_for_user"),
            "outcome": r.get("outcome"),
            "verdict": r.get("verdict", {}).get("verdict"),
            "reason": r.get("verdict", {}).get("reason"),
            "missing": r.get("verdict", {}).get("missing"),
            "result_msg": (r.get("final_row") or {}).get("result_message", "")[:400],
        } for r in runs],
        indent=2,
    ))
    print(f"\nDetail: {out}")

    return 0 if grand and tp == grand else 1


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    raise SystemExit(asyncio.run(main(per_category=n)))
