"""
Username/password authentication with bcrypt hashing and JWT tokens.
User records stored in Supabase engine_users table.
Rate limiting on login to prevent brute force.
"""

from __future__ import annotations

import re
import time
import uuid
from collections import defaultdict
from typing import Optional

import bcrypt
import jwt

from app.config import (
    JWT_SECRET,
    JWT_ALGORITHM,
    JWT_EXPIRY_HOURS,
    LOGIN_MAX_FAILURES,
    LOGIN_BLOCK_MINUTES,
    USERNAME_MIN_LEN,
    USERNAME_MAX_LEN,
    PASSWORD_MIN_LEN,
    PASSWORD_MAX_LEN,
    ADMIN_USERNAMES,
)
from app import supabase_client


# --- Login rate limiting ---
# Maps IP -> list of failure timestamps
_login_failures: dict[str, list[float]] = defaultdict(list)
# Hard cap to prevent unbounded memory growth from random IPs
_LOGIN_FAILURES_MAX_IPS = 10_000
_last_global_cleanup: float = 0.0


def _global_cleanup_failures() -> None:
    """Periodic sweep of the failure map to prevent unbounded growth."""
    global _last_global_cleanup
    now = time.time()
    if now - _last_global_cleanup < 60:
        return
    _last_global_cleanup = now
    cutoff = now - LOGIN_BLOCK_MINUTES * 60
    stale = [ip for ip, ts_list in _login_failures.items() if not ts_list or max(ts_list) < cutoff]
    for ip in stale:
        _login_failures.pop(ip, None)
    # If we're still way over the cap, drop oldest entries
    if len(_login_failures) > _LOGIN_FAILURES_MAX_IPS:
        sorted_ips = sorted(_login_failures.items(), key=lambda kv: max(kv[1]) if kv[1] else 0)
        for ip, _ in sorted_ips[: len(_login_failures) - _LOGIN_FAILURES_MAX_IPS]:
            _login_failures.pop(ip, None)


def _clean_old_failures(ip: str) -> None:
    """Remove failure records older than the block window."""
    cutoff = time.time() - LOGIN_BLOCK_MINUTES * 60
    _login_failures[ip] = [ts for ts in _login_failures[ip] if ts > cutoff]
    if not _login_failures[ip]:
        _login_failures.pop(ip, None)
    _global_cleanup_failures()


def check_login_rate_limit(ip: str) -> bool:
    """
    Return True if the IP is rate-limited (too many failed logins).
    """
    _clean_old_failures(ip)
    return len(_login_failures.get(ip, [])) >= LOGIN_MAX_FAILURES


def record_login_failure(ip: str) -> None:
    """Record a failed login attempt for the given IP."""
    _login_failures[ip].append(time.time())
    _global_cleanup_failures()


def clear_login_failures(ip: str) -> None:
    """Clear failure records on successful login."""
    _login_failures.pop(ip, None)


# --- Validation ---
_USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def validate_username(username: str) -> str | None:
    """Return error tag or None if valid."""
    if not username or not isinstance(username, str):
        return "missing"
    u = username.strip()
    if len(u) < USERNAME_MIN_LEN or len(u) > USERNAME_MAX_LEN:
        return "format"
    if not _USERNAME_RE.match(u):
        return "format"
    return None


def validate_password(password: str) -> str | None:
    """Return error tag or None if valid."""
    if not isinstance(password, str):
        return "missing"
    if len(password) < PASSWORD_MIN_LEN:
        return "too_short"
    if len(password) > PASSWORD_MAX_LEN:
        return "too_long"
    return None


def is_admin(username: str | None) -> bool:
    """Return True if the username is in the configured admin allow-list."""
    if not username:
        return False
    return username.lower() in {u.lower() for u in ADMIN_USERNAMES}


def _hash_password(password: str) -> str:
    """Hash a password with bcrypt."""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def _verify_password(password: str, hashed: str) -> bool:
    """Verify a password against its bcrypt hash."""
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


def _create_token(user_id: str, username: str) -> str:
    """Create a signed JWT with expiry."""
    payload = {
        "user_id": user_id,
        "username": username,
        "exp": int(time.time()) + JWT_EXPIRY_HOURS * 3600,
        "iat": int(time.time()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(token: str) -> dict | None:
    """
    Validate a JWT and return the payload dict with user_id and username.
    Returns None if invalid or expired.
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return {
            "user_id": payload["user_id"],
            "username": payload["username"],
        }
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


async def signup(username: str, password: str) -> dict:
    """
    Create a new user account.
    Returns {"success": True, "token": ..., "user_id": ...} or
            {"success": False, "error": "exists"|"failed"|"username"|"password_short"|"password_long"}.
    """
    u_err = validate_username(username)
    if u_err:
        return {"success": False, "error": "username"}
    p_err = validate_password(password)
    if p_err:
        return {"success": False, "error": f"password_{p_err}"}

    username = username.strip()

    # Check if user already exists
    try:
        existing = await supabase_client.select_rows(
            "engine_users",
            filters={"username": username},
            limit=1,
        )
    except Exception:
        return {"success": False, "error": "failed"}

    if existing:
        return {"success": False, "error": "exists"}

    user_id = str(uuid.uuid4())
    try:
        hashed = _hash_password(password)
    except Exception:
        return {"success": False, "error": "failed"}

    try:
        row = await supabase_client.insert_row(
            "engine_users",
            {
                "id": user_id,
                "username": username,
                "password_hash": hashed,
            },
        )
    except Exception:
        return {"success": False, "error": "failed"}

    if row is None:
        return {"success": False, "error": "failed"}

    token = _create_token(user_id, username)
    return {"success": True, "token": token, "user_id": user_id}


async def login(username: str, password: str, ip: str = "unknown") -> dict:
    """
    Authenticate an existing user.
    Returns {"success": True, "token": ..., "user_id": ...} or
            {"success": False, "error": "invalid"|"rate_limited"|"failed"}.
    """
    if not isinstance(username, str) or not isinstance(password, str):
        record_login_failure(ip)
        return {"success": False, "error": "invalid"}

    # Check rate limit
    if check_login_rate_limit(ip):
        return {"success": False, "error": "rate_limited"}

    username = username.strip()
    if not username or not password:
        record_login_failure(ip)
        return {"success": False, "error": "invalid"}

    try:
        rows = await supabase_client.select_rows(
            "engine_users",
            filters={"username": username},
            limit=1,
        )
    except Exception:
        return {"success": False, "error": "failed"}

    if not rows:
        record_login_failure(ip)
        return {"success": False, "error": "invalid"}

    user = rows[0]
    stored_hash = user.get("password_hash", "") or ""

    try:
        ok = bool(stored_hash) and _verify_password(password, stored_hash)
    except Exception:
        ok = False

    if not ok:
        record_login_failure(ip)
        return {"success": False, "error": "invalid"}

    # Success: clear failures
    clear_login_failures(ip)
    user_id = user.get("id", "")
    token = _create_token(user_id, username)
    return {"success": True, "token": token, "user_id": user_id}
