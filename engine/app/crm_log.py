"""Fire-and-forget logger that POSTs engine events to the CRM at /api/log.

Set ANTICIPY_API_URL (default https://www.anticipy.ai) and AGENT_LOG_SECRET to
enable. With no secret the call is skipped silently. All sends are scheduled
as background tasks so they never block the agent.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

API_URL = os.environ.get("ANTICIPY_API_URL", "https://www.anticipy.ai").rstrip("/")
LOG_SECRET = os.environ.get("AGENT_LOG_SECRET", "")


async def _post(payload: dict) -> None:
    if not LOG_SECRET:
        return
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{API_URL}/api/log",
                headers={
                    "Content-Type": "application/json",
                    "x-anticipy-log-secret": LOG_SECRET,
                },
                json=payload,
            )
    except Exception:
        # Non-fatal. The CRM feed is observability only.
        logger.debug("crm_log POST failed", exc_info=True)


def log_event(
    agent_name: str,
    action: str,
    summary: str,
    payload: Optional[dict[str, Any]] = None,
    related_entity_type: Optional[str] = None,
    related_entity_id: Optional[str] = None,
) -> None:
    """Schedule a non-blocking POST. Safe to call from any async context."""
    body: dict[str, Any] = {
        "agent_name": agent_name,
        "action": action,
        "summary": summary[:500],
    }
    if payload is not None:
        body["payload"] = payload
    if related_entity_type:
        body["related_entity_type"] = related_entity_type
    if related_entity_id:
        body["related_entity_id"] = related_entity_id
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_post(body))
    except RuntimeError:
        # No running loop (called from sync code at startup); fire a one-shot.
        asyncio.run(_post(body))
