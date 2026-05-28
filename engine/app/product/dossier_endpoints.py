"""FastAPI router for the V7 dossier-active loader.

Routes:

  GET  /api/dossier/active?account_id=&device_id=
      Returns the structured dossier (people, preferences, do_not_touch,
      pronoun map, recent topics, source path). The query param
      ``user_id`` is accepted as a synonym for ``account_id`` so legacy
      callers do not need to be rewritten.

  POST /api/dossier/active
      Body: {"account_id": "...", "device_id": "...",
             "entry": { ... dossier fragment ... }}
      Merges the dossier fragment into the on-disk dossier file at the
      same path the GET reads from. Accepts ``user_id`` as a synonym
      for ``account_id``. Returns the post-write snapshot.

  POST /api/dossier/refresh
      Body: {"account_id": "...", "device_id": "..."}
      Re-reads the dossier from disk. Returns updated snapshot. Accepts
      ``user_id`` as a synonym for ``account_id``.

  GET  /api/dossier/context?account_id=&max_chars=2000
      Returns the as_context_block() output that the action planner
      prepends to its planning prompt. Accepts ``user_id`` as a synonym
      for ``account_id``.

Partition fix (V7 memory partition mismatch):

  The historical bug was that legacy writes used ``USER_ID`` (or the
  ``user_id`` field on the retired ``/api/dossier/write`` endpoint)
  while reads use ``account_id``. Both keys now resolve to the same
  ScopedMemory partition via the ``_resolve_partition`` helper, so a
  write keyed under ``user_id`` is readable under ``account_id`` and
  vice versa. The on-disk path that the GET reads from is the same
  path that POST writes to.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.product.dossier_active_loader import (
    DossierLoader,
    _candidate_paths,
    _dossier_root,
    _safe_id,
)


router = APIRouter()


def _enqueue_dossier_snapshot(
    account_id: str, merged: dict[str, Any],
) -> dict[str, Any]:
    """Mirror the post-merge dossier to the cloud-sync outbox.

    The disk write above already succeeded; this step is best-effort.
    A missing ``SUPABASE_URL`` leaves the outbox in no-op mode and the
    worker silently skips. A misbehaving outbox import (PyInstaller
    drops, circular imports during cold start) never propagates back
    to the caller because the dossier write contract is "disk first".

    Returns a small diagnostic dict so callers (and the verifier) can
    see whether enqueue actually happened.
    """
    try:
        from app.product.memory_cloud_sync import get_sync
    except Exception as exc:
        return {"enqueued": False, "reason": f"import_failed:{type(exc).__name__}"}
    try:
        sync = get_sync()
    except Exception as exc:
        return {"enqueued": False, "reason": f"singleton_failed:{type(exc).__name__}"}
    if not getattr(sync, "_url", ""):
        # Local-only setup. Honor the silent no-op contract.
        return {"enqueued": False, "reason": "supabase_url_unset"}
    safe_id = _safe_id(account_id)
    # The envelope: ``kind`` selects the table, ``user_id`` becomes the
    # PK, ``dossier`` carries the structured payload that the shipper
    # transforms into per-column values.
    envelope = {
        "kind": "dossier",
        "account_id": safe_id,
        "user_id": safe_id,
        "dossier": dict(merged or {}),
        "source": "local_engine",
        "field_count": len(merged or {}),
    }
    try:
        item_id = sync.enqueue(envelope)
        return {"enqueued": True, "item_id": item_id,
                "pending_count": int(sync.pending_count())}
    except Exception as exc:
        return {"enqueued": False,
                "reason": f"enqueue_failed:{type(exc).__name__}"}


def _resolve_partition(
    account_id: Optional[str], user_id: Optional[str] = None,
) -> str:
    """Normalize ``account_id`` and ``user_id`` to one partition key.

    The historical bug: legacy product code wrote under ``user_id`` and
    the M1 dossier loader read under ``account_id``. They are now
    synonyms. Whichever the caller passes, the same on-disk file is
    used. If both are given, ``account_id`` wins (it is the V7
    canonical name); if only ``user_id`` is given, it becomes the
    partition key. This translation is the partition-fix seam.
    """
    a = (account_id or "").strip()
    u = (user_id or "").strip()
    chosen = a or u
    if not chosen:
        raise HTTPException(
            status_code=400,
            detail="account_id (or user_id) is required",
        )
    return chosen


def _loader(account_id: str, device_id: str = "") -> DossierLoader:
    return DossierLoader(account_id=account_id, device_id=device_id)


def _writable_dossier_path(account_id: str) -> Path:
    """The canonical on-disk path the GET reads from for a write target.

    Mirrors ``_candidate_paths`` priority. Writes always land at the
    per-account location so reads see them deterministically.
    """
    return _dossier_root() / _safe_id(account_id) / "dossier.json"


def _merge_dossier_fragment(existing: dict, fragment: dict) -> dict:
    """Merge a fragment into an existing dossier with sensible rules.

    - Dict keys: shallow-merge (fragment wins on collision).
    - List keys: extend (dedupe simple strings).
    - Scalar keys: overwrite.
    """
    out = dict(existing or {})
    for k, v in (fragment or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            merged = dict(out[k])
            merged.update(v)
            out[k] = merged
        elif isinstance(v, list) and isinstance(out.get(k), list):
            prev = list(out[k])
            for item in v:
                if (isinstance(item, str)
                        and item in prev):
                    continue
                prev.append(item)
            out[k] = prev
        else:
            out[k] = v
    return out


@router.get("/api/dossier/active")
def dossier_active(
    account_id: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    device_id: str = Query(""),
) -> JSONResponse:
    partition = _resolve_partition(account_id, user_id)
    loader = _loader(partition, device_id)
    snap = loader.snapshot()
    snap["ok"] = True
    snap["loaded"] = loader.loaded_path is not None
    # Surface both names so legacy callers see what they expect.
    snap["user_id"] = snap.get("account_id", partition)
    return JSONResponse(snap)


class ActiveWriteBody(BaseModel):
    account_id: Optional[str] = None
    user_id: Optional[str] = None
    device_id: Optional[str] = ""
    entry: Optional[dict[str, Any]] = None
    # Legacy single-key/value shape used by /api/dossier/write callers.
    key: Optional[str] = None
    value: Optional[Any] = None


@router.post("/api/dossier/active")
def dossier_active_write(body: ActiveWriteBody) -> JSONResponse:
    partition = _resolve_partition(body.account_id, body.user_id)
    target = _writable_dossier_path(partition)
    target.parent.mkdir(parents=True, exist_ok=True)

    existing: dict = {}
    if target.exists():
        try:
            existing = json.loads(
                target.read_text(encoding="utf-8") or "{}",
            )
            if not isinstance(existing, dict):
                existing = {}
        except Exception:
            existing = {}

    fragment: dict[str, Any] = {}
    if body.entry and isinstance(body.entry, dict):
        fragment = dict(body.entry)
    elif body.key:
        # Legacy single-pair shape: {"key": "name", "value": "Omar"}
        # lands under existing["facts"][key] = value so the file shape
        # stays compatible with the dossier loader. The loader does not
        # require a "facts" key, but it is preserved verbatim by the
        # snapshot so a round-trip works.
        facts = dict(existing.get("facts") or {})
        facts[str(body.key)] = body.value
        fragment = {"facts": facts}

    if not fragment:
        raise HTTPException(
            status_code=400,
            detail=("entry (or key/value) is required to write a "
                    "dossier fragment"),
        )

    merged = _merge_dossier_fragment(existing, fragment)
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(tmp, target)

    # M3 cloud-sync producer. Disk is the source of truth; the outbox
    # mirrors the post-merge snapshot to Supabase so the row matches
    # what the loader will read back. Failure here never blocks the
    # write because the outbox is durable on its own filesystem.
    enqueue_result = _enqueue_dossier_snapshot(
        account_id=partition, merged=merged,
    )

    loader = _loader(partition, body.device_id or "")
    snap = loader.snapshot()
    snap["ok"] = True
    snap["written_path"] = str(target)
    snap["loaded"] = loader.loaded_path is not None
    snap["user_id"] = snap.get("account_id", partition)
    snap["raw"] = merged
    snap["cloud_sync"] = enqueue_result
    return JSONResponse(snap)


class RefreshBody(BaseModel):
    account_id: Optional[str] = None
    user_id: Optional[str] = None
    device_id: Optional[str] = ""


@router.post("/api/dossier/refresh")
def dossier_refresh(body: RefreshBody) -> JSONResponse:
    partition = _resolve_partition(body.account_id, body.user_id)
    loader = _loader(partition, body.device_id or "")
    ok = loader.refresh()
    snap = loader.snapshot()
    snap["ok"] = True
    snap["loaded"] = ok
    snap["user_id"] = snap.get("account_id", partition)
    return JSONResponse(snap)


@router.get("/api/dossier/context")
def dossier_context(
    account_id: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    device_id: str = Query(""),
    max_chars: int = Query(2000, ge=64, le=20000),
) -> JSONResponse:
    partition = _resolve_partition(account_id, user_id)
    loader = _loader(partition, device_id)
    block = loader.as_context_block(max_chars=int(max_chars))
    return JSONResponse({
        "ok": True,
        "account_id": loader.account_id,
        "user_id": loader.account_id,
        "device_id": loader.device_id,
        "loaded": loader.loaded_path is not None,
        "source_path": str(loader.loaded_path) if loader.loaded_path else "",
        "max_chars": int(max_chars),
        "length": len(block),
        "context": block,
    })


__all__ = ["router"]
