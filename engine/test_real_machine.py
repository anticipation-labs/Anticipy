"""Real-machine end-to-end test: drives YOUR Chrome with YOUR extension via
Supabase Realtime broadcasts, polls engine_trajectories for the result.

WHY: Patchright in this codespace is unreliable on broadcast reception.
The legitimate test is YOUR real Chrome on YOUR real machine with the
extension installed and signed in, listening on anticipy-intents. This
codespace orchestrates:

  1. Insert/Broadcast a confirmed_intent on anticipy-intents (your user_id)
  2. YOUR extension picks it up, runs through the multi-agent pipeline
     (planner+executor+verifier+critic+reflector hitting /api/agent/*),
     completes the task in YOUR Chrome with YOUR cookies and YOUR IP
  3. The agent POSTs a trajectory to /api/engine/trajectory at end-of-task
  4. We poll engine_trajectories for the matching intent_id row, score it,
     repeat for each scenario

PRE-FLIGHT (do these on your machine):
  - Pull the latest main (so your extension/agent.js has the new
    agent-team integration): `git pull`
  - Open Chrome
  - Install /workspaces/Anticipy/extension as an unpacked extension
    (chrome://extensions → Developer mode → Load unpacked → pick the dir),
    or RELOAD the extension if already installed (the reload arrow on
    the extension card)
  - Click the Anticipy icon → enter access code: 77c04c26 → Connect
  - Pin the extension; the SW must be alive while the test runs
  - Don't actively type during the test — the agent drives a tab; let it work

THEN in this codespace:
  cd /workspaces/Anticipy/engine
  set -a && source ../.env.local && set +a
  python test_real_machine.py
  # or for a single scenario:
  python test_real_machine.py --scenario wiki_python_year
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import uuid
from typing import Any

import httpx

# Re-use the scenarios + verifier helpers from the Patchright harness.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_extension_runner import (  # noqa: E402
    SCENARIOS,
    REALTIME_TOPIC,
    SUPABASE_URL,
    SUPABASE_SERVICE_ROLE_KEY,
    _service_headers,
)


# ─── Real-machine config ─────────────────────────────────────────────


# Omar's actual user_id (engine_users where access_code='77c04c26').
DEFAULT_USER_ID = "cc3fb754-6c7b-46da-bce7-dfa127a576d2"
DEFAULT_ACCESS_CODE = "77c04c26"
USER_ID = os.environ.get("ANTICIPY_USER_ID") or DEFAULT_USER_ID
ACCESS_CODE = os.environ.get("ANTICIPY_ACCESS_CODE") or DEFAULT_ACCESS_CODE


# ─── Broadcast + trajectory polling ──────────────────────────────────


async def broadcast_real_intent(
    client: httpx.AsyncClient,
    *,
    intent_id: str,
    task: str,
) -> None:
    """Broadcast on anticipy-intents with the configured user_id. Same
    payload shape as /api/engine/confirm produces."""
    payload = {
        "id": intent_id,
        "user_id": USER_ID,
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
    resp = await client.post(
        f"{SUPABASE_URL}/realtime/v1/api/broadcast",
        headers=_service_headers(),
        json=body,
        timeout=15.0,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"broadcast failed: {resp.status_code} {resp.text[:200]}")


async def wait_for_trajectory(
    client: httpx.AsyncClient,
    *,
    intent_id: str,
    timeout_s: float,
    poll_every_s: float = 4.0,
) -> dict[str, Any] | None:
    """Poll engine_trajectories until a row with this intent_id appears or
    timeout. Service-role read bypasses RLS."""
    deadline = time.time() + timeout_s
    last_log = 0.0
    started = time.time()
    while time.time() < deadline:
        url = (
            f"{SUPABASE_URL}/rest/v1/engine_trajectories"
            f"?intent_id=eq.{intent_id}&select=*&limit=1"
        )
        try:
            resp = await client.get(url, headers=_service_headers(), timeout=10.0)
            if resp.status_code == 200:
                rows = resp.json()
                if rows:
                    return rows[0]
        except (httpx.TimeoutException, httpx.NetworkError):
            pass
        if time.time() - last_log > 30:
            elapsed = int(time.time() - started)
            print(f"    ... still waiting ({elapsed}s elapsed)", flush=True)
            last_log = time.time()
        await asyncio.sleep(poll_every_s)
    return None


# ─── Pre-flight ──────────────────────────────────────────────────────


async def preflight(client: httpx.AsyncClient) -> tuple[bool, str]:
    """Confirm the user exists and the agent-team routes are live."""
    # 1. user lookup
    url = (
        f"{SUPABASE_URL}/rest/v1/engine_users"
        f"?id=eq.{USER_ID}&select=id,access_code&limit=1"
    )
    try:
        resp = await client.get(url, headers=_service_headers(), timeout=10.0)
        if resp.status_code != 200 or not resp.json():
            return False, f"user_id {USER_ID} not in engine_users"
        if resp.json()[0]["access_code"] != ACCESS_CODE:
            return False, f"access_code mismatch for user_id {USER_ID}"
    except Exception as e:
        return False, f"engine_users lookup failed: {e}"

    # 2. /api/agent/plan reachability (auth handshake)
    try:
        resp = await client.post(
            "https://www.anticipy.ai/api/agent/plan",
            headers={
                "Content-Type": "application/json",
                "X-Anticipy-Code": ACCESS_CODE,
            },
            json={"task": "ping"},
            timeout=30,
        )
        if resp.status_code not in (200, 400):
            return False, f"/api/agent/plan returned {resp.status_code}"
    except Exception as e:
        return False, f"/api/agent/plan unreachable: {e}"

    return True, "ok"


# ─── LLM judge for verdicts ──────────────────────────────────────────


def judge_outcome(scenario: dict, trajectory: dict | None) -> tuple[bool, str]:
    """Use the existing per-scenario verifier (which itself wraps the LLM
    judge in app.llm_judge for non-trivial scenarios)."""
    if trajectory is None:
        return False, "NO TRAJECTORY (timed out — extension did not POST one)"
    msg = trajectory.get("outcome_message") or ""
    outcome = trajectory.get("outcome") or "unknown"
    try:
        verifier = scenario["verify"]
        passed = bool(verifier({"message": msg}))
        return passed, f"outcome={outcome} | message: {msg[:240]}"
    except Exception as e:
        return False, f"verifier raised: {e} | message: {msg[:240]}"


# ─── Main ────────────────────────────────────────────────────────────


async def main(
    scenario_filter: str | None = None,
    per_task_timeout_s: float = 360.0,
) -> int:
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        print("ERROR: SUPABASE env vars not set. source .env.local first.",
              file=sys.stderr)
        return 2

    print("=== Anticipy real-machine end-to-end test ===", flush=True)
    print(f"User ID:     {USER_ID}", flush=True)
    print(f"Access code: {ACCESS_CODE[:4]}...{ACCESS_CODE[-2:]}", flush=True)
    print(f"Endpoints:   https://www.anticipy.ai/api/agent/*", flush=True)

    async with httpx.AsyncClient() as client:
        ok, reason = await preflight(client)
        if not ok:
            print(f"\nPRE-FLIGHT FAILED: {reason}", flush=True)
            return 3
        print("Pre-flight OK\n", flush=True)
        print("(Make sure your Chrome is open with the Anticipy extension "
              "signed in.)", flush=True)
        print("(Pull latest main first: cd ~/Anticipy && git pull, then "
              "reload the extension in chrome://extensions.)", flush=True)

        scenarios = SCENARIOS
        if scenario_filter:
            scenarios = [s for s in SCENARIOS if scenario_filter in s["name"]]
            if not scenarios:
                print(f"No scenarios match filter '{scenario_filter}'", flush=True)
                return 4

        print(f"\nRunning {len(scenarios)} scenario(s)", flush=True)
        results: list[dict] = []

        for scenario in scenarios:
            intent_id = str(uuid.uuid4())
            print(f"\n== {scenario['name']} (intent {intent_id[:8]}…)", flush=True)
            print(f"   task: {scenario['task']}", flush=True)
            t0 = time.time()
            try:
                await broadcast_real_intent(
                    client, intent_id=intent_id, task=scenario["task"]
                )
            except Exception as e:
                print(f"   FAIL — broadcast: {e}", flush=True)
                results.append({
                    "scenario": scenario["name"],
                    "passed": False,
                    "reason": f"broadcast: {e}",
                    "duration_s": 0,
                })
                continue

            print(f"   broadcast sent — waiting for trajectory "
                  f"(≤{int(per_task_timeout_s)}s)...", flush=True)
            row = await wait_for_trajectory(
                client,
                intent_id=intent_id,
                timeout_s=per_task_timeout_s,
            )
            duration = time.time() - t0
            passed, detail = judge_outcome(scenario, row)
            mark = "PASS" if passed else "FAIL"
            print(f"   [{mark}] {duration:.1f}s — {detail[:240]}", flush=True)
            results.append({
                "scenario": scenario["name"],
                "passed": passed,
                "duration_s": duration,
                "detail": detail,
                "intent_id": intent_id,
                "trajectory_id": (row or {}).get("id"),
                "outcome": (row or {}).get("outcome"),
                "total_steps": (row or {}).get("total_steps"),
            })

        # Summary
        print("\n=== RESULTS ===", flush=True)
        for r in results:
            mark = "PASS" if r["passed"] else "FAIL"
            steps = r.get("total_steps")
            outcome = r.get("outcome") or "?"
            steps_str = f" steps={steps}" if steps is not None else ""
            print(f"  [{mark}] {r['scenario']}  {r.get('duration_s', 0):.1f}s "
                  f"outcome={outcome}{steps_str}", flush=True)
        passed_n = sum(1 for r in results if r["passed"])
        total = len(results)
        pct = 100.0 * passed_n / total if total else 0.0
        print(f"\n{passed_n}/{total} passed ({pct:.0f}%)", flush=True)

        # Persist
        out_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "logs",
            f"real_machine_{int(time.time())}.json",
        )
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w") as f:
            json.dump({
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "user_id": USER_ID,
                "access_code_prefix": ACCESS_CODE[:4] + "...",
                "results": results,
                "passed": passed_n,
                "total": total,
                "pct": pct,
            }, f, indent=2)
        print(f"\nLog: {out_path}", flush=True)

        return 0 if passed_n == total else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", help="Substring filter on scenario name "
                        "(e.g. 'wiki', 'compare', 'youtube')")
    parser.add_argument("--timeout", type=float, default=360.0,
                        help="Per-task timeout seconds (default 360 = 6 min)")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.scenario, args.timeout)))
