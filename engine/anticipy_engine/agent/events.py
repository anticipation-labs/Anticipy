"""Tiny in-process pub/sub for LIVE agent step-events.

The browser agent publishes a structured event for every step it takes (task start, each
click/type/select with the real CDP coordinates and the resulting URL, and the final answer +
cost). A Server-Sent-Events endpoint subscribes and streams them to the live "mission control"
console — so the per-step action log appears on screen, in real time, alongside the agent
advancing a background tab. This is observability only; it never affects the agent's outcome.
"""
from __future__ import annotations

import asyncio
import time
from typing import Dict, List

_subscribers: List[asyncio.Queue] = []


def publish(ev: Dict) -> None:
    ev = dict(ev)
    ev.setdefault("t", round(time.time(), 3))
    for q in list(_subscribers):
        try:
            q.put_nowait(ev)
        except Exception:
            pass  # a slow/full subscriber must never stall or crash the agent


def subscribe() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=2000)
    _subscribers.append(q)
    return q


def unsubscribe(q: asyncio.Queue) -> None:
    try:
        _subscribers.remove(q)
    except ValueError:
        pass
