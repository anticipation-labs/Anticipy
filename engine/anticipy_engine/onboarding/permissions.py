"""Per-service onboarding PERMISSIONS — the allow / allow / allow gate.

Before the loop reads any account it checks here. A service is read ONLY if the owner has explicitly
allowed it (default = NOT allowed). Persisted so consent survives restarts. The scrape is read-only
either way — this gate is about CONSENT, not capability: nothing is touched until you say "allow".
"""
from __future__ import annotations

import json
from pathlib import Path

# the services the onboarding scrape can touch, each gated independently (the allow-allow-allow list)
SERVICES = [
    {"service": "gmail", "label": "Gmail", "why": "to learn who you talk to and what's on your plate"},
    {"service": "calendar", "label": "Google Calendar", "why": "to learn your week and commitments"},
    {"service": "contacts", "label": "Google Contacts", "why": "to learn the people who matter"},
    {"service": "linkedin", "label": "LinkedIn", "why": "to learn your work and network"},
]
# which scrape-surface keys belong to which service (so one "allow Gmail" covers inbox + sent)
SURFACE_SERVICE = {
    "gmail_inbox": "gmail", "gmail_sent": "gmail",
    "calendar": "calendar", "contacts": "contacts", "linkedin": "linkedin",
}


class Permissions:
    def __init__(self, path):
        self.path = Path(path)
        self._allowed: dict = {}
        try:
            if self.path.exists():
                self._allowed = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            self._allowed = {}

    def _save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self._allowed, indent=2, sort_keys=True), encoding="utf-8")
        except Exception:
            pass

    def is_allowed(self, service: str) -> bool:
        return bool(self._allowed.get(service))

    def set(self, service: str, allowed: bool) -> dict:
        valid = {s["service"] for s in SERVICES}
        if service in valid:
            self._allowed[service] = bool(allowed)
            self._save()
        return self.state()

    def allowed_services(self) -> list:
        return [s for s, v in self._allowed.items() if v]

    def state(self) -> dict:
        return {"services": [{**s, "allowed": self.is_allowed(s["service"])} for s in SERVICES],
                "any_allowed": any(self.is_allowed(s["service"]) for s in SERVICES)}
