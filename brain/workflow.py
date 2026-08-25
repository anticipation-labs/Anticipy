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
    # SHELF 2 — act-and-tell.  Work that runs without waiting for a tap and is
    # reported afterwards with a real undo.
    #
    # The name is deliberately NOT "reversible".  Nothing in this tree
    # classifies reversibility and nothing should start by borrowing the word
    # (spec §8.6's naming note; `_IRREVERSIBLE_RE` does not detect
    # irreversibility either, it detects world-touching verbs).  This value
    # claims one narrow thing that a machine can check: the act lands in our
    # own store, and the recipe for undoing it was complete before it ran.
    #
    # It buys NO exemption by being spelled.  `admissible()` below is the
    # floor, and `backend/pb_hooks/workflow_guard.pb.js` re-runs it at the
    # queued transition — because a check that runs only in the Python that
    # minted the plan is not a check, it is a comment (spec §5.4).
    REVERSIBLE_LOCAL = "reversible_local"


TERMINAL_STATES = {
    PlanState.SUCCEEDED,
    PlanState.FAILED,
    PlanState.CANCELLED,
}


# ONE CORRUPT ROW MUST NOT SILENCE HIM FOR THE REST OF THE DAY.
#
# These enums raise ValueError on an empty or unrecognised value, and the
# plan blob is parsed inside hear(). So a single malformed row — a truncated
# write, an older shape, a hand-edited record — threw out of _queue_job, out
# of hear(), and the worker marked the EVENT as "error". The event had already
# been claimed, so it was never retried: every later line that touched that
# lineage died the same way, and nothing was ever said to him about any of it.
#
# Unreadable is not the same as absent, so both defaults are the cautious one:
# work whose consequence cannot be read is treated as world-changing (it gets
# every gate), and a plan whose state cannot be read is treated as parked for
# the owner — visible, unable to act on its own, and still recoverable.

def _consequence_or_safe(value) -> "Consequence":
    try:
        return Consequence(str(value or ""))
    except ValueError:
        return Consequence.CONSEQUENTIAL


def _state_or_safe(value) -> "PlanState":
    try:
        return PlanState(str(value or ""))
    except ValueError:
        return PlanState.NEEDS_USER


def _state_after_unreadable(raw_consequence, raw_state) -> "PlanState":
    """Park a plan whose consequence could not be read.

    Defaulting the consequence to "world-changing" is right, but on its own
    it manufactures an ILLEGAL plan: consequential work sitting in QUEUED or
    RUNNING without version-bound approval is exactly what assert_valid
    refuses, so the cautious default would have thrown the very exception it
    was added to prevent. Caught by its own test before it shipped.

    So an unreadable consequence parks the work as well as gating it: we
    cannot say what this plan would do, so it waits for him. Already-dead
    states are left alone — there is nothing left to park.
    """
    state = _state_or_safe(raw_state)
    try:
        Consequence(str(raw_consequence or ""))
        return state
    except ValueError:
        if state in (PlanState.FAILED, PlanState.CANCELLED):
            return state
        return PlanState.NEEDS_USER

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


# ============================================================== SHELF 2 =====
#
# THERE IS NO REVERSIBILITY CLASSIFIER HERE, AND THAT IS THE DESIGN.
#
# The card asked for one.  The spec's review (§5.1) refuses it three ways: not
# a word list, not a domain list, and NOT A MODEL CALL RETURNING A BIT either.
# "Is this reversible?" is a question about the future behaviour of a third
# party under conditions nobody has observed; the answer is one bit; a wrong
# bit in the unsafe direction is unrecoverable and invisible.  A bit cannot be
# audited, it can only be believed.
#
# What replaces it: ask the model for an ARTIFACT — "what exactly would undo
# this, step by step?" — and check the artifact MECHANICALLY.  The meaning
# question goes to a model with full context, asked alone (Law 1).  The
# release decision is a structural property of what the model wrote:
#
#     An act is admissible only when undoing it requires nothing the act
#     produced.                                                        (§4)
#
# and, because binding only the undo leaves a door in the middle of the design
# (§5.4 — a plan can declare `local_draft`, mint its own uuid, write a
# provenance-clean undo, and create a Gmail draft):
#
#     ...AND the act's declared reach is persisted on the row and bound to its
#     admitted act type, checked at the same guard leg.               (§5.4)
#
# Both sides are `admissible()` below.  POLARITY IS A FLOOR: no undo plan, an
# unparseable one, an unrecognised provenance tag, a reference that does not
# resolve, no verdict at all — every one of those is the same answer as "there
# is money here".  Refuse; the work goes to Shelf 3 and waits for a tap.  A
# floor that lifts on silence lifts itself.  There is no fifth outcome that
# means "proceed".


class Provenance(str, Enum):
    """Where an undo plan's input came from.  TYPED AND CLOSED, on purpose.

    §5.2: "A fourth provenance tag is a schema change, visible in a diff, not
    a string a model can invent at runtime."  An unrecognised tag is a
    refusal, never a default.
    """
    MINTED_BY_US = "minted_by_us"
    OWNER_SUPPLIED = "owner_supplied"
    CONSTANT = "constant"


PROVENANCE_TAGS: tuple[str, ...] = tuple(p.value for p in Provenance)

# A tap is a gesture, not wording (§7.3).  Closed set, same reason.
GESTURE_KINDS: tuple[str, ...] = ("tap",)


class Refusal(str, Enum):
    """The enumerated causes a Shelf 2 act can be refused for.

    §11: "Reasons are the enumerated refusal causes of §5.2 and §8.5's a-f,
    not free text."  A shelf that refuses in prose cannot be widened on
    evidence, because nobody can count what it refused.
    """
    ACT_TYPE_NOT_ADMITTED = "shelf2.act_type_not_admitted"
    REACH_DISAGREES = "shelf2.reach_disagrees"
    EXECUTOR_DISAGREES = "shelf2.executor_disagrees"
    NO_UNDO_PLAN = "shelf2.no_undo_plan"
    UNDO_ADDRESSES_ANOTHER_ACT = "shelf2.undo_addresses_another_act"
    UNKNOWN_PROVENANCE = "shelf2.unknown_provenance"
    UNRESOLVED_REFERENCE = "shelf2.unresolved_reference"
    UNDO_BINDS_NOTHING = "shelf2.undo_binds_nothing"
    # PRESENCE IS NOT CORRESPONDENCE, and these two are the difference.
    #
    # UNDO_BINDS_NOTHING asks whether SOME input carries the provenance the
    # admitted set requires.  It closed the vacuous empty-inputs case and
    # nothing more: an undo whose one `minted_by_us` input resolves cleanly to
    # a uuid the act will never create satisfies it completely, and is a
    # well-formed undo that cannot undo.  So the act declares the reference it
    # will address and the undo has to address the SAME one.
    ACT_TARGET_UNBOUND = "shelf2.act_target_unbound"
    UNDO_MISSES_THE_TARGET = "shelf2.undo_misses_the_target"
    NO_ANNOUNCE_OBLIGATION = "shelf2.no_announce_obligation"
    ANNOUNCE_LEAVES_THE_OWNER = "shelf2.announce_leaves_the_owner"
    UNORDERED_LINEAGE = "shelf2.unordered_lineage"
    # Kept apart from UNORDERED_LINEAGE deliberately.  "This undo has no
    # position" is a fact about the plan; "I could not read the lineage" is a
    # fact about our own infrastructure, and §10.5(a) is emphatic that the two
    # must be tellable apart — one outage on a Tuesday must not read as the
    # counterparty refusing.  Both refuse; only one of them means anything is
    # wrong with the work.
    LINEAGE_UNREADABLE = "shelf2.lineage_unreadable"
    SUPERSEDED_BY_LATER_ACT = "shelf2.superseded_by_later_act"


@dataclass(frozen=True)
class UndoInput:
    """One input an undo plan needs, and where it came from.

    `name` is for a human reading the row.  NOTHING BRANCHES ON IT.  §5.2:
    "The checker resolves every reference and refuses on any that does not
    resolve.  It never inspects a field name and never parses prose."  A
    checker that read names would be a word list wearing a different coat, and
    would be defeated by a model that calls a field `owner_supplied_reference`
    and fills it from the counterparty's response.
    """
    name: str
    provenance: str
    ref: str


@dataclass(frozen=True)
class UndoPlan:
    """A stored, complete, executable undo written BEFORE the act runs.

    `held` is the closed set of values we already have, bucketed by
    provenance.  Resolution is a dictionary lookup: a reference that resolves
    only after the act is, by construction, a hole the counterparty fills —
    and the checker discovers that by TRYING TO RESOLVE IT AND FAILING, not by
    reading what it is called.

    `steps` is model-authored prose describing the undo.  It is stored so a
    human can read it, a test can replay it, and a diff can compare it against
    what actually ran.  It is never parsed for meaning.
    """
    act_type: str
    steps: tuple[str, ...] = ()
    inputs: tuple[UndoInput, ...] = ()
    held: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)


@dataclass(frozen=True)
class ActDeclaration:
    """What the ACT touches — the half the first revision of the spec left
    unbound, and the half the §5.4 attack walks through.

    `touches` (brain/orchestrator.py) cannot supply this: it is a Python call
    argument with a lifetime of one decision, never persisted, and the string
    does not appear anywhere in backend/, extension/ or app/ios/ (§9).  This
    rides on the Plan and into `params._workflow`, where the database guard
    can read it.

    `executor` is here because a declared reach on a general browser session
    is a label attached to a process that can do anything the session can do
    (§8.7).  Day one's act type runs against our own store through our own
    code path, and that is the only mechanical containment available.
    """
    act_type: str
    reach: str
    executor: str
    # WHAT THIS ACT WILL ADDRESS, in the same typed shape the undo's inputs
    # use — deliberately, so one resolver checks both and so the undo can be
    # required to bind this exact (provenance, ref) pair.  Without it §6.1's
    # admission ("the undo is discard our row, needing nothing but an id we
    # minted") is satisfied by an undo that addresses nothing the act
    # produces: the id is not required to be the SAME id.
    #
    # NO DEFAULT, on purpose.  A caller that forgets it cannot construct an
    # act at all, which is the only place this can be made unrepresentable
    # rather than merely detectable.  A STORED row that predates it parses to
    # None (`from_dict` passes it explicitly) and is refused by name, because
    # a row that cannot be parsed is a row that can never be recovered.
    target: Optional[UndoInput]


@dataclass(frozen=True)
class Obligation:
    """The promise to tell him, recorded on the row (§8.3).

    "Act-and-tell means the tell is part of the work, not a best-effort text
    afterwards.  An act that ran and was not announced is an open obligation,
    not a completed job."  `notify_owner` returns a TRUTHY dict when there is
    no transport, so a send that never happened reads as a send that
    succeeded; on 2026-08-16 she stamped his questions delivered and sent
    nothing for ten hours.  A return value is not a record.

    Cleared only by evidence of delivery: `delivered_at` without `evidence` is
    the same claim with a timestamp on it.
    """
    channel: str
    owner_ref: str
    recorded_at: datetime
    delivered_at: Optional[datetime] = None
    evidence: tuple[str, ...] = ()

    @property
    def discharged(self) -> bool:
        return bool(self.delivered_at and self.evidence)


@dataclass(frozen=True)
class UndoOf:
    """What a compensating plan compensates, and where it sat in the lineage."""
    plan_id: str
    version: int
    effect_key: str
    act_seq: int


@dataclass(frozen=True)
class Gesture:
    """An authenticated owner tap.  NOT words (§7.3).

    `Approval.owner_words` exists because he said them; `Plan.authority_text`
    is documented as "never model-owned".  Stuffing "tapped undo" into
    `owner_words` would put a sentence he never said into the one field whose
    entire purpose is that he did — and that string is one line of Swift away
    at all times.  So a gesture is stored as a gesture: authenticated, bound
    to plan id, version and scope digest, and distinguishable at a glance from
    speech.
    """
    kind: str
    actor: str
    plan_id: str
    plan_version: int
    scope_digest: str
    made_at: datetime


@dataclass(frozen=True)
class AdmittedAct:
    """One member of the admitted set, with everything the checks need.

    §10.3: "A membership record that is only a name cannot support the checks
    §8.5 requires."  So it records the permitted reach, the executor that may
    run it, and the evidence that admitted it.
    """
    act_type: str
    reach: str
    executor: str
    # The provenances this act type's undo must actually bind at least one of.
    #
    # Without it `_resolves` is VACUOUSLY true for an undo plan with no inputs
    # at all: "delete the draft" with no id, which cannot execute and which
    # passes every other check in this file.  §5.2 asks for a "complete,
    # executable" undo plan; completeness of an empty input list is not
    # something a general rule can judge, but it is something the admitted set
    # can record per act type — which is what §10.3 means by "a membership
    # record that is only a name cannot support the checks §8.5 requires."
    binds: tuple[str, ...] = ()
    # The provenance this act type's TARGET must carry.  §6.1: "the id must be
    # CLIENT-minted, which is what makes the reference resolvable before the
    # draft exists at all."  A target the owner supplied is a row somebody
    # else made, and "discard our row" is then a sentence about a row that is
    # not ours.
    target_provenance: str = ""
    evidence: tuple[str, ...] = ()


# THE ADMITTED SET — A FLOOR, AND IT HAS ONE MEMBER.
#
# §10.3: "The admitted set can only ever REFUSE: an act type not in it is
# held, whatever the model wrote.  It never releases anything the structural
# test failed.  A list that can only hold is a seatbelt; a list that can
# release is the violation."
#
# §6.1 is the whole of the acting set on day one: a draft that is a row in our
# own store, shown only to the owner, whose undo is "discard our row" and
# needs nothing but an id we minted first.  A draft created in his Gmail
# account is NOT admitted — the effect left into a third-party system and the
# undo needs a message id the provider returned.  Same act in English,
# opposite side of the line, which is the clearest evidence available that a
# word list could never have drawn this boundary.
#
# A constant is licensed HERE AND ONLY HERE, by §6.4's sequencing note: while
# the set has one member a reader can check it in a single diff.  The repo-data
# form carrying committed receipts, and `overnight/shelf2_gate.py`, are
# REQUIRED BEFORE THE SECOND ADMISSION — because the second admission is the
# first one nobody can hold in their head.  Adding a member here without going
# through §10.1's six conditions is the failure this comment exists to name.
#
# `reach` is a separate, act-type-scoped vocabulary rather than `touches`'s
# compute/read/world (§9 leaves that choice open).  None of those three is
# honest about a write that never leaves our own store: it is not a read, it
# is not compute, and calling it "world" would put it on Shelf 3.
ADMITTED_ACT_TYPES: Mapping[str, AdmittedAct] = {
    "local_draft": AdmittedAct(
        act_type="local_draft",
        reach="local_store",
        executor="anticipy_store",
        # The undo is "discard our row", and it cannot be that without the id
        # we minted first.  §6.1: the id must be CLIENT-minted, which is what
        # makes the reference resolvable before the draft exists at all — a
        # draft whose id the store assigns on insert fails for a reason that
        # has nothing to do with whose store it is.
        binds=("minted_by_us",),
        target_provenance="minted_by_us",
        evidence=(
            "docs/superpowers/specs/2026-08-24-shelf-2-redesign.md "
            "§6.1 — admitted by spec, no live receipts yet; §10.1 conditions "
            "2, 3 and 5 are UNMET and must be met before this acts in "
            "production",
        ),
    ),
}


def _resolves_one(undo: UndoPlan, item: "UndoInput") -> str:
    """Resolve one typed reference against the values the plan already holds.

    Reads `provenance` and `ref`.  Never reads `name`, never parses `steps`.
    Shared with the ACT's own target so that both sides of the correspondence
    are held to the same "known-good BEFORE acting": a reference that can only
    resolve after the act fails here, now.
    """
    if not isinstance(item, UndoInput):
        return Refusal.NO_UNDO_PLAN.value
    if item.provenance not in PROVENANCE_TAGS:
        return Refusal.UNKNOWN_PROVENANCE.value
    bucket = undo.held.get(item.provenance)
    if not isinstance(bucket, Mapping):
        return Refusal.UNRESOLVED_REFERENCE.value
    if item.ref not in bucket:
        return Refusal.UNRESOLVED_REFERENCE.value
    if bucket[item.ref] in (None, ""):
        return Refusal.UNRESOLVED_REFERENCE.value
    return ""


def _resolves(undo: UndoPlan) -> str:
    """§5.2's checker.  Resolve every reference; refuse on any that does not."""
    for item in undo.inputs:
        why = _resolves_one(undo, item)
        if why:
            return why
    return ""


def admissible(plan: "Plan") -> str:
    """The two-sided test.  "" means the act may run unattended.

    Anything else is an enumerated `Refusal`.  Nothing here decides what the
    owner's words MEANT; every branch compares two stored values.

    The ACT side runs first and on purpose: §5.4 requires a plan whose
    declared reach disagrees with its admitted type to be refused "whatever
    its undo plan says, and before its undo plan is even examined."  The
    attack it defends against arrives WITH a flawless undo plan.
    """
    act = plan.act
    if not isinstance(act, ActDeclaration):
        return Refusal.ACT_TYPE_NOT_ADMITTED.value
    admitted = ADMITTED_ACT_TYPES.get(act.act_type)
    if admitted is None:
        return Refusal.ACT_TYPE_NOT_ADMITTED.value
    if act.reach != admitted.reach:
        return Refusal.REACH_DISAGREES.value
    if act.executor != admitted.executor:
        return Refusal.EXECUTOR_DISAGREES.value
    # Still the ACT side, so it runs before the undo plan is read (§5.4): an
    # act that never said what it will address leaves nothing for the undo to
    # correspond to, and `binds` collapses back into presence.
    target = act.target
    if not isinstance(target, UndoInput):
        return Refusal.ACT_TARGET_UNBOUND.value
    if target.provenance not in PROVENANCE_TAGS:
        return Refusal.UNKNOWN_PROVENANCE.value
    # NO TRUTHINESS GUARD.  `if admitted.target_provenance and ...` would let
    # a future member that forgot to record one skip the pin entirely, and the
    # guard's `targetTag !== SHELF2_TARGET_PROVENANCE[which]` refuses in that
    # same case — two layers disagreeing about a floor with nobody looking is
    # exactly the scar `NO_APPROVAL_NEEDED` carries.  An unset pin refuses.
    if target.provenance != admitted.target_provenance:
        return Refusal.ACT_TARGET_UNBOUND.value

    undo = plan.undo
    if not isinstance(undo, UndoPlan) or not undo.steps:
        return Refusal.NO_UNDO_PLAN.value
    if undo.act_type != act.act_type:
        return Refusal.UNDO_ADDRESSES_ANOTHER_ACT.value
    unresolved = _resolves(undo)
    if unresolved:
        return unresolved
    bound = set(item.provenance for item in undo.inputs
                if isinstance(item, UndoInput))
    for tag in admitted.binds:
        if tag not in bound:
            return Refusal.UNDO_BINDS_NOTHING.value
    # CORRESPONDENCE.  The target is a reference like any other, so it must
    # resolve before the act runs; and the undo must address THAT reference,
    # not merely one wearing the same provenance tag.
    unresolved = _resolves_one(undo, target)
    if unresolved:
        return unresolved
    if not any(item.provenance == target.provenance and item.ref == target.ref
               for item in undo.inputs if isinstance(item, UndoInput)):
        return Refusal.UNDO_MISSES_THE_TARGET.value

    tell = plan.announce
    if not isinstance(tell, Obligation) or not tell.channel.strip():
        return Refusal.NO_ANNOUNCE_OBLIGATION.value
    if tell.owner_ref != plan.owner_ref or not tell.owner_ref:
        return Refusal.ANNOUNCE_LEAVES_THE_OWNER.value

    if plan.lineage_seq < 1:
        return Refusal.UNORDERED_LINEAGE.value
    return ""


def compensation_is_current(*, undo_of: Optional[UndoOf],
                            ran_seqs: Iterable[Any]) -> str:
    """§7.4.  LIFO within a lineage, and a floor when the order is unreadable.

    An undo plan is written BEFORE its act runs, against the state as it was
    then.  Applying it later applies a compensation computed against a world
    that may no longer exist:

        Act A drafts the boiler email — row d, version 1.  He is told.
        Twenty minutes later act B revises it in place — row d, version 2.
        He is told again.  Undo(A) is "delete row d"; undo(B) is "restore row
        d to version 1".  He taps undo on A and the row is gone.  He then taps
        undo on B, still on screen, and the row is RESTORED.  A draft he was
        told forty seconds ago was gone is back, and both receipts are honest.

    Every check in §5 passes at every step.  The COMPOSITION is what fails.

    `ran_seqs` is the lineage position of every admitted act in this lineage
    that has already RUN.  Refusing is cheap: he asked to undo, and instead of
    a wrong undo he gets a true sentence and a tap.
    """
    if not isinstance(undo_of, UndoOf) or undo_of.act_seq < 1:
        return Refusal.UNORDERED_LINEAGE.value
    for raw in ran_seqs:
        if isinstance(raw, bool) or not isinstance(raw, int):
            try:
                raw = int(str(raw))
            except (TypeError, ValueError):
                return Refusal.LINEAGE_UNREADABLE.value
        if raw > undo_of.act_seq:
            return Refusal.SUPERSEDED_BY_LATER_ACT.value
    return ""


@dataclass(frozen=True)
class Approval:
    plan_id: str
    plan_version: int
    scope_digest: str
    owner_words: str
    approved_at: datetime
    # A tap carries no words (§7.3).  EXACTLY ONE of these two is how a
    # person said yes: `owner_words` when he spoke or typed, `gesture` when he
    # tapped.  Nothing may synthesise the other from the one it has.
    gesture: Optional["Gesture"] = None

    @property
    def carries_authority(self) -> bool:
        return bool(self.owner_words.strip() or self.gesture)


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
    # Exact owner-authored wording that grants the plan its concrete detail.
    # Models may shorten `goal`; this text is never model-owned and is bound
    # into the signed scope/effect payload whenever it exists.
    authority_text: str = ""
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
    # ---- SHELF 2.  All four are PERSISTED, and that is the requirement
    # rather than an implementation detail (§5.4.3): "A check that runs only
    # in the Python that minted the plan is not a check; it is a comment."
    # They ride into the row inside `params._workflow`, which is what
    # backend/pb_hooks/workflow_guard.pb.js reads and re-checks.
    act: Optional[ActDeclaration] = None
    undo: Optional[UndoPlan] = None
    announce: Optional[Obligation] = None
    undo_of: Optional[UndoOf] = None
    # Position in the lineage, so §7.4 has something to order by.  0 means
    # "unordered", which for a Shelf 2 act is a refusal, not a default.
    lineage_seq: int = 0

    @property
    def missing(self) -> tuple[str, ...]:
        return tuple(name for name in self.required
                     if name not in self.facts or self.facts[name] in (None, ""))

    @property
    def effect_key(self) -> str:
        payload = {
            "owner_ref": self.owner_ref,
            "plan_id": self.plan_id,
            "version": self.version,
            "goal": self.goal,
            "facts": dict(self.facts),
            "consequence": self.consequence.value,
        }
        # Conditional preserves legacy digests while binding new sourced work.
        if self.authority_text:
            payload["authority_text"] = self.authority_text
        return _digest(payload)

    @property
    def scope_digest(self) -> str:
        payload = {
            "plan_id": self.plan_id,
            "version": self.version,
            "goal": self.goal,
            "facts": dict(self.facts),
            "consequence": self.consequence.value,
        }
        if self.authority_text:
            payload["authority_text"] = self.authority_text
        return _digest(payload)

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
            "authority_text": self.authority_text,
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
                "gesture": ({
                    "kind": self.approval.gesture.kind,
                    "actor": self.approval.gesture.actor,
                    "plan_id": self.approval.gesture.plan_id,
                    "plan_version": self.approval.gesture.plan_version,
                    "scope_digest": self.approval.gesture.scope_digest,
                    "made_at": stamp(self.approval.gesture.made_at),
                } if self.approval.gesture else None),
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
            "act": ({
                "act_type": self.act.act_type,
                "reach": self.act.reach,
                "executor": self.act.executor,
                "target": ({"name": self.act.target.name,
                            "provenance": self.act.target.provenance,
                            "ref": self.act.target.ref}
                           if isinstance(self.act.target, UndoInput) else None),
            } if self.act else None),
            "undo": ({
                "act_type": self.undo.act_type,
                "steps": list(self.undo.steps),
                "inputs": [{"name": i.name, "provenance": i.provenance,
                            "ref": i.ref} for i in self.undo.inputs],
                "held": {str(k): dict(v) for k, v in self.undo.held.items()
                         if isinstance(v, Mapping)},
            } if self.undo else None),
            "announce": ({
                "channel": self.announce.channel,
                "owner_ref": self.announce.owner_ref,
                "recorded_at": stamp(self.announce.recorded_at),
                "delivered_at": stamp(self.announce.delivered_at),
                "evidence": list(self.announce.evidence),
            } if self.announce else None),
            "undo_of": ({
                "plan_id": self.undo_of.plan_id,
                "version": self.undo_of.version,
                "effect_key": self.undo_of.effect_key,
                "act_seq": self.undo_of.act_seq,
            } if self.undo_of else None),
            "lineage_seq": self.lineage_seq,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Plan":
        def moment(raw: Any) -> datetime:
            if isinstance(raw, datetime):
                return _at(raw)
            if not raw:
                return utcnow()
            return _at(datetime.fromisoformat(str(raw).replace("Z", "+00:00")))

        # EVERY SHELF 2 SUB-OBJECT PARSES TOLERANTLY AND NEVER RAISES.
        #
        # §3's surviving rule: "assert_valid must never grow a rule that can be
        # false for a legitimately stored row."  The scar above
        # `_consequence_or_safe` is twelve lines about one malformed row that
        # threw out of hear(), got the event marked error, and was never
        # retried — "and nothing was ever said to him about any of it."
        #
        # So a garbage undo plan comes back as None and is REFUSED by
        # `admissible()`, which is a state the row can recover from.  It never
        # comes back as an exception, which is a state it cannot.
        def maybe(raw, build):
            if not isinstance(raw, Mapping):
                return None
            try:
                return build(raw)
            except (TypeError, ValueError, AttributeError):
                return None

        a = value.get("approval") or None
        approval = (Approval(
            plan_id=str(a.get("plan_id") or ""),
            plan_version=int(a.get("plan_version") or 0),
            scope_digest=str(a.get("scope_digest") or ""),
            owner_words=str(a.get("owner_words") or ""),
            approved_at=moment(a.get("approved_at")),
            gesture=maybe(a.get("gesture"), lambda g: Gesture(
                kind=str(g.get("kind") or ""),
                actor=str(g.get("actor") or ""),
                plan_id=str(g.get("plan_id") or ""),
                plan_version=int(g.get("plan_version") or 0),
                scope_digest=str(g.get("scope_digest") or ""),
                made_at=moment(g.get("made_at")),
            )),
        ) if isinstance(a, Mapping) else None)

        def _undo(raw):
            held = raw.get("held")
            return UndoPlan(
                act_type=str(raw.get("act_type") or ""),
                steps=tuple(str(x) for x in (raw.get("steps") or []) if str(x)),
                inputs=tuple(UndoInput(
                    name=str(i.get("name") or ""),
                    provenance=str(i.get("provenance") or ""),
                    ref=str(i.get("ref") or ""),
                ) for i in (raw.get("inputs") or []) if isinstance(i, Mapping)),
                held=({str(k): dict(v) for k, v in held.items()
                       if isinstance(v, Mapping)}
                      if isinstance(held, Mapping) else {}),
            )

        act = maybe(value.get("act"), lambda r: ActDeclaration(
            act_type=str(r.get("act_type") or ""),
            reach=str(r.get("reach") or ""),
            executor=str(r.get("executor") or ""),
            # Passed EXPLICITLY, including as None: a row written before the
            # target existed must come back refusable, not unparseable.
            target=maybe(r.get("target"), lambda t: UndoInput(
                name=str(t.get("name") or ""),
                provenance=str(t.get("provenance") or ""),
                ref=str(t.get("ref") or ""),
            )),
        ))
        undo = maybe(value.get("undo"), _undo)
        announce = maybe(value.get("announce"), lambda r: Obligation(
            channel=str(r.get("channel") or ""),
            owner_ref=str(r.get("owner_ref") or ""),
            recorded_at=moment(r.get("recorded_at")),
            delivered_at=(moment(r.get("delivered_at"))
                          if r.get("delivered_at") else None),
            evidence=tuple(str(x) for x in (r.get("evidence") or []) if str(x)),
        ))
        undo_of = maybe(value.get("undo_of"), lambda r: UndoOf(
            plan_id=str(r.get("plan_id") or ""),
            version=int(r.get("version") or 0),
            effect_key=str(r.get("effect_key") or ""),
            act_seq=int(r.get("act_seq") or 0),
        ))
        try:
            lineage_seq = int(value.get("lineage_seq") or 0)
        except (TypeError, ValueError):
            lineage_seq = 0
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
            consequence=_consequence_or_safe(value.get("consequence")),
            state=_state_after_unreadable(value.get("consequence"),
                                          value.get("state")),
            authority_text=str(value.get("authority_text") or "").strip(),
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
            act=act,
            undo=undo,
            announce=announce,
            undo_of=undo_of,
            lineage_seq=lineage_seq,
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
             source_event_ids: Iterable[str] = (),
             authority_text: str = "",
             facts: Optional[Mapping[str, Any]] = None,
             required: Iterable[str] = (),
             plan_id: Optional[str] = None,
             act: Optional[ActDeclaration] = None,
             undo: Optional[UndoPlan] = None,
             announce: Optional[Obligation] = None,
             undo_of: Optional[UndoOf] = None,
             lineage_seq: int = 0,
             now: Optional[datetime] = None) -> Plan:
    at = _at(now)
    # Shelf 2 starts optimistic and is DEMOTED below by `_shelf2_lane`.  It is
    # written this way round so the demotion is one place, reads as a floor,
    # and cannot be reached past.
    state = (PlanState.QUEUED
             if consequence in (Consequence.READ_ONLY,
                                Consequence.REVERSIBLE_LOCAL)
             else PlanState.AWAITING_APPROVAL)
    events = list(dict.fromkeys(
        [str(value).strip() for value in source_event_ids if str(value).strip()]
        + ([source_event_id.strip()] if source_event_id.strip() else [])))
    plan = Plan(
        plan_id=plan_id or str(uuid.uuid4()),
        owner_ref=owner_ref.strip(),
        lineage_key=lineage_key.strip(),
        version=1,
        goal=goal.strip(),
        consequence=consequence,
        state=state,
        authority_text=authority_text.strip(),
        facts=_clean_facts(facts),
        required=tuple(dict.fromkeys(str(x).strip() for x in required
                                     if str(x).strip())),
        source_event_ids=tuple(events),
        created_at=at,
        updated_at=at,
        act=act,
        undo=undo,
        announce=announce,
        undo_of=undo_of,
        lineage_seq=int(lineage_seq or 0),
    )
    if plan.missing:
        plan = replace(plan, state=PlanState.DRAFT,
                       reason="missing: " + ", ".join(plan.missing))
    else:
        plan = _shelf2_lane(plan)
    plan.assert_valid()
    return plan


def _shelf2_lane(plan: Plan) -> Plan:
    """Demote a Shelf 2 plan that has not earned its lane.

    The floor, in the one place it can be applied: a plan whose consequence
    says "run without waiting for a tap" runs only when `admissible()` returns
    "".  Otherwise it is not an error and it is not dropped — IT GOES TO
    SHELF 3 AND WAITS FOR A TAP, carrying the enumerated reason it was
    refused so §11 can count it.

    This is a TRANSITION rule and never a validity rule.  §3: a law of this
    kind belongs in a transition guard, mirrored in
    backend/pb_hooks/workflow_guard.pb.js — never in `assert_valid`, where a
    rule that can be false for a legitimately stored row makes that row
    unparseable forever.
    """
    if plan.consequence != Consequence.REVERSIBLE_LOCAL:
        return plan
    if plan.state != PlanState.QUEUED:
        return plan
    why = admissible(plan)
    if not why:
        return plan
    return replace(plan, state=PlanState.AWAITING_APPROVAL, reason=why)


def merge(plan: Plan, *, expected_version: int, goal: Optional[str] = None,
          facts: Optional[Mapping[str, Any]] = None,
          authority_text: Optional[str] = None,
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
    next_authority = (plan.authority_text if authority_text is None
                      else authority_text.strip())
    events = list(plan.source_event_ids)
    if source_event_id.strip() and source_event_id.strip() not in events:
        events.append(source_event_id.strip())
    next_state = (PlanState.DRAFT if any(
        name not in next_facts or next_facts[name] in (None, "")
        for name in plan.required)
        else (PlanState.QUEUED
              if plan.consequence in (Consequence.READ_ONLY,
                                      Consequence.REVERSIBLE_LOCAL)
              else PlanState.AWAITING_APPROVAL))
    out = replace(
        plan,
        version=plan.version + 1,
        goal=next_goal,
        authority_text=next_authority,
        facts=next_facts,
        source_event_ids=tuple(events),
        state=next_state,
        approval=None,
        lease=None,
        receipt=None,
        reason="plan changed; previous approval invalidated",
        updated_at=at,
    )
    # A lane earned by an artifact has to be re-earned when the plan changes.
    out = _shelf2_lane(out)
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
    # A fresh owner authorization is a fresh execution budget. Leaving the
    # old count in place let three legitimate question-rounds exhaust the
    # attempt cap, after which every re-approval minted a version the
    # executor could never claim (live, 2026-08-15).
    out = replace(out, approval=approval, state=PlanState.QUEUED,
                  attempts=0, reason="approved by owner", updated_at=at)
    out.assert_valid()
    return out


def approve_by_gesture(plan: Plan, *, expected_version: int,
                       gesture: Gesture,
                       now: Optional[datetime] = None) -> Plan:
    """He tapped.  Record a tap.

    §7.3 is a seam, not a nicety: `approve()` raises "approval must retain the
    owner's actual words", the database guard refuses an empty
    `approval.owner_words`, and `approvalFields(for:)` in
    app/ios/Anticipy/AnticipyApp.swift is where the field is minted.  That is
    the layer closest to the gesture and furthest from the law, and therefore
    the layer where somebody writes `"owner_words": "tapped undo"` — one line
    of Swift, and the field whose entire purpose is that he said it now
    contains a sentence he did not.

    So there are two doors and they are not interchangeable.  `approve()` is
    speech and still demands words; this is a gesture and demands binding
    instead: an authenticated actor, a closed `kind`, and the same plan id,
    version and scope digest that words would have been bound to.  A typed
    reply of "undo" IS words and should use `approve()` honestly.

    NOTE: a gesture cannot carry `changes`.  A tap has no content, so it
    cannot supply a fact, and a door that let it would be inventing detail he
    never gave.
    """
    plan.assert_valid()
    if plan.version != expected_version:
        raise WorkflowViolation("approval addressed a stale plan version")
    if plan.state not in (PlanState.DRAFT, PlanState.AWAITING_APPROVAL,
                          PlanState.NEEDS_USER):
        raise WorkflowViolation("this plan is not waiting on its owner")
    if not isinstance(gesture, Gesture):
        raise WorkflowViolation("a gesture approval needs a recorded gesture")
    if gesture.kind not in GESTURE_KINDS:
        raise WorkflowViolation("unrecognised owner gesture")
    if not gesture.actor.strip():
        raise WorkflowViolation("an owner gesture must be authenticated")
    # AND IT MUST BE HIS.  "Authenticated" was a non-empty string: any actor
    # the caller could name — another account, a service identity, an agent id
    # — bought on the owner's work exactly what the owner's own tap buys.  A
    # gesture buys what words buy and nothing more, and words are only ever
    # his words (§7.3).
    if gesture.actor.strip() != plan.owner_ref:
        raise WorkflowViolation("a gesture must be made by this plan's owner")
    if (gesture.plan_id != plan.plan_id
            or gesture.plan_version != plan.version
            or gesture.scope_digest != plan.scope_digest):
        raise WorkflowViolation("gesture is not bound to this exact plan version")
    if plan.missing:
        raise WorkflowViolation("approval cannot invent missing required facts")
    at = _at(now)
    approval = Approval(
        plan_id=plan.plan_id,
        plan_version=plan.version,
        scope_digest=plan.scope_digest,
        owner_words="",
        approved_at=at,
        gesture=gesture,
    )
    out = replace(plan, approval=approval, state=PlanState.QUEUED,
                  attempts=0, reason="approved by owner gesture",
                  updated_at=at)
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
        # A row that lost its undo evidence between attempts must not be
        # handed back to the unattended lane on its way through recovery.
        out = _shelf2_lane(out)
    out.assert_valid()
    return out
