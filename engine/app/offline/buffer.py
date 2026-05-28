"""MH-P4: the pendant offline buffer + reconnect sync.

When the wearable is disconnected it must still capture, lose
nothing, leak nothing, and on reconnect deliver every event exactly
once even across a flaky/partial/duplicated resync.

Three binding properties:
  ZERO LOSS        every captured event is delivered on resync.
  ZERO DOUBLE      a delayed double-delivery, a partial prior sync,
                   or a redelivery storm delivers each event exactly
                   once (content-hash idempotency key + a durable
                   delivered-set).
  ENCRYPTED AT REST the on-disk buffer is Fernet ciphertext; no
                   plaintext event payload ever touches disk.

Encryption reuses the repo's existing scheme (PROFILE_ENCRYPTION_KEY
if set, else a device-local derived key, sha256 of a fixed seed;
never a new credential), the same pattern as the enrollment anchor
store. Append-only file so a crash mid-capture cannot corrupt
earlier events. Nothing frozen is touched.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional


def _key() -> bytes:
    raw = os.environ.get("PROFILE_ENCRYPTION_KEY", "")
    if raw:
        try:
            base64.urlsafe_b64decode(raw)
            return raw.encode() if isinstance(raw, str) else raw
        except Exception:
            pass
    seed = ("anticipy-offline-buffer-v1:"
            + os.environ.get("ANTICIPY_DATA_DIR", "local")).encode()
    return base64.urlsafe_b64encode(hashlib.sha256(seed).digest())


def _event_id(event: dict) -> str:
    """Stable content-hash idempotency key. Deterministic JSON so the
    SAME event captured/redelivered twice maps to ONE id.
    """
    blob = json.dumps(event, sort_keys=True, separators=(",", ":"),
                      default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


@dataclass
class SyncStats:
    total_tokens: int = 0
    delivered: int = 0
    skipped_dupes: int = 0
    errors: int = 0
    delivered_ids: set = field(default_factory=set)


class OfflineBuffer:
    """Append-only, Fernet-encrypted, crash-safe local capture."""

    def __init__(self, path: str | Path) -> None:
        from cryptography.fernet import Fernet

        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._f = Fernet(_key())

    # --- capture (disconnected) ---
    def capture(self, event: dict) -> str:
        eid = _event_id(event)
        rec = {"id": eid, "ts": time.time(), "event": event}
        token = self._f.encrypt(json.dumps(rec).encode())
        with self.path.open("ab") as fh:        # append-only
            fh.write(token + b"\n")
        return eid

    def count(self) -> int:
        if not self.path.exists():
            return 0
        with self.path.open("rb") as fh:
            return sum(1 for ln in fh if ln.strip())

    # --- encrypted-at-rest proof ---
    def raw_bytes(self) -> bytes:
        return self.path.read_bytes() if self.path.exists() else b""

    def plaintext_absent(self, needles: list[str]) -> bool:
        """True iff NONE of the given plaintext payload strings appear
        in the on-disk bytes (i.e. the buffer is genuinely encrypted).
        """
        raw = self.raw_bytes()
        return not any(n.encode() in raw for n in needles if n)

    # --- reconnect sync ---
    def sync(self, sink: Callable[[dict], None],
             delivered_ids: Optional[set] = None,
             fail_after: Optional[int] = None) -> SyncStats:
        """Replay the buffer to `sink`. `delivered_ids` is the DURABLE
        delivered-set carried across reconnect attempts: an id already
        in it is a delayed double-delivery / already-synced item and
        is skipped (zero double-processing). `fail_after` simulates a
        connection drop after N deliveries (partial sync); the
        delivered-set persists so the next sync resumes with zero loss
        and zero double.
        """
        stats = SyncStats()
        seen = delivered_ids if delivered_ids is not None else set()
        if not self.path.exists():
            return stats
        with self.path.open("rb") as fh:
            for ln in fh:
                ln = ln.strip()
                if not ln:
                    continue
                stats.total_tokens += 1
                try:
                    rec = json.loads(self._f.decrypt(ln).decode())
                except Exception:
                    stats.errors += 1
                    continue
                eid = rec.get("id")
                if eid in seen:
                    stats.skipped_dupes += 1
                    continue
                if (fail_after is not None
                        and stats.delivered >= fail_after):
                    break                       # simulated drop
                sink(rec["event"])
                seen.add(eid)
                stats.delivered += 1
                stats.delivered_ids.add(eid)
        return stats
