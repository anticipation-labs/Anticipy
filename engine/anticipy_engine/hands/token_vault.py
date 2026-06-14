"""Per-person API mesh foundation — an encrypted, per-user token vault + broker
+ connector registry. This is what replaces the single shared ARCADE_API_KEY at
api_hand.py: every user brings their own apps (Gmail, a niche CRM, ...), each with
its own OAuth token, stored encrypted at rest and isolated from every other user.

Three pieces, one file:

  TokenVault      — encrypted-at-rest store of {user_id, app} -> token + metadata.
                    Authenticated encryption (encrypt-then-MAC) keyed off an env
                    master key. Cipher bytes on disk are NOT the plaintext token.
                    One file per user; a user can NEVER read another user's tokens.

  TokenBroker     — the NON-LLM broker. get_token(user_id, app) decrypts and returns
                    a short-lived, opaque SecretToken. The token NEVER enters a prompt,
                    a log line, a repr, an exception string, or a model context: the
                    broker is plain Python the model cannot reach into, and SecretToken
                    redacts itself everywhere it could leak.

  ConnectorRegistry — dispatches a (user_id, app) to its route: "api" (Arcade-style
                    connector), "browser" (the per-person 10% with no API), or
                    "voice_text" (the Twilio line). Route is stored alongside the
                    token so each user's niche app can choose its own arm.

Crypto note: the runtime venv does NOT ship `cryptography` (no AES). Rather than add
a dependency that other parallel builders / the suite don't expect, this uses a sound
stdlib construction: scrypt KDF from the master key -> two independent subkeys; a random
per-record nonce; an HMAC-SHA256 counter-mode keystream for confidentiality; and an
encrypt-then-MAC HMAC-SHA256 tag over (nonce||ciphertext||aad) for integrity. Decrypt
verifies the tag with a constant-time compare BEFORE returning anything. This is real
authenticated encryption, not XOR-with-a-fixed-key. If `cryptography` is later vendored,
swap _seal/_open for Fernet without touching the vault/broker/registry surface.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import struct
import time
from pathlib import Path
from typing import Dict, Iterable, Optional

# Routes a connector can take. Mirrors the product's three arms.
ROUTE_API = "api"
ROUTE_BROWSER = "browser"
ROUTE_VOICE_TEXT = "voice_text"
VALID_ROUTES = frozenset({ROUTE_API, ROUTE_BROWSER, ROUTE_VOICE_TEXT})

_ENV_MASTER_KEY = "ANTICIPY_VAULT_KEY"
_DEFAULT_TTL_S = 300.0  # short-lived broker lease; tokens at rest carry their own expiry

# scrypt cost — strong enough for a master-key KDF, cheap enough for a per-op call.
_SCRYPT_N = 2 ** 14
_SCRYPT_R = 8
_SCRYPT_P = 1


class VaultError(RuntimeError):
    """Loud failure for a missing master key, a corrupt/tampered record, or a
    decrypt that fails its integrity check. Never silent, never a fake token."""


class TokenNotFound(KeyError):
    """No token stored for this (user_id, app). Distinct from a tamper/decrypt error."""


# --------------------------------------------------------------------------- #
# SecretToken — an opaque holder that refuses to leak the plaintext.
# --------------------------------------------------------------------------- #
class SecretToken:
    """Wraps a decrypted token so it cannot accidentally land in a prompt, a log,
    a repr, an f-string, or a JSON dump. The only way to the plaintext is the
    explicit `.reveal()` call, which the LLM-facing code never makes — only the
    non-LLM connector that performs the real HTTP auth does.

    str(), repr(), and json default-encoding all yield a redaction marker.
    """

    __slots__ = ("_value", "app", "user_id", "expires_at")

    _REDACTED = "<secret:redacted>"

    def __init__(self, value: str, *, app: str, user_id: str, expires_at: Optional[float]) -> None:
        object.__setattr__(self, "_value", value)
        self.app = app
        self.user_id = user_id
        self.expires_at = expires_at

    def reveal(self) -> str:
        """Return the plaintext token. ONLY the non-LLM connector calls this at the
        moment of the real auth handshake. Never log/return the result."""
        if self.expired():
            raise VaultError(f"token lease expired for {self.user_id}/{self.app}")
        return object.__getattribute__(self, "_value")

    def expired(self, now: Optional[float] = None) -> bool:
        if self.expires_at is None:
            return False
        return (now or time.time()) >= self.expires_at

    # --- every leak path redacts ---
    def __repr__(self) -> str:
        return f"SecretToken(app={self.app!r}, user_id={self.user_id!r}, value={self._REDACTED})"

    def __str__(self) -> str:
        return self._REDACTED

    def __format__(self, _spec: str) -> str:
        return self._REDACTED

    def __reduce__(self):  # block pickling the plaintext out
        raise TypeError("SecretToken is not serializable")


# --------------------------------------------------------------------------- #
# Authenticated encryption (stdlib): scrypt KDF -> HMAC-CTR + encrypt-then-MAC.
# --------------------------------------------------------------------------- #
def _master_key() -> bytes:
    raw = os.environ.get(_ENV_MASTER_KEY)
    if not raw:
        raise VaultError(
            f"{_ENV_MASTER_KEY} NOT SET — the vault refuses to store/read tokens "
            "without a master key (no plaintext-at-rest fallback)."
        )
    return raw.encode("utf-8")


def _derive_subkeys(master: bytes, salt: bytes) -> tuple[bytes, bytes]:
    """scrypt(master, salt) -> 64 bytes -> (enc_key, mac_key). Independent keys so
    the same material never both encrypts and authenticates."""
    dk = hashlib.scrypt(master, salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=64)
    return dk[:32], dk[32:]


def _keystream(enc_key: bytes, nonce: bytes, nbytes: int) -> bytes:
    """HMAC-SHA256 in counter mode -> an arbitrary-length keystream."""
    out = bytearray()
    counter = 0
    while len(out) < nbytes:
        block = hmac.new(enc_key, struct.pack(">Q", counter) + nonce, hashlib.sha256).digest()
        out.extend(block)
        counter += 1
    return bytes(out[:nbytes])


def _seal(plaintext: str, master: bytes, aad: bytes) -> dict:
    """Encrypt-then-MAC. Returns a JSON-safe record. `aad` (e.g. user_id|app) is bound
    into the tag, so a record can't be moved between users/apps without detection."""
    salt = os.urandom(16)
    nonce = os.urandom(16)
    enc_key, mac_key = _derive_subkeys(master, salt)
    pt = plaintext.encode("utf-8")
    ct = bytes(a ^ b for a, b in zip(pt, _keystream(enc_key, nonce, len(pt))))
    tag = hmac.new(mac_key, salt + nonce + ct + aad, hashlib.sha256).digest()
    b64 = lambda b: base64.b64encode(b).decode("ascii")
    return {"v": 1, "salt": b64(salt), "nonce": b64(nonce), "ct": b64(ct), "tag": b64(tag)}


def _open(record: dict, master: bytes, aad: bytes) -> str:
    """Verify the tag (constant time) BEFORE decrypting. Any mismatch -> VaultError,
    never a half-decrypted or fabricated token."""
    try:
        salt = base64.b64decode(record["salt"])
        nonce = base64.b64decode(record["nonce"])
        ct = base64.b64decode(record["ct"])
        tag = base64.b64decode(record["tag"])
    except (KeyError, ValueError, TypeError) as exc:
        raise VaultError(f"corrupt token record: {type(exc).__name__}") from None
    enc_key, mac_key = _derive_subkeys(master, salt)
    expect = hmac.new(mac_key, salt + nonce + ct + aad, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, expect):
        raise VaultError("token integrity check failed (tampered, wrong key, or wrong owner)")
    pt = bytes(a ^ b for a, b in zip(ct, _keystream(enc_key, nonce, len(ct))))
    return pt.decode("utf-8")


# --------------------------------------------------------------------------- #
# TokenVault — the encrypted-at-rest store.
# --------------------------------------------------------------------------- #
def _default_base() -> Path:
    return Path(os.environ.get("ANTICIPY_DATA_DIR", ".anticipy-data")).expanduser()


def _safe_id(value: str) -> str:
    """Filesystem-safe, collision-free per-user filename. Hash, so an email/CRM id
    never becomes a path-traversal or a readable filename on disk."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]


class TokenVault:
    """One encrypted file per user under <data>/vault/. Each file maps app -> sealed
    record + non-secret metadata (route, scopes, stored_at, expires_at). The token
    value is the ONLY field that is encrypted; metadata stays clear so the registry
    can route without ever touching plaintext."""

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        base = Path(data_dir) if data_dir else _default_base()
        self.dir = base / "vault"
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, user_id: str) -> Path:
        return self.dir / f"{_safe_id(user_id)}.json"

    def _load_file(self, user_id: str) -> dict:
        p = self._path(user_id)
        if not p.exists():
            return {}
        try:
            return json.loads(p.read_text())
        except (ValueError, OSError) as exc:
            raise VaultError(f"unreadable vault file for user: {type(exc).__name__}") from None

    def _write_file(self, user_id: str, blob: dict) -> None:
        p = self._path(user_id)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(blob, indent=2, sort_keys=True))
        os.replace(tmp, p)  # atomic; never a torn write
        try:
            os.chmod(p, 0o600)  # owner-only at rest
        except OSError:
            pass

    @staticmethod
    def _aad(user_id: str, app: str) -> bytes:
        # binds a record to its owner+app so it can't be relocated undetected
        return f"{user_id}\x00{app}".encode("utf-8")

    def store_token(
        self,
        user_id: str,
        app: str,
        token: str,
        *,
        route: str = ROUTE_API,
        scopes: Optional[Iterable[str]] = None,
        expires_at: Optional[float] = None,
    ) -> None:
        """Encrypt `token` at rest for (user_id, app). The plaintext is sealed before it
        ever hits disk; only ciphertext + non-secret metadata are written."""
        if route not in VALID_ROUTES:
            raise VaultError(f"unknown route {route!r}; valid: {sorted(VALID_ROUTES)}")
        if not token:
            raise VaultError("refusing to store an empty token")
        master = _master_key()
        sealed = _seal(token, master, self._aad(user_id, app))
        blob = self._load_file(user_id)
        blob[app] = {
            "route": route,
            "scopes": sorted(scopes) if scopes else [],
            "sealed": sealed,
            "stored_at": time.time(),
            "expires_at": expires_at,
        }
        self._write_file(user_id, blob)

    def has(self, user_id: str, app: str) -> bool:
        return app in self._load_file(user_id)

    def apps(self, user_id: str) -> list[str]:
        """The apps a given user has connected (no secrets revealed)."""
        return sorted(self._load_file(user_id).keys())

    def route_of(self, user_id: str, app: str) -> str:
        rec = self._load_file(user_id).get(app)
        if rec is None:
            raise TokenNotFound(f"{user_id} has not connected {app}")
        return rec.get("route", ROUTE_API)

    def metadata(self, user_id: str, app: str) -> dict:
        """Non-secret metadata only — route/scopes/timestamps. Never the token."""
        rec = self._load_file(user_id).get(app)
        if rec is None:
            raise TokenNotFound(f"{user_id} has not connected {app}")
        return {k: rec.get(k) for k in ("route", "scopes", "stored_at", "expires_at")}

    def _decrypt(self, user_id: str, app: str) -> tuple[str, Optional[float]]:
        """Internal: decrypt the at-rest token. Callers outside this module must go
        through TokenBroker so the plaintext stays wrapped in a SecretToken."""
        rec = self._load_file(user_id).get(app)
        if rec is None:
            raise TokenNotFound(f"{user_id} has not connected {app}")
        master = _master_key()
        value = _open(rec["sealed"], master, self._aad(user_id, app))
        return value, rec.get("expires_at")

    def revoke(self, user_id: str, app: str) -> bool:
        blob = self._load_file(user_id)
        if app not in blob:
            return False
        del blob[app]
        self._write_file(user_id, blob)
        return True


# --------------------------------------------------------------------------- #
# TokenBroker — the NON-LLM gate to the plaintext.
# --------------------------------------------------------------------------- #
class TokenBroker:
    """Plain-Python broker the LLM cannot call. get_token decrypts and hands back a
    short-lived SecretToken; the non-LLM connector reveals it only at the auth
    handshake. The broker never logs, prints, or returns a raw token string."""

    def __init__(self, vault: TokenVault, *, lease_ttl_s: float = _DEFAULT_TTL_S) -> None:
        self._vault = vault
        self._lease_ttl_s = lease_ttl_s

    def get_token(self, user_id: str, app: str) -> SecretToken:
        value, at_rest_expiry = self._vault._decrypt(user_id, app)
        lease_expiry = time.time() + self._lease_ttl_s
        # the lease is the SOONER of the stored expiry and the broker's short lease
        expires_at = lease_expiry if at_rest_expiry is None else min(lease_expiry, at_rest_expiry)
        return SecretToken(value, app=app, user_id=user_id, expires_at=expires_at)


# --------------------------------------------------------------------------- #
# ConnectorRegistry — dispatch on the stored route.
# --------------------------------------------------------------------------- #
class ConnectorRegistry:
    """Maps each (user_id, app) to the arm that services it: api / browser / voice_text.
    The route is whatever the user stored with their token, so one user's niche CRM
    can go through the browser arm while another's Gmail goes through the api arm.
    Handlers are injected (kept out of this foundation slice); resolve() tells the
    caller which arm + hands back the broker lease the arm needs."""

    def __init__(self, vault: TokenVault, broker: Optional[TokenBroker] = None) -> None:
        self.vault = vault
        self.broker = broker or TokenBroker(vault)
        self._handlers: Dict[str, object] = {}

    def register_route(self, route: str, handler: object) -> None:
        if route not in VALID_ROUTES:
            raise VaultError(f"unknown route {route!r}")
        self._handlers[route] = handler

    def route_for(self, user_id: str, app: str) -> str:
        return self.vault.route_of(user_id, app)

    def resolve(self, user_id: str, app: str) -> dict:
        """Return the dispatch decision for this user's app: the route, the registered
        handler (if any), and a short-lived SecretToken lease. The caller (a non-LLM
        connector) reveals the token only at the moment of the real call."""
        route = self.vault.route_of(user_id, app)
        return {
            "route": route,
            "handler": self._handlers.get(route),
            "token": self.broker.get_token(user_id, app),
            "metadata": self.vault.metadata(user_id, app),
        }
