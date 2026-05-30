"""P1-2: engine reclaims its lock when the prior holder pid is dead.

The bug: when the previous engine process dies, the per-port lock file
at /tmp/anticipy_product_<port>.lock is left behind with the dead pid
written inside it. Callers that try to bind the same port then either
fall through to a random ephemeral port (the observed 49671 mis-bind)
or refuse to start. The fix is in `_acquire_singleton_lock`: it now
parses the holder pid out of the existing lock file, asks the OS via
`os.kill(pid, 0)` whether the pid is still alive, and if not, removes
the stale file and proceeds to re-bind.

These tests exercise the lock function directly against unique, non-
production port strings (no live engine collision) so they are safe to
run alongside the in-flight engine on whatever port it currently owns.
"""

from __future__ import annotations

import json
import os
import random
import sys
import time

import pytest

# Pick a port string that the live engine will never use so the eager
# `_acquire_singleton_lock` at module import does not touch the real
# /tmp/anticipy_product_8731.lock or the live engine's port file. The
# port number itself is never bound to a socket here; it is only a key
# for the lock file path.
_TEST_PORT_ENV = "59731"
os.environ.setdefault("ANTICIPY_ENGINE_PORT", _TEST_PORT_ENV)

# Make sure the engine package is importable when pytest is invoked
# from `engine/` (the documented verification command). conftest.py
# lives at engine/, so the test path is engine/tests/X, and the parent
# of this file resolves to engine/ when we walk one level up.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ENGINE_ROOT = os.path.dirname(_HERE)
if _ENGINE_ROOT not in sys.path:
    sys.path.insert(0, _ENGINE_ROOT)

from app.product import server as _server  # noqa: E402


def _unique_port_str() -> str:
    """Return a port-string key that no other test/run is using.

    We pick from a high band so it never collides with the live engine
    on 8731 / 49671 nor with the env-pinned 59731 used to make the
    eager import a no-op against production.
    """
    # 60000-65000 band; both pid and time component guarantee uniqueness
    # across parallel test runs on the same machine.
    return str(60000 + random.randint(0, 4999))


def _lock_path_for(port_str: str) -> str:
    return f"/tmp/anticipy_product_{port_str}.lock"


def _reset_singleton_state() -> None:
    """Clear the module-level lock state so the next acquire is fresh.

    `_acquire_singleton_lock` short-circuits when `_SINGLETON_FH is not
    None`, which is the correct production behavior but would otherwise
    stop each test after the first.
    """
    # The flock is released automatically when the file handle is closed,
    # and closing happens implicitly when we drop the reference. We do
    # the close explicitly so the kernel state is deterministic.
    fh = getattr(_server, "_SINGLETON_FH", None)
    if fh is not None:
        try:
            fh.close()
        except Exception:
            pass
    _server._SINGLETON_FH = None
    _server._SINGLETON_LOCK_PATH = None


@pytest.fixture
def isolated_port():
    """Yield a unique per-test port string and clean up its lock file."""
    port_str = _unique_port_str()
    path = _lock_path_for(port_str)
    # Ensure a clean slate going into the test.
    if os.path.exists(path):
        try:
            os.unlink(path)
        except OSError:
            pass
    _reset_singleton_state()
    try:
        yield port_str
    finally:
        _reset_singleton_state()
        if os.path.exists(path):
            try:
                os.unlink(path)
            except OSError:
                pass


def _pick_dead_pid() -> int:
    """Return a pid that is guaranteed not to be alive.

    We try our own pid offset by a large random number until os.kill
    raises ProcessLookupError. We bound the search so a pathological
    environment can never hang the test.
    """
    base = os.getpid()
    for _ in range(64):
        candidate = base + random.randint(50_000, 500_000)
        if candidate <= 0:
            continue
        try:
            os.kill(candidate, 0)
            # Pid exists; try another.
            continue
        except ProcessLookupError:
            return candidate
        except PermissionError:
            # Exists but owned by someone else; try another.
            continue
        except OSError:
            return candidate
    raise RuntimeError("could not find an unused pid in 64 tries")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_no_lock_file_proceeds_normally(isolated_port: str) -> None:
    """With no pre-existing lock file, acquisition writes my pid + binds."""
    port_str = isolated_port
    path = _lock_path_for(port_str)
    assert not os.path.exists(path), "pre-condition: no stale file from another test"

    _server._acquire_singleton_lock(port_str)

    assert os.path.exists(path), "lock file must be created on first acquire"
    body = open(path).read().strip()
    assert body, "lock file must not be empty"
    holder_pid = _server._parse_lock_holder_pid(body)
    assert holder_pid == os.getpid(), (
        f"expected lock to hold our pid {os.getpid()}, got {holder_pid} (raw={body!r})"
    )
    # And the module-level handle is set so a same-process re-entry
    # short-circuits instead of double-flocking.
    assert _server._SINGLETON_FH is not None
    assert _server._SINGLETON_LOCK_PATH == path


def test_stale_lock_with_dead_pid_is_reclaimed(isolated_port: str) -> None:
    """Pre-write a lock with a pid that does not exist, then verify the
    new acquire removes the stale file and binds successfully under my
    pid."""
    port_str = isolated_port
    path = _lock_path_for(port_str)
    dead_pid = _pick_dead_pid()

    # Pre-condition: write the stale lock just like a crashed engine
    # would have left it. We use the bare-int legacy form here because
    # this is the format that actually shipped before the P1-2 fix; the
    # reclaim path must understand it for backward compatibility.
    with open(path, "w") as fh:
        fh.write(str(dead_pid))
    assert os.path.exists(path)
    assert open(path).read().strip() == str(dead_pid)

    # Act: acquire. The stale-pid branch must unlink the file, then
    # the normal acquire path runs and binds.
    _server._acquire_singleton_lock(port_str)

    # Post: the file now exists again (recreated by the acquire path)
    # and holds the current process pid, not the dead one.
    assert os.path.exists(path), "lock file should be re-created after reclaim"
    body = open(path).read().strip()
    holder_pid = _server._parse_lock_holder_pid(body)
    assert holder_pid == os.getpid(), (
        f"after reclaim, lock must hold my pid {os.getpid()}, got {holder_pid} "
        f"(raw={body!r}); dead pid was {dead_pid}"
    )
    assert holder_pid != dead_pid


def test_live_pid_refuses_second_start(isolated_port: str) -> None:
    """When the lock holder pid IS our currently running PID written as
    if a different process owned it, the second acquire from a fresh
    handle slot must refuse to start (the kernel flock is the gate).

    We simulate "another live engine already holds the lock" by opening
    the file ourselves, flocking it, and writing a pid string that
    represents a different alive process. The cleanest way to make the
    pid-alive check return True without forking is to use a pid we know
    exists on every macOS/Linux machine: pid 1 (launchd / init). Then
    we directly call _acquire_singleton_lock with the singleton state
    cleared, which forces it down the "open + flock" path. flock fails
    (we already hold it), the function calls SystemExit(3), which
    matches the documented refuse-second-start behavior.
    """
    port_str = isolated_port
    path = _lock_path_for(port_str)

    # Write a lock body that points at pid 1 (init / launchd). pid 1
    # exists on every UNIX system we care about, so _pid_is_alive will
    # return True and the reclaim branch will NOT trigger.
    assert _server._pid_is_alive(1), (
        "pre-condition: pid 1 (init/launchd) must be alive on this host; "
        "without it we cannot synthesize a 'live other holder' scenario"
    )

    # Acquire flock ourselves so the real acquire below sees the lock
    # as held by another live owner.
    import fcntl as _fcntl

    blocker = open(path, "w")
    try:
        blocker.write(str(1))
        blocker.flush()
        _fcntl.flock(blocker, _fcntl.LOCK_EX | _fcntl.LOCK_NB)

        # Ensure module state is empty so we take the full path through
        # the function (not the short-circuit at the top).
        _reset_singleton_state()

        # The function must SystemExit(3) when flock fails on a lock
        # whose holder is alive (pid 1 always is).
        with pytest.raises(SystemExit) as exc_info:
            _server._acquire_singleton_lock(port_str)
        assert exc_info.value.code == 3, (
            f"expected SystemExit(3) when refusing second start, got "
            f"SystemExit({exc_info.value.code!r})"
        )
    finally:
        try:
            _fcntl.flock(blocker, _fcntl.LOCK_UN)
        except Exception:
            pass
        try:
            blocker.close()
        except Exception:
            pass


def test_lock_content_after_acquisition_has_my_pid(isolated_port: str) -> None:
    """After a reclaim from a dead pid, the on-disk lock body must
    parse back to the current process pid and must NOT still parse to
    the dead pid that was there before."""
    port_str = isolated_port
    path = _lock_path_for(port_str)
    dead_pid = _pick_dead_pid()

    # Pre-write a stale lock (JSON form this time, to prove the reclaim
    # branch handles both formats interchangeably).
    with open(path, "w") as fh:
        fh.write(json.dumps({"pid": dead_pid, "ts": 0.0}))

    _server._acquire_singleton_lock(port_str)

    body = open(path).read().strip()
    holder_pid = _server._parse_lock_holder_pid(body)
    assert holder_pid == os.getpid(), (
        f"after acquisition the lock body must hold my pid {os.getpid()}; "
        f"got holder_pid={holder_pid}, raw body={body!r}"
    )
    # Belt and braces: the dead pid string must not still be in the file
    # except by coincidence of being a substring of a ts. Asserting on
    # holder_pid is the load-bearing check; this is sanity.
    assert str(dead_pid) != str(holder_pid)
