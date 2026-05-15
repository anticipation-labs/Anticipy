"""Phase 9 watchdog — health-checks every 5 min, canaries every 4 h.

Runs as a launchd LaunchAgent at
~/Library/LaunchAgents/ai.anticipy.watchdog.plist (StartInterval=300).

Each invocation:
  1. health_check.run() — verifies all dependencies are reachable
     (Chrome :9222, mlx-lm :1234 if running, Supabase, voter
     providers). Restarts crashed services where it can. Heartbeat
     to anticipy_results_v2 (or a dedicated heartbeat table).
  2. canary.maybe_run() — if it's been ≥4h since the last canary,
     run the top 3 skills against live infra (Calendar create+
     delete, Slack post+delete, Notion page+archive). Bumps the
     skill_library success_count / failure_count for Hermes
     promotion/demotion (Phase 9 lifecycle).
  3. If 3 consecutive heartbeats failed → Aevoy alert email.
"""

from .health_check import HealthCheck, run_health_check
from .canary import Canary

__all__ = ["HealthCheck", "run_health_check", "Canary"]
