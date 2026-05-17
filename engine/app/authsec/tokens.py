"""MH-P5: auth + per-user isolation + token lifecycle.

Real lifecycle LOGIC, proven against a simulated identity provider;
the real OAuth network exchange (real Google/email credentials) is
the labelled gated edge, never faked.

Binding properties:
  PER-USER ISOLATION  a tenant accessor can ONLY read/write its own
    user's tokens and task state. A cross-tenant access returns
    nothing and is refused: no wrong-user data, ever (the app-layer
    equivalent of DB row-level security; real Supabase RLS is the
    wired edge).
  TOKEN-EXPIRY MID-ACTION  if the access token expires WHILE a task
    is running, the lifecycle detects it, refreshes via the refresh
    token, and the SAME task resumes from its durable checkpoint and
    completes EXACTLY ONCE: no lost task, no double execution, no
    wrong-user data.

Tokens are Fernet-encrypted at rest with the repo's existing key
scheme (PROFILE_ENCRYPTION_KEY else a device-derived sha256 seed;
never a new credential). Nothing frozen is modified.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from typing import Callable, Optional


def _key() -> bytes:
    raw = os.environ.get("PROFILE_ENCRYPTION_KEY", "")
    if raw:
        try:
            base64.urlsafe_b64decode(raw)
            return raw.encode() if isinstance(raw, str) else raw
        except Exception:
            pass
    seed = ("anticipy-authsec-v1:"
            + os.environ.get("ANTICIPY_DATA_DIR", "local")).encode()
    return base64.urlsafe_b64encode(hashlib.sha256(seed).digest())


class CrossTenantError(PermissionError):
    """Raised when one tenant attempts to touch another's data."""


@dataclass
class Token:
    user_id: str
    access: str
    refresh: str
    expires_at: float

    def expired(self, now: Optional[float] = None) -> bool:
        return (now or time.time()) >= self.expires_at


@dataclass
class TokenStore:
    """Per-user encrypted token vault. Keyed strictly by user_id; a
    read for a different user_id returns None (never another user's
    token).
    """
    _blob: dict = field(default_factory=dict)        # user_id -> ciphertext

    def _f(self):
        from cryptography.fernet import Fernet

        return Fernet(_key())

    def put(self, tok: Token) -> None:
        self._blob[tok.user_id] = self._f().encrypt(
            json.dumps(tok.__dict__).encode())

    def get(self, requesting_user: str, target_user: str
            ) -> Optional[Token]:
        if requesting_user != target_user:
            raise CrossTenantError(
                f"{requesting_user!r} may not read {target_user!r}")
        ct = self._blob.get(target_user)
        if not ct:
            return None
        return Token(**json.loads(self._f().decrypt(ct).decode()))

    def is_ciphertext(self, user_id: str, plaintext_needle: str) -> bool:
        ct = self._blob.get(user_id, b"")
        return bool(ct) and plaintext_needle.encode() not in ct


@dataclass
class TaskCheckpoint:
    task_id: str
    user_id: str
    step: int = 0
    done: bool = False
    result: Optional[str] = None
    runs: int = 0                                   # execution count


class DurableRuntime:
    """Minimal durable runtime: a task is a list of steps; a
    checkpoint persists progress so a mid-task token refresh resumes
    the SAME task instead of restarting it. Per-user isolated.
    """

    def __init__(self) -> None:
        self._cp: dict[tuple[str, str], TaskCheckpoint] = {}

    def checkpoint(self, requesting_user: str, user_id: str,
                   task_id: str) -> TaskCheckpoint:
        if requesting_user != user_id:
            raise CrossTenantError("cross-tenant checkpoint read")
        return self._cp.setdefault(
            (user_id, task_id),
            TaskCheckpoint(task_id=task_id, user_id=user_id))

    def run_task(self, user_id: str, task_id: str, steps: list,
                 store: TokenStore,
                 refresh_idp: Callable[[Token], Token]) -> TaskCheckpoint:
        """Execute `steps` for user_id. Each step needs a live token.
        If the token is expired the lifecycle refreshes (real logic;
        refresh_idp is the simulated IdP, the real OAuth call is the
        gated edge) and the task RESUMES from the persisted step, not
        from zero. Idempotent: an already-done task is not re-run.
        """
        cp = self.checkpoint(user_id, user_id, task_id)
        if cp.done:
            return cp                                # idempotent resume
        cp.runs += 1
        while cp.step < len(steps):
            tok = store.get(user_id, user_id)
            if tok is None:
                raise RuntimeError("no token for user")
            if tok.expired():
                fresh = refresh_idp(tok)            # real refresh logic
                if fresh.user_id != user_id:
                    raise CrossTenantError("refresh crossed users")
                store.put(fresh)
                continue                            # retry SAME step
            steps[cp.step](tok)                      # do the step
            cp.step += 1
        cp.done = True
        cp.result = f"completed {len(steps)} steps for {user_id}"
        return cp
