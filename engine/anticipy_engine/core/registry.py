"""Per-user ControlCore registry — the load-bearing data-isolation seam.

Today there is ONE global brain. This registry gives every signed-in user their OWN
``ControlCore`` with its OWN ``data_dir`` (``<base>/users/<safe(user_id)>``), so each
user's cards / memory / goals / permissions / token-vault live in a separate directory
and one user can never see another user's data.

Design contract (kept deliberately small so it cannot half-miss):

  * ``DEFAULT_USER`` — a STABLE id used for every unauthenticated / local-dev / suite /
    background caller. Its core's ``data_dir`` is the EXISTING base (``ANTICIPY_DATA_DIR``
    or ``.anticipy-data``), NOT ``<base>/users/...`` — so the suite, local dev, and the
    startup/proactive path behave EXACTLY as before (one default core at the old path).
    Per-user dirs sit BESIDE it under ``<base>/users/``.

  * ``core_for(user_id)`` — get-or-create the core for a user id, cached in a dict under a
    lock so two concurrent requests for a brand-new user build exactly one core.

  * a ``contextvars.ContextVar`` carries the current request's user id; the HTTP auth
    middleware sets it to ``request.state.user_id or DEFAULT_USER``. ``current_core()``
    reads that var and returns the right core. Outside any request (startup, the proactive
    clock, the inbound poller) the var is unset and ``current_core()`` falls back to the
    DEFAULT core — never a wrong user, never a crash.

The DEFAULT core is registered by ``main`` (the module-global ``core``) via
``register_default`` so that ``current_core()`` for an unauthenticated request returns the
SAME object the module exposes (the suite imports ``main.core`` and also drives it over
HTTP — both paths must hit one object).
"""
from __future__ import annotations

import asyncio
import contextvars
import hashlib
import os
import re
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional

if TYPE_CHECKING:  # avoid an import cycle at module-load time
    from .control_core import ControlCore


def default_user() -> str:
    """The stable id for unauthenticated / local / suite / background callers.

    Prefers ADMIN_EMAIL (the owner) so a single-user local install keeps an intuitive
    identity; falls back to the literal ``"owner"``. This is only an identity LABEL — the
    DEFAULT core's data_dir is the existing base, not a per-user subdir (see module doc)."""
    return (os.environ.get("ADMIN_EMAIL") or "owner").strip() or "owner"


# The current request's user id. Unset (-> default_user()) outside any HTTP request, so
# startup / the proactive clock / the inbound poller always resolve to the DEFAULT core.
_current_user: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "anticipy_current_user", default=None
)

_lock = threading.RLock()
_cores: dict[str, "ControlCore"] = {}
_default_core: Optional["ControlCore"] = None
# How to build a NON-default user's core, given its data_dir AND its user id (so the core can
# key per-user action identity off WHO it belongs to). Injected by main with the real
# ControlCore factory so this module has no import-time dependency on the (heavy) control_core
# module.
_factory: Optional[Callable[[Path, str], "ControlCore"]] = None


def _safe(user_id: str) -> str:
    """A filesystem-safe, collision-resistant slug for a user id (a Supabase UUID, an
    email, or the owner label). Keep the readable part for humans, but ALWAYS append a hash
    of the raw id so two ids that sanitise to the same string still get distinct dirs and
    nobody can traverse out of <base>/users/ with a crafted id."""
    raw = (user_id or "").strip() or "unknown"
    slug = re.sub(r"[^A-Za-z0-9._-]", "_", raw)[:48].strip("._-") or "user"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return f"{slug}-{digest}"


def _base_dir() -> Path:
    """The existing data base the DEFAULT core uses (mirrors control_core._base).
    abspath -> absolute at build so it stays cwd-stable, without resolving symlinks (see control_core._base)."""
    return Path(os.path.abspath(Path(os.environ.get("ANTICIPY_DATA_DIR", ".anticipy-data")).expanduser()))


def user_data_dir(user_id: str) -> Path:
    """Where a NON-default user's core stores its data: <base>/users/<safe(user_id)>."""
    return _base_dir() / "users" / _safe(user_id)


def set_factory(factory: Callable[[Path, str], "ControlCore"]) -> None:
    """Inject the ControlCore factory (called once by main at import time).

    The factory is called ``factory(data_dir, user_id)`` so the per-user core knows WHO it is
    (its action identity), not just where its data lives."""
    global _factory
    _factory = factory


def register_default(core: "ControlCore", user_id: Optional[str] = None) -> None:
    """Register the already-constructed module-global core as the DEFAULT core.

    The default keeps the EXISTING base data_dir; we just map default_user() -> this exact
    object so an unauthenticated request resolves to the SAME core the module exposes."""
    global _default_core
    uid = (user_id or default_user())
    with _lock:
        _default_core = core
        _cores[uid] = core


def default_core() -> "ControlCore":
    if _default_core is None:  # pragma: no cover - main always registers before serving
        raise RuntimeError("registry default core not registered yet")
    return _default_core


def _ensure_bus_started(core: "ControlCore") -> None:
    """Make sure this core's bus runner is draining the queue, IF we are on a running loop.

    Idempotent (bus.start_sync() no-ops once the runner exists). Called on every core_for()
    so a core that was first built OUTSIDE a loop (e.g. an eager test/registry access with no
    event loop) still gets its runner started the first time it is used inside a request — so
    the first submit_job (which awaits a job future) can never hang on an unstarted runner.
    With no running loop we skip; the lifespan / next in-loop use starts it."""
    try:
        asyncio.get_running_loop()  # raises if there is no running loop
    except RuntimeError:
        return
    core.bus.start_sync()


def core_for(user_id: Optional[str]) -> "ControlCore":
    """Get-or-create the ControlCore for ``user_id`` (thread-safe).

    The default user (and an empty/None id) always returns the DEFAULT core at the existing
    base path (started in the lifespan). Any other id gets its own core rooted at
    ``<base>/users/<safe(id)>``; its bus runner is (re)ensured-started on every call so the
    very first ingest cannot hang on an unstarted runner, even if the core object was first
    constructed outside an event loop."""
    uid = (user_id or "").strip() or default_user()
    if uid == default_user():
        return default_core()
    with _lock:
        core = _cores.get(uid)
        if core is None:
            if _factory is None:  # pragma: no cover - main injects the factory at import
                raise RuntimeError("registry factory not set")
            core = _factory(user_data_dir(uid), uid)
            _cores[uid] = core
    _ensure_bus_started(core)
    return core


def current_user() -> str:
    """The user id for the in-flight request, or the default outside any request."""
    return _current_user.get() or default_user()


def current_core() -> "ControlCore":
    """The ControlCore for the in-flight request's user (DEFAULT outside a request)."""
    return core_for(current_user())


def set_current_user(user_id: Optional[str]):
    """Bind the current request's user id; returns the contextvars Token to reset with."""
    return _current_user.set((user_id or "").strip() or default_user())


def reset_current_user(token) -> None:
    """Restore the previous user binding (call in a finally after the request)."""
    _current_user.reset(token)


def all_cores() -> list["ControlCore"]:
    """Every constructed core (default + per-user). Used to start/stop them as a set."""
    with _lock:
        # de-dup by identity (the default user maps to _default_core)
        seen: dict[int, "ControlCore"] = {}
        for c in _cores.values():
            seen.setdefault(id(c), c)
        return list(seen.values())
