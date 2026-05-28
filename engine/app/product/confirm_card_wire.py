"""Attach the V7 confirm-card router to the running FastAPI app.

Imports are deferred inside `attach()` to mirror the existing
attach-point pattern in `app/product/server.py` (the engine is bound
to a port; we never want a side-effect import on startup to crash).
"""

from __future__ import annotations


def attach() -> bool:
    """Register the confirm-card router. True on success, False if not."""
    try:
        from app.product.server import app
        from app.product.confirm_card_endpoints import router

        existing = {getattr(r, "path", None) for r in app.routes}
        new = {getattr(r, "path", None) for r in router.routes}
        if new and new.issubset(existing):
            return True
        app.include_router(router)
        return True
    except Exception:
        return False
