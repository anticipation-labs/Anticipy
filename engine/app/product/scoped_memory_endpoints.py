"""FastAPI router for the V7 scoped memory wrapper.

Endpoints: provision, write, read, seed, diag. This router does NOT
touch frozen memory; it is the canonical product write/read surface.

Partition fix: ``user_id`` is accepted as a synonym for ``account_id``
on every endpoint. A write keyed under ``user_id`` is readable under
``account_id`` and vice versa. This is the V7 memory partition seam.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.product.scoped_memory import (
    KIND_ALIAS,
    KIND_DO_NOT_TOUCH,
    KIND_PERSON,
    KIND_PREFERENCE,
    ScopedMemory,
)

router = APIRouter()


def _resolve_partition(
    account_id: Optional[str], user_id: Optional[str] = None,
) -> str:
    """``account_id`` and ``user_id`` resolve to the same partition.

    See ``dossier_endpoints._resolve_partition`` for the rationale.
    Whichever the caller passes lands in the same ScopedMemory file.
    """
    a = (account_id or "").strip()
    u = (user_id or "").strip()
    return a or u


def _scope(account_id: str, device_id: str) -> ScopedMemory:
    if not account_id or not device_id:
        raise HTTPException(
            status_code=400,
            detail=("account_id (or user_id) and device_id are "
                    "required"),
        )
    return ScopedMemory(account_id=account_id, device_id=device_id)


class ProvisionBody(BaseModel):
    account_id: Optional[str] = None
    user_id: Optional[str] = None
    device_id: str
    build_id: Optional[str] = None
    site_url: Optional[str] = None


@router.post("/api/memory/provision")
def memory_provision(body: ProvisionBody) -> JSONResponse:
    partition = _resolve_partition(body.account_id, body.user_id)
    scope = _scope(partition, body.device_id)
    scope.dir.mkdir(parents=True, exist_ok=True)
    scope.write(
        kind="provision", key="namespace", value=str(scope.path),
        source="provision_endpoint", provenance="api_call",
        extra={"build_id": body.build_id or "",
               "site_url": body.site_url or ""},
    )
    return JSONResponse({
        "ok": True,
        "namespace": str(scope.dir),
        "memory_path": str(scope.path),
        "diag": scope.diag(),
    })


class WriteBody(BaseModel):
    account_id: Optional[str] = None
    user_id: Optional[str] = None
    device_id: str
    kind: str
    key: str
    value: str
    source: Optional[str] = "product_runtime"
    provenance: Optional[str] = "api_write"
    confidence: Optional[float] = 1.0
    extra: Optional[dict[str, Any]] = None
    dedupe: Optional[bool] = True


@router.post("/api/memory/write")
def memory_write(body: WriteBody) -> JSONResponse:
    partition = _resolve_partition(body.account_id, body.user_id)
    scope = _scope(partition, body.device_id)
    item = scope.write(
        kind=body.kind, key=body.key, value=body.value,
        source=body.source or "product_runtime",
        provenance=body.provenance or "api_write",
        confidence=float(body.confidence or 1.0),
        extra=dict(body.extra or {}),
        dedupe=bool(body.dedupe if body.dedupe is not None else True),
    )
    return JSONResponse({"ok": True, "item": item.to_dict()})


@router.get("/api/memory/read")
def memory_read(
    account_id: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    device_id: str = Query(...),
    kind: Optional[str] = Query(None),
    key: Optional[str] = Query(None),
    active_only: bool = Query(True),
) -> JSONResponse:
    partition = _resolve_partition(account_id, user_id)
    scope = _scope(partition, device_id)
    items = scope.read(kind=kind, key=key, active_only=active_only)
    return JSONResponse({"ok": True, "items": items, "count": len(items),
                         "account_id": partition, "user_id": partition})


class SeedPerson(BaseModel):
    name: str
    email: Optional[str] = None
    role: Optional[str] = None
    gender: Optional[str] = None


class SeedPreference(BaseModel):
    key: str
    value: str


class SeedAlias(BaseModel):
    alias: str
    target: str


class SeedBody(BaseModel):
    account_id: Optional[str] = None
    user_id: Optional[str] = None
    device_id: str
    people: Optional[list[SeedPerson]] = None
    preferences: Optional[list[SeedPreference]] = None
    aliases: Optional[list[SeedAlias]] = None
    do_not_touch: Optional[list[str]] = None
    source: Optional[str] = "dossier_seed"


@router.post("/api/memory/seed")
def memory_seed(body: SeedBody) -> JSONResponse:
    partition = _resolve_partition(body.account_id, body.user_id)
    scope = _scope(partition, body.device_id)
    src = body.source or "dossier_seed"
    written = {"people": 0, "preferences": 0,
               "aliases": 0, "do_not_touch": 0}
    for p in body.people or []:
        if not p.name:
            continue
        scope.write(
            kind=KIND_PERSON, key=p.name,
            value=p.email or p.name,
            source=src, provenance="seed",
            extra={"email": p.email or "", "role": p.role or "",
                   "gender": (p.gender or "").lower()},
        )
        written["people"] += 1
    for pref in body.preferences or []:
        if not pref.key:
            continue
        scope.write(kind=KIND_PREFERENCE, key=pref.key,
                    value=pref.value or "",
                    source=src, provenance="seed")
        written["preferences"] += 1
    for al in body.aliases or []:
        if not al.alias or not al.target:
            continue
        scope.write(kind=KIND_ALIAS, key=al.alias, value=al.target,
                    source=src, provenance="seed")
        written["aliases"] += 1
    for dnt in body.do_not_touch or []:
        if not dnt:
            continue
        scope.write(kind=KIND_DO_NOT_TOUCH, key=str(dnt),
                    value=str(dnt), source=src, provenance="seed")
        written["do_not_touch"] += 1
    return JSONResponse({"ok": True, "written": written,
                         "diag": scope.diag()})


@router.get("/api/memory/diag")
def memory_diag(
    account_id: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    device_id: str = Query(...),
) -> JSONResponse:
    partition = _resolve_partition(account_id, user_id)
    scope = _scope(partition, device_id)
    return JSONResponse({"ok": True, **scope.diag(),
                         "user_id": partition})
