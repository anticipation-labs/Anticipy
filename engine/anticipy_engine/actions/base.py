"""Action adapter interface. Both the connector and browser paths implement it."""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..shared.schema import ActionPath, ActionRequest


class ActionAdapter(ABC):
    path: ActionPath

    @abstractmethod
    def execute(self, request: ActionRequest) -> dict:
        """Carry out an action request. Scaffold adapters return a stub result."""
