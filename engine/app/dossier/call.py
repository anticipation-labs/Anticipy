"""Stub for app.dossier.call.

Added to satisfy lazy imports in server.py:7801, 7833, 7845 that came in
with the units 09+10 excise commit bef48039. The intended Twilio dossier
call handlers are still pending; this stub returns safe empty responses
so the engine does not crash when those endpoints are hit.

Real implementation goes here when the Twilio inhale flow is wired up.
"""

from __future__ import annotations

from typing import Any


def handle_outbound(payload: dict[str, Any]) -> dict[str, Any]:
    return {"ok": False, "error": "dossier call not yet implemented"}


def handle_inbound(form: dict[str, Any]) -> str:
    return '<?xml version="1.0" encoding="UTF-8"?><Response><Say>Service not yet available.</Say></Response>'


def recent_events(limit: int = 50) -> list[dict[str, Any]]:
    return []


def recent_dossier_writes(limit: int = 10) -> list[dict[str, Any]]:
    return []


def mock_mode() -> bool:
    return True
