"""Deterministic workflow law for Anticipy.

Models may propose a goal, facts, or a reply.  They do not own state.  This
module is the one place that answers whether work may be approved, claimed,
retried, cancelled, or called complete.

The types are deliberately storage-neutral.  PocketBase jobs carry the same
fields in production, while tests and recovery tools can exercise the exact
state machine without a network or an LLM.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from enum import Enum
import hashlib
import json
import uuid
from typing import Any, Iterable, Mapping, Optional


class WorkflowViolation(ValueError):
    """A requested transition would break a product invariant."""


class PlanState(str, Enum):
    DRAFT = "draft"
    AWAITING_APPROVAL = "awaiting_approval"
    QUEUED = "queued"
    RUNNING = "running"
    NEEDS_USER = "needs_user"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Consequence(str, Enum):
    READ_ONLY = "read_only"
    CONSEQUENTIAL = "consequential"


TERMINAL_STATES = {
    PlanState.SUCCEEDED,
    PlanState.FAILED,
    PlanState.CANCELLED,
}

LEGACY_STATUS = {
    PlanState.DRAFT: "awaiting_confirm",
    PlanState.AWAITING_APPROVAL: "awaiting_confirm",
    PlanState.QUEUED: "queued",
    PlanState.RUNNING: "running",
    PlanState.NEEDS_USER: "needs_user",
    PlanState.SUCCEEDED: "done",
    PlanState.FAILED: "failed",
    PlanState.CANCELLED: "cancelled",
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _at(value: Optional[datetime]) -> datetime:
    value = value or utcnow()
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _clean_facts(facts: Optional[Mapping[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in dict(facts or {}).items():
        name = str(key).strip()
        if not name or value is None:
            continue
        if isinstance(value, str):
            value = value.strip()
            if not value:
                continue
        out[name] = value
    return out


@dataclass(frozen=True)
class Approval:
    plan_id: str
    plan_version: int
    scope_digest: str
    owner_words: str
    approved_at: datetime


@dataclass(frozen=True)
class Lease:
    token: str
    actor_id: str
    acquired_at: datetime
    expires_at: datetime
    attempt: int

    def live_at(self, now: Optional[datetime] = None) -> bool:
        return self.expires_at > _at(now)


@dataclass(frozen=True)
class Receipt:
    effect_key: str
    summary: str
    evidence: tuple[str, ...]
    verified: bool
    recorded_at: datetime


@dataclass(frozen=True)
class Plan:
    plan_id: str
    owner_ref: str
    lineage_key: str
    version: int
    goal: str
    consequence: Consequence
    state: PlanState
    facts: Mapping[str, Any] = field(default_factory=dict)
    required: tuple[str, ...] = ()
    source_event_ids: tuple[str, ...] = ()
    approval: Optional[Approval] = None
    lease: Optional[Lease] = None
    receipt: Optional[Receipt] = None
    attempts: int = 0
    reason: str = ""
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)

    @property
    def missing(self) -> tuple[str, ...]:
        return tuple(name for name in self.required
                     if name not in self.facts or self.facts[name] in (None, ""))

    @property
    def effect_key(self) -> str:
        return _digest({
            "owner_ref": self.owner_ref,
            "plan_id": self.plan_id,
            "version": self.version,
            "goal": self.goal,
            "facts": dict(self.facts),
            "consequence": self.consequence.value,
        })

    @property
    def scope_digest(self) -> str:
        return _digest({
            "plan_id": self.plan_id,
            "version": self.version,
            "goal": self.goal,
            "facts": dict(self.facts),
            "consequence": self.consequence.value,
        })

    @property
    def approved_for_current_version(self) -> bool:
        return bool(
            self.approval
            and self.approval.plan_id == self.plan_id
            and self.approval.plan_version == self.version
            and self.approval.scope_digest == self.scope_digest
        )

    def assert_valid(self) -> None:
        if not self.plan_id or not self.owner_ref or not self.lineage_key:
            raise WorkflowViolation("every plan needs plan, owner, and lineage ids")
        if not self.goal.strip():
            raise WorkflowViolation("a plan cannot have a blank goal")
        if self.version < 1 or self.attempts < 0:
            raise WorkflowViolation("plan version and attempts cannot be negative")
        if len(set(self.source_event_ids)) != len(self.source_event_ids):
            raise WorkflowViolation("a source event may appear only once")
        if self.state == PlanState.RUNNING and not self.lease:
            raise WorkflowViolation("running work must have a lease")
        if self.state != PlanState.RUNNING and self.lease:
            raise WorkflowViolation("only running work may retain a lease")
        if self.state == PlanState.SUCCEEDED:
            if not self.receipt or not self.receipt.verified:
                raise WorkflowViolation("success requires a verified receipt")
            if self.receipt.effect_key != self.effect_key:
                raise WorkflowViolation("receipt belongs to a different plan version")
        elif self.receipt:
            raise WorkflowViolation("only successful work may carry a final receipt")
        if self.consequence == Consequence.CONSEQUENTIAL \
                and self.state in (PlanState.QUEUED, PlanState.RUNNING,
                                   PlanState.SUCCEEDED) \
                and not self.approved_for_current_version:
            raise WorkflowViolation("consequential work needs version-bound approval")

    def as_dict(self) -> dict[str, Any]:
        def stamp(value: Optional[datetime]) -> Optional[str]:
            return value.isoformat() if value else None

        return {
            "plan_id": self.plan_id,
            "owner_ref": self.owner_ref,
            "lineage_key": self.lineage_key,
            "version": self.version,
            "goal": self.goal,
            "consequence": self.consequence.value,
            "state": self.state.value,
            "scope_digest": self.scope_digest,
            "effect_key": self.effect_key,
            "facts": dict(self.facts),
            "required": list(self.required),
            "source_event_ids": list(self.source_event_ids),
            "approval": ({
                "plan_id": self.approval.plan_id,
                "plan_version": self.approval.plan_version,
                "scope_digest": self.approval.scope_digest,
                "owner_words": self.approval.owner_words,
                "approved_at": stamp(self.approval.approved_at),
            } if self.approval else None),
            "lease": ({
                "token": self.lease.token,
                "actor_id": self.lease.actor_id,
                "acquired_at": stamp(self.lease.acquired_at),
                "expires_at": stamp(self.lease.expires_at),
                "attempt": self.lease.attempt,
            } if self.lease else None),
            "receipt": ({
                "effect_key": self.receipt.effect_key,
                "summary": self.receipt.summary,
                "evidence": list(self.receipt.evidence),
                "verified": self.receipt.verified,
                "recorded_at": stamp(self.receipt.recorded_at),
            } if self.receipt else None),
            "attempts": self.attempts,
            "reason": self.reason,
            "created_at": stamp(self.created_at),
            "updated_at": stamp(self.updated_at),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Plan":
        def moment(raw: Any) -> datetime:
            if isinstance(raw, datetime):
                return _at(raw)
            if not raw:
                return utcnow()
            return _at(datetime.fromisoformat(str(raw).replace("Z", "+00:00")))

        a = value.get("approval") or None
        approval = (Approval(
            plan_id=str(a.get("plan_id") or ""),
            plan_version=int(a.get("plan_version") or 0),
            scope_digest=str(a.get("scope_digest") or ""),
            owner_words=str(a.get("owner_words") or ""),
            approved_at=moment(a.get("approved_at")),
        ) if isinstance(a, Mapping) else None)
        l = value.get("lease") or None
        lease = (Lease(
            token=str(l.get("token") or ""),
            actor_id=str(l.get("actor_id") or ""),
            acquired_at=moment(l.get("acquired_at")),
            expires_at=moment(l.get("expires_at")),
            attempt=int(l.get("attempt") or 0),
        ) if isinstance(l, Mapping) else None)
        r = value.get("receipt") or None
        receipt = (Receipt(
            effect_key=str(r.get("effect_key") or ""),
            summary=str(r.get("summary") or ""),
            evidence=tuple(str(x) for x in (r.get("evidence") or []) if str(x)),
            verified=bool(r.get("verified")),
            recorded_at=moment(r.get("recorded_at")),
        ) if isinstance(r, Mapping) else None)
        out = cls(
            plan_id=str(value.get("plan_id") or ""),
            owner_ref=str(value.get("owner_ref") or ""),
            lineage_key=str(value.get("lineage_key") or ""),
            version=int(value.get("version") or 0),
            goal=str(value.get("goal") or ""),
            consequence=Consequence(str(value.get("consequence") or "")),
            state=PlanState(str(value.get("state") or "")),
            facts=_clean_facts(value.get("facts") or {}),
            required=tuple(str(x) for x in (value.get("required") or []) if str(x)),
            source_event_ids=tuple(str(x) for x in
                                   (value.get("source_event_ids") or []) if str(x)),
            approval=approval,
            lease=lease,
            receipt=receipt,
            attempts=int(value.get("attempts") or 0),
            reason=str(value.get("reason") or ""),
            created_at=moment(value.get("created_at")),
            updated_at=moment(value.get("updated_at")),
        )
        out.assert_valid()
        return out

    def job_fields(self) -> dict[str, Any]:
        """PocketBase fields that make the canonical state auditable."""
        approval = _canonical(self.as_dict()["approval"]) if self.approval else ""
        receipt = _canonical(self.as_dict()["receipt"]) if self.receipt else ""
        lease_until = self.lease.expires_at.isoformat() if self.lease else ""
        return {
            "workflow_id": self.plan_id,
            "workflow_version": self.version,
            "workflow_state": self.state.value,
            "consequence": self.consequence.value,
            "lineage_key": self.lineage_key,
            "effect_key": self.effect_key,
            "scope_digest": self.scope_digest,
            "approval": approval,
            "receipt": receipt,
            "lease_token": self.lease.token if self.lease else "",
            "lease_until": lease_until,
            "source_event_ids": _canonical(list(self.source_event_ids)),
            "attempts": self.attempts,
            "status": LEGACY_STATUS[self.state],
        }


WORKFLOW_PARAM = "_workflow"


def put_in_params(params: Optional[Mapping[str, Any]], plan: Plan) -> dict[str, Any]:
    out = dict(params or {})
    out[WORKFLOW_PARAM] = plan.as_dict()
    return out


def from_params(params: Mapping[str, Any]) -> Optional[Plan]:
    raw = params.get(WORKFLOW_PARAM)
    if not isinstance(raw, Mapping):
        return None
    return Plan.from_dict(raw)


def new_plan(*, owner_ref: str, lineage_key: str, goal: str,
             consequence: Consequence,
             source_event_id: str,
             facts: Optional[Mapping[str, Any]] = None,
             required: Iterable[str] = (),
             plan_id: Optional[str] = None,
             now: Optional[datetime] = None) -> Plan:
    at = _at(now)
    state = (PlanState.QUEUED if consequence == Consequence.READ_ONLY
             else PlanState.AWAITING_APPROVAL)
    plan = Plan(
        plan_id=plan_id or str(uuid.uuid4()),
        owner_ref=owner_ref.strip(),
        lineage_key=lineage_key.strip(),
        version=1,
        goal=goal.strip(),
        consequence=consequence,
        state=state,
        facts=_clean_facts(facts),
        required=tuple(dict.fromkeys(str(x).strip() for x in required
                                     if str(x).strip())),
        source_event_ids=(source_event_id.strip(),) if source_event_id.strip() else (),
        created_at=at,
        updated_at=at,
    )
    if plan.missing:
        plan = replace(plan, state=PlanState.DRAFT,
                       reason="missing: " + ", ".join(plan.missing))
    plan.assert_valid()
    return plan


def merge(plan: Plan, *, expected_version: int, goal: Optional[str] = None,
          facts: Optional[Mapping[str, Any]] = None,
          source_event_id: str = "", now: Optional[datetime] = None) -> Plan:
    """Atomically improve/correct one plan and invalidate stale authority."""
    plan.assert_valid()
    if plan.version != expected_version:
        raise WorkflowViolation("stale plan version")
    if plan.state in TERMINAL_STATES:
        raise WorkflowViolation("terminal work cannot be amended")
    if plan.state == PlanState.RUNNING:
        raise WorkflowViolation("stop running work before amending it")
    at = _at(now)
    next_facts = dict(plan.facts)
    next_facts.update(_clean_facts(facts))
    next_goal = (goal or plan.goal).strip()
    events = list(plan.source_event_ids)
    if source_event_id.strip() and source_event_id.strip() not in events:
        events.append(source_event_id.strip())
    next_state = (PlanState.DRAFT if any(
        name not in next_facts or next_facts[name] in (None, "")
        for name in plan.required)
        else (PlanState.QUEUED if plan.consequence == Consequence.READ_ONLY
              else PlanState.AWAITING_APPROVAL))
    out = replace(
        plan,
        version=plan.version + 1,
        goal=next_goal,
        facts=next_facts,
        source_event_ids=tuple(events),
        state=next_state,
        approval=None,
        lease=None,
        receipt=None,
        reason="plan changed; previous approval invalidated",
        updated_at=at,
    )
    out.assert_valid()
    return out


def approve(plan: Plan, *, expected_version: int, owner_words: str,
            changes: Optional[Mapping[str, Any]] = None,
            now: Optional[datetime] = None) -> Plan:
    """Bind a person's exact approval to one exact version and payload."""
    plan.assert_valid()
    if plan.version != expected_version:
        raise WorkflowViolation("approval addressed a stale plan version")
    if plan.state not in (PlanState.DRAFT, PlanState.AWAITING_APPROVAL,
                          PlanState.NEEDS_USER):
        raise WorkflowViolation("this plan is not waiting on its owner")
    words = owner_words.strip()
    if not words:
        raise WorkflowViolation("approval must retain the owner's actual words")
    out = plan
    clean = _clean_facts(changes)
    if clean:
        next_facts = dict(plan.facts)
        next_facts.update(clean)
        out = replace(plan, version=plan.version + 1, facts=next_facts,
                      approval=None, lease=None, receipt=None)
    if out.missing:
        raise WorkflowViolation("approval cannot invent missing required facts")
    at = _at(now)
    approval = Approval(
        plan_id=out.plan_id,
        plan_version=out.version,
        scope_digest=out.scope_digest,
        owner_words=words,
        approved_at=at,
    )
    out = replace(out, approval=approval, state=PlanState.QUEUED,
                  reason="approved by owner", updated_at=at)
    out.assert_valid()
    return out


def claim(plan: Plan, *, expected_version: int, actor_id: str,
          lease_seconds: int = 120, now: Optional[datetime] = None,
          token: Optional[str] = None) -> Plan:
    plan.assert_valid()
    if plan.version != expected_version:
        raise WorkflowViolation("claim addressed a stale plan version")
    if plan.state != PlanState.QUEUED:
        raise WorkflowViolation("only queued work may be claimed")
    if not actor_id.strip():
        raise WorkflowViolation("a claim needs an actor")
    at = _at(now)
    lease = Lease(
        token=token or str(uuid.uuid4()),
        actor_id=actor_id.strip(),
        acquired_at=at,
        expires_at=at + timedelta(seconds=max(5, lease_seconds)),
        attempt=plan.attempts + 1,
    )
    out = replace(plan, state=PlanState.RUNNING, lease=lease,
                  attempts=plan.attempts + 1, reason="claimed",
                  updated_at=at)
    out.assert_valid()
    return out


def heartbeat(plan: Plan, *, lease_token: str, lease_seconds: int = 120,
              now: Optional[datetime] = None) -> Plan:
    plan.assert_valid()
    if plan.state != PlanState.RUNNING or not plan.lease:
        raise WorkflowViolation("only running work has a heartbeat")
    if plan.lease.token != lease_token:
        raise WorkflowViolation("heartbeat came from the wrong lease")
    at = _at(now)
    out = replace(plan, lease=replace(
        plan.lease, expires_at=at + timedelta(seconds=max(5, lease_seconds))),
        updated_at=at)
    out.assert_valid()
    return out


def needs_user(plan: Plan, *, lease_token: str, reason: str,
               now: Optional[datetime] = None) -> Plan:
    plan.assert_valid()
    if plan.state != PlanState.RUNNING or not plan.lease \
            or plan.lease.token != lease_token:
        raise WorkflowViolation("only the active attempt may ask the owner")
    if not reason.strip():
        raise WorkflowViolation("a parked plan must say what it needs")
    out = replace(plan, state=PlanState.NEEDS_USER, lease=None,
                  reason=reason.strip(), updated_at=_at(now))
    out.assert_valid()
    return out


def succeed(plan: Plan, *, lease_token: str, summary: str,
            evidence: Iterable[str], verified: bool,
            now: Optional[datetime] = None) -> Plan:
    plan.assert_valid()
    if plan.state != PlanState.RUNNING or not plan.lease \
            or plan.lease.token != lease_token:
        raise WorkflowViolation("only the active attempt may complete work")
    proof = tuple(str(x).strip() for x in evidence if str(x).strip())
    if not verified or not proof:
        raise WorkflowViolation("completion needs independent evidence")
    at = _at(now)
    receipt = Receipt(effect_key=plan.effect_key, summary=summary.strip(),
                      evidence=proof, verified=True, recorded_at=at)
    out = replace(plan, state=PlanState.SUCCEEDED, lease=None,
                  receipt=receipt, reason="verified complete", updated_at=at)
    out.assert_valid()
    return out


def fail(plan: Plan, *, lease_token: str, reason: str,
         now: Optional[datetime] = None) -> Plan:
    plan.assert_valid()
    if plan.state != PlanState.RUNNING or not plan.lease \
            or plan.lease.token != lease_token:
        raise WorkflowViolation("only the active attempt may fail work")
    out = replace(plan, state=PlanState.FAILED, lease=None,
                  reason=reason.strip() or "execution failed", updated_at=_at(now))
    out.assert_valid()
    return out


def cancel(plan: Plan, *, reason: str, now: Optional[datetime] = None) -> Plan:
    plan.assert_valid()
    if plan.state in TERMINAL_STATES:
        if plan.state == PlanState.CANCELLED:
            return plan
        raise WorkflowViolation("completed work cannot be cancelled retroactively")
    out = replace(plan, state=PlanState.CANCELLED, lease=None,
                  approval=None, reason=reason.strip() or "cancelled by owner",
                  updated_at=_at(now))
    out.assert_valid()
    return out


def recover_expired(plan: Plan, *, max_attempts: int = 3,
                    external_effect_uncertain: bool = False,
                    now: Optional[datetime] = None) -> Plan:
    """Recover a dead executor without ever repeating an uncertain effect."""
    plan.assert_valid()
    at = _at(now)
    if plan.state != PlanState.RUNNING or not plan.lease:
        raise WorkflowViolation("only running work can have an expired lease")
    if plan.lease.live_at(at):
        raise WorkflowViolation("the active lease has not expired")
    if external_effect_uncertain:
        out = replace(plan, state=PlanState.NEEDS_USER, lease=None,
                      reason="executor stopped after a possible external effect; verify before retry",
                      updated_at=at)
    elif plan.attempts >= max_attempts:
        out = replace(plan, state=PlanState.FAILED, lease=None,
                      reason=f"stopped after {plan.attempts} attempts",
                      updated_at=at)
    else:
        out = replace(plan, state=PlanState.QUEUED, lease=None,
                      reason="executor lease expired before any external effect",
                      updated_at=at)
    out.assert_valid()
    return out
