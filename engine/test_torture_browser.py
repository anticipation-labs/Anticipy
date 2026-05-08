"""
Browser-agent torture test.

Same philosophy as test_torture_proactive.py:
- LLM generates adversarial scenarios across hard categories.
- LLM-as-judge decides per scenario: pass / partial / fail.
- No keyword tables, no per-site whitelists, no string-match cheats.

Categories cover the failure modes that broke us before:
- canvas_editor   → Google Docs / Sheets text input via offscreen iframe
- webgl_or_map    → coordinate-based pointer dispatch on a canvas surface
- shadow_dom      → form inside open/closed shadow roots (LWC, Polymer)
- multi_field_form → 5+ fields, no silent field-skipping
- autocomplete    → React-controlled input that fights plain typing
- lazy_load       → results below the fold, requires scroll
- login_wall      → graceful detect + clean message
- multi_step      → 3+ navigations chained
- ambiguous_goal  → underspecified user request, agent must pick sensibly

Run:
    cd engine && DISPLAY=:99 python test_torture_browser.py [N]

N = scenarios per category (default 2). Total runtime ≈ N × ~45 s × 9 cats.
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, ".")
env_file = Path(__file__).parent.parent / ".env.local"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

from app.agent import execute_task  # noqa: E402


GEMINI_KEY = os.environ.get("GOOGLE_API_KEY")
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash:generateContent"
)


async def _gemini_json(system: str, user: str, max_tokens: int = 4096) -> dict:
    """JSON call with Gemini → Groq cascade. Direct API (no proactive
    adapter) so this file can run before the engine app is fully wired.

    Retries Gemini 3x then falls back to Groq's `llama-3.3-70b-versatile`
    (OpenAI-compatible endpoint) so 429s don't take down the harness."""

    # ── Gemini ──
    gemini_payload = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": max_tokens,
            "responseMimeType": "application/json",
        },
    }
    last_status = None
    last_body = ""
    async with httpx.AsyncClient(timeout=120) as client:
        for attempt in range(3):
            r = await client.post(
                f"{GEMINI_URL}?key={GEMINI_KEY}",
                json=gemini_payload,
            )
            last_status = r.status_code
            last_body = r.text[:200]
            if r.status_code == 200:
                data = r.json()
                try:
                    txt = data["candidates"][0]["content"]["parts"][0]["text"]
                    return json.loads(txt)
                except Exception:
                    if attempt == 2:
                        break
                    await asyncio.sleep(2)
            elif r.status_code == 429:
                # Don't burn extra Gemini calls when we're already rate-limited
                break
            else:
                if attempt == 2:
                    break
                await asyncio.sleep(2)

    # ── Groq fallback ──
    groq_key = os.environ.get("GROQ_API_KEY")
    if groq_key:
        groq_url = "https://api.groq.com/openai/v1/chat/completions"
        groq_body = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.0,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        async with httpx.AsyncClient(timeout=120) as client:
            for attempt in range(2):
                try:
                    r = await client.post(
                        groq_url,
                        json=groq_body,
                        headers={"Authorization": f"Bearer {groq_key}"},
                    )
                    if r.status_code == 200:
                        data = r.json()
                        txt = data["choices"][0]["message"]["content"]
                        return json.loads(txt)
                    last_status = r.status_code
                    last_body = r.text[:200]
                except json.JSONDecodeError as e:
                    last_status = "groq_json_decode"
                    last_body = str(e)[:200]
                except Exception:
                    pass
                if attempt < 1:
                    await asyncio.sleep(2)

    # ── Kimi (Moonshot) tertiary fallback ──
    # When both Gemini AND Groq exhaust their daily token budget, the
    # harness used to die. Kimi is on a separate quota / org so it survives
    # those simultaneous walls. Use `moonshot-v1-32k` because `kimi-k2.6`
    # requires `temperature=1.0` (returns 400 at temp 0) and we need
    # deterministic verdicts here.
    kimi_key = os.environ.get("KIMI_API_KEY")
    if kimi_key:
        kimi_url = "https://api.moonshot.ai/v1/chat/completions"
        kimi_body = {
            "model": "moonshot-v1-32k",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.0,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        async with httpx.AsyncClient(timeout=120) as client:
            for attempt in range(2):
                try:
                    r = await client.post(
                        kimi_url,
                        json=kimi_body,
                        headers={"Authorization": f"Bearer {kimi_key}"},
                    )
                    if r.status_code == 200:
                        data = r.json()
                        txt = data["choices"][0]["message"]["content"]
                        return json.loads(txt)
                    last_status = r.status_code
                    last_body = r.text[:200]
                except json.JSONDecodeError as e:
                    last_status = "kimi_json_decode"
                    last_body = str(e)[:200]
                except Exception:
                    pass
                if attempt < 1:
                    await asyncio.sleep(2)

    raise RuntimeError(
        f"all providers failed (last gemini/groq/kimi {last_status}: {last_body})"
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

GEN_SYSTEM = """You generate ONE adversarial test for a browser-automation agent.

The agent receives a plain-English goal, opens Chromium, and tries to complete \
the task on a real public website. The goal must be hard for a generic agent \
but solvable for a well-equipped one. No login required. No payment required. \
No fake or made-up sites — only real, currently-reachable public sites.

You return ONE JSON object with these exact fields:

{
  "category": "<exact category name from the list>",
  "goal": "<the natural-language task the user types to the agent>",
  "success_criteria": "<concrete check: what must appear in the agent's final \
answer, or what state must be true on the page, for this to count as a pass>",
  "fail_modes": ["<short string>", ...],
  "expected_techniques": ["<which generic capability the agent likely needs>"],
  "min_steps_estimate": <int>,
  "max_steps_estimate": <int>
}

CRITICAL RULES
- The goal is what a human says, not a script. Don't say "use selector X". \
Say "find Y" or "fill out the contact form with these details: ...".
- success_criteria must be checkable from the agent's final TEXT response or \
its state log. If a value is required, name it.
- For canvas_editor pick a public Google Docs / Sheets template URL that's \
in view-only or editable demo mode (e.g. a public "make a copy" template).
- For webgl_or_map pick a real map app (e.g. openstreetmap.org, \
maps.google.com search) or 3D viewer.
- For shadow_dom pick a public site known to use Lit / Polymer / LWC web \
components (e.g. youtube.com, salesforce help, ionic showcase).
- For login_wall the goal should be one the agent CAN'T finish without \
login. The pass criterion is that the agent reports the wall cleanly without \
faking success.
- expected_techniques is one or more of: \
"force_type", "canvas_type", "pierce_query", "canvas_pointer", \
"vision", "scroll", "multi_step", "graceful_decline".
"""

GEN_USER_TMPL = """Generate an adversarial scenario for category: {category}

Be creative — don't reuse goals you've seen before. Pick a real public URL.
Make the goal feel like something a real person would say to an assistant.
"""


async def _generate_scenario(category: str) -> dict:
    user = GEN_USER_TMPL.format(category=category)
    s = await _gemini_json(GEN_SYSTEM, user, max_tokens=2048)
    s.setdefault("category", category)
    return s


# ---------------------------------------------------------------------------
# Run one scenario
# ---------------------------------------------------------------------------


async def _run_scenario(scenario: dict, timeout: int = 240) -> dict:
    messages = []

    async def send(data):
        messages.append(data)
        t = data.get("type", "")
        m = (data.get("message") or "")[:120]
        print(f"  [{t}] {m}", flush=True)

    async def recv():
        return "yes"

    start = time.time()
    # Use user_id=None so each scenario gets a fresh ephemeral profile dir.
    # Sharing one stable dir across scenarios leaves SingletonLock and other
    # Chromium first-launch state behind — a previously-failed launch can
    # corrupt the next scenario's start.
    try:
        await asyncio.wait_for(
            execute_task(scenario["goal"], send, recv, user_id=None),
            timeout=timeout + 30,
        )
    except asyncio.TimeoutError:
        messages.append({"type": "error", "message": "HARD TIMEOUT"})
    except Exception as e:
        messages.append({"type": "error", "message": f"{type(e).__name__}: {str(e)[:120]}"})

    elapsed = time.time() - start

    complete = [m for m in messages if m.get("type") == "complete"]
    error = [m for m in messages if m.get("type") == "error"]
    final_text = ""
    if complete:
        final_text = complete[-1].get("message", "")
    elif error:
        final_text = error[-1].get("message", "")

    return {
        "scenario": scenario,
        "final_text": final_text,
        "messages": messages,
        "elapsed": round(elapsed, 1),
        "outcome": (
            "complete" if complete else
            "login_needed" if any(m.get("type") == "login_needed" for m in messages) else
            "error" if error else
            "stuck"
        ),
    }


# ---------------------------------------------------------------------------
# Judge
# ---------------------------------------------------------------------------

JUDGE_SYSTEM = """You are an impartial judge for a browser-automation agent.

You will see ONE scenario (goal + success criteria + fail modes) and the \
agent's final user-facing text. Decide whether the agent succeeded.

Return JSON: {
  "verdict": "pass" | "partial" | "fail",
  "reason": "<one sentence>",
  "missing": "<what's missing if partial/fail, else empty>"
}

Rules:
- "pass": all required information / state described in success_criteria is \
present and correct in the agent's final text. No hallucinated values.
- "partial": agent answered most fields but dropped at least one explicitly \
requested item, OR cleanly aborted with "I need login" when login_wall was \
the category (login_wall expects graceful decline → pass, not partial).
- "fail": agent didn't address the goal, faked an answer, returned a generic \
error, hallucinated a value, or the answer contradicts success_criteria.
- For login_wall: the agent passes by reporting the wall cleanly (no fake \
success). The agent fails by claiming completion of a task that requires \
login it doesn't have.
- Don't penalize the agent for verbose output — only for missing or wrong \
content.
"""


async def _judge(run: dict) -> dict:
    s = run["scenario"]
    user = json.dumps({
        "goal": s.get("goal"),
        "category": s.get("category"),
        "success_criteria": s.get("success_criteria"),
        "fail_modes": s.get("fail_modes", []),
        "agent_outcome": run["outcome"],
        "agent_final_text": run["final_text"][:2000],
    }, indent=2)
    # 512 tokens was getting truncated mid-string on verbose agent outputs
    # (cluster: "judge error: Unterminated string starting at..."). Pump it up
    # so the judge can finish a long `reason` field. Keeps the output schema
    # the same (verdict / reason / missing) and matches the rest of the
    # benchmark harness which uses 1024+.
    return await _gemini_json(JUDGE_SYSTEM, user, max_tokens=1024)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main(per_category: int = 2):
    print(f"Generating {per_category * len(CATEGORIES)} scenarios...", flush=True)
    scenarios = []
    for cat in CATEGORIES:
        for _ in range(per_category):
            try:
                s = await _generate_scenario(cat)
                scenarios.append(s)
                print(f"  [{cat}] {s.get('goal','')[:80]}", flush=True)
            except Exception as e:
                print(f"  [{cat}] generation failed: {e}", flush=True)

    print(f"\nRunning {len(scenarios)} scenarios...\n", flush=True)
    runs = []
    for i, sc in enumerate(scenarios, 1):
        print(f"\n=== {i}/{len(scenarios)}  [{sc.get('category')}] {sc.get('goal','')[:90]} ===", flush=True)
        run = await _run_scenario(sc)
        try:
            verdict = await _judge(run)
        except Exception as e:
            verdict = {"verdict": "fail", "reason": f"judge error: {e}", "missing": ""}
        run["verdict"] = verdict
        runs.append(run)
        v = verdict.get("verdict", "fail")
        print(f"  → {v.upper()}: {verdict.get('reason','')[:120]}", flush=True)

    # Aggregate
    by_cat = {}
    for r in runs:
        c = r["scenario"].get("category", "?")
        v = r["verdict"].get("verdict", "fail")
        by_cat.setdefault(c, {"pass": 0, "partial": 0, "fail": 0, "total": 0})
        by_cat[c][v] += 1
        by_cat[c]["total"] += 1

    print("\n" + "=" * 70)
    print("RESULTS BY CATEGORY")
    print("=" * 70)
    total_pass = total_partial = total_fail = 0
    for c, d in sorted(by_cat.items()):
        total_pass += d["pass"]
        total_partial += d["partial"]
        total_fail += d["fail"]
        print(f"  {c:22s}  pass={d['pass']:>2}  partial={d['partial']:>2}  fail={d['fail']:>2}  /{d['total']}")
    grand = total_pass + total_partial + total_fail
    pct = 100.0 * total_pass / grand if grand else 0.0
    print("-" * 70)
    print(f"  TOTAL: pass={total_pass}  partial={total_partial}  fail={total_fail}  ({pct:.1f}% strict pass)")

    out_path = Path("/tmp/torture_browser_detail.json")
    out_path.write_text(json.dumps(
        [{"category": r["scenario"].get("category"),
          "goal": r["scenario"].get("goal"),
          "verdict": r["verdict"].get("verdict"),
          "reason": r["verdict"].get("reason"),
          "missing": r["verdict"].get("missing"),
          "elapsed": r["elapsed"],
          "outcome": r["outcome"],
          "final_text": r["final_text"][:500]} for r in runs],
        indent=2,
    ))
    print(f"\nDetail: {out_path}")

    return total_pass, total_partial, total_fail


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    asyncio.run(main(per_category=n))
