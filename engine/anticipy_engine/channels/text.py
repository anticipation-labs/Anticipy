"""TextChannel — SMS (Twilio later). Stub: no real text sent."""
from __future__ import annotations

from .base import Channel


class TextChannel(Channel):
    name = "text"

    def send(self, to: str, message: str) -> dict:
        return self._stub(to, message)
