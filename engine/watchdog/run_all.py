"""Watchdog tick — runs health_check + hermes sync each tick.

Invoked by ~/Library/LaunchAgents/ai.anticipy.watchdog.plist every
300s. Writes a combined JSON status object to stdout (captured to
~/.anticipy/watchdog.stdout.log).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(REPO_ROOT / ".env.local")

from watchdog.canary import Canary  # noqa: E402
from watchdog.health_check import run_health_check  # noqa: E402
from watchdog.hermes import sync_once as hermes_sync  # noqa: E402


def main() -> int:
    out = {
        "health": run_health_check(),
        "hermes": hermes_sync(),
        "canary": Canary().maybe_run(),
    }
    print(json.dumps(out, indent=2))
    return 0 if out["health"]["all_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
