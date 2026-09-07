"""Run the real brain for the disposable simulator account, through the metered model gateway."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
state = ROOT / "work/audit"
account = json.loads((state / "overnight-visual-account.json").read_text())
env = {key: os.environ[key] for key in ("PATH", "HOME", "LANG", "TMPDIR") if key in os.environ}
env.update({
    "PYTHONPATH": str(ROOT), "PYTHONUNBUFFERED": "1",
    "ANTICIPY_AUDIT_RUN": "overnight-ui",
    "OPENROUTER_API_KEY": (state / "gateway-token").read_text().strip(),
    "ANTICIPY_PB": "http://127.0.0.1:8787",
    "ANTICIPY_OWNER_REF": account["id"], "ANTICIPY_OWNER_ID": account["id"],
    "ANTICIPY_SERVICE_TOKEN": "overnight-local-service-only",
    "ANTICIPY_SUPERVISED": "1", "ANTICIPY_SMS_PROVIDER": "mock",
    "ANTICIPY_MEMORY_DB": str(state / "overnight-ui-memory.db"),
    "ANTICIPY_CLOCK_STATE": str(state / "overnight-ui-clock.json"),
    "ANTICIPY_TZ": "America/Vancouver",
    "ANTICIPY_MODEL": "deepseek/deepseek-v3.2",
    "ANTICIPY_STRONG_MODEL": "google/gemini-3.1-pro-preview",
})
subprocess.run([sys.executable, str(ROOT / "proof/audit/run_transcripts.py"), "--child"], cwd=ROOT, env=env, check=True)
