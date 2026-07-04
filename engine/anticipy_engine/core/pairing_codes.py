"""Signed per-user PAIRING codes (B12) — the hermetic HMAC handshake behind ANTICIPY_PER_USER_HANDS.

On a SHARED cloud engine the browser extension must bind its hand to the SIGNED-IN user's core,
not the owner's. Today the extension does an unauthenticated ``GET /ws/token`` + connects
``/ws/extension?token=`` with no ``?user=`` — so on a shared engine the hand binds to the OWNER
core. This module closes that hole WITHOUT trusting the extension:

  * The signed-in web app (which holds ``ENGINE_INTERNAL_TOKEN`` server-side) asks the engine to
    MINT a short-lived code carrying the caller's Supabase ``user_id``, HMAC-signed with that
    shared secret (``mint_pairing_code``). The web app hands the code to the extension via the
    ``pair_device`` external message.
  * The extension presents the code to ``POST /ws/pair`` (it has no Supabase bearer — the HMAC IS
    the auth). The engine RE-DERIVES the HMAC and, only if it matches AND the code is unexpired,
    returns that user's per-user ``browser_link`` token so the WS binds via ``?user=<id>``
    (``verify_pairing_code``). A forged (wrong secret / tampered) or expired code is rejected.

The whole per-user-pairing path is OFF by default (``per_user_hands_enabled()`` is False) so the
single-owner local behavior stays byte-identical; it is enabled explicitly per deploy and must
never be flipped on casually. Fail-closed: with no ``ENGINE_INTERNAL_TOKEN`` configured, minting
AND verification both refuse, so nobody can pair per-user on a mis-provisioned engine.

Pure stdlib (hmac/hashlib/base64), no network, no model — so the whole handshake is testable
hermetically. The code format is a JS-friendly, dot-delimited, url-safe-base64 string:

    apc1.<b64url(user_id)>.<exp_unix>.<b64url(hmac_sha256)>
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from typing import Optional

_PREFIX = "apc1"  # anticipy pairing code, format v1
_DEFAULT_TTL = 120  # seconds a minted code stays valid — short-lived by design (a pairing is prompt)


def per_user_hands_enabled() -> bool:
    """The master gate for the signed per-user-pairing path.

    Default OFF -> the /ws/pair(_code) endpoints report disabled and the engine keeps its
    single-owner behavior byte-identical. Truthy: 1/true/yes/on (case-insensitive)."""
    return (os.environ.get("ANTICIPY_PER_USER_HANDS", "") or "").strip().lower() in ("1", "true", "yes", "on")


def _secret() -> bytes:
    """The shared HMAC key: ENGINE_INTERNAL_TOKEN. Empty -> no secret configured -> minting and
    verification BOTH refuse (fail closed: without a server secret nobody can pair per-user)."""
    return (os.environ.get("ENGINE_INTERNAL_TOKEN", "") or "").strip().encode("utf-8")


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64(txt: str) -> bytes:
    pad = "=" * (-len(txt) % 4)
    return base64.urlsafe_b64decode(txt + pad)


def _sig(payload: str, secret: bytes) -> str:
    return _b64(hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).digest())


def mint_pairing_code(user_id: str, ttl_seconds: int = _DEFAULT_TTL, now: Optional[float] = None) -> Optional[str]:
    """Mint a signed, short-lived pairing code for ``user_id``.

    Returns None when no secret is configured or ``user_id`` is empty (fail closed). ``now`` is
    injectable for deterministic tests."""
    secret = _secret()
    uid = (user_id or "").strip()
    if not secret or not uid:
        return None
    exp = int((now if now is not None else time.time()) + max(1, int(ttl_seconds)))
    payload = f"{_PREFIX}.{_b64(uid.encode('utf-8'))}.{exp}"
    return f"{payload}.{_sig(payload, secret)}"


def verify_pairing_code(code: str, now: Optional[float] = None) -> Optional[str]:
    """Return the ``user_id`` iff the code is well-formed, correctly HMAC-signed with the CURRENT
    secret, and unexpired. Any tamper / forgery / wrong-secret / expiry -> None. The signature
    compare is constant-time (``hmac.compare_digest``) so it leaks no timing oracle."""
    secret = _secret()
    if not secret or not code:
        return None
    parts = str(code).split(".")
    if len(parts) != 4 or parts[0] != _PREFIX:
        return None
    _pfx, uid_b64, exp_s, got_sig = parts
    payload = f"{_PREFIX}.{uid_b64}.{exp_s}"
    if not hmac.compare_digest(got_sig, _sig(payload, secret)):
        return None
    try:
        exp = int(exp_s)
    except ValueError:
        return None
    if (now if now is not None else time.time()) > exp:
        return None
    try:
        return _unb64(uid_b64).decode("utf-8")
    except Exception:
        return None
