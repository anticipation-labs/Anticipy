"""BrowserAdapter — the browser fallback.

Wraps the browser engine (for things no connector covers) in the action chunk.
Stub for the scaffold.
"""
from __future__ import annotations

from .base import ActionAdapter
from ..shared.schema import ActionRequest


class BrowserAdapter(ActionAdapter):
    path = "browser"

    def execute(self, request: ActionRequest) -> dict:
        return {
            "ok": False,
            "stub": True,
            "path": self.path,
            "intent": request.intent,
            "note": "browser engine wrapped in the action chunk",
        }
