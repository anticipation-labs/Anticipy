"""Channel interface. call / text / app all implement it."""
from __future__ import annotations

from abc import ABC, abstractmethod


class Channel(ABC):
    name: str

    @abstractmethod
    def send(self, to: str, message: str) -> dict:
        """Reach the user. Scaffold channels do not actually send."""

    def _stub(self, to: str, message: str) -> dict:
        return {"sent": False, "stub": True, "channel": self.name, "to": to, "message": message}
