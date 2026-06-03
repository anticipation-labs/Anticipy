"""ConnectorAdapter — reach common apps via a third-party connector service.

Security-first, per-user-scoped. We do not hand-build integrations. The vendor
(a Composio / Arcade / MCP-gateway-type service) is chosen and wired in the
action chunk. Stub for the scaffold.
"""
from __future__ import annotations

from .base import ActionAdapter
from ..shared.schema import ActionRequest


class ConnectorAdapter(ActionAdapter):
    path = "connector"
    vendor = None  # TBD in the action chunk (security-first, per-user-scoped)

    def execute(self, request: ActionRequest) -> dict:
        return {
            "ok": False,
            "stub": True,
            "path": self.path,
            "intent": request.intent,
            "note": "connector vendor wired in the action chunk",
        }
