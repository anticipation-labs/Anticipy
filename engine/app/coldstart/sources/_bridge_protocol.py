"""Bridge dispatch protocol used by every dossier source extractor.

Why this file exists:

* Phase 3 owns the production ``bridge_extension.dispatch`` rewrite.
  Until that lands, every extractor in this package needs to be able
  to talk to *something* shaped like ``dispatch(payload) -> dict``.
* Tests monkey-patch the dispatch by passing a small fake bridge
  object. Production code passes the real ``bridge_extension`` module
  (or a thin wrapper around it).
* This module owns the duck-typed adapter so we never call
  ``bridge.dispatch`` directly from an extractor without first
  validating the bridge actually has it.

Contract for the ``bridge`` argument:

* It MAY be a module exposing a ``dispatch(payload) -> Awaitable[dict]``
  coroutine.
* It MAY be an object (instance) with a ``dispatch`` method of the
  same shape (sync OR async; we await either).
* It MAY be a plain callable that takes a dict payload and returns a
  dict (sync OR async). Useful for tests.

In every case the resolved value MUST be a JSON-serializable dict
shaped roughly like::

    {
        "ok": bool,
        "data": {...},      # source-specific payload
        "error": str,       # only when ok is False
    }

Extractors NEVER read ``bridge.dispatch`` directly. They call
``await _bridge_protocol.dispatch(bridge, payload)`` instead so the
adapter logic stays in one place.
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any, Awaitable


async def dispatch(bridge: Any, payload: dict) -> dict:
    """Resolve the bridge to a callable and invoke it with ``payload``.

    Returns whatever the callable returned, with one normalization:
    a non-dict return is coerced to ``{"ok": False, "error": "<repr>"}``
    so extractors never have to type-check.
    """
    if bridge is None:
        raise RuntimeError("bridge is None; no dispatcher available")

    fn: Any = None

    # 1. Object / module with a 'dispatch' attribute
    cand = getattr(bridge, "dispatch", None)
    if callable(cand):
        fn = cand
    elif callable(bridge):
        # 2. Plain callable
        fn = bridge

    if fn is None:
        raise RuntimeError(
            "bridge has no dispatch method and is not callable; "
            f"got {type(bridge).__name__}"
        )

    # Invoke. Support sync and async return values without forcing
    # extractors to know which they have.
    result = fn(payload)
    if inspect.isawaitable(result):
        result = await result  # type: ignore[assignment]
    elif isinstance(result, Awaitable):  # type: ignore[arg-type]
        result = await result  # type: ignore[assignment]

    if not isinstance(result, dict):
        return {
            "ok": False,
            "error": f"non-dict dispatch result: {type(result).__name__}",
        }
    return result


__all__ = ["dispatch"]
