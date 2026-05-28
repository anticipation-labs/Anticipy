"""Attach the V7 scoped memory router to the running FastAPI app.

Imports are deferred inside `attach()` so importing this module at
server startup never triggers FastAPI/uvicorn singleton lock issues
when the engine is already bound to a port. This mirrors the existing
attach-point pattern in `app/product/server.py`.
"""

from __future__ import annotations


def attach() -> bool:
    """Register the scoped memory router on the existing FastAPI app.

    Returns True on success, False on any failure. FIX (W2O): the bare
    ``except Exception: return False`` previously hid PyInstaller misses
    on ``scoped_memory_endpoints``; the binary advertised no
    ``/api/memory/read`` route and there was no log line to diagnose
    the regression. The except branch now logs the traceback to stderr
    before returning False so ``_safe_attach`` in ``app.product.server``
    can surface a CRITICAL alert (it re-raises for this router).
    """
    import sys
    import traceback as _traceback
    try:
        from app.product.server import app
        from app.product.scoped_memory_endpoints import router

        # Avoid double-registration if attach() is called twice.
        existing_paths = {getattr(r, "path", None) for r in app.routes}
        new_paths = {getattr(r, "path", None) for r in router.routes}
        if new_paths and new_paths.issubset(existing_paths):
            return True

        app.include_router(router)
        return True
    except Exception as exc:
        try:
            print(f"[scoped_memory_router_wire] attach failed: "
                  f"{type(exc).__name__}: {exc}\n{_traceback.format_exc()}",
                  file=sys.stderr, flush=True)
        except Exception:
            pass
        return False
