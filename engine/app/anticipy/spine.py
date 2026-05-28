"""The durable multi tenant spine.

One codebase, two form factors. The local single user form is the multi
tenant system with tenant count one. At scale it is one isolated engine
instance per user, storage per user partitioned, the SAME code. This
module is the per user isolation boundary that holds in both forms.

Isolation is enforced, not advisory. A user scoped client is bound to
exactly one user_id and physically cannot reach another user's
partition: a cross tenant read fails closed, returns nothing, never
another user's rows, ever. The service role client is a separate,
explicitly named object used only by migration and admin code, never by
engine decision logic, so engine code cannot reach across tenants even
by accident. This mirrors, in the local form, the database layer RLS
that enforces the same property at scale (see the committed Supabase
migration in engine/migrations and its RLS coverage validator).
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from typing import Any, Optional

from app.anticipy import platform_adapter

_lock = threading.Lock()
_conn: Optional[sqlite3.Connection] = None


def _db() -> sqlite3.Connection:
    global _conn
    if _conn is not None:
        return _conn
    path = platform_adapter.data_dir() / "spine.sqlite3"
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    # Every user data row carries its owning user_id. The scoped client
    # below ALWAYS constrains by it; there is no code path that selects
    # without the owner predicate, which is the local equivalent of a
    # row level security policy keyed on auth.uid().
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS user_rows (
            user_id   TEXT NOT NULL,
            table_ns  TEXT NOT NULL,
            row_key   TEXT NOT NULL,
            value_json TEXT NOT NULL,
            ts        REAL NOT NULL,
            PRIMARY KEY (user_id, table_ns, row_key)
        );
        CREATE TABLE IF NOT EXISTS vault (
            user_id  TEXT NOT NULL,
            opaque_key TEXT NOT NULL,
            secret_ref TEXT NOT NULL,
            scope    TEXT NOT NULL,
            read_only_context INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (user_id, opaque_key)
        );
        """
    )
    conn.commit()
    _conn = conn
    return conn


def reset_for_tests() -> None:
    global _conn
    with _lock:
        if _conn is not None:
            _conn.close()
            _conn = None


class CrossTenantError(RuntimeError):
    """Raised if engine code ever tries to read or write across the
    user boundary through a scoped client. Fail closed, never serve
    another tenant's data.
    """


class ScopedClient:
    """An RLS scoped client bound to ONE user. Every operation is
    constrained by self._uid. There is no method that can read another
    user's rows; attempting to pass a different user_id raises
    CrossTenantError rather than silently crossing tenants.
    """

    def __init__(self, user_id: str) -> None:
        if not user_id:
            raise CrossTenantError("scoped client requires a user_id")
        self._uid = user_id

    def put(self, table_ns: str, row_key: str, value: dict) -> None:
        with _lock:
            _db().execute(
                "INSERT OR REPLACE INTO user_rows VALUES (?,?,?,?,?)",
                (self._uid, table_ns, row_key, json.dumps(value), time.time()),
            )
            _db().commit()

    def get(self, table_ns: str, row_key: str, owner: Optional[str] = None) -> Optional[dict]:
        # owner is accepted only to PROVE isolation in tests: asking for
        # another user's row through this client is a hard error, not a
        # silent cross read.
        if owner is not None and owner != self._uid:
            raise CrossTenantError(
                f"scoped client for {self._uid} may not read rows owned by {owner}"
            )
        with _lock:
            r = _db().execute(
                "SELECT value_json FROM user_rows WHERE user_id=? AND table_ns=? AND row_key=?",
                (self._uid, table_ns, row_key),
            ).fetchone()
        return json.loads(r[0]) if r else None

    def list(self, table_ns: str) -> list[dict]:
        with _lock:
            rows = _db().execute(
                "SELECT value_json FROM user_rows WHERE user_id=? AND table_ns=?",
                (self._uid, table_ns),
            ).fetchall()
        return [json.loads(x[0]) for x in rows]

    def vault_put(self, opaque_key: str, secret_ref: str, scope: str, read_only_context: bool = True) -> None:
        with _lock:
            _db().execute(
                "INSERT OR REPLACE INTO vault VALUES (?,?,?,?,?)",
                (self._uid, opaque_key, secret_ref, scope, 1 if read_only_context else 0),
            )
            _db().commit()

    def vault_ref(self, opaque_key: str) -> Optional[dict]:
        with _lock:
            r = _db().execute(
                "SELECT secret_ref, scope, read_only_context FROM vault WHERE user_id=? AND opaque_key=?",
                (self._uid, opaque_key),
            ).fetchone()
        return {"secret_ref": r[0], "scope": r[1], "read_only_context": bool(r[2])} if r else None


class ServiceRoleClient:
    """Admin only, explicitly separate and named. Used by migration and
    isolation proofs, NEVER by engine decision logic. It can see all
    users on purpose, which is exactly why engine code must never hold
    one.
    """

    def raw_count(self, table_ns: str) -> int:
        with _lock:
            r = _db().execute(
                "SELECT COUNT(*) FROM user_rows WHERE table_ns=?", (table_ns,)
            ).fetchone()
        return int(r[0]) if r else 0

    def owners_of(self, table_ns: str) -> set:
        with _lock:
            rows = _db().execute(
                "SELECT DISTINCT user_id FROM user_rows WHERE table_ns=?", (table_ns,)
            ).fetchall()
        return {x[0] for x in rows}


def scoped_client(user_ctx: Any) -> ScopedClient:
    uid = getattr(user_ctx, "user_id", None) or (user_ctx if isinstance(user_ctx, str) else None)
    return ScopedClient(uid)


def service_role_client() -> ServiceRoleClient:
    return ServiceRoleClient()
