"""Durable local-to-Supabase memory sync (V7).

Per plan section 6 task 7: move fire-and-forget hosted memory writes
to awaited writes or a durable outbox. This module is the outbox.

Items land in ``~/.anticipy/v7/memory_outbox.jsonl`` (append-only).
A background worker reads pending lines, POSTs to the appropriate
Supabase PostgREST table, then appends an ack record to
``memory_outbox.ack.jsonl``. Failed shipments retry with exponential
backoff up to a max attempt count, then quarantine so the worker
does not loop on poisoned rows. HTTP transport is stdlib ``urllib``
so we add no new dependency. If ``SUPABASE_URL`` is unset the worker
silently no-ops, allowing local-only setups to keep working.
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


_OUTBOX_DIR = Path.home() / ".anticipy" / "v7"
_OUTBOX_PATH = _OUTBOX_DIR / "memory_outbox.jsonl"
_ACK_PATH = _OUTBOX_DIR / "memory_outbox.ack.jsonl"

# Map an item's "kind" to a Supabase table. Anything not mapped lands
# in anticipy_memory (the general-purpose memory table). Aliases for
# the four canonical tables per plan section 6.
_KIND_TABLE: dict[str, str] = {
    "preference": "anticipy_preferences",
    "preferences": "anticipy_preferences",
    "profile": "anticipy_user_profile",
    "user_profile": "anticipy_user_profile",
    "anticipy_user_profile": "anticipy_user_profile",
    "dossier": "dossiers",
    "dossiers": "dossiers",
}
_DEFAULT_TABLE = "anticipy_memory"

# Retry policy.
_MAX_RETRIES = 5
_BASE_BACKOFF_SECONDS = 0.5
_WORKER_TICK_SECONDS = 0.25
_HTTP_TIMEOUT_SECONDS = 8.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_table(kind: str) -> str:
    return _KIND_TABLE.get(str(kind or "").strip().lower(), _DEFAULT_TABLE)


# Per the 20260523_onboarding_dossiers migration, the dossiers table has
# exactly these columns. Anything else PostgREST rejects with PGRST204
# ("Could not find the X column"). Keep this in lockstep with the SQL.
_DOSSIERS_COLUMNS: tuple[str, ...] = (
    "user_id", "profile", "pronoun_map", "people", "do_not_touch",
    "source", "field_count", "updated_at",
)


def _row_for_dossiers(item: dict) -> Optional[dict]:
    """Coerce an outbox item into the dossiers-table row shape.

    The producer enqueues an envelope like::

        {"kind": "dossier", "item_id": "...", "account_id": "<uid>",
         "user_id": "<uid>", "dossier": { ...merged on-disk dossier... },
         "source": "local_engine"}

    The dossiers table primary key is ``user_id`` (text), so we prefer
    the explicit ``user_id`` field; if missing we fall back to
    ``account_id`` since they are V7 synonyms. The structured columns
    pull from the merged ``dossier`` sub-dict; everything else lands in
    ``profile`` so no data is silently dropped.

    Returns None when no user_id can be resolved; the caller treats
    that as a non-shippable row.
    """
    user_id = str(item.get("user_id") or item.get("account_id") or "").strip()
    if not user_id:
        return None
    dossier = item.get("dossier")
    if not isinstance(dossier, dict):
        # The legacy path stored the dossier flat under the envelope.
        # Pull recognized fields from the envelope itself so older
        # outbox files still ship cleanly after the migration.
        dossier = {
            k: item[k] for k in (
                "profile", "pronoun_map", "people", "do_not_touch",
                "preferences", "recent_topics", "facts",
            ) if k in item
        }
    # Normalize the four jsonb sub-objects to their column types.
    people = dossier.get("people")
    if not isinstance(people, (dict, list)):
        people = {}
    pronoun_map = dossier.get("pronoun_map")
    if not isinstance(pronoun_map, dict):
        pronoun_map = {}
    do_not_touch = dossier.get("do_not_touch")
    if not isinstance(do_not_touch, (list, dict)):
        do_not_touch = []
    # "profile" gets every dossier key NOT mapped to its own column,
    # so the cloud row is a full snapshot. Strip envelope-only fields.
    structured_keys = {"people", "pronoun_map", "do_not_touch"}
    profile = {k: v for k, v in dossier.items() if k not in structured_keys}
    if not isinstance(profile, dict):
        profile = {}
    field_count = item.get("field_count")
    if not isinstance(field_count, int):
        try:
            field_count = int(field_count)
        except (TypeError, ValueError):
            # Default: count top-level keys in the merged dossier so
            # cloud row stats line up with on-disk shape.
            field_count = len(dossier) if isinstance(dossier, dict) else 0
    source = str(item.get("source") or "local_engine").strip() or "local_engine"
    updated_at = str(item.get("updated_at") or _now_iso())
    row = {
        "user_id": user_id,
        "profile": profile,
        "pronoun_map": pronoun_map,
        "people": people,
        "do_not_touch": do_not_touch,
        "source": source,
        "field_count": int(field_count),
        "updated_at": updated_at,
    }
    # Final guard: the row must contain only known columns. Any
    # accidental extra key would re-trigger PGRST204.
    return {k: row[k] for k in _DOSSIERS_COLUMNS if k in row}


def _row_for_table(table: str, item: dict) -> Optional[dict]:
    """Dispatch the per-table shape transform.

    For unmapped tables the item is shipped verbatim (the historical
    behavior). The dossiers table is the only one with a hard schema
    that mismatches the envelope, so it is the only one transformed
    today. Adding a new table-aware transform here is the seam.
    """
    if table == "dossiers":
        return _row_for_dossiers(item)
    # Default: ship the item but strip the outbox-internal envelope
    # keys so we never leak ``item_id``/``kind`` into a table that
    # does not have those columns.
    out = {k: v for k, v in item.items() if k not in ("item_id", "kind")}
    return out


def _allow_path_override() -> Optional[Path]:
    raw = os.environ.get("ANTICIPY_V7_MEMORY_OUTBOX_DIR", "").strip()
    if not raw:
        return None
    return Path(raw).expanduser()


class MemoryCloudSync:
    """Outbox-backed shipper from local memory to hosted Supabase.

    Cheap to construct. Call ``start_worker()`` once at attach time.
    Call ``enqueue(item)`` from any thread; it is non-blocking and
    durable across restarts.
    """

    def __init__(
        self,
        supabase_url: Optional[str] = None,
        supabase_service_role_key: Optional[str] = None,
        outbox_dir: Optional[Path] = None,
    ) -> None:
        self._url = (
            supabase_url
            if supabase_url is not None
            else os.environ.get("SUPABASE_URL", "")
        ).rstrip("/")
        self._key = (
            supabase_service_role_key
            if supabase_service_role_key is not None
            else (
                os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
                or os.environ.get("SUPABASE_SERVICE_KEY", "")
            )
        )
        base = outbox_dir or _allow_path_override() or _OUTBOX_DIR
        self._outbox_path = base / "memory_outbox.jsonl"
        self._ack_path = base / "memory_outbox.ack.jsonl"
        self._lock = threading.Lock()
        self._worker: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._running = threading.Event()
        # Track retry state in-memory only; persisted state is the
        # outbox + ack files. On restart, failed items just retry
        # from attempt 1 with a fresh backoff schedule.
        self._attempts: dict[str, int] = {}
        self._next_attempt_at: dict[str, float] = {}
        # Permanently quarantined item ids (>= _MAX_RETRIES failures
        # this process). Quarantined ids are written to the ack file
        # with a sentinel so they do not block pending_count.
        self._quarantined: set[str] = set()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def enqueue(self, memory_item: dict) -> str:
        """Append item to outbox. Non-blocking. Returns its item_id."""
        if not isinstance(memory_item, dict):
            raise TypeError("memory_item must be a dict")
        item = dict(memory_item)
        item_id = str(item.get("item_id") or "").strip()
        if not item_id:
            item_id = (
                f"outbox-{int(time.time() * 1000)}-"
                f"{os.getpid()}-{id(item) & 0xffff:04x}"
            )
            item["item_id"] = item_id
        line = json.dumps(item, ensure_ascii=False, sort_keys=True)
        with self._lock:
            self._outbox_path.parent.mkdir(parents=True, exist_ok=True)
            with self._outbox_path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        return item_id

    def start_worker(self) -> bool:
        """Spawn the background shipper thread. Idempotent.

        Returns True if a worker is now running, False if startup was
        skipped (no SUPABASE_URL, the no-op case).
        """
        if not self._url:
            # Local-only setup, no cloud configured. Silent no-op.
            return False
        with self._lock:
            if self._worker is not None and self._worker.is_alive():
                return True
            self._stop.clear()
            t = threading.Thread(
                target=self._worker_loop,
                name="anticipy-memory-cloud-sync",
                daemon=True,
            )
            self._worker = t
            t.start()
            # Block briefly so callers see ``worker_running`` true.
            self._running.wait(timeout=1.0)
        return True

    def stop_worker(self, timeout: float = 5.0) -> None:
        """Signal the worker to stop and join it."""
        self._stop.set()
        t = self._worker
        if t is not None and t.is_alive():
            t.join(timeout=timeout)
        self._running.clear()

    def pending_count(self) -> int:
        """Count items in the outbox that have no shipped ack."""
        shipped = self._load_acked_ids()
        total = 0
        for it in self._iter_outbox():
            iid = str(it.get("item_id") or "")
            if iid and iid in shipped:
                continue
            if iid and iid in self._quarantined:
                continue
            total += 1
        return total

    def last_shipped_at(self) -> Optional[str]:
        """ISO timestamp of the most recent ack, or None."""
        if not self._ack_path.exists():
            return None
        last: Optional[str] = None
        try:
            for line in self._ack_path.read_text(
                encoding="utf-8",
            ).splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                ts = rec.get("shipped_at")
                if ts and (last is None or str(ts) > last):
                    last = str(ts)
        except Exception:
            return None
        return last

    def worker_running(self) -> bool:
        t = self._worker
        return bool(t is not None and t.is_alive()
                    and self._running.is_set())

    def flush(self, max_seconds: float = 10.0) -> dict:
        """Force-flush pending items now, bypassing backoff."""
        if not self._url:
            return {"shipped": 0, "failed": 0,
                    "note": "supabase_url_unset"}
        deadline = time.time() + max(0.5, float(max_seconds))
        shipped = failed = 0
        seen: set[str] = set()
        while time.time() < deadline:
            pending = [
                it for it in self._snapshot_pending()
                if str(it.get("item_id") or "") not in seen
            ]
            if not pending:
                break
            for item in pending:
                if time.time() >= deadline:
                    break
                iid = str(item.get("item_id") or "")
                seen.add(iid)
                if self._ship_one(item):
                    self._record_ack(iid)
                    shipped += 1
                else:
                    failed += 1
        return {"shipped": shipped, "failed": failed,
                "pending_after": self.pending_count()}

    # ------------------------------------------------------------------
    # Worker internals
    # ------------------------------------------------------------------

    def _worker_loop(self) -> None:
        self._running.set()
        try:
            while not self._stop.is_set():
                try:
                    self._worker_tick()
                except Exception:
                    pass  # never crash on a single bad row
                self._stop.wait(timeout=_WORKER_TICK_SECONDS)
        finally:
            self._running.clear()

    def _worker_tick(self) -> None:
        now = time.time()
        for item in self._snapshot_pending():
            if self._stop.is_set():
                return
            iid = str(item.get("item_id") or "")
            if not iid or self._next_attempt_at.get(iid, 0.0) > now:
                continue
            if self._ship_one(item):
                self._record_ack(iid)
                self._attempts.pop(iid, None)
                self._next_attempt_at.pop(iid, None)
                continue
            n = self._attempts.get(iid, 0) + 1
            self._attempts[iid] = n
            if n >= _MAX_RETRIES:
                self._quarantined.add(iid)
                self._record_ack(iid, status="quarantined")
            else:
                self._next_attempt_at[iid] = (
                    time.time() + _BASE_BACKOFF_SECONDS * (2 ** (n - 1))
                )

    def _ship_one(self, item: dict) -> bool:
        """POST one item to its resolved table. True on 2xx or 409.

        Shape transform per table. The outbox stores envelope keys
        (``kind``, ``item_id``, ``account_id``, etc.) that PostgREST
        rejects because they are not real columns. ``_row_for_table``
        derives the on-disk row that matches the target table schema
        before serialization. The ``Prefer: resolution=merge-duplicates``
        header turns a re-write into a PostgreSQL upsert on the
        primary-key conflict, so a second flush updates the row instead
        of raising 409.
        """
        if not self._url:
            return False
        kind = item.get("kind")
        table = _resolve_table(kind)
        row = _row_for_table(table, item)
        if row is None:
            # Item shape cannot be coerced to this table. Treat as a
            # poison row so the worker quarantines it rather than
            # looping. Returning False makes the retry counter tick.
            return False
        url = f"{self._url}/rest/v1/{table}"
        payload = json.dumps([row], ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url, data=payload, method="POST",
            headers={
                "Content-Type": "application/json",
                "apikey": self._key or "",
                "Authorization": f"Bearer {self._key or ''}",
                # merge-duplicates upserts on PK conflict; return=minimal
                # avoids fetching the row back over the wire.
                "Prefer": (
                    "return=minimal,resolution=merge-duplicates"
                ),
            },
        )
        try:
            with urllib.request.urlopen(
                req, timeout=_HTTP_TIMEOUT_SECONDS,
            ) as r:
                try:
                    r.read()
                except Exception:
                    pass
                return 200 <= int(getattr(r, "status", 200)) < 300
        except urllib.error.HTTPError as exc:
            # 409 = unique-index collision: row exists, treat as ok.
            return getattr(exc, "code", 0) == 409
        except (urllib.error.URLError, TimeoutError, OSError):
            return False
        except Exception:
            return False

    # ------------------------------------------------------------------
    # File helpers
    # ------------------------------------------------------------------

    def _iter_jsonl(self, path: Path):
        if not path.exists():
            return
        try:
            with path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        yield json.loads(line)
                    except Exception:
                        continue
        except FileNotFoundError:
            return

    def _snapshot_pending(self) -> list[dict]:
        shipped = self._load_acked_ids()
        out: list[dict] = []
        for it in self._iter_jsonl(self._outbox_path):
            iid = str(it.get("item_id") or "")
            if not iid or iid in shipped or iid in self._quarantined:
                continue
            out.append(it)
        return out

    def _iter_outbox(self):
        return self._iter_jsonl(self._outbox_path)

    def _load_acked_ids(self) -> set[str]:
        return {
            str(rec.get("item_id") or "")
            for rec in self._iter_jsonl(self._ack_path)
            if rec.get("item_id")
        }

    def _record_ack(self, item_id: str, status: str = "shipped") -> None:
        rec = {
            "item_id": item_id,
            "shipped_at": _now_iso(),
            "status": status,
        }
        with self._lock:
            self._ack_path.parent.mkdir(parents=True, exist_ok=True)
            with self._ack_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


# ----------------------------------------------------------------------
# Process-singleton accessor. The router and server attach point both
# call get_sync() so they share the same outbox state.
# ----------------------------------------------------------------------

_SINGLETON_LOCK = threading.Lock()
_SINGLETON: Optional[MemoryCloudSync] = None


def get_sync() -> MemoryCloudSync:
    """Return the process-wide ``MemoryCloudSync`` instance."""
    global _SINGLETON
    with _SINGLETON_LOCK:
        if _SINGLETON is None:
            _SINGLETON = MemoryCloudSync()
        return _SINGLETON


def reset_singleton_for_tests() -> None:
    """Test-only: drop the singleton so a fresh instance can be built."""
    global _SINGLETON
    with _SINGLETON_LOCK:
        if _SINGLETON is not None:
            try:
                _SINGLETON.stop_worker(timeout=1.0)
            except Exception:
                pass
        _SINGLETON = None
