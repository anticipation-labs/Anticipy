"""
Tests for the security-relevant surfaces of app.main:

  - WebSocket connection rate limiting (per-user and per-IP caps)
  - X-Forwarded-For trust gate (TRUST_FORWARDED_FOR env var)
  - Confirmation token issuance + verification edge cases
  - Bearer token requirement on /execute-intent

These run without booting the FastAPI server — we exercise the helper
functions and a TestClient where possible. Live HTTP endpoint behavior
involving the LLM cascade is covered by the integration smoke.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Ensure required env is set before main.py imports
os.environ.setdefault("JWT_SECRET", "x" * 48)
os.environ.setdefault("PROFILE_ENCRYPTION_KEY", "y" * 44 + "=")

import jwt  # noqa: E402

from app.config import JWT_ALGORITHM, JWT_SECRET  # noqa: E402
from app import auth as auth_module  # noqa: E402
from app import main as main_module  # noqa: E402


# --- WS connection rate limit -------------------------------------------------


def test_ws_connection_admit_under_limit_admits():
    main_module._ws_connections_by_user.clear()
    main_module._ws_connections_by_ip.clear()
    refusal = main_module._ws_connection_admit("u1", "1.2.3.4")
    assert refusal is None
    assert main_module._ws_connections_by_user["u1"] == 1
    assert main_module._ws_connections_by_ip["1.2.3.4"] == 1


def test_ws_connection_admit_per_user_cap():
    main_module._ws_connections_by_user.clear()
    main_module._ws_connections_by_ip.clear()
    cap = main_module.MAX_WS_CONCURRENT_PER_USER
    # Fill the cap from different IPs so the per-IP gate doesn't fire first.
    for i in range(cap):
        assert main_module._ws_connection_admit("u1", f"ip-{i}") is None
    refusal = main_module._ws_connection_admit("u1", "ip-extra")
    assert refusal is not None
    assert "user" in refusal.lower()


def test_ws_connection_admit_per_ip_cap():
    main_module._ws_connections_by_user.clear()
    main_module._ws_connections_by_ip.clear()
    cap = main_module.MAX_WS_CONCURRENT_PER_IP
    # Fill the cap from different users so the per-user gate doesn't fire.
    for i in range(cap):
        assert main_module._ws_connection_admit(f"user-{i}", "1.2.3.4") is None
    refusal = main_module._ws_connection_admit("user-extra", "1.2.3.4")
    assert refusal is not None
    assert "network" in refusal.lower() or "ip" in refusal.lower()


def test_ws_connection_release_decrements():
    main_module._ws_connections_by_user.clear()
    main_module._ws_connections_by_ip.clear()
    main_module._ws_connection_admit("u1", "1.2.3.4")
    assert main_module._ws_connections_by_user["u1"] == 1
    main_module._ws_connection_release("u1", "1.2.3.4")
    assert main_module._ws_connections_by_user["u1"] == 0
    assert main_module._ws_connections_by_ip["1.2.3.4"] == 0


def test_ws_connection_release_under_zero_safe():
    """Calling release more times than admit does not go negative."""
    main_module._ws_connections_by_user.clear()
    main_module._ws_connections_by_ip.clear()
    main_module._ws_connection_release("u1", "1.2.3.4")  # never admitted
    assert main_module._ws_connections_by_user.get("u1", 0) == 0


def test_ws_connection_admit_anonymous_user_only_caps_ip():
    """If user_id is None (e.g., during pre-auth phases), only IP gate runs."""
    main_module._ws_connections_by_user.clear()
    main_module._ws_connections_by_ip.clear()
    cap = main_module.MAX_WS_CONCURRENT_PER_IP
    for i in range(cap):
        assert main_module._ws_connection_admit(None, "1.2.3.4") is None
    refusal = main_module._ws_connection_admit(None, "1.2.3.4")
    assert refusal is not None


# --- X-Forwarded-For trust gate -----------------------------------------------


class _FakeRequest:
    def __init__(self, host: str = "10.0.0.1", forwarded: str | None = None):
        self.client = type("client", (), {"host": host})()
        self.headers = {}
        if forwarded:
            self.headers["x-forwarded-for"] = forwarded


def test_get_client_ip_default_uses_direct_connection():
    """Without TRUST_FORWARDED_FOR=1, X-Forwarded-For is ignored."""
    os.environ.pop("TRUST_FORWARDED_FOR", None)
    req = _FakeRequest(host="10.0.0.1", forwarded="6.6.6.6")
    assert main_module._get_client_ip(req) == "10.0.0.1"


def test_get_client_ip_trusts_forwarded_when_enabled():
    os.environ["TRUST_FORWARDED_FOR"] = "1"
    try:
        req = _FakeRequest(host="10.0.0.1", forwarded="6.6.6.6, 7.7.7.7")
        assert main_module._get_client_ip(req) == "6.6.6.6"
    finally:
        os.environ.pop("TRUST_FORWARDED_FOR", None)


def test_get_client_ip_handles_missing_client():
    os.environ.pop("TRUST_FORWARDED_FOR", None)
    req = _FakeRequest(host="10.0.0.1")
    req.client = None  # simulate disconnected
    assert main_module._get_client_ip(req) == "unknown"


# --- Confirmation tokens (issuance + verification) ---------------------------


def test_confirmation_token_round_trip_success():
    token = main_module._issue_confirmation_token("buy a book", "user-1")
    assert main_module._verify_confirmation_token(token, "buy a book", "user-1") is True


def test_confirmation_token_rejects_task_mismatch():
    token = main_module._issue_confirmation_token("buy a book", "user-1")
    assert main_module._verify_confirmation_token(token, "wire money", "user-1") is False


def test_confirmation_token_rejects_user_mismatch():
    token = main_module._issue_confirmation_token("buy a book", "user-1")
    # Token was issued for user-1; verifying as user-2 must fail.
    assert main_module._verify_confirmation_token(token, "buy a book", "user-2") is False


def test_confirmation_token_rejects_expired():
    """An expired token must fail. We forge one via direct jwt.encode."""
    import time as _time
    payload = {
        "task_hash": main_module._hash_task("buy a book"),
        "user_id": "user-1",
        "exp": int(_time.time()) - 10,  # expired
        "iat": int(_time.time()) - 1000,
        "purpose": "execute_intent",
    }
    expired = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    assert main_module._verify_confirmation_token(expired, "buy a book", "user-1") is False


def test_confirmation_token_rejects_wrong_purpose():
    """A token for some other purpose must not authorize execute-intent."""
    import time as _time
    payload = {
        "task_hash": main_module._hash_task("buy a book"),
        "user_id": "user-1",
        "exp": int(_time.time()) + 600,
        "iat": int(_time.time()),
        "purpose": "different_thing",  # wrong purpose
    }
    bad = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    assert main_module._verify_confirmation_token(bad, "buy a book", "user-1") is False


def test_confirmation_token_rejects_invalid_signature():
    """Token signed with a different secret must fail."""
    import time as _time
    payload = {
        "task_hash": main_module._hash_task("buy a book"),
        "user_id": "user-1",
        "exp": int(_time.time()) + 600,
        "iat": int(_time.time()),
        "purpose": "execute_intent",
    }
    forged = jwt.encode(payload, "different-secret-aaaa-bbbb-cccc-dddd", algorithm=JWT_ALGORITHM)
    assert main_module._verify_confirmation_token(forged, "buy a book", "user-1") is False


# --- Bearer auth helper -------------------------------------------------------


def test_bearer_user_rejects_missing_header():
    from fastapi import HTTPException
    try:
        main_module._bearer_user(None)
        assert False, "expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 401


def test_bearer_user_rejects_non_bearer_scheme():
    from fastapi import HTTPException
    try:
        main_module._bearer_user("Basic abc123")
        assert False, "expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 401


def test_bearer_user_rejects_invalid_token():
    from fastapi import HTTPException
    try:
        main_module._bearer_user("Bearer total-garbage")
        assert False, "expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 401


def test_bearer_user_accepts_valid_token():
    token = auth_module._create_token("user-1", "alice")
    payload = main_module._bearer_user(f"Bearer {token}")
    assert payload["user_id"] == "user-1"
    assert payload["username"] == "alice"


# --- runner -------------------------------------------------------------------


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
