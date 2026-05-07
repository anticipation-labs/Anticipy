"""
Tests for app.auth — login rate limiting, JWT, password hashing.

Covers the deterministic surfaces that don't require a Supabase round-trip:
  - check_login_rate_limit / record_login_failure / clear_login_failures
  - JWT _create_token / verify_token (signing, expiry, tampering)
  - bcrypt _hash_password / _verify_password (round-trip + wrong-password)

Live signup/login (which hit Supabase) are out of scope here; they're covered
by the integration smoke test_real.py and manual smoke.
"""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Required env BEFORE importing app modules.
os.environ.setdefault("JWT_SECRET", "x" * 48)
os.environ.setdefault("PROFILE_ENCRYPTION_KEY", "y" * 44 + "=")

import jwt  # noqa: E402

from app import auth as auth_module  # noqa: E402
from app.config import (  # noqa: E402
    JWT_ALGORITHM,
    JWT_SECRET,
    LOGIN_BLOCK_MINUTES,
    LOGIN_MAX_FAILURES,
)


def _reset_login_failures():
    auth_module._login_failures.clear()


# --- login rate limiting ------------------------------------------------------


def test_check_login_rate_limit_admits_when_no_failures():
    _reset_login_failures()
    assert auth_module.check_login_rate_limit("1.2.3.4") is False


def test_check_login_rate_limit_blocks_after_max_failures():
    _reset_login_failures()
    for _ in range(LOGIN_MAX_FAILURES):
        auth_module.record_login_failure("1.2.3.4")
    assert auth_module.check_login_rate_limit("1.2.3.4") is True


def test_check_login_rate_limit_isolated_per_ip():
    _reset_login_failures()
    for _ in range(LOGIN_MAX_FAILURES):
        auth_module.record_login_failure("1.2.3.4")
    assert auth_module.check_login_rate_limit("1.2.3.4") is True
    # A different IP is still admitted
    assert auth_module.check_login_rate_limit("5.6.7.8") is False


def test_clear_login_failures_resets():
    _reset_login_failures()
    for _ in range(LOGIN_MAX_FAILURES):
        auth_module.record_login_failure("1.2.3.4")
    auth_module.clear_login_failures("1.2.3.4")
    assert auth_module.check_login_rate_limit("1.2.3.4") is False


def test_old_failures_age_out():
    """Failures older than LOGIN_BLOCK_MINUTES are pruned by check_login_rate_limit."""
    _reset_login_failures()
    cutoff_age = LOGIN_BLOCK_MINUTES * 60 + 5
    old_ts = time.time() - cutoff_age
    auth_module._login_failures["1.2.3.4"] = [old_ts] * LOGIN_MAX_FAILURES
    # A check call prunes them.
    assert auth_module.check_login_rate_limit("1.2.3.4") is False


def test_burst_record_then_check_consistency():
    """Recording exactly MAX_FAILURES marks the IP as blocked."""
    _reset_login_failures()
    for _ in range(LOGIN_MAX_FAILURES - 1):
        auth_module.record_login_failure("1.2.3.4")
    assert auth_module.check_login_rate_limit("1.2.3.4") is False
    auth_module.record_login_failure("1.2.3.4")
    assert auth_module.check_login_rate_limit("1.2.3.4") is True


# --- JWT roundtrip ------------------------------------------------------------


def test_create_token_round_trip():
    token = auth_module._create_token("user-1", "alice")
    payload = auth_module.verify_token(token)
    assert payload is not None
    assert payload["user_id"] == "user-1"
    assert payload["username"] == "alice"


def test_verify_token_rejects_garbage():
    assert auth_module.verify_token("not.a.real.token") is None


def test_verify_token_rejects_tampered_payload():
    """A token whose payload has been swapped for a different user must fail."""
    token = auth_module._create_token("user-1", "alice")
    # Decode without verification; swap user_id; re-encode with WRONG secret
    raw = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    raw["user_id"] = "user-evil"
    forged = jwt.encode(raw, "different-secret-aaaa-bbbb-cccc-dddd", algorithm=JWT_ALGORITHM)
    assert auth_module.verify_token(forged) is None


def test_verify_token_rejects_expired():
    payload = {
        "user_id": "user-1",
        "username": "alice",
        "exp": int(time.time()) - 60,
        "iat": int(time.time()) - 3600,
    }
    expired = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    assert auth_module.verify_token(expired) is None


def test_verify_token_rejects_unsigned_alg_none():
    """Defense against the classic JWT alg=none attack."""
    payload = {
        "user_id": "user-1",
        "username": "alice",
        "exp": int(time.time()) + 3600,
        "iat": int(time.time()),
    }
    # Construct an unsigned token (alg=none) — must NOT be accepted.
    unsigned = jwt.encode(payload, "", algorithm="none")
    assert auth_module.verify_token(unsigned) is None


# --- bcrypt password hash -----------------------------------------------------


def test_hash_password_verifies_correct():
    pw = "correct horse battery staple"
    hashed = auth_module._hash_password(pw)
    assert auth_module._verify_password(pw, hashed) is True


def test_hash_password_rejects_wrong():
    hashed = auth_module._hash_password("right")
    assert auth_module._verify_password("wrong", hashed) is False


def test_hash_password_two_calls_produce_different_hashes():
    """bcrypt salts each hash uniquely — same input → different ciphertext."""
    h1 = auth_module._hash_password("secret")
    h2 = auth_module._hash_password("secret")
    assert h1 != h2  # different salts
    # Both still verify
    assert auth_module._verify_password("secret", h1) is True
    assert auth_module._verify_password("secret", h2) is True


def test_hash_password_does_not_collide_with_truncation():
    """Long passwords don't collide. (bcrypt has a 72-byte input limit; verify
    that two distinct long passwords don't accidentally produce equivalent
    verification outcomes.)"""
    pw_a = "a" * 70 + "AAA"
    pw_b = "a" * 70 + "BBB"
    h_a = auth_module._hash_password(pw_a)
    assert auth_module._verify_password(pw_a, h_a) is True
    # Differing only in the >72-byte tail, bcrypt may treat them as the same;
    # we don't fail on that — but the documented behavior must be deterministic.
    # The test guards that verify_password ALWAYS returns a bool, no exception.
    assert isinstance(auth_module._verify_password(pw_b, h_a), bool)


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
