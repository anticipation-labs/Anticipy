"""ActionLayer — the gate + the two adapter seams, wired together.

An ActionRequest goes through the gate first. Only if the gate says ``act`` is
the request routed (by ``path``) to the connector or browser adapter. Otherwise
the decision is returned for the app to surface (confirm / escalate).
"""
from __future__ import annotations

from .browser import BrowserAdapter
from .connector import ConnectorAdapter
from .gate import ActGate
from ..shared.schema import ActionRequest


class ActionLayer:
    def __init__(self) -> None:
        self.gate = ActGate()
        self.connector = ConnectorAdapter()
        self.browser = BrowserAdapter()

    def _adapter(self, request: ActionRequest):
        return self.connector if request.path == "connector" else self.browser

    def handle(self, request: ActionRequest) -> dict:
        decision = self.gate.decide(request)
        result = self._adapter(request).execute(request) if decision == "act" else None
        return {"decision": decision, "result": result, "request_id": request.id}
