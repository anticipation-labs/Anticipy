"""Direct test of the deployed multi-agent brain — Planner / Verifier / Critic.

Bypasses the Chrome extension entirely. Calls /api/agent/{plan,verify,critic}
on www.anticipy.ai with mock-but-realistic page signals to validate the
reasoning chain produces coherent plans + verdicts WITHOUT touching the
flaky Patchright codespace harness.

Five test scenarios cover the four reasoning paths:
  1. Happy path: planner → executor (mocked correct) → verifier (satisfied)
  2. Silent stall: executor returns success but page didn't change → verifier
     should reject (critical capability)
  3. Wrong navigation: executor went to wrong site → verifier rejects
  4. Multi-step plan: navigate → search → extract → done; verifier advances
  5. Critic invocation: 2 verifier rejects → critic produces new approach

Run:
    set -a && source ../.env.local && set +a
    python test_multi_agent_brain.py
"""
from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

import httpx


BASE_URL = "https://www.anticipy.ai"
ACCESS_CODE = "77c04c26"  # Omar's access code

HEADERS = {
    "Content-Type": "application/json",
    "X-Anticipy-Code": ACCESS_CODE,
}


# ─── Fixtures: realistic page signal pairs (before, after) ─────────────


SIG_BLANK = {
    "url": "about:blank",
    "title": "",
    "topHeading": "",
    "buttonCount": 0,
    "inputCount": 0,
    "linkCount": 0,
    "formCount": 0,
    "hasModal": False,
    "bodyTextLen": 0,
    "bodyFingerprint": "blank",
}

SIG_WIKI_HOME = {
    "url": "https://www.wikipedia.org/",
    "title": "Wikipedia",
    "topHeading": "Wikipedia",
    "buttonCount": 12,
    "inputCount": 1,
    "linkCount": 350,
    "formCount": 1,
    "hasModal": False,
    "bodyTextLen": 1800,
    "bodyFingerprint": "wikihome",
}

SIG_WIKI_PYTHON = {
    "url": "https://en.wikipedia.org/wiki/Python_(programming_language)",
    "title": "Python (programming language) - Wikipedia",
    "topHeading": "Python (programming language)",
    "buttonCount": 18,
    "inputCount": 2,
    "linkCount": 820,
    "formCount": 2,
    "hasModal": False,
    "bodyTextLen": 98000,
    "bodyFingerprint": "pyarticle",
}

SIG_WRONG_PAGE = {
    "url": "https://www.python.org/",
    "title": "Welcome to Python.org",
    "topHeading": "Get Started",
    "buttonCount": 30,
    "inputCount": 1,
    "linkCount": 200,
    "formCount": 0,
    "hasModal": False,
    "bodyTextLen": 8000,
    "bodyFingerprint": "pythonorg",
}


# ─── Test scenarios ───────────────────────────────────────────────────


async def test_planner_returns_coherent_plan(client: httpx.AsyncClient) -> dict:
    """Planner must produce 3-7 numbered steps with observable success_criteria."""
    name = "planner_coherence"
    print(f"\n[1/5] {name}", flush=True)
    resp = await client.post(
        f"{BASE_URL}/api/agent/plan",
        headers=HEADERS,
        json={
            "task": "Look up on Wikipedia what year Python was first released.",
            "current_url": "about:blank",
            "domain": "",
        },
        timeout=60,
    )
    if resp.status_code != 200:
        return {"name": name, "passed": False, "reason": f"HTTP {resp.status_code}"}
    data = resp.json()
    plan = data.get("plan", [])
    if not isinstance(plan, list) or not (3 <= len(plan) <= 7):
        return {"name": name, "passed": False, "reason": f"plan length {len(plan)} not in 3-7"}
    for step in plan:
        if not isinstance(step.get("step"), int):
            return {"name": name, "passed": False, "reason": "step not numeric"}
        if not step.get("goal", "").strip():
            return {"name": name, "passed": False, "reason": "missing goal"}
        if not step.get("success_criteria", "").strip():
            return {"name": name, "passed": False, "reason": "missing success_criteria"}
    print(f"  PASS — {len(plan)} steps, all with goal+success_criteria", flush=True)
    return {"name": name, "passed": True, "plan": plan}


async def test_verifier_catches_silent_stall(client: httpx.AsyncClient) -> dict:
    """Action returned success=True but page didn't change. Verifier MUST reject."""
    name = "verifier_silent_stall"
    print(f"\n[2/5] {name}", flush=True)
    # Same signals before AND after — page didn't change
    resp = await client.post(
        f"{BASE_URL}/api/agent/verify",
        headers=HEADERS,
        json={
            "task": "Look up Python's release year on Wikipedia",
            "plan_step": {
                "step": 1,
                "goal": "Navigate to Python's Wikipedia article",
                "success_criteria": "URL contains '/wiki/Python' and heading mentions Python",
            },
            "action": {"action": "click", "selector": ".search-button"},
            "before_signals": SIG_WIKI_HOME,
            "after_signals": SIG_WIKI_HOME,  # NO CHANGE
            "last_step_success": True,  # executor LIES
        },
        timeout=30,
    )
    if resp.status_code != 200:
        return {"name": name, "passed": False, "reason": f"HTTP {resp.status_code}"}
    data = resp.json()
    if data.get("satisfied"):
        return {"name": name, "passed": False, "reason": f"verifier wrongly said satisfied: {data.get('evidence','')}"}
    print(f"  PASS — verifier rejected silent stall: {data.get('evidence','')[:120]}", flush=True)
    return {"name": name, "passed": True}


async def test_verifier_accepts_real_progress(client: httpx.AsyncClient) -> dict:
    """Action navigated to the right page. Verifier MUST accept + advance plan."""
    name = "verifier_accepts_progress"
    print(f"\n[3/5] {name}", flush=True)
    resp = await client.post(
        f"{BASE_URL}/api/agent/verify",
        headers=HEADERS,
        json={
            "task": "Look up Python's release year on Wikipedia",
            "plan_step": {
                "step": 1,
                "goal": "Navigate to Python's Wikipedia article",
                "success_criteria": "URL contains '/wiki/Python' and heading mentions Python",
            },
            "action": {"action": "navigate", "url": "https://en.wikipedia.org/wiki/Python_(programming_language)"},
            "before_signals": SIG_BLANK,
            "after_signals": SIG_WIKI_PYTHON,
            "last_step_success": True,
            "visible_text_excerpt": "Python (programming language). Python is a high-level programming language. First appeared 1991.",
        },
        timeout=30,
    )
    if resp.status_code != 200:
        return {"name": name, "passed": False, "reason": f"HTTP {resp.status_code}"}
    data = resp.json()
    if not data.get("satisfied"):
        return {"name": name, "passed": False, "reason": f"verifier wrongly rejected: {data.get('evidence','')}"}
    if not data.get("advance_plan"):
        return {"name": name, "passed": False, "reason": "verifier didn't advance the plan"}
    print(f"  PASS — verifier accepted + advanced: {data.get('evidence','')[:120]}", flush=True)
    return {"name": name, "passed": True}


async def test_verifier_rejects_wrong_navigation(client: httpx.AsyncClient) -> dict:
    """Plan said go to Wikipedia. Executor went to python.org. Verifier MUST reject."""
    name = "verifier_wrong_target"
    print(f"\n[4/5] {name}", flush=True)
    resp = await client.post(
        f"{BASE_URL}/api/agent/verify",
        headers=HEADERS,
        json={
            "task": "Look up Python's release year on Wikipedia",
            "plan_step": {
                "step": 1,
                "goal": "Navigate to Python's Wikipedia article",
                "success_criteria": "URL contains 'wikipedia.org' AND '/wiki/Python'",
            },
            "action": {"action": "navigate", "url": "https://www.python.org"},
            "before_signals": SIG_BLANK,
            "after_signals": SIG_WRONG_PAGE,
            "last_step_success": True,
        },
        timeout=30,
    )
    if resp.status_code != 200:
        return {"name": name, "passed": False, "reason": f"HTTP {resp.status_code}"}
    data = resp.json()
    if data.get("satisfied"):
        return {"name": name, "passed": False, "reason": f"verifier accepted wrong page: {data.get('evidence','')}"}
    print(f"  PASS — verifier rejected wrong target: {data.get('evidence','')[:120]}", flush=True)
    return {"name": name, "passed": True}


async def test_critic_proposes_recovery(client: httpx.AsyncClient) -> dict:
    """After 2 verifier-rejects, critic should diagnose + propose a different approach."""
    name = "critic_recovers"
    print(f"\n[5/5] {name}", flush=True)
    resp = await client.post(
        f"{BASE_URL}/api/agent/critic",
        headers=HEADERS,
        json={
            "task": "Look up Python's release year on Wikipedia",
            "plan": [
                {"step": 1, "goal": "Navigate to Wikipedia", "success_criteria": "URL contains wikipedia"},
                {"step": 2, "goal": "Search for Python", "success_criteria": "URL contains /wiki/Python"},
                {"step": 3, "goal": "Extract release year", "success_criteria": "Year extracted"},
            ],
            "current_step_index": 1,
            "history": [
                {"action": {"action": "click", "selector": "a.first-link"},
                 "result": {"success": True, "error": None},
                 "signalDiff": "NONE — page didn't visibly change"},
                {"action": {"action": "click", "selector": "a.first-link"},
                 "result": {"success": True, "error": None},
                 "signalDiff": "NONE — page didn't visibly change"},
            ],
            "verifier_evidence": "Two consecutive clicks fired but URL did not change. Selector may be wrong or click is being intercepted.",
            "domain": "wikipedia.org",
        },
        timeout=30,
    )
    if resp.status_code != 200:
        return {"name": name, "passed": False, "reason": f"HTTP {resp.status_code}"}
    data = resp.json()
    diagnosis = data.get("diagnosis", "")
    new_approach = data.get("new_approach", "")
    if not diagnosis.strip() or not new_approach.strip():
        return {"name": name, "passed": False, "reason": "missing diagnosis or new_approach"}
    if data.get("abort"):
        return {"name": name, "passed": False, "reason": f"critic wrongly aborted: {data.get('abort_reason')}"}
    print(f"  PASS — critic diagnosed + proposed:", flush=True)
    print(f"    diagnosis: {diagnosis[:160]}", flush=True)
    print(f"    new_approach: {new_approach[:160]}", flush=True)
    return {"name": name, "passed": True}


# ─── Runner ────────────────────────────────────────────────────────────


async def main() -> int:
    print("=== Multi-agent brain — direct API test ===", flush=True)
    print(f"Endpoints: {BASE_URL}/api/agent/*", flush=True)

    async with httpx.AsyncClient() as client:
        results = []
        for fn in [
            test_planner_returns_coherent_plan,
            test_verifier_catches_silent_stall,
            test_verifier_accepts_real_progress,
            test_verifier_rejects_wrong_navigation,
            test_critic_proposes_recovery,
        ]:
            try:
                r = await fn(client)
                results.append(r)
            except Exception as e:
                results.append({"name": fn.__name__, "passed": False, "reason": f"exception: {e}"})

    print("\n=== RESULTS ===", flush=True)
    for r in results:
        mark = "PASS" if r["passed"] else "FAIL"
        print(f"  [{mark}] {r['name']}", flush=True)
        if not r["passed"]:
            print(f"      reason: {r.get('reason','?')}", flush=True)

    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    pct = 100.0 * passed / total
    print(f"\n{passed}/{total} passed ({pct:.0f}%)", flush=True)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
