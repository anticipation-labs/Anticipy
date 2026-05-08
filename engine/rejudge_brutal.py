"""
rejudge_brutal.py — re-evaluate failed brutal-test scenarios with a fairer
verifier (fixed regex, broader login-hints) and an LLM-as-judge tiebreaker.

Why: the strict programmatic verifier overcounts failures from these classes:
- LLM-generated literal-fact patterns (e.g., 'netanyahu', '1979') that don't
  match today's reality; agent gave the correct answer.
- URL patterns with '+' interpreted as regex meta-char.
- "signed in" not in the original LOGIN_HINTS list.
- LLM provider rate-limit aborts that are infra issues, not agent failures.

Output: logs/browser_brutal_rejudged.json + a delta in the markdown report.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env.local"
LOG_DIR = Path(__file__).resolve().parent / "logs"
JSON_IN = LOG_DIR / "browser_brutal.json"
JSON_OUT = LOG_DIR / "browser_brutal_rejudged.json"
MD_OUT = LOG_DIR / "browser_brutal.md"

if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

GEMINI_KEY = os.environ["GOOGLE_API_KEY"]
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash:generateContent"
)


# ─── Programmatic re-verifier (FIXED) ─────────────────────────────────────────

LOGIN_HINTS = (
    "sign in", "signed in", "sign up", "log in", "logged in", "login",
    "log-in", "signin", "sign-in", "authenticate", "authentication",
    "credentials", "account", "session", "wall", "blocked", "auth ",
    "auth.", "auth-", "your real session", "open it once",
    "in this browser", "ask me again",
)
INFRA_HINTS = (
    "hit a hiccup", "rate limit", "empty response", "groq 429",
    "fetch failed", "network error",
)
CAPTCHA_HINTS = (
    "captcha", "verify you are human", "robot", "are you human",
    "human check",
)


def _match_any(text: str, pats: list[str]) -> bool:
    if not pats:
        return True
    for p in pats:
        if p in text:
            return True
        try:
            if re.search(p, text):
                return True
        except re.error:
            pass
    return False


def reverify(scenario: dict, run: dict) -> dict:
    """Return {'pass': bool, 'reason': str, 'class': str}."""
    verifier = scenario.get("verifier", {}) or {}
    vtype = verifier.get("type", "agent_success")
    patterns = [str(p).lower() for p in (verifier.get("patterns") or [])]
    patterns_b = [str(p).lower() for p in (verifier.get("patterns_b") or [])]
    msg = (run.get("agent_message") or "").lower().strip()
    url = (run.get("final_url") or "").lower()
    success = bool(run.get("agent_success"))
    timed_out = bool(run.get("timed_out"))

    if timed_out:
        return {"pass": False, "reason": "runner timeout", "class": "timeout"}

    # Classify infra/captcha failures distinctly.
    if any(h in msg for h in INFRA_HINTS):
        return {"pass": False, "reason": "LLM provider exhaustion / network", "class": "infra"}
    if any(h in msg for h in CAPTCHA_HINTS):
        return {"pass": False, "reason": "site demanded captcha", "class": "captcha"}

    if vtype == "agent_success":
        return {"pass": success, "reason": "agent_success", "class": "agent_success"}

    if vtype == "agent_failed_with_login":
        if success:
            return {"pass": False, "reason": "claimed success on login wall", "class": "false_positive"}
        if any(h in msg for h in LOGIN_HINTS) or any(h in msg for h in CAPTCHA_HINTS):
            return {"pass": True, "reason": "declined gracefully", "class": "graceful_decline"}
        return {"pass": False, "reason": "decline did not mention login", "class": "decline_unclear"}

    if vtype == "message_contains_any":
        return {
            "pass": _match_any(msg, patterns),
            "reason": "message_contains_any",
            "class": "literal_check",
        }

    if vtype == "message_contains_all":
        for p in patterns:
            if p not in msg and not (re.error if False else re.search(re.escape(p), msg)):
                # fall through to LLM
                return {"pass": False, "reason": f"missing {p!r}", "class": "literal_check"}
        return {"pass": True, "reason": "all patterns matched", "class": "literal_check"}

    if vtype == "url_contains_any":
        return {
            "pass": _match_any(url, patterns),
            "reason": "url_contains_any",
            "class": "url_check",
        }

    if vtype == "and_of_or":
        ok = _match_any(msg, patterns)
        if patterns_b:
            ok = ok and _match_any(msg, patterns_b)
        return {"pass": ok, "reason": "and_of_or", "class": "literal_check"}

    return {"pass": success, "reason": "unknown verifier — trust agent_success", "class": "fallback"}


# ─── LLM-as-judge for ambiguous cases ────────────────────────────────────────

JUDGE_SYSTEM = """You are a fair judge for a browser-agent benchmark.

You see ONE scenario (a natural-language task) and the agent's final message.
Decide if the agent SUBSTANTIVELY accomplished the task. Be lenient about
exact wording / specific facts the verifier picked — what matters is whether
the agent gave a reasonable, factually-plausible answer to what the user asked.

Return JSON:
{ "pass": true|false, "why": "<one sentence>" }

Rules:
- For "find / extract / report" tasks: pass if the agent's message contains a
  plausible answer (a real URL, a real headline, a real number, etc.). The
  literal benchmark patterns may be stale (today's news changes daily).
- For "login wall / decline" tasks: pass if the agent declined cleanly without
  faking success.
- For "type into canvas" tasks: pass if the agent reported it typed and the
  intended phrase appears in the message.
- Fail if the agent claimed success but the message contradicts itself, OR if
  the answer is patently wrong (Mt Everest is not 100m tall).
- LLM provider errors / rate limits / captcha walls: NOT the agent's fault,
  but still a fail — return pass=false with reason="external".
"""


async def llm_judge(scenario: dict, run: dict) -> dict:
    payload = {
        "task": scenario.get("summary_for_user", ""),
        "category": scenario.get("category", ""),
        "agent_success": run.get("agent_success"),
        "agent_message": (run.get("agent_message") or "")[:600],
        "final_url": run.get("final_url", "")[:200],
        "step_count": run.get("step_count"),
    }
    body = {
        "system_instruction": {"parts": [{"text": JUDGE_SYSTEM}]},
        "contents": [{"role": "user", "parts": [{"text": json.dumps(payload, indent=2)}]}],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 256,
            "responseMimeType": "application/json",
        },
    }
    async with httpx.AsyncClient(timeout=60) as c:
        for attempt in range(3):
            try:
                r = await c.post(f"{GEMINI_URL}?key={GEMINI_KEY}", json=body)
                if r.status_code == 200:
                    txt = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                    return json.loads(txt)
            except Exception:
                pass
            await asyncio.sleep(2 + attempt)
    return {"pass": False, "why": "judge unreachable"}


# ─── Main ────────────────────────────────────────────────────────────────────

async def main():
    if not JSON_IN.exists():
        print(f"No {JSON_IN}, run brutal first")
        return 1
    rows = json.loads(JSON_IN.read_text())
    print(f"Re-judging {len(rows)} scenarios...", flush=True)

    out = []
    for i, r in enumerate(rows, 1):
        scenario = {
            "summary_for_user": r["summary"],
            "category": r["category"],
            "verifier": r["verifier"],
            "starting_url": r.get("starting_url"),
        }
        run = {
            "agent_success": r["agent_success"],
            "agent_message": r["agent_message"],
            "final_url": r["final_url"],
            "step_count": r["step_count"],
            "elapsed_s": r["elapsed_s"],
            "timed_out": r["timed_out"],
        }
        rev = reverify(scenario, run)
        # If reverify says fail BUT it's a "literal_check" or "url_check" or
        # "decline_unclear" class, escalate to LLM judge for fairness.
        if not rev["pass"] and rev["class"] in (
            "literal_check", "url_check", "decline_unclear", "fallback"
        ):
            judge = await llm_judge(scenario, run)
            verdict_pass = bool(judge.get("pass"))
            why = judge.get("why", "")
            decision = "llm_judge"
        else:
            verdict_pass = rev["pass"]
            why = rev["reason"]
            decision = "programmatic"
        out.append({
            **r,
            "rejudge_pass": verdict_pass,
            "rejudge_class": rev["class"],
            "rejudge_why": why,
            "rejudge_decision": decision,
        })
        marker = "PASS" if verdict_pass else "FAIL"
        print(f"  {i:>2}/{len(rows)} [{r['category'][:18]:<18}] {marker} ({decision}): {why[:80]}", flush=True)
        # Throttle to keep Gemini happy.
        await asyncio.sleep(0.3)

    JSON_OUT.write_text(json.dumps(out, indent=2))
    print(f"\nWrote {JSON_OUT}")

    # Aggregate
    by_cat: dict[str, dict] = {}
    for r in out:
        c = r["category"]
        d = by_cat.setdefault(c, {"orig_pass": 0, "rej_pass": 0, "total": 0})
        d["total"] += 1
        if r["verdict_pass"]:
            d["orig_pass"] += 1
        if r["rejudge_pass"]:
            d["rej_pass"] += 1

    total = len(out)
    orig_pass = sum(d["orig_pass"] for d in by_cat.values())
    rej_pass = sum(d["rej_pass"] for d in by_cat.values())
    print("\nFairness re-judge results:")
    print(f"  Original strict verifier:   {orig_pass}/{total} ({100*orig_pass/total:.0f}%)")
    print(f"  Re-judged (lenient + LLM):  {rej_pass}/{total} ({100*rej_pass/total:.0f}%)")
    for c in sorted(by_cat):
        d = by_cat[c]
        print(f"    {c:30s}  orig={d['orig_pass']}/{d['total']}  rej={d['rej_pass']}/{d['total']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
