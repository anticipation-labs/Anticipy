"""AppChannel — in-app delivery to the SwiftUI app. Stub: nothing surfaced yet."""
from __future__ import annotations

from .base import Channel


class AppChannel(Channel):
    name = "app"

    def send(self, to: str, message: str) -> dict:
        return self._stub(to, message)
