"""Owner onboarding contract.

Onboarding is not a separate product. It is the first memory write that tells the
Action Engine who the owner is, who matters, which apps/accounts exist, and what
still needs connection before actions can run.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ConnectionStatus = Literal["connected", "needs_auth", "needs_setup", "unavailable", "unknown"]
ConnectionRoute = Literal["api", "browser", "voice_text", "memory"]


class OwnerPersonIn(BaseModel):
    name: str
    relationship: str = ""
    notes: str = ""
    channels: list[str] = Field(default_factory=list)


class OwnerConnectionIn(BaseModel):
    name: str
    status: ConnectionStatus = "unknown"
    route: ConnectionRoute = "api"
    identifier: str = ""
    notes: str = ""


class OwnerStoreIn(BaseModel):
    name: str
    url: str = ""
    notes: str = ""
    route: ConnectionRoute = "browser"


class OwnerOnboardingIn(BaseModel):
    owner_name: str = ""
    timezone: str = ""
    phone: str = ""
    email: str = ""
    preferences: list[str] = Field(default_factory=list)
    people: list[OwnerPersonIn] = Field(default_factory=list)
    connections: list[OwnerConnectionIn] = Field(default_factory=list)
    stores: list[OwnerStoreIn] = Field(default_factory=list)
    raw_notes: str = ""
    source: str = "onboarding"


class OwnerOnboardingMemory(BaseModel):
    drawer: Literal["profile", "open_loops"]
    text: str
    fields: dict
    status: str
    confidence: float = 1.0
    importance: float = 0.8


class OwnerOnboardingPlan(BaseModel):
    source: str
    memories: list[OwnerOnboardingMemory]
    missing_connections: list[str]


def _nonempty(value: str) -> str:
    return " ".join((value or "").split())


def build_onboarding_plan(body: OwnerOnboardingIn) -> OwnerOnboardingPlan:
    memories: list[OwnerOnboardingMemory] = []
    missing: list[str] = []
    source = body.source or "onboarding"

    profile_fields = {"source": source, "kind": "owner_identity"}
    identity_bits = []
    if _nonempty(body.owner_name):
        identity_bits.append(f"name: {_nonempty(body.owner_name)}")
        profile_fields["owner_name"] = _nonempty(body.owner_name)
    if _nonempty(body.timezone):
        identity_bits.append(f"timezone: {_nonempty(body.timezone)}")
        profile_fields["timezone"] = _nonempty(body.timezone)
    if _nonempty(body.phone):
        identity_bits.append(f"phone: {_nonempty(body.phone)}")
        profile_fields["phone"] = _nonempty(body.phone)
    if _nonempty(body.email):
        identity_bits.append(f"email: {_nonempty(body.email)}")
        profile_fields["email"] = _nonempty(body.email)
    if identity_bits:
        memories.append(OwnerOnboardingMemory(
            drawer="profile",
            text="Owner identity: " + "; ".join(identity_bits),
            fields=profile_fields,
            status="active",
            importance=0.95,
        ))

    for pref in body.preferences:
        pref = _nonempty(pref)
        if not pref:
            continue
        memories.append(OwnerOnboardingMemory(
            drawer="profile",
            text=f"Owner preference: {pref}",
            fields={"source": source, "kind": "preference", "preference": pref},
            status="active",
            importance=0.75,
        ))

    for person in body.people:
        name = _nonempty(person.name)
        if not name:
            continue
        bits = [name]
        if _nonempty(person.relationship):
            bits.append(f"relationship: {_nonempty(person.relationship)}")
        if person.channels:
            bits.append("channels: " + ", ".join(_nonempty(c) for c in person.channels if _nonempty(c)))
        if _nonempty(person.notes):
            bits.append(f"notes: {_nonempty(person.notes)}")
        memories.append(OwnerOnboardingMemory(
            drawer="profile",
            text="Important person: " + "; ".join(bits),
            fields={
                "source": source,
                "kind": "person",
                "name": name,
                "relationship": _nonempty(person.relationship),
                "channels": [_nonempty(c) for c in person.channels if _nonempty(c)],
                "notes": _nonempty(person.notes),
            },
            status="active",
            importance=0.9,
        ))

    for conn in body.connections:
        name = _nonempty(conn.name)
        if not name:
            continue
        fields = {
            "source": source,
            "kind": "app_connection",
            "name": name,
            "status": conn.status,
            "route": conn.route,
            "identifier": _nonempty(conn.identifier),
            "notes": _nonempty(conn.notes),
        }
        memories.append(OwnerOnboardingMemory(
            drawer="profile",
            text=f"App connection: {name}; status: {conn.status}; route: {conn.route}",
            fields=fields,
            status="active",
            importance=0.82,
        ))
        if conn.status != "connected":
            missing.append(name)
            memories.append(OwnerOnboardingMemory(
                drawer="open_loops",
                text=f"Connect {name} for Owner Action Engine",
                fields={**fields, "disposition": "blocked", "action": "connect_account"},
                status="waiting",
                confidence=0.95,
                importance=0.9,
            ))

    for store in body.stores:
        name = _nonempty(store.name)
        if not name:
            continue
        memories.append(OwnerOnboardingMemory(
            drawer="profile",
            text=f"Common store/account: {name}" + (f"; url: {_nonempty(store.url)}" if _nonempty(store.url) else ""),
            fields={
                "source": source,
                "kind": "store_account",
                "name": name,
                "url": _nonempty(store.url),
                "route": store.route,
                "notes": _nonempty(store.notes),
            },
            status="active",
            importance=0.7,
        ))

    notes = _nonempty(body.raw_notes)
    if notes:
        memories.append(OwnerOnboardingMemory(
            drawer="profile",
            text=f"Onboarding notes: {notes}",
            fields={"source": source, "kind": "raw_onboarding_notes"},
            status="active",
            confidence=0.85,
            importance=0.65,
        ))

    return OwnerOnboardingPlan(source=source, memories=memories, missing_connections=missing)
