"""
Unit tests for the in-memory rate-limit + cleanup helpers in `app.main`:

  - `_check_task_rate_limit(user_id)` — per-user MAX_TASKS_PER_HOUR /
    MAX_TASKS_PER_DAY caps. Returns None on admit, error string on cap.
  - `_record_task(user_id)` — appends a timestamp to the user's bucket.
  - `_cleanup_rate_state()` — periodic sweep that drops dead user_ids.
  - `_check_ws_msg_rate(ip)` — bucketed per-IP message-rate limiter,
    returns True (= throttled) when the IP exceeds
    `WS_MAX_MESSAGES_PER_MINUTE` in a rolling minute.
  - `_ws_client_ip(websocket)` — TRUST_FORWARDED_FOR-aware (sibling of the
    HTTP `_get_client_ip`).

`test_main_security.py` covers the connection-cap counters; this file
covers the orthogonal *message-rate* + *task-creation-rate* surfaces.
"""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ.setdefault("JWT_SECRET", "x" * 48)
os.environ.setdefault(
    "PROFILE_ENCRYPTION_KEY",
    "RoUzc1lJ3gkPkHrxoYQzv1trmEJSQbgo6mNhlQYgfJk=",
)

from app import main as main_module  # noqa: E402
from app.config import (  # noqa: E402
    MAX_TASKS_PER_HOUR,
    MAX_TASKS_PER_DAY,
    WS_MAX_MESSAGES_PER_MINUTE,
)


def _reset_state() -> None:
    main_module._task_timestamps.clear()
    main_module._ws_msg_timestamps.clear()
    main_module._last_rate_cleanup = 0.0
    main_module._last_ws_cleanup = 0.0


# --- _check_task_rate_limit + _record_task ----------------------------------


def test_task_rate_first_call_admits():
    _reset_state()
    assert main_module._check_task_rate_limit("u1") is None


def test_task_rate_admits_under_hour_cap():
    _reset_state()
    for _ in range(MAX_TASKS_PER_HOUR - 1):
        main_module._record_task("u1")
    # Caller's hour-count is N, threshold is `>= MAX_TASKS_PER_HOUR`.
    assert main_module._check_task_rate_limit("u1") is None


def test_task_rate_blocks_at_hour_cap():
    _reset_state()
    for _ in range(MAX_TASKS_PER_HOUR):
        main_module._record_task("u1")
    err = main_module._check_task_rate_limit("u1")
    assert err is not None
    # Don't assert on exact wording — we use `messages.RATE_LIMIT_TASKS`
    assert isinstance(err, str)
    assert err  # non-empty


def test_task_rate_blocks_at_day_cap_when_under_hour_cap():
    """If day count ≥ MAX_TASKS_PER_DAY but the hour count is below the
    hourly cap (i.e. tasks are old enough to be off the hourly window
    but still in the 24h window), we still refuse with the daily message."""
    _reset_state()
    now = time.time()
    # Create MAX_TASKS_PER_DAY timestamps spread across the past 22h
    span = 22 * 3600
    base = now - span
    for i in range(MAX_TASKS_PER_DAY):
        # Spread evenly so most are older than 1h
        main_module._task_timestamps["u1"].append(base + (i * span / MAX_TASKS_PER_DAY))
    err = main_module._check_task_rate_limit("u1")
    assert err is not None


def test_task_rate_isolates_users():
    """Hitting u1's cap must NOT affect u2."""
    _reset_state()
    for _ in range(MAX_TASKS_PER_HOUR):
        main_module._record_task("u1")
    assert main_module._check_task_rate_limit("u1") is not None
    assert main_module._check_task_rate_limit("u2") is None


def test_record_task_appends_timestamp():
    _reset_state()
    main_module._record_task("u1")
    assert len(main_module._task_timestamps["u1"]) == 1
    main_module._record_task("u1")
    assert len(main_module._task_timestamps["u1"]) == 2


def test_task_rate_drops_old_timestamps():
    """After 24h+, a timestamp falls out of the day window and the user's
    quota recovers — verified by inserting a stale timestamp."""
    _reset_state()
    main_module._task_timestamps["u1"].append(time.time() - 90000)  # 25h ago
    assert main_module._check_task_rate_limit("u1") is None
    # The check should also have pruned it
    assert all(ts > time.time() - 86400 for ts in main_module._task_timestamps["u1"])


# --- _cleanup_rate_state ----------------------------------------------------


def test_cleanup_rate_state_drops_dead_users():
    _reset_state()
    # User with no timestamps left → dead
    main_module._task_timestamps["dead-user"].append(time.time() - 90000)
    # Force the 5-minute throttle to expire so cleanup actually runs
    main_module._last_rate_cleanup = 0.0
    main_module._cleanup_rate_state()
    assert "dead-user" not in main_module._task_timestamps


def test_cleanup_rate_state_keeps_active_users():
    _reset_state()
    main_module._task_timestamps["alive-user"].append(time.time())
    main_module._last_rate_cleanup = 0.0
    main_module._cleanup_rate_state()
    assert "alive-user" in main_module._task_timestamps


def test_cleanup_rate_state_throttle_skips_recent_runs():
    """The cleanup itself is throttled to once per 5 min so a hot loop
    doesn't repeatedly scan thousands of users."""
    _reset_state()
    main_module._last_rate_cleanup = time.time()  # just ran
    # If throttle works, this should be a no-op even with stale state
    main_module._task_timestamps["dead"].append(time.time() - 90000)
    main_module._cleanup_rate_state()
    assert "dead" in main_module._task_timestamps


# --- _check_ws_msg_rate -----------------------------------------------------


def test_ws_msg_rate_first_message_admitted():
    _reset_state()
    assert main_module._check_ws_msg_rate("1.2.3.4") is False


def test_ws_msg_rate_under_cap_admits():
    _reset_state()
    for _ in range(WS_MAX_MESSAGES_PER_MINUTE - 1):
        assert main_module._check_ws_msg_rate("1.2.3.4") is False


def test_ws_msg_rate_blocks_at_cap():
    _reset_state()
    # Fire WS_MAX_MESSAGES_PER_MINUTE messages (each call counts itself)
    for _ in range(WS_MAX_MESSAGES_PER_MINUTE):
        main_module._check_ws_msg_rate("1.2.3.4")
    # Next call exceeds — must throttle
    assert main_module._check_ws_msg_rate("1.2.3.4") is True


def test_ws_msg_rate_isolates_ips():
    _reset_state()
    for _ in range(WS_MAX_MESSAGES_PER_MINUTE):
        main_module._check_ws_msg_rate("1.2.3.4")
    # 1.2.3.4 is now over cap; 5.6.7.8 should still be admitted
    assert main_module._check_ws_msg_rate("5.6.7.8") is False


def test_ws_msg_rate_drops_old_timestamps():
    """A burst from > 60s ago shouldn't count against the current minute."""
    _reset_state()
    old_ts = time.time() - 120  # 2 min ago
    main_module._ws_msg_timestamps["1.2.3.4"] = [old_ts] * (
        WS_MAX_MESSAGES_PER_MINUTE + 5
    )
    # Fresh check should drop old timestamps and admit
    assert main_module._check_ws_msg_rate("1.2.3.4") is False


# --- _ws_client_ip TRUST_FORWARDED_FOR --------------------------------------


class _FakeWS:
    def __init__(self, host: str = "10.0.0.1", forwarded: str | None = None,
                 real_ip: str | None = None) -> None:
        self.client = type("c", (), {"host": host})()
        self.headers: dict[str, str] = {}
        if forwarded:
            self.headers["x-forwarded-for"] = forwarded
        if real_ip:
            self.headers["x-real-ip"] = real_ip


def test_ws_client_ip_default_uses_direct_connection():
    """Without TRUST_FORWARDED_FOR=1, x-forwarded-for is IGNORED."""
    os.environ.pop("TRUST_FORWARDED_FOR", None)
    ws = _FakeWS(host="10.0.0.1", forwarded="6.6.6.6")
    assert main_module._ws_client_ip(ws) == "10.0.0.1"


def test_ws_client_ip_trusts_forwarded_when_enabled():
    os.environ["TRUST_FORWARDED_FOR"] = "1"
    try:
        ws = _FakeWS(host="10.0.0.1", forwarded="6.6.6.6, 7.7.7.7")
        assert main_module._ws_client_ip(ws) == "6.6.6.6"
    finally:
        os.environ.pop("TRUST_FORWARDED_FOR", None)


def test_ws_client_ip_falls_back_to_real_ip_when_forwarded_blank():
    os.environ["TRUST_FORWARDED_FOR"] = "1"
    try:
        ws = _FakeWS(host="10.0.0.1", real_ip="9.9.9.9")
        assert main_module._ws_client_ip(ws) == "9.9.9.9"
    finally:
        os.environ.pop("TRUST_FORWARDED_FOR", None)


def test_ws_client_ip_handles_missing_client():
    os.environ.pop("TRUST_FORWARDED_FOR", None)
    ws = _FakeWS()
    ws.client = None  # disconnected
    assert main_module._ws_client_ip(ws) == "unknown"


# --- runner -----------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        (name, obj) for name, obj in sorted(globals().items())
        if name.startswith("test_") and callable(obj)
    ]
    print(f"running {len(tests)} tests...")
    failed: list[tuple[str, str]] = []
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as e:
            failed.append((name, f"AssertionError: {e}"))
            print(f"  FAIL  {name}")
        except Exception as e:
            failed.append((name, f"{type(e).__name__}: {e}"))
            print(f"  ERR   {name}  ({type(e).__name__}: {e})")

    print()
    print(f"{len(tests) - len(failed)}/{len(tests)} passed")
    if failed:
        for name, err in failed:
            print(f"  {name}: {err}")
        sys.exit(1)
