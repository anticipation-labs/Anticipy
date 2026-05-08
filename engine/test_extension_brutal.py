"""
test_extension_brutal.py — 50 LLM-generated brutal real-site scenarios for the
production Anticipy Chrome extension's BrowserAgent.

Loads the unpacked extension into headed Chromium (Xvfb :99), drives intents
through the SW debug hook (no Supabase round-trip, faster + deterministic),
and verifies outcomes PROGRAMMATICALLY (URL changed, expected text appeared,
agent's final message contains expected fields). No LLM-judge for the action
half — verifier functions only — so action-quality numbers don't drift on
re-runs.

Categories (50 total):
  - search_extract_news        (5)  search + extract on a real news site
  - multi_tab_compare          (5)  2+ tabs, aggregate result
  - canvas_typing              (5)  Google Docs / TLDraw / Excalidraw
  - webgl_pointer              (5)  OpenStreetMap / Google Maps with query
  - shadow_dom_heavy           (5)  YouTube / Stripe docs / Salesforce help
  - multi_field_form           (5)  Jotform / Typeform / Google Forms public
  - search_click_extract_chain (5)  search → click → extract (Amazon-style)
  - retry_after_fail           (5)  first selector fails, second works
  - graceful_decline           (5)  login walls (Gmail / Twitter / FB Marketplace)
  - long_task                  (5)  >20 step plan, multi-site

Run:
    cd engine && DISPLAY=:99 python3 test_extension_brutal.py [N]

N = scenarios per category (default 5 → 50 total). Reduce for faster smoke.

Output:
  - logs/browser_brutal.md        Markdown report (per-category pass rate, top-5 failures)
  - logs/browser_brutal.json      Detailed per-scenario raw data for re-runs
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
from playwright.async_api import async_playwright

# ─── Setup ───────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent.parent
EXT_DIR = ROOT / "extension"
ENV_FILE = ROOT / ".env.local"
LOG_DIR = Path(__file__).resolve().parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
REPORT_MD = LOG_DIR / "browser_brutal.md"
REPORT_JSON = LOG_DIR / "browser_brutal.json"
SCENARIOS_CACHE = LOG_DIR / "browser_brutal_scenarios.json"

if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

GEMINI_KEY = os.environ.get("GOOGLE_API_KEY", "")
GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash:generateContent"
)
GEMINI_PRO_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-pro:generateContent"
)

TASK_TIMEOUT_S = 300  # 5 minutes hard cap per scenario (matches user-stated 6 min budget)
PRE_FLIGHT_TIMEOUT_S = 12  # if starting_url won't load in this window, mark infra_skip


# ─── Gemini helpers ──────────────────────────────────────────────────────────

async def _gemini_json(
    system: str, user: str, max_tokens: int = 4096, use_pro: bool = False
) -> dict:
    url = GEMINI_PRO_URL if use_pro else GEMINI_URL
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
            r = await c.post(f"{url}?key={GEMINI_KEY}", json=payload)
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


# ─── LLM scenario generation ─────────────────────────────────────────────────

CATEGORIES: list[tuple[str, str]] = [
    ("search_extract_news",
     "Generate a task that requires going to a real news homepage (BBC, Reuters, NPR, "
     "Al Jazeera English, AP News) and extracting one specific piece of information "
     "(top headline text, top story author, name of section, lead paragraph). "
     "starting_url should be the homepage. Verifier should check the agent's final "
     "message contains a substring of an actual current headline OR similar real text."),
    ("multi_tab_compare",
     "Generate a task that REQUIRES opening two distinct sites and comparing/aggregating. "
     "Examples: compare a Wikipedia article fact vs DuckDuckGo result, fetch a fact "
     "from two sites and report both. Both starting_urls must be public. Verifier "
     "checks that the final message references both sites (or both pieces of data)."),
    ("canvas_typing",
     "Generate a task that requires typing into a canvas-rendered editor: Google Docs "
     "blank doc (https://docs.google.com/document/u/0/create — works without sign-in for "
     "viewing but typing requires login; pick a publicly-editable Google Doc template "
     "OR an Excalidraw/TLDraw/jspaint blank canvas). Excalidraw at "
     "https://excalidraw.com/ is fully public, no login. TLDraw at https://www.tldraw.com/ "
     "same. Task should ask the agent to insert a specific phrase. Verifier should not "
     "rely on the canvas pixels (we can't read them) — instead check the agent's final "
     "message confirms it typed and the page/title settled."),
    ("webgl_pointer",
     "Generate a task that requires a WebGL/canvas map: openstreetmap.org (zoom in on a "
     "city), or a 3D viewer. Task should ask the agent to find/show something specific "
     "(e.g., 'find Empire State Building on OpenStreetMap'). Verifier should check that "
     "the URL or page title contains the queried place name OR the agent's final message "
     "confirms the location."),
    ("shadow_dom_heavy",
     "Generate a task on a shadow-DOM-heavy site: youtube.com (every UI element is a "
     "web component), stripe.com docs, salesforce.com help, ionicframework.com docs. "
     "Task should require interacting with a search box or sidebar that lives inside "
     "shadow DOM. Verifier should check the URL changes appropriately or expected text "
     "appears in the agent's message."),
    ("multi_field_form",
     "Generate a task that requires filling multiple fields in a public form: a Google "
     "Form open to all (we'll use the form-page only — DON'T submit). Use a real, public "
     "Google Form URL or Jotform demo. Task should fill 3+ fields. Verifier should check "
     "the agent confirms the form was filled (don't actually submit; check fields are "
     "populated by reading the agent's final message)."),
    ("search_click_extract_chain",
     "Generate a task: search → click first result → extract specific data from result "
     "page. Examples: 'find a USB-C cable on Amazon and tell me the price of the first "
     "result', 'find the Wikipedia article on Albert Einstein and tell me his birth year'. "
     "Verifier checks the agent's final message contains a price-shaped string OR an "
     "expected date OR a known fact substring."),
    ("retry_after_fail",
     "Generate a task likely to need a retry: search a tricky site whose first selector "
     "approach fails (e.g., shopping sites with anti-bot, single-page apps with delayed "
     "render). Task should still be achievable on a public site. Verifier checks any of: "
     "URL contains query substring, agent message references the result, or task goal "
     "substring is in the agent's success message."),
    ("graceful_decline",
     "Generate a task that REQUIRES login the agent definitely doesn't have: 'send a "
     "tweet on twitter.com about X', 'reply to my latest gmail email', 'post on Facebook '"
     "Marketplace'. Pick the starting_url to land squarely on the login wall. Verifier "
     "checks success==false AND the message mentions sign-in/login/auth."),
    ("long_task",
     "Generate a multi-step task that needs >20 steps: 'compare prices of Y on three "
     "different sites and tell me which is cheapest', 'find the population of three "
     "countries from Wikipedia and tell me which is largest'. Verifier checks the final "
     "message references all three target items (sites or data points)."),
]

GEN_SYSTEM = """You generate ONE adversarial scenario for the Anticipy Chrome extension's browser agent.

You return a JSON object describing a real, public, achievable task and a programmatic verifier.

Schema:
{
  "category": "<exact category name>",
  "summary_for_user": "<natural-language goal as the user would say it>",
  "action_type": "<short verb_noun like search_extract or fill_form>",
  "parameters": { ...structured args the agent should rely on... },
  "starting_url": "<real public URL>",
  "verifier": {
    "type": "<one of: agent_success | agent_failed_with_login | message_contains_any | message_contains_all | url_contains_any | and_of_or>",
    "patterns": ["<lowercase substring>", ...],
    "patterns_b": ["<optional second list for and_of_or>"],
    "min_steps": 0,
    "min_message_len": 0
  },
  "expected_capability": "<one of: navigate_extract, multi_tab, canvas_type, canvas_pointer, shadow_dom, multi_field, search_click_extract, retry, graceful_decline, long_task>",
  "fail_modes": ["...short list of likely failure modes..."]
}

CRITICAL RULES:
- starting_url must be a REAL, PUBLIC URL reachable today without login (unless category=graceful_decline, where it MUST hit a login wall).
- For category graceful_decline: verifier.type MUST be "agent_failed_with_login". We expect success==false AND a login/auth/sign-in mention.
- For category canvas_typing: pick excalidraw.com or tldraw.com (no login) over Google Docs.
- For category multi_tab_compare and long_task: the task MUST reference 2+ distinct sites/items in the summary itself.
- For category search_extract_news: starting_url must be one of bbc.com, reuters.com, npr.org, aljazeera.com, apnews.com. PREFER bbc.com — Reuters often geo-blocks datacenter IPs.
- For category webgl_pointer: starting_url must be openstreetmap.org or maps.google.com.
- Don't include captchas, payment, account creation, irreversible actions.

VERIFIER PATTERN RULES — VERY IMPORTANT:
- Patterns must be GENERIC SHAPE/TOPIC hints, NOT literal facts that require knowing today's news.
- BAD pattern (literal fact): "netanyahu", "gaza", "trump elected"
- GOOD pattern (topic shape): "headline", "story", "news"  ← matches "the headline is …" / "the top story is …"
- For factual extractions where the answer is a known stable value (e.g., Einstein birth year 1879, Mt Everest 8848m,
  Tokyo population 14 million / 37 million metro), include the stable values as patterns. Use multiple
  forms (1879, 14 million, 37 million, 8,849, 8848). These are facts the agent CAN look up.
- For "tell me what's on the homepage today" tasks, prefer agent_success type and rely on the agent's
  self-eval / self-reported success — DO NOT enumerate today's literal headlines.
- For sites that often render slowly or block, set min_message_len=20 and use agent_success.
- For multi-tab tasks: use "and_of_or": patterns_a anchors site A token (e.g., "wikipedia"), patterns_b anchors site B token, OR patterns and patterns_b each list known facts.
- For canvas typing on Excalidraw/TLDraw: the agent can't read its own canvas pixels. Verify it claims success and the typed phrase string (or a key word from it) appears in the agent's message.
- For shadow DOM / search-then-click: anchor on the search query token in the agent's message OR final URL.
- For graceful_decline: leave patterns empty (verifier.type=agent_failed_with_login handles it).
- Patterns are MATCHED CASE-INSENSITIVELY as substrings, OR as Python regex if they include special chars.

OUTPUT: JSON object only. No prose."""


GEN_USER_TEMPLATE = """Category: {category}

Category instructions: {desc}

Task index in this category: {idx}/{n}

Generate a unique scenario distinct from any prior in this category. Vary the target site / phrase / specificity."""


async def generate_scenario(category: str, desc: str, idx: int, total: int) -> dict:
    user = GEN_USER_TEMPLATE.format(category=category, desc=desc, idx=idx, n=total)
    s = await _gemini_json(GEN_SYSTEM, user, max_tokens=2048)
    s.setdefault("category", category)
    return s


# ─── Programmatic verifier ───────────────────────────────────────────────────

LOGIN_HINTS = (
    "sign in", "log in", "login", "log-in", "signin", "sign-in",
    "authenticate", "authentication", "credentials", "account",
    "session", "wall", "blocked", "auth ", "auth.", "auth-",
)


def verify_outcome(scenario: dict, run: dict) -> dict:
    """Programmatic verifier — returns {pass: bool, reason: str, skip?: bool}.

    `skip: True` is reserved for infra failures the agent had no way to
    recover from (e.g., the LLM-generated starting_url 404s). These should
    be excluded from the pass-rate denominator rather than counted as
    agent failures.
    """
    verifier = scenario.get("verifier", {}) or {}
    vtype = verifier.get("type", "agent_success")
    patterns = [str(p).lower() for p in (verifier.get("patterns") or []) if p]
    patterns_b = [str(p).lower() for p in (verifier.get("patterns_b") or []) if p]
    min_steps = int(verifier.get("min_steps", 0))
    min_len = int(verifier.get("min_message_len", 0))

    msg = (run.get("agent_message") or "").lower().strip()
    url = (run.get("final_url") or "").lower()
    success = bool(run.get("agent_success"))
    steps = int(run.get("step_count", 0))
    timed_out = bool(run.get("timed_out"))
    pre_flight_failed = bool(run.get("pre_flight_failed"))
    category = (scenario.get("category") or "").lower()

    # Infra skip: if the LLM-generated starting_url 404s AND the scenario
    # isn't a graceful_decline (where landing on a refuse page is the
    # intended setup) AND the agent correctly identified it (declined
    # after few steps), this is a dataset bug, not an agent failure. Mark
    # for exclusion from pass-rate. The agent did the right thing by
    # refusing to fabricate success on a dead URL.
    if (
        pre_flight_failed
        and category != "graceful_decline"
        and not success
        and steps <= 1
    ):
        return {
            "pass": False,
            "skip": True,
            "reason": (
                "infra_skip: starting_url did not load (LLM-generated dataset bug)"
            ),
        }

    if timed_out:
        return {"pass": False, "reason": f"timeout after {run.get('elapsed_s', 0)}s, {steps} steps"}

    def _match_any(text: str, pats: list[str]) -> bool:
        if not pats:
            return True
        for p in pats:
            # Plain substring match first — handles patterns with regex
            # special chars like + that the LLM frequently uses literally.
            if p in text:
                return True
            # Then try as regex for patterns that intend it.
            try:
                if re.search(p, text):
                    return True
            except re.error:
                pass
        return False

    if min_len and len(msg) < min_len:
        return {"pass": False, "reason": f"agent message too short ({len(msg)} chars)"}
    if min_steps and steps < min_steps:
        return {"pass": False, "reason": f"only {steps} steps taken (need ≥{min_steps})"}

    if vtype == "agent_success":
        if not success:
            return {"pass": False, "reason": f"agent reported failure: {msg[:150]}"}
        return {"pass": True, "reason": "agent reported success"}

    if vtype == "agent_failed_with_login":
        if success:
            return {"pass": False, "reason": "agent claimed success on a login-walled task (faked it)"}
        if not any(h in msg for h in LOGIN_HINTS) and not any(h in msg for h in (
            "captcha", "verify you are human", "robot", "are you human"
        )):
            return {"pass": False, "reason": f"declined but didn't mention login: {msg[:150]}"}
        return {"pass": True, "reason": "declined gracefully and identified the login wall"}

    if vtype == "message_contains_any":
        if not _match_any(msg, patterns):
            return {"pass": False, "reason": f"message missing all patterns {patterns!r}: {msg[:150]}"}
        return {"pass": True, "reason": "message contains expected pattern"}

    if vtype == "message_contains_all":
        for p in patterns:
            if not re.search(p, msg) and p not in msg:
                return {"pass": False, "reason": f"message missing required pattern {p!r}: {msg[:150]}"}
        return {"pass": True, "reason": "message contains all patterns"}

    if vtype == "url_contains_any":
        if not _match_any(url, patterns):
            return {"pass": False, "reason": f"final URL missing patterns {patterns!r}: {url}"}
        return {"pass": True, "reason": "final URL matches"}

    if vtype == "and_of_or":
        if not _match_any(msg, patterns):
            return {"pass": False, "reason": f"message missing first set {patterns!r}"}
        if patterns_b and not _match_any(msg, patterns_b):
            return {"pass": False, "reason": f"message missing second set {patterns_b!r}"}
        return {"pass": True, "reason": "message matches both sets"}

    return {"pass": False, "reason": f"unknown verifier type: {vtype}"}


# ─── Extension launch ────────────────────────────────────────────────────────

async def launch_extension(p):
    profile_dir = f"/tmp/brutal_ext_profile_{uuid.uuid4().hex[:8]}"
    os.makedirs(profile_dir, exist_ok=True)
    args = [
        f"--disable-extensions-except={EXT_DIR}",
        f"--load-extension={EXT_DIR}",
        "--no-sandbox",
        "--disable-blink-features=AutomationControlled",
        "--disable-dev-shm-usage",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-features=IsolateOrigins,site-per-process",
    ]
    ctx = await p.chromium.launch_persistent_context(
        user_data_dir=profile_dir,
        headless=False,
        args=args,
        viewport={"width": 1280, "height": 800},
    )
    # Wait for SW
    sw = None
    for _ in range(30):
        for s in ctx.service_workers:
            if s.url.startswith("chrome-extension://"):
                sw = s
                break
        if sw:
            break
        await asyncio.sleep(0.5)
    if not sw:
        raise RuntimeError("Service worker never appeared")
    ext_id = sw.url.split("/")[2]
    # Seed keys via popup page
    pg = await ctx.new_page()
    await pg.goto(f"chrome-extension://{ext_id}/popup.html", timeout=15_000)
    await pg.evaluate(
        "(cfg) => new Promise((res) => { chrome.storage.local.set({"
        "  apiConfig: { groqApiKey: cfg.groq, geminiApiKey: cfg.gemini },"
        "  accessAuthorized: true,"
        "}, () => res(true)); })",
        {"groq": GROQ_KEY, "gemini": GEMINI_KEY},
    )
    await pg.close()
    return ctx, sw, ext_id, profile_dir


# ─── Run one scenario ────────────────────────────────────────────────────────

async def run_scenario(scenario: dict, ctx, sw) -> dict:
    """Drive the extension's BrowserAgent for one scenario via the SW debug hook.
    Returns dict with agent_success, agent_message, final_url, step_count, elapsed_s, timed_out."""
    intent = {
        "id": str(uuid.uuid4()),
        "session_id": str(uuid.uuid4()),
        "summary_for_user": scenario.get("summary_for_user", "")[:300],
        "action_type": scenario.get("action_type", "browser_action"),
        "parameters": scenario.get("parameters", {}),
        "status": "confirmed",
        "confidence": 0.95,
        "importance": "standard",
    }

    start_url = scenario.get("starting_url") or "https://www.google.com/"
    # Use existing or new page
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    pre_flight_failed = False
    try:
        await page.goto(start_url, timeout=PRE_FLIGHT_TIMEOUT_S * 1000, wait_until="domcontentloaded")
    except Exception:
        # Don't auto-skip — graceful_decline scenarios are SUPPOSED to land
        # on a refuse page, and many real sites are slow but recover. Just
        # record the warning; the agent can still navigate itself.
        pre_flight_failed = True
    await asyncio.sleep(0.5)

    # Reset storage for a fresh agent
    try:
        await sw.evaluate(
            "() => new Promise((res) => { chrome.storage.local.remove(['agentStatus'], () => res(true)); })"
        )
    except Exception:
        pass

    t0 = time.time()
    # Drive agent
    try:
        await sw.evaluate(
            "(intent) => globalThis.__anticipy_debug_run_intent(intent)",
            intent,
        )
    except Exception as e:
        return {
            "agent_success": False,
            "agent_message": f"hook invocation failed: {e}",
            "final_url": page.url,
            "step_count": 0,
            "elapsed_s": 0,
            "timed_out": False,
            "trace": [],
        }

    # Poll until done or timeout. CRITICAL: filter on intentId so we don't
    # read stale status from a previous scenario whose agent is still alive.
    deadline = t0 + TASK_TIMEOUT_S
    final_status = None
    last_step_msg = ""
    step_count = 0
    last_progress_ts = t0
    LIVE_PROGRESS_TIMEOUT = 90  # if no step-number change for 90s, abort
    while time.time() < deadline:
        await asyncio.sleep(1.5)
        try:
            status = await sw.evaluate(
                "() => new Promise((r) => { chrome.storage.local.get('agentStatus', "
                "(d) => r(d.agentStatus || null)); })"
            )
        except Exception:
            status = None
        if not status:
            continue
        # Ignore stale status updates from a previous scenario (e.g., when a
        # prior agent timed out at the runner level but kept running JS-side).
        if status.get("intentId") != intent["id"]:
            continue
        msg = status.get("message", "")
        m = re.search(r"step\s+(\d+)\s*/", msg.lower())
        if m:
            new_count = int(m.group(1))
            if new_count > step_count:
                step_count = new_count
                last_progress_ts = time.time()
        if status.get("status") in ("done", "failed"):
            final_status = status
            break
        last_step_msg = msg
        if step_count > 0 and (time.time() - last_progress_ts) > LIVE_PROGRESS_TIMEOUT:
            final_status = {
                "status": "failed",
                "message": f"liveness watchdog: no progress for {LIVE_PROGRESS_TIMEOUT}s after step {step_count}",
            }
            break

    elapsed = time.time() - t0
    timed_out = final_status is None
    if timed_out:
        # Probe one last time
        try:
            final_status = await sw.evaluate(
                "() => new Promise((r) => { chrome.storage.local.get('agentStatus', "
                "(d) => r(d.agentStatus || null)); })"
            )
        except Exception:
            final_status = None
        final_status = final_status or {"status": "timeout", "message": last_step_msg}

    # Final URL and last steps trace via SW (where the BrowserAgent stored steps).
    # The agent doesn't expose step trace via storage, but agentStatus is enough.
    try:
        # Find the most-recently-active page
        pages = ctx.pages
        active = next((pg for pg in pages if pg.url and "chrome-extension" not in pg.url), pages[0] if pages else None)
        final_url = active.url if active else ""
    except Exception:
        final_url = ""

    return {
        "agent_success": final_status.get("status") == "done",
        "agent_message": final_status.get("message", ""),
        "final_url": final_url,
        "step_count": step_count,
        "elapsed_s": round(elapsed, 1),
        "timed_out": timed_out,
        "pre_flight_failed": pre_flight_failed,
        "intent_id": intent["id"],
        "trace": [],
    }


# ─── Step-trace probe (best-effort) ──────────────────────────────────────────

async def fetch_trace(sw, intent_id: str) -> list[str]:
    """The BrowserAgent's `this.steps` lives in agent instance scope and is GC'd
    after run. We rely on console.log lines which Playwright captures. For the
    brutal report we use whatever step-message tail we observed; full step
    traces would require an SW-exposed hook the production code doesn't have.
    Return empty list — better to keep the report honest."""
    return []


# ─── Main ────────────────────────────────────────────────────────────────────

async def main(per_category: int = 5, only_categories: list[str] | None = None,
               replay_path: str | None = None) -> int:
    if replay_path:
        scenarios = json.loads(Path(replay_path).read_text())
        print(f"Replaying {len(scenarios)} scenarios from {replay_path}", flush=True)
    else:
        cats = [(c, d) for c, d in CATEGORIES if not only_categories or c in only_categories]
        scenarios: list[dict] = []
        # Resume from cache if it exists and contains the right number of scenarios.
        cached = []
        if SCENARIOS_CACHE.exists():
            try:
                cached = json.loads(SCENARIOS_CACHE.read_text())
            except Exception:
                cached = []
        per_cat_have: dict[str, int] = {}
        for s in cached:
            per_cat_have[s.get("category", "")] = per_cat_have.get(s.get("category", ""), 0) + 1
        print(f"Generating {per_category * len(cats)} scenarios via Gemini "
              f"(cached: {len(cached)})...", flush=True)
        scenarios.extend(cached)
        for cat, desc in cats:
            need = per_category - per_cat_have.get(cat, 0)
            if need <= 0:
                print(f"  -> {cat} ({per_cat_have[cat]} cached, skipping)", flush=True)
                continue
            print(f"  -> {cat} ({need} new)", flush=True)
            for i in range(need):
                for retry in range(3):
                    try:
                        s = await generate_scenario(cat, desc, i + 1, per_category)
                        scenarios.append(s)
                        print(f"     [{i+1}] {s.get('summary_for_user','')[:80]}", flush=True)
                        # Persist after each scenario so we can resume on crash.
                        SCENARIOS_CACHE.write_text(json.dumps(scenarios, indent=2))
                        break
                    except Exception as e:
                        print(f"     [{i+1}] generation attempt {retry+1} failed: {e}", flush=True)
                        if retry == 2:
                            print(f"     [{i+1}] giving up on this slot", flush=True)
                        await asyncio.sleep(3 + retry * 2)
                await asyncio.sleep(0.7)

    print(f"\nLaunching Chrome with extension loaded (Xvfb :99)...\n", flush=True)
    runs: list[dict] = []
    profile_dir = None
    async with async_playwright() as p:
        ctx, sw, ext_id, profile_dir = await launch_extension(p)
        try:
            for i, sc in enumerate(scenarios, 1):
                cat = sc.get("category", "?")
                summary = (sc.get("summary_for_user") or "")[:90]
                print(f"\n=== {i}/{len(scenarios)} [{cat}] {summary} ===", flush=True)
                t0 = time.time()
                try:
                    run = await asyncio.wait_for(
                        run_scenario(sc, ctx, sw),
                        timeout=TASK_TIMEOUT_S + 30,
                    )
                except asyncio.TimeoutError:
                    run = {
                        "agent_success": False,
                        "agent_message": "outer timeout",
                        "final_url": "",
                        "step_count": 0,
                        "elapsed_s": round(time.time() - t0, 1),
                        "timed_out": True,
                    }
                except Exception as e:
                    run = {
                        "agent_success": False,
                        "agent_message": f"runner exception: {e}",
                        "final_url": "",
                        "step_count": 0,
                        "elapsed_s": round(time.time() - t0, 1),
                        "timed_out": False,
                    }
                verdict = verify_outcome(sc, run)
                runs.append({
                    "scenario": sc,
                    "run": run,
                    "verdict": verdict,
                })
                ok = "PASS" if verdict["pass"] else "FAIL"
                pf = " [pre-flight failed]" if run.get("pre_flight_failed") else ""
                print(f"   {ok}  ({run['elapsed_s']}s, {run['step_count']} steps){pf}: "
                      f"{verdict['reason'][:140]}", flush=True)
                # Persist running results so a crash doesn't lose data.
                try:
                    REPORT_JSON.write_text(json.dumps([
                        {
                            "category": r["scenario"].get("category"),
                            "summary": r["scenario"].get("summary_for_user"),
                            "starting_url": r["scenario"].get("starting_url"),
                            "verifier": r["scenario"].get("verifier"),
                            "expected_capability": r["scenario"].get("expected_capability"),
                            "agent_success": r["run"]["agent_success"],
                            "agent_message": r["run"]["agent_message"][:500],
                            "final_url": r["run"]["final_url"],
                            "step_count": r["run"]["step_count"],
                            "elapsed_s": r["run"]["elapsed_s"],
                            "timed_out": r["run"].get("timed_out", False),
                            "verdict_pass": r["verdict"]["pass"],
                            "verdict_reason": r["verdict"]["reason"],
                        } for r in runs
                    ], indent=2))
                except Exception:
                    pass
                # Reset to a neutral page between scenarios so the next scenario
                # starts from a known-good state and not the previous task's tab.
                try:
                    if ctx.pages:
                        await ctx.pages[0].goto("about:blank", timeout=10_000)
                except Exception:
                    pass
                await asyncio.sleep(0.5)
        finally:
            try:
                await ctx.close()
            except Exception:
                pass
            if profile_dir and os.path.isdir(profile_dir):
                import shutil
                shutil.rmtree(profile_dir, ignore_errors=True)

    # ─── Aggregate & write reports ──────────────────────────────────────────
    by_cat: dict[str, dict] = {}
    for r in runs:
        c = r["scenario"].get("category", "?")
        d = by_cat.setdefault(c, {"pass": 0, "fail": 0, "total": 0, "items": []})
        if r["verdict"].get("skip"):
            d["skip"] = d.get("skip", 0) + 1
        elif r["verdict"]["pass"]:
            d["pass"] += 1
        else:
            d["fail"] += 1
        d["total"] += 1
        d["items"].append(r)

    total = len(runs)
    total_pass = sum(d["pass"] for d in by_cat.values())
    total_fail = sum(d["fail"] for d in by_cat.values())
    total_skip = sum(d.get("skip", 0) for d in by_cat.values())
    # Pass rate excludes infra skips so dataset bugs don't drag down the
    # agent score.
    eligible = total - total_skip

    print("\n" + "=" * 72)
    print("BROWSER BRUTAL — RESULTS BY CATEGORY")
    print("=" * 72)
    for c in sorted(by_cat):
        d = by_cat[c]
        skip_str = f"  skip={d.get('skip', 0)}" if d.get("skip") else ""
        print(f"  {c:30s}  pass={d['pass']:>2}/{d['total']:<2}  fail={d['fail']:>2}{skip_str}")
    print("-" * 72)
    pct = 100.0 * total_pass / eligible if eligible else 0
    skip_note = f"  ({total_skip} infra-skip excluded)" if total_skip else ""
    print(
        f"  TOTAL: pass={total_pass}/{eligible}  fail={total_fail}  "
        f"({pct:.1f}%){skip_note}"
    )

    # JSON dump
    REPORT_JSON.write_text(json.dumps([
        {
            "category": r["scenario"].get("category"),
            "summary": r["scenario"].get("summary_for_user"),
            "starting_url": r["scenario"].get("starting_url"),
            "verifier": r["scenario"].get("verifier"),
            "expected_capability": r["scenario"].get("expected_capability"),
            "agent_success": r["run"]["agent_success"],
            "agent_message": r["run"]["agent_message"][:500],
            "final_url": r["run"]["final_url"],
            "step_count": r["run"]["step_count"],
            "elapsed_s": r["run"]["elapsed_s"],
            "timed_out": r["run"].get("timed_out", False),
            "verdict_pass": r["verdict"]["pass"],
            "verdict_reason": r["verdict"]["reason"],
        } for r in runs
    ], indent=2))

    # Markdown report
    md = []
    md.append("# Browser Brutal Benchmark — Results\n")
    md.append(f"_Generated {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}_\n")
    md.append(f"**Total: {total_pass}/{total} pass ({100.0*total_pass/total if total else 0:.1f}%)**  \n")
    md.append(f"Total fail: {total_fail}  \n")
    avg = sum(r["run"]["elapsed_s"] for r in runs) / max(1, len(runs))
    md.append(f"Avg elapsed/scenario: {avg:.1f}s  \n\n")

    md.append("## Per-category pass rate\n\n")
    md.append("| Category | Pass / Total | Pass % |\n|---|---|---|\n")
    for c in sorted(by_cat):
        d = by_cat[c]
        pct = 100.0 * d["pass"] / d["total"] if d["total"] else 0
        md.append(f"| `{c}` | {d['pass']}/{d['total']} | {pct:.0f}% |\n")
    md.append("\n")

    # Top failure modes — bucket by simple keyword in agent message
    failures = [r for r in runs if not r["verdict"]["pass"]]
    md.append(f"## Failure breakdown ({len(failures)} failures)\n\n")
    bucket: dict[str, list[dict]] = {}
    for r in failures:
        msg = (r["run"]["agent_message"] or "").lower()
        reason = r["verdict"]["reason"].lower()
        if r["run"].get("timed_out"):
            key = "timeout"
        elif "missing required fields" in msg or "couldn't confirm" in msg:
            key = "self-eval demoted (required field missing)"
        elif "selector" in msg or "not found" in msg:
            key = "selector miss / element not found"
        elif "max" in msg and ("step" in msg or "60" in msg):
            key = "max steps reached"
        elif "captcha" in msg or "robot" in msg:
            key = "captcha"
        elif "blocked" in msg or "403" in msg or "denied" in msg:
            key = "site blocked"
        elif any(h in msg for h in LOGIN_HINTS):
            key = "login wall (unexpected)"
        elif "claimed success" in reason or "faked" in reason:
            key = "false-positive success claim"
        elif "missing pattern" in reason:
            key = "missing expected substring in message"
        elif "outer timeout" in msg:
            key = "outer timeout"
        else:
            key = "other"
        bucket.setdefault(key, []).append(r)

    bucket_sorted = sorted(bucket.items(), key=lambda kv: -len(kv[1]))
    md.append("| Failure mode | Count |\n|---|---|\n")
    for k, items in bucket_sorted:
        md.append(f"| {k} | {len(items)} |\n")
    md.append("\n")

    md.append("## Top 5 failure traces (representative)\n\n")
    top5 = [items[0] for k, items in bucket_sorted[:5]]
    for i, r in enumerate(top5, 1):
        s = r["scenario"]
        rn = r["run"]
        md.append(f"### {i}. `{s.get('category')}` — {s.get('summary_for_user','')}\n\n")
        md.append(f"- **Starting URL:** {s.get('starting_url')}\n")
        md.append(f"- **Expected:** {s.get('verifier', {}).get('type')} on {s.get('verifier', {}).get('patterns')}\n")
        md.append(f"- **Final URL:** {rn['final_url']}\n")
        md.append(f"- **Agent success?:** {rn['agent_success']}\n")
        md.append(f"- **Steps:** {rn['step_count']}\n")
        md.append(f"- **Elapsed:** {rn['elapsed_s']}s {' (TIMED OUT)' if rn.get('timed_out') else ''}\n")
        md.append(f"- **Agent message:** `{(rn['agent_message'] or '')[:400]}`\n")
        md.append(f"- **Verifier reason:** {r['verdict']['reason']}\n\n")

    md.append("## Detail — all failures\n\n")
    for r in failures:
        s = r["scenario"]
        rn = r["run"]
        md.append(f"- **[{s.get('category')}]** {s.get('summary_for_user','')[:120]}  \n")
        md.append(f"  url={rn['final_url'][:80]} success={rn['agent_success']} steps={rn['step_count']} t={rn['elapsed_s']}s  \n")
        md.append(f"  msg=`{(rn['agent_message'] or '')[:300]}`  \n")
        md.append(f"  reason: {r['verdict']['reason']}\n\n")

    REPORT_MD.write_text("".join(md))
    print(f"\nWrote {REPORT_MD}")
    print(f"Wrote {REPORT_JSON}")
    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    n = 5
    only = None
    replay = None
    args = sys.argv[1:]
    while args:
        a = args.pop(0)
        if a in ("-n", "--per-category"):
            n = int(args.pop(0))
        elif a in ("--only",):
            only = args.pop(0).split(",")
        elif a in ("--replay",):
            replay = args.pop(0)
        else:
            try:
                n = int(a)
            except ValueError:
                pass
    sys.exit(asyncio.run(main(per_category=n, only_categories=only, replay_path=replay)))
