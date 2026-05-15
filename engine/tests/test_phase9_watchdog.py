"""Phase 9 watchdog test — runs health_check end-to-end against real
endpoints. Per Rule 13: this gates the watchdog ship.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT.parent / ".env.local")

from watchdog.health_check import run_health_check  # noqa: E402
from watchdog.canary import Canary  # noqa: E402

cases: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = ""):
    cases.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}{('  — ' + detail) if detail else ''}")


def main() -> int:
    out = run_health_check()
    record("watchdog.has_timestamp", isinstance(out.get("timestamp"), str) and len(out["timestamp"]) > 0)
    record("watchdog.has_checks", isinstance(out.get("checks"), list) and len(out["checks"]) >= 5)

    by_name = {c["name"]: c for c in out["checks"]}
    record("watchdog.chrome_9222", by_name.get("chrome_9222", {}).get("ok") is True,
        by_name.get("chrome_9222", {}).get("detail", ""))
    record("watchdog.supabase_reachable", by_name.get("supabase", {}).get("ok") is True,
        by_name.get("supabase", {}).get("detail", ""))
    # At least 2 of the 5 voter providers must respond OK
    provider_ok_count = sum(
        1 for c in out["checks"]
        if c["name"].startswith("provider:") and c["ok"]
    )
    record("watchdog.at_least_2_providers_ok",
        provider_ok_count >= 2,
        f"providers_ok={provider_ok_count}")

    canary = Canary()
    is_due_initially = canary.is_due()
    canary.mark_run()
    is_due_after = canary.is_due()
    record("canary.is_due_returns_bool",
        isinstance(is_due_initially, bool) and isinstance(is_due_after, bool),
        f"initially={is_due_initially} after={is_due_after}")
    record("canary.mark_run_persists",
        is_due_after is False,
        "mark_run flips is_due to False until 4h elapses")

    n = len(cases)
    hits = sum(1 for _, ok, _ in cases if ok)
    print()
    print(f"== SUMMARY: {hits}/{n} ==")
    for name, ok, detail in cases:
        if not ok:
            print(f"   FAIL  {name}  {detail}")
    return 0 if hits == n else 1


if __name__ == "__main__":
    sys.exit(main())
