"""Generic action dispatcher.

This module replaces the per-site hardcoded recipes (gmail_compose,
calendar_create, etc.) with one function that routes every browser
action through the Chrome extension's native messaging bridge.

Architecture (per planning/00-handoff/ARCHITECTURE.md section 4):

  Today: site-specific scripts inside action_engine/ each click their
  way through a fixed surface (Gmail compose, Calendar event create...).

  New: ONE function
      dispatch_action(goal, intent_payload) -> result

  The function:
    1. Picks the best transport for the current surface:
       - extension_native_bridge (production): bridge_extension.dispatch
       - explicit_cdp (legacy fallback): caller's CDP path
    2. Sends the bounded primitive
    3. Returns a standardized dict the engine routes back to /api/act

  Per the architecture: no "if site == gmail then click_id(compose)" any
  more. The planner picks the URL, the executor reads the DOM, the LLM
  decides what to click. This dispatcher is the seam.

The hardcoded recipes (gmail_compose.py etc.) remain importable so
the receipt path and back-compat call sites do not break, but they
are NOT called from the primary action dispatch path. New code MUST
import dispatch_action; do not import gmail_compose for new flows.
"""

from __future__ import annotations

from typing import Any


def dispatch_action(
    goal: str,
    intent_payload: dict | None = None,
    *,
    timeout_s: float = 30.0,
) -> dict[str, Any]:
    """Send an action to the user's Chrome via the extension surface.

    Returns the standardized dispatch result dict shape:
      {
        "ran":             bool,
        "surface":         str,     # "extension" on success
        "screenshot_path": str,     # optional proof shot path
        "url":             str,     # URL the extension landed on
        "error":           str,     # empty on success
        "proof":           dict,    # raw surface_proof receipt
        "source":          str,     # transport identifier
      }
    """
    from app.bridge_extension import dispatch as _bridge_dispatch
    return _bridge_dispatch(
        goal=goal,
        intent_payload=intent_payload,
        timeout_s=timeout_s,
    )


def extension_surface_available() -> bool:
    """Return True iff the extension native bridge accepts commands.

    Cheap loopback probe. Callers wrap the dispatch path with this so
    they fall back to the legacy CDP path when the bridge is closed.
    """
    from app.bridge_extension import surface_available
    return surface_available()


__all__ = [
    "dispatch_action",
    "extension_surface_available",
]
