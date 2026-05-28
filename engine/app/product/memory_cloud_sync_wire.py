"""Attach the V7 memory cloud-sync router to the running FastAPI app
and auto-start the outbox worker.

Imports are deferred inside ``attach()`` so importing this module at
server startup never triggers FastAPI/uvicorn singleton lock issues
when the engine is already bound to a port. Mirrors the pattern in
``scoped_memory_router_wire.py``.

Auto-start rule (per spec): if ``SUPABASE_URL`` is set in the env,
the worker is started inside ``attach()``. Otherwise the worker
silently no-ops so local-only setups keep working.
"""

from __future__ import annotations

import os


def attach() -> bool:
    """Register the sync router and (if configured) start the worker.

    Returns True on success, False on any failure (silently safe so a
    server import never crashes the engine).
    """
    try:
        from app.product.server import app
        from app.product.memory_cloud_sync import get_sync
        from app.product.memory_cloud_sync_endpoints import router

        existing_paths = {getattr(r, "path", None) for r in app.routes}
        new_paths = {getattr(r, "path", None) for r in router.routes}
        if not new_paths or not new_paths.issubset(existing_paths):
            app.include_router(router)

        # Auto-start the worker when Supabase credentials are present.
        sync = get_sync()
        if os.environ.get("SUPABASE_URL", "").strip():
            sync.start_worker()
        return True
    except Exception:
        return False
