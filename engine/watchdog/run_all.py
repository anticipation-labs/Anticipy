"""Watchdog tick — runs health_check + hermes sync + canary + restart
of crashed services each tick.

Invoked by ~/Library/LaunchAgents/ai.anticipy.watchdog.plist every
300s. Writes a combined JSON status object to stdout (captured to
~/.anticipy/watchdog.stdout.log).

Per master prompt Phase 9: "Restarts crashed services automatically."
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(REPO_ROOT / ".env.local")

from watchdog.canary import Canary  # noqa: E402
from watchdog.health_check import run_health_check  # noqa: E402
from watchdog.hermes import sync_once as hermes_sync  # noqa: E402


def restart_chrome() -> dict:
    """Use launchctl kickstart to restart the Chrome :9222 LaunchAgent.
    Idempotent — if already running, kickstart is a no-op."""
    try:
        # `launchctl kickstart -k gui/<uid>/com.anticipy.chrome` will
        # restart it if running. The -k forces a fresh launch even if
        # already up; we only call this when health says Chrome is down.
        import os
        uid = os.getuid()
        r = subprocess.run(
            ["launchctl", "kickstart", "-k", f"gui/{uid}/com.anticipy.chrome"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return {"ok": r.returncode == 0, "stdout": r.stdout.strip(), "stderr": r.stderr.strip()}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def main() -> int:
    health = run_health_check()
    restarts = {}
    chrome_check = next((c for c in health["checks"] if c["name"] == "chrome_9222"), None)
    if chrome_check and not chrome_check["ok"]:
        restarts["chrome"] = restart_chrome()
    out = {
        "health": health,
        "restarts": restarts,
        "hermes": hermes_sync(),
        "canary": Canary().maybe_run(),
    }
    print(json.dumps(out, indent=2))
    return 0 if health["all_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
