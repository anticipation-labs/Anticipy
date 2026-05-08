"""
Master benchmark — the SINGLE NUMBER for end-to-end Anticipy quality.

For every scenario in engine/data/proactive_e2e.jsonl we:

  voice half (always run)
  ───────────────────────
    1. POST the transcript to https://www.anticipy.ai/api/engine/analyze
       with a Supabase JWT for an e2e-test-*@anticipy-test.local user (so
       the analyze route's email-skip kicks in — no admin inbox spam).
    2. Read intents back from anticipy_intents.
    3. Hand transcript + ground truth + extracted to a Gemini judge ->
       counts of matched / missed / fp-on-noise / spurious.

  action half (only when an actionable browser-routed intent landed)
  ────────────────────────────────────────────────────────────────
    4. Spawn a headed Chrome with the extension loaded (mirroring
       test_extension_hard.py launch helpers).
    5. Drive the BrowserAgent via the SW debug hook
       (globalThis.__anticipy_debug_run_intent).
    6. Poll chrome.storage.local.agentStatus until done/failed/timeout.
    7. Pass if status='done', or status='failed' with a graceful decline
       message ("requires login", "not browser-doable", etc).

Final score = scenarios where BOTH halves pass / total.
For scenarios with zero expected intents, the action half passes
automatically when the voice half extracts nothing.

Output:
  - terminal: per-category pass rate, overall, top-5 failures
  - file: /tmp/master_benchmark_detail.json (one row per scenario)

Run:
  cd engine && DISPLAY=:99 python test_master_benchmark.py            # all 200
  cd engine && DISPLAY=:99 python test_master_benchmark.py 30         # first 30
  cd engine && DISPLAY=:99 python test_master_benchmark.py 30 voice   # voice-only
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import uuid
from collections import Counter
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env.local"
EXT_DIR = ROOT / "extension"
DATASET = Path(__file__).resolve().parent / "data" / "proactive_e2e.jsonl"

if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

SUPABASE_URL = os.environ["NEXT_PUBLIC_SUPABASE_URL"].rstrip("/")
SUPABASE_SERVICE = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
SUPABASE_ANON = os.environ["NEXT_PUBLIC_SUPABASE_ANON_KEY"]
ANTICIPY_BASE = os.environ.get("ANTICIPY_BASE", "https://www.anticipy.ai")
GEMINI_KEY = os.environ["GOOGLE_API_KEY"]
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash:generateContent"
)
PROD_AUTH_ENDPOINT = f"{ANTICIPY_BASE}/api/extension/auth"

HDR = {
    "apikey": SUPABASE_SERVICE,
    "Authorization": f"Bearer {SUPABASE_SERVICE}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}


# ---------------------------------------------------------------------------
# Auth + Supabase helpers (lifted from test_proactive_dataset.py)
# ---------------------------------------------------------------------------


async def get_or_create_test_user_jwt(email: str, password: str) -> str:
    async with httpx.AsyncClient(timeout=30) as c:
        await c.post(
            f"{SUPABASE_URL}/auth/v1/admin/users",
            headers={
                "apikey": SUPABASE_SERVICE,
                "Authorization": f"Bearer {SUPABASE_SERVICE}",
                "Content-Type": "application/json",
            },
            json={"email": email, "password": password, "email_confirm": True},
        )
        r = await c.post(
            f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
            headers={"apikey": SUPABASE_ANON, "Content-Type": "application/json"},
            json={"email": email, "password": password},
        )
        if r.status_code != 200:
            raise RuntimeError(f"signin {r.status_code}: {r.text[:200]}")
        return r.json()["access_token"]


async def get_user_id_from_jwt(jwt: str) -> str | None:
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(
            f"{SUPABASE_URL}/auth/v1/user",
            headers={"apikey": SUPABASE_ANON, "Authorization": f"Bearer {jwt}"},
        )
        if r.status_code != 200:
            return None
        return r.json().get("id")


async def insert_session(session_id: str, user_email: str, user_id: str | None) -> None:
    async with httpx.AsyncClient(timeout=15) as c:
        body = {
            "id": session_id,
            "status": "recording",
            "user_email": user_email,
            "metadata": {"e2e_test": True, "dataset": "master_benchmark"},
        }
        if user_id:
            body["user_id"] = user_id
        r = await c.post(f"{SUPABASE_URL}/rest/v1/anticipy_sessions", headers=HDR, json=body)
        if r.status_code not in (200, 201):
            raise RuntimeError(f"session insert {r.status_code}: {r.text[:200]}")


async def cleanup_session(session_id: str) -> None:
    async with httpx.AsyncClient(timeout=15) as c:
        await c.delete(
            f"{SUPABASE_URL}/rest/v1/anticipy_intents?session_id=eq.{session_id}",
            headers=HDR,
        )
        await c.delete(
            f"{SUPABASE_URL}/rest/v1/anticipy_sessions?id=eq.{session_id}",
            headers=HDR,
        )


# ---------------------------------------------------------------------------
# /api/engine/analyze + intent fetch
# ---------------------------------------------------------------------------


async def call_analyze(transcript_lines: list[str], session_id: str, jwt: str) -> dict:
    payload = {
        "sessionId": session_id,
        "transcript": "\n".join(transcript_lines),
        "isFinal": True,
    }
    async with httpx.AsyncClient(timeout=240) as c:
        r = await c.post(
            f"{ANTICIPY_BASE}/api/engine/analyze",
            headers={"Authorization": f"Bearer {jwt}"},
            json=payload,
        )
        if r.status_code != 200:
            return {"error": f"analyze {r.status_code}: {r.text[:300]}"}
        return r.json()


async def get_session_intents(session_id: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(
            f"{SUPABASE_URL}/rest/v1/anticipy_intents"
            f"?session_id=eq.{session_id}&select=*&order=created_at",
            headers=HDR,
        )
        if r.status_code != 200:
            return []
        return r.json()


# ---------------------------------------------------------------------------
# LLM judge — voice half
# ---------------------------------------------------------------------------


JUDGE_SYSTEM = """You judge whether a proactive intent-extraction system did the right thing.

You see:
- The conversation transcript
- The list of EXPECTED intents (ground truth — the system SHOULD have extracted these)
- The list of NOISE items (the system should NOT have extracted these)
- The list of EXTRACTED intents (what the system actually produced)
- An OPTIONAL expected_clarification (a question the system SHOULD ask the user)

For EACH expected intent, decide if it has a clear match in extracted (ignoring phrasing differences).
For EACH noise item, decide if extracted contains anything that corresponds (i.e. a false positive).
For EACH extracted intent that doesn't correspond to any expected OR noise item, count it as 'spurious'.
If expected_clarification is present, an extracted intent whose summary is a clarification question
counts as MATCHED for the corresponding expected intent — that's the correct behavior for missing slots.

Return JSON:
{
  "matched_expected": <int>,
  "missed_expected": <int>,
  "false_positives_on_noise": <int>,
  "spurious_extra": <int>,
  "clarification_asked": <bool>,
  "details": [
    {"kind": "matched", "expected": "<>", "extracted": "<>"},
    {"kind": "missed", "expected": "<>"},
    {"kind": "false_positive", "noise": "<>", "extracted": "<>"},
    {"kind": "spurious", "extracted": "<>"}
  ]
}

Rules:
- Match by INTENT, not exact wording. "email Sarah about Friday" matches "Send email to Sarah re: Friday meeting".
- A retracted item that was extracted (e.g. agent extracted 'cancel picnic if rains' even though the user retracted it) IS a false positive on noise.
- Quantity matters: if expected has 3 items and extracted has 1, that's 1 matched + 2 missed.
- Delegations to other people that the system extracted as wearer-actions are false positives on noise.
- A clarifying QUESTION extracted (e.g. "Where would you like to fly from?") is GOOD when expected_clarification is present.
"""


async def judge_extraction(
    transcript: list[str],
    expected: list[str],
    noise: list[str],
    extracted: list[str],
    expected_clarification: str | None = None,
) -> dict:
    payload = {
        "transcript": "\n".join(transcript),
        "expected_intents": expected,
        "noise_should_NOT_act_on": noise,
        "extracted_intents": extracted,
    }
    if expected_clarification:
        payload["expected_clarification"] = expected_clarification

    body = {
        "system_instruction": {"parts": [{"text": JUDGE_SYSTEM}]},
        "contents": [{"role": "user", "parts": [{"text": json.dumps(payload, indent=2)}]}],
        "generationConfig": {
            "temperature": 0.0,
            "maxOutputTokens": 4096,
            "responseMimeType": "application/json",
        },
    }
    last_err: str | None = None
    for _ in range(3):
        try:
            async with httpx.AsyncClient(timeout=60) as c:
                r = await c.post(f"{GEMINI_URL}?key={GEMINI_KEY}", json=body)
                if r.status_code != 200:
                    last_err = f"judge {r.status_code}: {r.text[:200]}"
                    await asyncio.sleep(2)
                    continue
                txt = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                t = txt.strip()
                if t.startswith("```"):
                    t = t.split("\n", 1)[1] if "\n" in t else t
                    if t.endswith("```"):
                        t = t.rsplit("```", 1)[0]
                try:
                    return json.loads(t)
                except json.JSONDecodeError:
                    s, e = txt.find("{"), txt.rfind("}")
                    if s >= 0 and e > s:
                        return json.loads(txt[s : e + 1])
                    raise
        except Exception as e:
            last_err = f"judge: {type(e).__name__}: {e}"
            await asyncio.sleep(2)
    return {"error": last_err or "judge exhausted"}


def score_voice(scenario: dict, judgment: dict) -> dict:
    expected_n = len(scenario["expected_intents"])
    matched = judgment.get("matched_expected", 0)
    missed = judgment.get("missed_expected", 0)
    fp = judgment.get("false_positives_on_noise", 0)
    spurious = judgment.get("spurious_extra", 0)
    pp = matched + fp + spurious
    precision = (matched / pp) if pp else (1.0 if expected_n == 0 else 0.0)
    recall = (matched / expected_n) if expected_n else (1.0 if (fp + spurious) == 0 else 0.0)
    passed = (missed == 0) and (fp == 0) and (spurious == 0)
    return {
        "expected_n": expected_n,
        "matched": matched,
        "missed": missed,
        "false_positives_on_noise": fp,
        "spurious_extra": spurious,
        "precision": round(precision, 2),
        "recall": round(recall, 2),
        "passed": passed,
    }


# ---------------------------------------------------------------------------
# Action half — Playwright + extension (lifted/distilled from test_extension_hard.py)
# ---------------------------------------------------------------------------


async def fetch_extension_keys() -> dict:
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(
            f"{SUPABASE_URL}/rest/v1/engine_users?select=access_code&limit=1",
            headers={"apikey": SUPABASE_SERVICE, "Authorization": f"Bearer {SUPABASE_SERVICE}"},
        )
        code = r.json()[0]["access_code"]
        r = await c.post(PROD_AUTH_ENDPOINT, json={"code": code})
        return r.json()


async def launch_extension(p):
    profile = f"/tmp/master_bench_profile_{uuid.uuid4().hex[:8]}"
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
        user_data_dir=profile,
        headless=False,
        args=args,
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


async def seed_extension_keys(ctx, ext_id: str, keys: dict) -> None:
    page = await ctx.new_page()
    try:
        await page.goto(f"chrome-extension://{ext_id}/popup.html", timeout=15_000)
        await page.evaluate(
            """(cfg) => new Promise((res) => {
                chrome.storage.local.set({
                  apiConfig: { groqApiKey: cfg.g, geminiApiKey: cfg.gem },
                  accessAuthorized: true,
                }, () => res(true));
            })""",
            {"g": keys.get("groqApiKey", ""), "gem": keys.get("geminiApiKey", "")},
        )
    finally:
        await page.close()


DECLINE_SIGNALS = (
    "cannot ", "can't ", "unable to ",
    "real-world action", "requires a real",
    "requires login", "require login", "requires logging",
    "logging into", "login required", "log in", "log-in",
    "not signed in", "not logged in", "needs sign in",
    "sign in", "sign-in",
    "not a browser", "out of scope", "not actionable",
    "not possible in a browser", "no clear way",
    "google account", "requires authentication",
    "communication task", "messaging task",
    "directly performed", "cannot directly",
    "cannot complete", "cannot proceed", "cannot continue",
    "cannot be done", "cannot be performed",
    "needs your account", "user account",
    "credentials", "i need credentials",
)


async def drive_extension_action(intent_row: dict, ctx, ext_id: str, timeout_s: int = 240) -> dict:
    visited = set()

    def on_request(req):
        try:
            if req.resource_type == "document":
                visited.add(req.url)
        except Exception:
            pass

    ctx.on("request", on_request)
    main_page = await ctx.new_page()
    try:
        try:
            await main_page.goto(
                "https://www.google.com/", timeout=20_000, wait_until="domcontentloaded"
            )
            visited.add("https://www.google.com/")
        except Exception:
            pass
        await asyncio.sleep(1.0)

        sw = None
        for s in ctx.service_workers:
            if s.url.startswith(f"chrome-extension://{ext_id}/"):
                sw = s
                break
        if sw is None:
            return {"agent_status": None, "error": "no SW", "visited_urls": list(visited)}

        try:
            await sw.evaluate(
                "() => new Promise(r => chrome.storage.local.remove('agentStatus', () => r(true)))"
            )
        except Exception:
            pass

        payload = {
            **intent_row,
            "status": "confirmed",
            "parameters": {
                **(intent_row.get("parameters") or {}),
                "browser_task": (intent_row.get("parameters", {}) or {}).get("browser_task")
                or intent_row.get("summary_for_user", ""),
            },
        }
        try:
            await sw.evaluate(
                "(intent) => globalThis.__anticipy_debug_run_intent && globalThis.__anticipy_debug_run_intent(intent)",
                payload,
            )
        except Exception as e:
            return {"agent_status": None, "error": f"debug hook: {e}", "visited_urls": list(visited)}

        deadline = time.time() + timeout_s
        last_status = None
        agent_status: dict | None = None
        while time.time() < deadline:
            await asyncio.sleep(4)
            try:
                agent_status = await sw.evaluate(
                    """() => new Promise(r => chrome.storage.local.get('agentStatus', d => r(d.agentStatus || null)))"""
                )
            except Exception:
                agent_status = None
            cur = (agent_status or {}).get("status")
            if cur != last_status:
                last_status = cur
            if cur in ("done", "failed"):
                break

        return {
            "agent_status": agent_status,
            "final_message": (agent_status or {}).get("message", ""),
            "visited_urls": list(visited),
        }
    finally:
        try:
            ctx.remove_listener("request", on_request)
        except Exception:
            pass
        try:
            await main_page.close()
        except Exception:
            pass


def score_action(action_result: dict | None) -> tuple[bool, str]:
    if not action_result:
        return False, "no action_result"
    if action_result.get("error"):
        return False, action_result["error"][:80]
    ag = action_result.get("agent_status") or {}
    status = ag.get("status")
    msg = (ag.get("message") or "").lower()
    if status == "done":
        return True, "done"
    if status == "failed" and any(s in msg for s in DECLINE_SIGNALS):
        return True, "graceful_decline"
    return False, f"status={status}; msg={msg[:60]}"


# ---------------------------------------------------------------------------
# Per-scenario runner
# ---------------------------------------------------------------------------


async def run_scenario(
    scenario: dict,
    user_email: str,
    user_id: str | None,
    jwt: str,
    *,
    ctx=None,
    ext_id: str | None = None,
    drive_action: bool = True,
) -> dict:
    name = scenario["name"]
    session_id = str(uuid.uuid4())
    expected_n = len(scenario["expected_intents"])
    cat_label = (scenario.get("category") or scenario.get("pattern_id") or "uncat")[:18]
    print(
        f"\n=== {name} (cat={cat_label:<18} d={scenario.get('difficulty', '?')[:6]:<6}) ===",
        flush=True,
    )
    print(
        f"  exp={expected_n} noise={len(scenario['noise_should_NOT_act_on'])} "
        f"clar={'Y' if scenario.get('expected_clarification') else '-'}",
        flush=True,
    )

    try:
        await insert_session(session_id, user_email, user_id)
    except Exception as e:
        return {
            "scenario": scenario,
            "error": f"session-insert: {e}",
            "voice_passed": False,
            "action_passed": False,
            "passed": False,
        }

    try:
        t0 = time.time()
        analyze_resp = await call_analyze(scenario["transcript"], session_id, jwt)
        analyze_dt = time.time() - t0
        if "error" in analyze_resp:
            print(f"  [analyze ERROR] {analyze_resp['error']}", flush=True)
            return {
                "scenario": scenario,
                "session_id": session_id,
                "error": analyze_resp["error"],
                "voice_passed": False,
                "action_passed": False,
                "passed": False,
            }

        await asyncio.sleep(2)
        intents = await get_session_intents(session_id)
        extracted_summaries = [i.get("summary_for_user") or "" for i in intents]
        print(f"  analyze: {analyze_dt:.1f}s -> {len(extracted_summaries)} intents", flush=True)
        for s in extracted_summaries[:5]:
            print(f"    · {s[:140]}", flush=True)

        judgment = await judge_extraction(
            scenario["transcript"],
            scenario["expected_intents"],
            scenario["noise_should_NOT_act_on"],
            extracted_summaries,
            scenario.get("expected_clarification"),
        )
        if "error" in judgment:
            return {
                "scenario": scenario,
                "session_id": session_id,
                "error": judgment["error"],
                "voice_passed": False,
                "action_passed": False,
                "passed": False,
            }

        vscore = score_voice(scenario, judgment)
        vtag = "PASS" if vscore["passed"] else "FAIL"
        print(
            f"  voice {vtag}: matched={vscore['matched']}/{vscore['expected_n']} "
            f"missed={vscore['missed']} fp={vscore['false_positives_on_noise']} "
            f"sp={vscore['spurious_extra']} (p={vscore['precision']} r={vscore['recall']})",
            flush=True,
        )
        if not vscore["passed"]:
            for d in (judgment.get("details") or [])[:4]:
                print(f"    {d}", flush=True)

        # ---- ACTION HALF ----
        action_result: dict | None = None
        action_pass: bool = False
        action_reason: str = ""

        if not intents:
            # No intents to drive — auto-pass for noise-only scenarios.
            action_pass = expected_n == 0
            action_reason = "no_intents (correct for zero-expected)" if action_pass \
                            else "no_intents but expected some"
        elif not drive_action:
            # Voice-only mode: action half is N/A; auto-pass so the voice
            # number drives end-to-end. Caller can still see voice_passed.
            action_pass = True
            action_reason = "skipped (voice-only mode, action n/a)"
        elif not (ctx and ext_id):
            action_pass = False
            action_reason = "skipped (no ctx/ext_id available)"
        else:
            actionable = [i for i in intents if (i.get("action_type") or "").startswith("browser")]
            if not actionable:
                # Communication / unknown action types — graceful no-op for the action half.
                # The voice half already scored. Treat as auto-pass since extension can't run them.
                action_pass = True
                action_reason = "non-browser action type, action half auto-pass"
            else:
                target = actionable[0]
                print(f"  -> driving extension on: {(target.get('summary_for_user') or '')[:90]}", flush=True)
                try:
                    action_result = await drive_extension_action(target, ctx, ext_id)
                except Exception as e:
                    action_result = {"error": f"driver: {e}", "agent_status": None, "visited_urls": []}
                action_pass, action_reason = score_action(action_result)

        atag = "PASS" if action_pass else "FAIL"
        print(f"  action {atag}: {action_reason}", flush=True)

        full_pass = vscore["passed"] and action_pass

        return {
            "scenario": scenario,
            "session_id": session_id,
            "extracted": extracted_summaries,
            "judgment": judgment,
            "voice_score": vscore,
            "voice_passed": vscore["passed"],
            "action_passed": action_pass,
            "action_reason": action_reason,
            "action_result": action_result,
            "passed": full_pass,
            "elapsed_s": round(time.time() - t0, 2),
        }
    finally:
        try:
            await cleanup_session(session_id)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def load_dataset(limit: int | None = None, stratified: bool = False) -> list[dict]:
    """Load scenarios. With stratified=True, take a category-balanced sample
    of size `limit` rather than the first N (which over-represents the older
    uncategorized scenarios at the head of the file)."""
    scenarios: list[dict] = []
    with DATASET.open() as f:
        for line in f:
            line = line.strip()
            if line:
                scenarios.append(json.loads(line))
    if limit is None:
        return scenarios
    if not stratified:
        return scenarios[:limit]

    # Stratified pick: round-robin across categories, taking from each in turn.
    by_cat: dict[str, list[dict]] = {}
    for sc in scenarios:
        c = sc.get("category") or "uncategorized"
        by_cat.setdefault(c, []).append(sc)
    cats = sorted(by_cat.keys())
    picked: list[dict] = []
    idx = 0
    while len(picked) < limit:
        progressed = False
        for c in cats:
            if idx < len(by_cat[c]):
                picked.append(by_cat[c][idx])
                progressed = True
                if len(picked) >= limit:
                    break
        if not progressed:
            break
        idx += 1
    return picked[:limit]


def report(runs: list[dict]) -> dict:
    n = len(runs) or 1
    voice_n = sum(1 for r in runs if r.get("voice_passed"))
    action_n = sum(1 for r in runs if r.get("action_passed"))
    full_n = sum(1 for r in runs if r.get("passed"))

    cat_total: Counter[str] = Counter()
    cat_voice: Counter[str] = Counter()
    cat_action: Counter[str] = Counter()
    cat_full: Counter[str] = Counter()

    for r in runs:
        sc = r["scenario"]
        # Fall back to pattern_id, else "uncategorized" — the older 50
        # scenarios at the head of the dataset only have pattern_id.
        c = sc.get("category") or sc.get("pattern_id") or "uncategorized"
        cat_total[c] += 1
        if r.get("voice_passed"):
            cat_voice[c] += 1
        if r.get("action_passed"):
            cat_action[c] += 1
        if r.get("passed"):
            cat_full[c] += 1

    print("\n" + "=" * 72)
    print(f"MASTER BENCHMARK: {full_n}/{n} ({100 * full_n / n:.0f}%) end-to-end pass")
    print(f"  voice half:  {voice_n}/{n} ({100 * voice_n / n:.0f}%)")
    print(f"  action half: {action_n}/{n} ({100 * action_n / n:.0f}%)")
    print("=" * 72)
    print(f"\n  {'category':<22} {'total':>5} {'voice':>10} {'action':>10} {'full':>10}")
    for c, t in sorted(cat_total.items(), key=lambda kv: (-kv[1], kv[0])):
        print(
            f"  {c:<22} {t:>5} "
            f"{cat_voice[c]:>4}/{t:<4} "
            f"{cat_action[c]:>4}/{t:<4} "
            f"{cat_full[c]:>4}/{t:<4}"
        )

    # Top-5 failure scenarios — sorted by combined badness
    def badness(r: dict) -> int:
        if r.get("error"):
            return 10000
        s = r.get("voice_score") or {}
        return (
            (0 if r.get("passed") else 1) * 5000
            + (0 if r.get("voice_passed") else 1) * 1000
            + (0 if r.get("action_passed") else 1) * 500
            + s.get("missed", 0) * 30
            + s.get("false_positives_on_noise", 0) * 15
            + s.get("spurious_extra", 0) * 5
        )

    failures = sorted([r for r in runs if not r.get("passed")], key=badness, reverse=True)
    print("\nTop failures:")
    for r in failures[:5]:
        sc = r["scenario"]
        s = r.get("voice_score") or {}
        if r.get("error"):
            print(
                f"  - [{sc.get('category','?')}/{sc.get('difficulty','?')}] {sc['name']}: "
                f"ERROR {r['error'][:90]}"
            )
        else:
            v = "vPASS" if r.get("voice_passed") else "vFAIL"
            a = "aPASS" if r.get("action_passed") else "aFAIL"
            extra = ""
            if not r.get("voice_passed"):
                extra = (
                    f" miss={s.get('missed',0)} fp={s.get('false_positives_on_noise',0)} "
                    f"sp={s.get('spurious_extra',0)}"
                )
            if not r.get("action_passed"):
                extra += f" actionReason={(r.get('action_reason') or '')[:50]}"
            print(
                f"  - [{sc.get('category','?')}/{sc.get('difficulty','?')}] {sc['name']}: "
                f"{v} {a}{extra}"
            )

    return {
        "total": n,
        "voice_passed": voice_n,
        "action_passed": action_n,
        "passed": full_n,
        "by_category": {
            c: {
                "total": t,
                "voice": cat_voice[c],
                "action": cat_action[c],
                "full": cat_full[c],
            }
            for c, t in cat_total.items()
        },
    }


async def main(
    limit: int | None = None,
    mode: str = "full",
    concurrency: int = 4,
    stratified: bool = False,
) -> int:
    scenarios = load_dataset(limit=limit, stratified=stratified)
    if not scenarios:
        print(f"FAIL: dataset empty at {DATASET}")
        return 1

    user_email = f"e2e-test-{uuid.uuid4().hex[:8]}@anticipy-test.local"
    user_pw = f"E2eTest!{uuid.uuid4().hex[:12]}"

    print(f"Master benchmark — {len(scenarios)} scenarios, mode={mode}")
    print(f"  dataset: {DATASET}")
    print(f"  target:  {ANTICIPY_BASE}/api/engine/analyze")
    print(f"  user:    {user_email}")
    print(f"  concurrency: {concurrency}")

    print("\nProvisioning Supabase Auth user...", flush=True)
    try:
        jwt = await get_or_create_test_user_jwt(user_email, user_pw)
    except Exception as e:
        print(f"FAIL: auth provisioning: {e}")
        return 1
    user_id = await get_user_id_from_jwt(jwt)
    print(f"  jwt_len={len(jwt)} user_id={user_id}", flush=True)

    runs: list[dict] = []

    if mode == "voice":
        # Voice-only: parallelize across concurrency
        sem = asyncio.Semaphore(concurrency)

        async def go(sc: dict) -> None:
            async with sem:
                try:
                    r = await run_scenario(
                        sc, user_email, user_id, jwt, drive_action=False
                    )
                except Exception as e:
                    r = {
                        "scenario": sc,
                        "error": f"{type(e).__name__}: {e}",
                        "voice_passed": False,
                        "action_passed": False,
                        "passed": False,
                    }
                runs.append(r)

        await asyncio.gather(*[go(sc) for sc in scenarios])

    else:
        # Full mode: voice runs in parallel first, then action half runs sequentially
        # for actionable browser intents only (Chrome can host one BrowserAgent at a time).
        print("\n[phase 1] running voice half in parallel...", flush=True)
        sem = asyncio.Semaphore(concurrency)

        async def voice_only(sc: dict) -> dict:
            async with sem:
                try:
                    return await run_scenario(
                        sc, user_email, user_id, jwt, drive_action=False
                    )
                except Exception as e:
                    return {
                        "scenario": sc,
                        "error": f"{type(e).__name__}: {e}",
                        "voice_passed": False,
                        "action_passed": False,
                        "passed": False,
                    }

        voice_runs = await asyncio.gather(*[voice_only(sc) for sc in scenarios])

        # Determine which scenarios are eligible for action-half drive.
        action_targets: list[tuple[int, dict, dict]] = []
        for idx, vr in enumerate(voice_runs):
            sc = vr["scenario"]
            if vr.get("error"):
                continue
            extracted = vr.get("extracted") or []
            # Re-fetch full intent rows for action drive — we cleaned up the
            # session in run_scenario, so we need to re-run analyze. But we
            # already scored voice — for the action half we'll create a NEW
            # session and call analyze again, then drive.
            if extracted and len(sc.get("expected_intents", [])) > 0:
                action_targets.append((idx, sc, vr))

        print(
            f"\n[phase 2] action half: {len(action_targets)} of {len(voice_runs)} scenarios "
            "have non-empty extractions to drive",
            flush=True,
        )

        # Launch Chrome ONCE and reuse across action-half runs
        if action_targets:
            from playwright.async_api import async_playwright

            ext_keys = await fetch_extension_keys()
            if not (ext_keys.get("groqApiKey") or ext_keys.get("geminiApiKey")):
                print("WARN: no extension keys — action half will SKIP (counts as fail)")
                action_targets = []

        action_results_by_idx: dict[int, dict] = {}
        if action_targets:
            from playwright.async_api import async_playwright

            print("Launching extension Chrome...", flush=True)
            async with async_playwright() as p:
                ctx, profile = await launch_extension(p)
                try:
                    ext_id = await wait_extension(ctx)
                    if not ext_id:
                        print("FAIL: extension did not load")
                    else:
                        print(f"  ext_id: {ext_id}", flush=True)
                        await asyncio.sleep(3)
                        await seed_extension_keys(ctx, ext_id, ext_keys)
                        print("  keys seeded", flush=True)

                        for i, (idx, sc, vr) in enumerate(action_targets):
                            print(
                                f"\n[action {i+1}/{len(action_targets)}] {sc['name']}",
                                flush=True,
                            )
                            # Recreate a session + re-analyze so we get fresh intent rows
                            session_id = str(uuid.uuid4())
                            try:
                                await insert_session(session_id, user_email, user_id)
                                await call_analyze(sc["transcript"], session_id, jwt)
                                await asyncio.sleep(2)
                                intents = await get_session_intents(session_id)
                                actionable = [
                                    i
                                    for i in intents
                                    if (i.get("action_type") or "").startswith("browser")
                                ]
                                if not actionable:
                                    action_results_by_idx[idx] = {
                                        "agent_status": None,
                                        "final_message": "non-browser action type",
                                        "_pass": True,
                                        "_reason": "non-browser action type, auto-pass",
                                    }
                                    continue
                                target_intent = actionable[0]
                                print(
                                    f"  -> {(target_intent.get('summary_for_user') or '')[:80]}",
                                    flush=True,
                                )
                                ar = await asyncio.wait_for(
                                    drive_extension_action(target_intent, ctx, ext_id),
                                    timeout=300,
                                )
                                ok, reason = score_action(ar)
                                ar["_pass"] = ok
                                ar["_reason"] = reason
                                action_results_by_idx[idx] = ar
                            except asyncio.TimeoutError:
                                action_results_by_idx[idx] = {
                                    "agent_status": None,
                                    "_pass": False,
                                    "_reason": "harness_timeout",
                                }
                            except Exception as e:
                                action_results_by_idx[idx] = {
                                    "agent_status": None,
                                    "_pass": False,
                                    "_reason": f"action exc: {type(e).__name__}: {e}",
                                }
                            finally:
                                try:
                                    await cleanup_session(session_id)
                                except Exception:
                                    pass
                finally:
                    try:
                        await ctx.close()
                    except Exception:
                        pass
                    import shutil

                    shutil.rmtree(profile, ignore_errors=True)

        # Merge: for each voice run, decide final action_passed
        for idx, vr in enumerate(voice_runs):
            sc = vr["scenario"]
            extracted = vr.get("extracted") or []
            expected_n = len(sc.get("expected_intents", []))

            if vr.get("error"):
                vr["action_passed"] = False
                vr["action_reason"] = "voice errored, action skipped"
            elif not extracted:
                vr["action_passed"] = expected_n == 0
                vr["action_reason"] = (
                    "no_intents (correct for zero-expected)"
                    if expected_n == 0
                    else "no_intents but expected some"
                )
            elif idx in action_results_by_idx:
                ar = action_results_by_idx[idx]
                vr["action_passed"] = ar.get("_pass", False)
                vr["action_reason"] = ar.get("_reason", "")
                vr["action_result"] = ar
            else:
                # Should not happen, but mark as fail if action_targets selected this idx
                # but we never got around to driving it.
                vr["action_passed"] = False
                vr["action_reason"] = "action drive missed"

            vr["passed"] = vr.get("voice_passed", False) and vr.get("action_passed", False)
            runs.append(vr)

    summary = report(runs)

    # Save detail JSON
    out = Path("/tmp/master_benchmark_detail.json")
    out.write_text(
        json.dumps(
            {
                "summary": summary,
                "runs": [
                    {
                        "name": r["scenario"]["name"],
                        "category": r["scenario"].get("category"),
                        "difficulty": r["scenario"].get("difficulty"),
                        "expected_n": len(r["scenario"].get("expected_intents", [])),
                        "noise_n": len(r["scenario"].get("noise_should_NOT_act_on", [])),
                        "expects_clarification": bool(r["scenario"].get("expected_clarification")),
                        "passed": r.get("passed", False),
                        "voice_passed": r.get("voice_passed", False),
                        "action_passed": r.get("action_passed", False),
                        "action_reason": r.get("action_reason"),
                        "error": r.get("error"),
                        "extracted": r.get("extracted", []),
                        "expected": r["scenario"].get("expected_intents", []),
                        "noise": r["scenario"].get("noise_should_NOT_act_on", []),
                        "voice_score": r.get("voice_score", {}),
                        "judgment_details": (r.get("judgment") or {}).get("details", []),
                        "action_message": ((r.get("action_result") or {}).get("final_message") or ""),
                    }
                    for r in runs
                ],
            },
            indent=2,
        )
    )
    print(f"\nDetail saved -> {out}")

    return 0 if summary["passed"] == summary["total"] else 1


if __name__ == "__main__":
    limit = None
    mode = "full"  # 'full' or 'voice'
    stratified = False
    args = sys.argv[1:]
    if args:
        try:
            limit = int(args[0])
            args = args[1:]
        except ValueError:
            pass
    while args:
        a = args[0]
        if a in ("voice", "full"):
            mode = a
        elif a in ("strat", "stratified"):
            stratified = True
        else:
            break
        args = args[1:]
    raise SystemExit(
        asyncio.run(main(limit=limit, mode=mode, stratified=stratified))
    )
