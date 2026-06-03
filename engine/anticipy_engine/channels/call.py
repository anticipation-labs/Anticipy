"""CallChannel — voice (Twilio later). Stub: no real call placed."""
from __future__ import annotations

from .base import Channel


class CallChannel(Channel):
    name = "call"

    def send(self, to: str, message: str) -> dict:
        return self._stub(to, message)
