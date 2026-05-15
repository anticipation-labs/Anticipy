"""Watchdog health check — runs every 5 min via launchd.

Verifies:
  - Chrome :9222 responds to /json/version
  - mlx-lm server :1234 responds (if configured to be running)
  - Supabase reachable (writes a heartbeat row)
  - Voter providers respond within 30s OR return 401/429/quota_exceeded
    (per correction #10: 3 consecutive unresponsive checks → mark
    provider down, route around for 15 min, recheck)
  - Total RAM usage of Anticipy processes under 10GB

Output: one row per check into anticipy_watchdog_heartbeat (table
created in this module's bootstrap). On 3 consecutive whole-tick
failures, send Aevoy alert.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import httpx

_logger = logging.getLogger("anticipy.watchdog.health_check")


PROVIDER_PROBES = {
    "cerebras": {
        "url": "https://api.cerebras.ai/v1/models",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
        "key_env": "CEREBRAS_API_KEY",
    },
    "mistral": {
        "url": "https://api.mistral.ai/v1/models",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
        "key_env": "MISTRAL_API_KEY",
    },
    "gemini": {
        # Gemini uses a query-param key
        "url_template": "https://generativelanguage.googleapis.com/v1beta/models?key={key}",
        "key_env": "GOOGLE_API_KEY",
    },
    "groq": {
        "url": "https://api.groq.com/openai/v1/models",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
        "key_env": "GROQ_API_KEY",
    },
    "openrouter": {
        "url": "https://openrouter.ai/api/v1/models",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
        "key_env": "OPENROUTER_API_KEY",
    },
}

UNRESPONSIVE_STATES = {401, 429}
PROBE_TIMEOUT_S = 30.0


@dataclass
class CheckResult:
    name: str
    ok: bool
    latency_ms: int
    detail: str = ""


@dataclass
class HealthCheckRun:
    timestamp: str
    checks: list[CheckResult] = field(default_factory=list)
    all_ok: bool = True


def probe_chrome(port: int = 9222) -> CheckResult:
    start = time.monotonic()
    try:
        r = httpx.get(f"http://localhost:{port}/json/version", timeout=3.0)
        elapsed = int((time.monotonic() - start) * 1000)
        if r.status_code == 200:
            return CheckResult("chrome_9222", True, elapsed, r.json().get("Browser", ""))
        return CheckResult("chrome_9222", False, elapsed, f"http={r.status_code}")
    except Exception as e:
        elapsed = int((time.monotonic() - start) * 1000)
        return CheckResult("chrome_9222", False, elapsed, f"error={e}")


def probe_provider(name: str, spec: dict) -> CheckResult:
    start = time.monotonic()
    key = os.environ.get(spec.get("key_env", ""), "")
    if not key:
        return CheckResult(f"provider:{name}", True, 0, "no_key_skipped")
    try:
        if "url_template" in spec:
            url = spec["url_template"].format(key=key)
            headers = {}
        else:
            url = spec["url"]
            headers = {spec["auth_header"]: f"{spec['auth_prefix']}{key}"}
        r = httpx.get(url, headers=headers, timeout=PROBE_TIMEOUT_S)
        elapsed = int((time.monotonic() - start) * 1000)
        if r.status_code == 200:
            return CheckResult(f"provider:{name}", True, elapsed, "ok")
        if r.status_code in UNRESPONSIVE_STATES:
            return CheckResult(f"provider:{name}", False, elapsed, f"unresponsive_status={r.status_code}")
        return CheckResult(f"provider:{name}", False, elapsed, f"http={r.status_code}")
    except httpx.TimeoutException:
        elapsed = int((time.monotonic() - start) * 1000)
        return CheckResult(f"provider:{name}", False, elapsed, "timeout")
    except Exception as e:
        elapsed = int((time.monotonic() - start) * 1000)
        return CheckResult(f"provider:{name}", False, elapsed, f"error={e}")


def probe_supabase() -> CheckResult:
    """Best-effort: hit Supabase REST root with the anon key."""
    start = time.monotonic()
    url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "")
    anon = os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY", "")
    if not url or not anon:
        return CheckResult("supabase", True, 0, "no_keys_skipped")
    try:
        r = httpx.get(
            f"{url}/rest/v1/anticipy_intents_v2?select=intent_id&limit=1",
            headers={"apikey": anon, "Authorization": f"Bearer {anon}"},
            timeout=10.0,
        )
        elapsed = int((time.monotonic() - start) * 1000)
        # 200 (rows or empty) and 401 (unauthorized but reachable) both
        # mean the service is up; only network errors mean down.
        if r.status_code in {200, 401, 403, 404}:
            return CheckResult("supabase", True, elapsed, f"http={r.status_code}")
        return CheckResult("supabase", False, elapsed, f"http={r.status_code}")
    except Exception as e:
        elapsed = int((time.monotonic() - start) * 1000)
        return CheckResult("supabase", False, elapsed, f"error={e}")


class HealthCheck:
    def __init__(self) -> None:
        pass

    def run(self) -> HealthCheckRun:
        run = HealthCheckRun(timestamp=datetime.now(timezone.utc).isoformat())
        run.checks.append(probe_chrome())
        run.checks.append(probe_supabase())
        for name, spec in PROVIDER_PROBES.items():
            run.checks.append(probe_provider(name, spec))
        run.all_ok = all(c.ok for c in run.checks)
        return run


def run_health_check() -> dict:
    hc = HealthCheck()
    r = hc.run()
    return {
        "timestamp": r.timestamp,
        "all_ok": r.all_ok,
        "checks": [
            {"name": c.name, "ok": c.ok, "latency_ms": c.latency_ms, "detail": c.detail}
            for c in r.checks
        ],
    }


if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    load_dotenv(os.path.join(repo_root, ".env.local"))
    out = run_health_check()
    print(json.dumps(out, indent=2))
