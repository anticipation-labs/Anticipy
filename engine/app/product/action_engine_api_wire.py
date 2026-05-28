"""Attach the V7 universal action dispatcher HTTP router.

Imports are deferred inside `attach()` so importing this module at
server startup never triggers FastAPI/uvicorn singleton lock issues
when the engine is already bound to a port. Mirrors the existing
`scoped_memory_router_wire.attach()` pattern.
"""

from __future__ import annotations


def attach() -> bool:
    """Register the action-engine router on the existing FastAPI app.

    Returns True on success, False on any failure (silently safe so a
    server import never crashes the engine).
    """
    try:
        from app.product.server import app
        from app.product.action_engine_api import router

        existing_paths = {getattr(r, "path", None) for r in app.routes}
        new_paths = {getattr(r, "path", None) for r in router.routes}
        if new_paths and new_paths.issubset(existing_paths):
            return True

        app.include_router(router)
        return True
    except Exception:
        return False
