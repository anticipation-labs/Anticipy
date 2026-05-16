"""Mem0 style per user memory with the ADD / UPDATE / DELETE / NOOP
reconciliation primitive, plus reference resolution against memory and
the profile seam.

Why a reconciliation primitive and not an append log: when the WEARER
says "actually never mind" the prior latent intent must be removed, not
duplicated; when they refine ("make that 8pm not 7") the prior intent
must be updated in place. Mem0's insight is that a model compares a new
candidate against the existing relevant memory and decides exactly one
of ADD (genuinely new), UPDATE (refines or corrects an existing entry),
DELETE (retracts an existing entry), or NOOP (already known or not worth
storing). That decision is the primitive everything else builds on.

Storage is portable per user JSONL under the adapter data dir, the same
shape local and at the multi tenant scale. Memory unavailable or corrupt
degrades safely: references that need memory become ASK, never a guessed
ACT (build spec section 8).
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from app.anticipy import platform_adapter

_lock = threading.Lock()


def _path(user_id: str):
    return platform_adapter.user_data_dir(user_id) / "memory.jsonl"


@dataclass
class MemoryEntry:
    mem_id: str
    kind: str          # latent_intent | preference | aversion | contact | fact | anchor
    key: str           # short stable id, e.g. "usual place"
    value: str
    evidence: str
    ts: float
    active: bool = True

    def to_dict(self) -> dict:
        return {
            "mem_id": self.mem_id, "kind": self.kind, "key": self.key,
            "value": self.value, "evidence": self.evidence, "ts": self.ts,
            "active": self.active,
        }


def _load(user_id: str) -> list[MemoryEntry]:
    p = _path(user_id)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
            out.append(MemoryEntry(**d))
        except Exception:
            continue
    return out


def _save(user_id: str, entries: list[MemoryEntry]) -> None:
    p = _path(user_id)
    with p.open("w", encoding="utf-8") as fh:
        for e in entries:
            fh.write(json.dumps(e.to_dict(), ensure_ascii=False) + "\n")


def reset(user_id: str) -> None:
    with _lock:
        p = _path(user_id)
        if p.exists():
            p.unlink()


def seed(user_id: str, anchors: dict[str, str], kind: str = "anchor") -> None:
    """Test and onboarding helper: install known anchors (the usual
    place, our spot, the boss) so reference resolution has something to
    resolve against. In production the onboarding profile and accrued
    memory fill this; here it is the controllable equivalent.
    """
    with _lock:
        entries = _load(user_id)
        for k, v in anchors.items():
            entries.append(MemoryEntry(
                mem_id=f"seed-{k}-{int(time.time()*1000)%100000}",
                kind=kind, key=k, value=v, evidence="seeded", ts=time.time(),
            ))
        _save(user_id, entries)


def active_snapshot(user_id: str) -> list[dict]:
    return [e.to_dict() for e in _load(user_id) if e.active]


def add_latent(user_id: str, text: str) -> str:
    """Directly register a latent intent (deterministic, not model
    gated). Used when a STORE_AS_LATENT decision is made and as the
    setup half of the nevermind ADD then DELETE reconciliation test.
    """
    with _lock:
        entries = _load(user_id)
        mem_id = f"latent-{int(time.time()*1000)}-{len(entries)}"
        entries.append(MemoryEntry(
            mem_id=mem_id, kind="latent_intent", key=text[:40],
            value=text, evidence=text, ts=time.time(),
        ))
        _save(user_id, entries)
    return mem_id


def has_active_matching(user_id: str, gist: str) -> bool:
    g = gist.strip().lower()
    if not g:
        return False
    for e in _load(user_id):
        if e.active and e.kind == "latent_intent" and g[:24] in e.value.lower():
            return True
    return False


_RECONCILE_SYS = """\
You maintain a user's long term memory. Given the existing relevant
memory entries and one new candidate observation, choose EXACTLY ONE
reconciliation operation:

  ADD    the candidate is genuinely new information worth keeping.
  UPDATE the candidate refines or corrects an existing entry (give the
         mem_id it updates and the new value).
  DELETE the candidate retracts or cancels an existing entry (a "never
         mind", "forget that", "cancel that"); give the mem_id removed.
  NOOP   already known, or not worth storing, or no actionable content.

Return STRICT JSON only:
{"op":"ADD|UPDATE|DELETE|NOOP","mem_id":"<id or "">","value":"<value or "">","reason":"<short>"}
"""


@dataclass
class ReconcileResult:
    op: str
    mem_id: str
    value: str
    reason: str


async def reconcile(user_id: str, candidate_kind: str, candidate_text: str) -> ReconcileResult:
    """Mem0 style: a model decides ADD/UPDATE/DELETE/NOOP for the
    candidate against existing active memory, then the op is applied.
    Fails safe to NOOP (never silently corrupts memory).
    """
    with _lock:
        entries = _load(user_id)
    active = [e for e in entries if e.active]
    existing_repr = json.dumps(
        [{"mem_id": e.mem_id, "kind": e.kind, "key": e.key, "value": e.value} for e in active],
        ensure_ascii=False,
    )
    user = (
        f"EXISTING ACTIVE MEMORY:\n{existing_repr}\n\n"
        f"NEW CANDIDATE (kind={candidate_kind}): {candidate_text}\n\n"
        "Return the JSON object now."
    )
    res = await asyncio.to_thread(
        platform_adapter.model_call, _RECONCILE_SYS, user, 300, 0.0, False
    )
    op, mem_id, value, reason = "NOOP", "", "", "reconcile_default"
    if res.ok:
        s = res.content
        a, b = s.find("{"), s.rfind("}")
        if a != -1 and b != -1 and b > a:
            try:
                p = json.loads(s[a : b + 1])
                if p.get("op") in {"ADD", "UPDATE", "DELETE", "NOOP"}:
                    op = p["op"]
                    mem_id = str(p.get("mem_id", ""))
                    value = str(p.get("value", ""))
                    reason = str(p.get("reason", ""))[:160]
            except Exception:
                pass

    with _lock:
        entries = _load(user_id)
        if op == "ADD":
            entries.append(MemoryEntry(
                mem_id=f"m-{int(time.time()*1000)}",
                kind=candidate_kind, key=candidate_text[:40],
                value=candidate_text, evidence=candidate_text,
                ts=time.time(),
            ))
        elif op == "UPDATE":
            for e in entries:
                if e.mem_id == mem_id:
                    e.value = value or candidate_text
                    e.ts = time.time()
        elif op == "DELETE":
            for e in entries:
                if e.mem_id == mem_id:
                    e.active = False
        _save(user_id, entries)
    return ReconcileResult(op, mem_id, value, reason)


_RESOLVE_SYS = """\
You resolve a vague reference in a task against the user's known memory
and profile anchors. Return STRICT JSON only:
{"resolved": true|false, "value": "<the concrete resolved value or "">",
 "confidence": 0.0, "reason": "<short>"}
Only set resolved true with a value if a specific anchor clearly
matches. If nothing matches, resolved=false. Do not invent a value.
"""


@dataclass
class ResolveResult:
    resolved: bool
    value: str
    confidence: float
    reason: str


async def resolve_reference(
    user_id: str, reference_text: str, profile=None
) -> ResolveResult:
    """Resolve a reference ("the usual place", "the boss", "our spot")
    against active memory plus the profile people and anchors. Returns
    confidence; the caller treats >= 0.70 as resolved. On any failure
    returns unresolved so the caller ASKs rather than guesses an ACT.
    """
    try:
        with _lock:
            active = [e for e in _load(user_id) if e.active]
    except Exception:
        return ResolveResult(False, "", 0.0, "memory_unavailable")

    anchors = [{"key": e.key, "value": e.value} for e in active]
    if profile is not None:
        for rel, who in (getattr(profile, "people", {}) or {}).items():
            anchors.append({"key": rel, "value": who})
    if not anchors:
        return ResolveResult(False, "", 0.0, "no_anchors")

    user = (
        f"KNOWN ANCHORS:\n{json.dumps(anchors, ensure_ascii=False)}\n\n"
        f"REFERENCE TO RESOLVE: {reference_text}\n\nReturn the JSON now."
    )
    res = await asyncio.to_thread(
        platform_adapter.model_call, _RESOLVE_SYS, user, 256, 0.0, False
    )
    if not res.ok:
        return ResolveResult(False, "", 0.0, "resolve_model_failed")
    s = res.content
    a, b = s.find("{"), s.rfind("}")
    if a == -1 or b == -1 or b <= a:
        return ResolveResult(False, "", 0.0, "resolve_no_json")
    try:
        p = json.loads(s[a : b + 1])
    except Exception:
        return ResolveResult(False, "", 0.0, "resolve_bad_json")
    return ResolveResult(
        resolved=bool(p.get("resolved")) and bool(p.get("value")),
        value=str(p.get("value", "")),
        confidence=float(p.get("confidence", 0.0) or 0.0),
        reason=str(p.get("reason", ""))[:160],
    )
