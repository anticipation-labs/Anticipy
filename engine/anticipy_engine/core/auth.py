"""Per-user auth: verify a Supabase access token (JWT) and resolve WHO the caller is.

Robust by construction: we validate the presented token against Supabase's own /auth/v1/user
endpoint, so it works whether the project signs JWTs with HS256 or asymmetric keys — no secret-
guessing, no JWT library. A short in-memory cache makes it one network call per token per TTL
(not per request). The single-owner-token path (ANTICIPY_OWNER_API_TOKEN) stays ADDITIVE for
local dev + the deterministic suite; this only ADDS the "a real signed-in Supabase user" path.

Returns a stable user_id (the Supabase user UUID) that the engine keys per-user data by.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

_CACHE: dict = {}      # token -> (user_id, email, expiry_epoch)
_TTL = 300.0           # re-validate a token at most every 5 min
_NEG_TTL = 30.0        # cache a rejection briefly so a bad token doesn't hammer Supabase


def _supabase_url() -> str:
    return (os.environ.get("NEXT_PUBLIC_SUPABASE_URL") or os.environ.get("SUPABASE_URL") or "").strip().rstrip("/")


def _anon_key() -> str:
    return (os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY") or os.environ.get("SUPABASE_ANON_KEY") or "").strip()


def verify_supabase_token(token, now: float | None = None) -> dict | None:
    """{'user_id', 'email'} for a valid Supabase access token, else None. Never raises."""
    token = (token or "").strip()
    if not token or token.count(".") != 2:   # must look like a JWT (header.payload.sig)
        return None
    now = time.time() if now is None else now
    hit = _CACHE.get(token)
    if hit is not None and hit[2] > now:
        return None if hit[0] is None else {"user_id": hit[0], "email": hit[1]}
    base, anon = _supabase_url(), _anon_key()
    if not base or not anon:
        return None
    try:
        req = urllib.request.Request(
            base + "/auth/v1/user",
            headers={"apikey": anon, "Authorization": "Bearer " + token},
        )
        with urllib.request.urlopen(req, timeout=8) as r:
            user = json.loads(r.read().decode("utf-8"))
        uid = str(user.get("id") or "").strip()
        if not uid:
            _CACHE[token] = (None, "", now + _NEG_TTL)
            return None
        email = str(user.get("email") or "")
        _CACHE[token] = (uid, email, now + _TTL)
        return {"user_id": uid, "email": email}
    except urllib.error.HTTPError:
        _CACHE[token] = (None, "", now + _NEG_TTL)   # 401/403 -> not a valid user
        return None
    except Exception:
        return None   # transient (network/timeout): don't cache, don't authorize this request
