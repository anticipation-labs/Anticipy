"""Attach the V7 dossier-active loader router to the running FastAPI app.

Imports are deferred inside ``attach()`` so importing this module at
server startup never triggers FastAPI/uvicorn singleton lock issues
when the engine is already bound to a port. Mirrors the pattern used
by ``scoped_memory_router_wire``.
"""

from __future__ import annotations


def attach() -> bool:
    """Register the dossier router on the existing FastAPI app.

    Returns True on success, False on any failure. FIX (W2O): the
    previous form silently swallowed the inner exception via a bare
    ``except Exception: return False``. When PyInstaller dropped
    ``dossier_endpoints`` (or any transitive import) the packaged
    binary would advertise no dossier routes and the caller had no way
    to find out why. The except branch now logs the traceback to
    stderr before returning False so the outer ``_safe_attach`` wrapper
    in ``app.product.server`` can surface a CRITICAL alert. Callers
    that need a hard failure can still consult ``_safe_attach``'s
    re-raise on critical routers.
    """
    import sys
    import traceback as _traceback
    try:
        from app.product.server import app
        from app.product.dossier_endpoints import router

        existing_paths = {getattr(r, "path", None) for r in app.routes}
        new_paths = {getattr(r, "path", None) for r in router.routes}
        if new_paths and new_paths.issubset(existing_paths):
            return True

        app.include_router(router)
        return True
    except Exception as exc:
        try:
            print(f"[dossier_router_wire] attach failed: {type(exc).__name__}: "
                  f"{exc}\n{_traceback.format_exc()}",
                  file=sys.stderr, flush=True)
        except Exception:
            pass
        return False
