"""Resume-state store for the browser agent's wall handoff.

When a login / captcha / Cloudflare wall PAUSES a run, the mid-plan state (subgoals, step index,
history, visited, committed, the unblocked URL) is saved here under the run's resume_token. When the
human clears the wall in their own tab and /agent/resume fires with that token, the run CONTINUES
mid-plan instead of restarting cold. Tokens are opaque random ids — NOT secrets, they carry no
credentials. Entries expire (TTL) so abandoned walls don't accumulate.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

_TTL_SECONDS = 24 * 3600  # an abandoned wall expires after a day


class ResumeStore:
    def __init__(self, path):
        self.path = Path(path)

    def _load(self) -> dict:
        try:
            if self.path.exists():
                d = json.loads(self.path.read_text(encoding="utf-8"))
                return d if isinstance(d, dict) else {}
        except Exception:
            pass
        return {}

    def _save(self, data: dict) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(data), encoding="utf-8")
        except Exception:
            pass

    def _prune(self, data: dict, now: float) -> dict:
        return {k: v for k, v in data.items()
                if isinstance(v, dict) and (now - float(v.get("_ts", 0))) < _TTL_SECONDS}

    def put(self, token: str, state: dict, now: float | None = None) -> None:
        now = time.time() if now is None else now
        data = self._prune(self._load(), now)
        data[str(token)] = {**(state or {}), "_ts": now}
        self._save(data)

    def get(self, token: str, now: float | None = None) -> dict | None:
        now = time.time() if now is None else now
        entry = self._prune(self._load(), now).get(str(token))
        return None if entry is None else {k: v for k, v in entry.items() if k != "_ts"}

    def pop(self, token: str, now: float | None = None) -> dict | None:
        now = time.time() if now is None else now
        data = self._prune(self._load(), now)
        entry = data.pop(str(token), None)
        self._save(data)
        return None if entry is None else {k: v for k, v in entry.items() if k != "_ts"}
