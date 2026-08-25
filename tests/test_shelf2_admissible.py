"""Shelf 2's entry condition, both sides of it.

Spec: `docs/superpowers/specs/2026-08-24-shelf-2-redesign.md` (commit 2f5bdd64).

The card asked for a review of "the reversibility classifier".  §5.1's finding
is that the classifier is the wrong object — not as a word list, not as a
domain list, not as a threshold, and **not as a model call returning a bit**
either.  A bit about the future behaviour of a third party cannot be audited;
it can only be believed.

So the release decision is a structural property of a stored artifact:

    An act is admissible only when undoing it requires nothing the act
    produced.  (§4)

and, because the first revision of the spec bound only the undo:

    ...AND the act's declared reach is persisted and bound to its admitted
    act type, checked at the same guard leg.  (§5.4)

Both sides are tested here.  The tests that matter most are the ones that show
the checker is NOT reading names or prose: a field called
`owner_supplied_reference` that does not resolve is refused, and a field whose
name is literally `{{confirmation_number}}` that DOES resolve is admitted.
That pair is the whole difference between a seatbelt and a word list (§5.2:
"it never inspects a field name and never parses prose").
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from brain.workflow import (
    ADMITTED_ACT_TYPES,
    ActDeclaration,
    Consequence,
    Gesture,
    Obligation,
    PlanState,
    Provenance,
    Refusal,
    UndoInput,
    UndoOf,
    UndoPlan,
    WorkflowViolation,
    admissible,
    approve_by_gesture,
    compensation_is_current,
    merge,
    new_plan,
    from_params,
    put_in_params,
)


NOW = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)
OWNER = "owner-a"
DRAFT_ID = "d4f0c2ee-0000-4000-8000-000000000001"


def act(act_type="local_draft", reach="local_store", executor="anticipy_store"):
    return ActDeclaration(act_type=act_type, reach=reach, executor=executor)


def undo_plan(*, act_type="local_draft", inputs=None, held=None, steps=None):
    """The undo for day one's one act type: discard the row we minted.

    The id is client-minted before the act exists — `new_plan` already does
    exactly this with `plan_id=plan_id or str(uuid.uuid4())` (§6.1), so the
    reference resolves at write time and nothing has to come back from
    anywhere for the undo to be complete.
    """
    return UndoPlan(
        act_type=act_type,
        steps=tuple(steps if steps is not None
                    else ("delete the draft row whose id we minted",)),
        inputs=tuple(inputs if inputs is not None else (
            UndoInput(name="draft_id", provenance=Provenance.MINTED_BY_US.value,
                      ref="draft_id"),
        )),
        held=dict(held if held is not None else {
            Provenance.MINTED_BY_US.value: {"draft_id": DRAFT_ID},
        }),
    )


def obligation(owner_ref=OWNER, channel="sms"):
    return Obligation(channel=channel, owner_ref=owner_ref, recorded_at=NOW)


def shelf2_plan(**kwargs):
    fields = dict(
        owner_ref=OWNER, lineage_key="conversation-1",
        goal="draft the email to the landlord about the boiler",
        consequence=Consequence.REVERSIBLE_LOCAL, source_event_id="event-1",
        act=act(), undo=undo_plan(), announce=obligation(), lineage_seq=1,
        plan_id="plan-1", now=NOW,
    )
    fields.update(kwargs)
    return new_plan(**fields)


# ------------------------------------------------------------- the happy lane

def test_the_one_admitted_act_type_runs_without_waiting_for_a_tap():
    """§6.1.  Day one's whole acting set is one item: a draft that is a row in
    our own store.  It reaches QUEUED with no approval, which is the entire
    point of a middle shelf."""
    p = shelf2_plan()
    assert p.consequence is Consequence.REVERSIBLE_LOCAL
    assert p.state is PlanState.QUEUED, p.reason
    assert p.approval is None, "shelf 2 does not wait for a tap"
    assert admissible(p) == ""


def test_the_admitted_set_has_exactly_one_member_on_day_one():
    """§6.1/§6.4.  'Do not widen it.'  A second member is a human decision
    behind §10.1's six conditions, and this assertion is what makes adding one
    a deliberate act rather than a convenient one."""
    assert list(ADMITTED_ACT_TYPES) == ["local_draft"], ADMITTED_ACT_TYPES
    entry = ADMITTED_ACT_TYPES["local_draft"]
    assert entry.reach == "local_store"
    assert entry.executor == "anticipy_store"
    assert entry.evidence, "a membership record that is only a name cannot " \
                           "support the checks §8.5 requires (§10.3)"


# ------------------------------------- the UNDO side: §5.2, resolution not names

def test_an_undo_that_needs_something_the_act_produced_is_refused():
    """§4, the entry condition.  The booking case, reduced: the undo needs a
    confirmation reference the counterparty will hand back.  There is no such
    value held at write time, so the reference does not resolve, so the act
    does not run."""
    p = shelf2_plan(undo=undo_plan(
        inputs=(UndoInput(name="reference", provenance="minted_by_us",
                          ref="confirmation_reference"),),
        held={"minted_by_us": {"draft_id": DRAFT_ID}}))
    assert p.state is PlanState.AWAITING_APPROVAL
    assert p.reason == Refusal.UNRESOLVED_REFERENCE.value, p.reason


def test_a_field_named_to_look_owner_supplied_is_still_refused_if_it_does_not_resolve():
    """§5.2's named defeat: 'trivially defeated by a model that names a field
    `owner_supplied_reference` and fills it from the response.'  The checker
    never reads the name, so the flattering name buys nothing."""
    p = shelf2_plan(undo=undo_plan(
        inputs=(UndoInput(name="owner_supplied_reference",
                          provenance="owner_supplied",
                          ref="owner_supplied_reference"),),
        held={"owner_supplied": {}}))
    assert p.state is PlanState.AWAITING_APPROVAL
    assert p.reason == Refusal.UNRESOLVED_REFERENCE.value, p.reason


def test_a_field_whose_name_looks_like_a_placeholder_is_admitted_when_it_resolves():
    """The other half of the same proof, and the half a word-list
    implementation always fails.  A checker that scanned for `{{...}}` or for
    the word 'confirmation' would refuse this; a checker that RESOLVES sees a
    value it already holds and lets it through."""
    p = shelf2_plan(undo=undo_plan(
        inputs=(UndoInput(name="{{confirmation_number}}",
                          provenance="minted_by_us",
                          ref="{{confirmation_number}}"),),
        held={"minted_by_us": {"{{confirmation_number}}": DRAFT_ID}}))
    assert p.state is PlanState.QUEUED, p.reason
    assert admissible(p) == ""


def test_an_unrecognised_provenance_tag_is_a_refusal_not_a_default():
    """§5.2: 'Typed and closed.  A fourth provenance tag is a schema change,
    visible in a diff, not a string a model can invent at runtime.'"""
    p = shelf2_plan(undo=undo_plan(
        inputs=(UndoInput(name="draft_id", provenance="returned_by_provider",
                          ref="draft_id"),),
        held={"returned_by_provider": {"draft_id": DRAFT_ID}}))
    assert p.state is PlanState.AWAITING_APPROVAL
    assert p.reason == Refusal.UNKNOWN_PROVENANCE.value, p.reason


def test_the_provenance_vocabulary_is_closed_at_three():
    assert [p.value for p in Provenance] == [
        "minted_by_us", "owner_supplied", "constant"]


def test_a_reference_resolving_to_an_empty_value_does_not_resolve():
    """A key that exists holding "" is a hole with a lid on it."""
    p = shelf2_plan(undo=undo_plan(
        held={"minted_by_us": {"draft_id": ""}}))
    assert p.reason == Refusal.UNRESOLVED_REFERENCE.value, p.reason


def test_an_undo_plan_that_binds_nothing_at_all_is_refused():
    """Found by attacking my own work, not by the spec.

    `_resolves` iterates the inputs, so an undo plan with NO inputs passes it
    vacuously: "delete the draft row whose id we minted" with no id bound.
    Every other leg waves it through — the act type is admitted, the reach
    agrees, the tell is recorded — and what runs unattended is an act whose
    undo cannot execute.  The admitted set records what each act type's undo
    must bind, which is the only place that knowledge can live."""
    p = shelf2_plan(undo=undo_plan(inputs=(), held={}))
    assert p.state is PlanState.AWAITING_APPROVAL
    assert p.reason == Refusal.UNDO_BINDS_NOTHING.value, p.reason


def test_an_undo_binding_only_the_wrong_provenance_is_refused():
    """A constant is not an id we minted.  Resolvable, well-formed, and not
    the thing this act type's undo has to address."""
    p = shelf2_plan(undo=undo_plan(
        inputs=(UndoInput(name="table", provenance="constant", ref="table"),),
        held={"constant": {"table": "drafts"}}))
    assert p.reason == Refusal.UNDO_BINDS_NOTHING.value, p.reason


def test_a_missing_undo_plan_is_a_refusal():
    p = shelf2_plan(undo=None)
    assert p.state is PlanState.AWAITING_APPROVAL
    assert p.reason == Refusal.NO_UNDO_PLAN.value, p.reason


def test_an_undo_plan_with_no_steps_is_a_refusal():
    """A recipe with no steps is not a recipe.  §5.2 requires a 'complete,
    executable undo plan', and the emptiest possible way to satisfy a
    structural check is to satisfy it with nothing in it."""
    p = shelf2_plan(undo=undo_plan(steps=()))
    assert p.reason == Refusal.NO_UNDO_PLAN.value, p.reason


def test_an_undo_plan_for_a_different_act_is_a_refusal():
    """An impeccable undo recipe for some other act is not an undo for this
    one.  §8.4's residual is a model writing fiction; this is the mechanical
    half we CAN catch — the fiction is about a different act type."""
    p = shelf2_plan(undo=undo_plan(act_type="local_note"))
    assert p.reason == Refusal.UNDO_ADDRESSES_ANOTHER_ACT.value, p.reason


# ---------------------------------------- the ACT side: §5.4, the label attack

def test_the_label_attack_is_refused_before_the_undo_plan_is_read():
    """§5.4, verbatim: a plan declares `act_type: local_draft` and a reach of
    `read`, its steps open Gmail, and its undo is `DELETE /drafts/{id}` where
    the id is a uuid WE minted — provenance-clean, resolvable, zero unbound
    fields.  It passes §5.2 outright.

    The reach is what refuses it, and the refusal has to happen BEFORE the
    undo plan is examined ('whatever its undo plan says, and before its undo
    plan is even examined'), so the reason returned is the reach and not
    anything about the undo."""
    p = shelf2_plan(act=act(reach="read"))
    assert p.state is PlanState.AWAITING_APPROVAL
    assert p.reason == Refusal.REACH_DISAGREES.value, (
        "the act side must refuse first; an impeccable undo plan must not be "
        f"able to answer for a reach that disagrees: {p.reason}")


def test_an_act_type_outside_the_admitted_set_is_refused():
    """§10.3: the set can only ever REFUSE.  A well-formed undo plan for an
    unadmitted act type is refused whatever it says (§8.4)."""
    p = shelf2_plan(act=act(act_type="gmail_draft"),
                    undo=undo_plan(act_type="gmail_draft"))
    assert p.reason == Refusal.ACT_TYPE_NOT_ADMITTED.value, p.reason


def test_a_plan_with_no_act_declaration_at_all_is_refused():
    """Floor polarity (§5.2): 'no verdict' is the same answer as 'there is
    money here'.  Silence never releases."""
    p = shelf2_plan(act=None)
    assert p.reason == Refusal.ACT_TYPE_NOT_ADMITTED.value, p.reason


def test_the_browser_executor_may_not_run_an_admitted_act():
    """§8.7 / §10.3.  'An act type executed by a general browser agent has no
    declared reach worth the name — the declaration is a label attached to a
    process that can do anything the session can do.'  The admitted set names
    the executor, and a plan naming a different one is refused."""
    p = shelf2_plan(act=act(executor="browser_agent"))
    assert p.reason == Refusal.EXECUTOR_DISAGREES.value, p.reason


def test_the_declared_reach_is_persisted_and_survives_a_round_trip():
    """§5.4 requirement 3: 'A check that runs only in the Python that minted
    the plan is not a check; it is a comment.'  `touches` lives for the
    duration of one Python call and is then gone (§9); this must not."""
    p = shelf2_plan()
    back = from_params(put_in_params({}, p))
    assert back.act == p.act
    assert back.act.reach == "local_store"
    assert back.undo == p.undo
    assert back.announce.owner_ref == OWNER
    assert back.lineage_seq == 1


# --------------------------------------------------- §8.3, the durable tell

def test_an_act_with_no_recorded_announcement_obligation_is_refused():
    """§8.3: 'an act may not run unattended unless its announcement is on the
    same durable path as the act.'  An act that ran and was not announced is
    moment 49 — he never learns it happened, so he never undoes it."""
    p = shelf2_plan(announce=None)
    assert p.reason == Refusal.NO_ANNOUNCE_OBLIGATION.value, p.reason


def test_an_announcement_aimed_at_anyone_but_the_owner_is_refused():
    """§10.1 condition 4, which also binds the tell (§8.2): 'an act whose
    announcement would reach anyone but the owner is Shelf 3.'  Absolute."""
    p = shelf2_plan(announce=obligation(owner_ref="somebody-else"))
    assert p.reason == Refusal.ANNOUNCE_LEAVES_THE_OWNER.value, p.reason


# ----------------------------------------------------------- §7.4, LIFO order

def test_an_unordered_act_cannot_be_undone_in_order():
    """§7.4's law needs a position in the lineage to compare.  Floor polarity:
    'if we cannot determine the ordering, we refuse the undo and ask.'"""
    p = shelf2_plan(lineage_seq=0)
    assert p.reason == Refusal.UNORDERED_LINEAGE.value, p.reason


def test_undoing_the_head_of_the_lineage_is_allowed():
    ref = UndoOf(plan_id="plan-1", version=1, effect_key="eff", act_seq=2)
    assert compensation_is_current(undo_of=ref, ran_seqs=[1, 2]) == ""


def test_undoing_an_act_a_later_act_has_already_overwritten_is_refused():
    """§7.4's worked example.  Act A drafts the boiler email (seq 1); act B
    revises it in place (seq 2).  Undo(A) is 'delete row d'; undo(B) is
    'restore row d to version 1'.  Both undos required nothing their act
    produced and both receipts are honest — the COMPOSITION is what fails, and
    a draft he was told was gone comes back."""
    ref = UndoOf(plan_id="plan-1", version=1, effect_key="eff", act_seq=1)
    assert compensation_is_current(undo_of=ref, ran_seqs=[1, 2]) == \
        Refusal.SUPERSEDED_BY_LATER_ACT.value


def test_a_later_act_that_has_not_run_does_not_block_the_undo():
    """The law is about acts that have RUN, not acts that were minted.  A
    queued successor has changed nothing yet."""
    ref = UndoOf(plan_id="plan-1", version=1, effect_key="eff", act_seq=1)
    assert compensation_is_current(undo_of=ref, ran_seqs=[1]) == ""


def test_an_unreadable_lineage_position_refuses_the_undo():
    """Both refuse, and they are DIFFERENT refusals.  §10.5(a): a rule that
    cannot tell our own store blinking from the counterparty refusing demotes
    the shelf permanently after one outage on a Tuesday, and because the
    demotion is expensive to reverse by design, nobody reverses it."""
    ref = UndoOf(plan_id="plan-1", version=1, effect_key="eff", act_seq=1)
    assert compensation_is_current(undo_of=ref, ran_seqs=["later"]) == \
        Refusal.LINEAGE_UNREADABLE.value
    assert compensation_is_current(undo_of=None, ran_seqs=[]) == \
        Refusal.UNORDERED_LINEAGE.value


# -------------------------------------------------- §7.3, the tap has no words

def test_a_tap_is_recorded_as_a_gesture_and_never_as_owner_words():
    """§7.3.  `Approval.owner_words` exists because he said them.  Stuffing
    'tapped undo' into it would put a sentence he never said into the one
    field whose entire purpose is that he did — and it is one line of Swift
    away at all times."""
    p = shelf2_plan(consequence=Consequence.CONSEQUENTIAL, act=None,
                    undo=None, announce=None, lineage_seq=0)
    tap = Gesture(kind="tap", actor=OWNER, plan_id=p.plan_id,
                  plan_version=p.version, scope_digest=p.scope_digest,
                  made_at=NOW)
    out = approve_by_gesture(p, expected_version=p.version, gesture=tap,
                             now=NOW)
    assert out.state is PlanState.QUEUED
    assert out.approval.owner_words == "", (
        "a gesture must not manufacture words he never said")
    assert out.approval.gesture == tap
    assert out.approved_for_current_version


def test_a_gesture_bound_to_another_version_is_refused():
    p = shelf2_plan(consequence=Consequence.CONSEQUENTIAL, act=None,
                    undo=None, announce=None, lineage_seq=0)
    stale = Gesture(kind="tap", actor=OWNER, plan_id=p.plan_id,
                    plan_version=p.version + 1, scope_digest=p.scope_digest,
                    made_at=NOW)
    with pytest.raises(WorkflowViolation):
        approve_by_gesture(p, expected_version=p.version, gesture=stale,
                           now=NOW)


def test_a_gesture_of_an_unknown_kind_is_refused():
    p = shelf2_plan(consequence=Consequence.CONSEQUENTIAL, act=None,
                    undo=None, announce=None, lineage_seq=0)
    weird = Gesture(kind="voice", actor=OWNER, plan_id=p.plan_id,
                    plan_version=p.version, scope_digest=p.scope_digest,
                    made_at=NOW)
    with pytest.raises(WorkflowViolation):
        approve_by_gesture(p, expected_version=p.version, gesture=weird,
                           now=NOW)


def test_an_unauthenticated_gesture_is_refused():
    p = shelf2_plan(consequence=Consequence.CONSEQUENTIAL, act=None,
                    undo=None, announce=None, lineage_seq=0)
    anon = Gesture(kind="tap", actor="", plan_id=p.plan_id,
                   plan_version=p.version, scope_digest=p.scope_digest,
                   made_at=NOW)
    with pytest.raises(WorkflowViolation):
        approve_by_gesture(p, expected_version=p.version, gesture=anon,
                           now=NOW)


def test_spoken_approval_still_requires_the_owners_actual_words():
    """The seam must not become a way to skip words on the speech path."""
    from brain.workflow import approve
    p = shelf2_plan(consequence=Consequence.CONSEQUENTIAL, act=None,
                    undo=None, announce=None, lineage_seq=0)
    with pytest.raises(WorkflowViolation):
        approve(p, expected_version=p.version, owner_words="   ", now=NOW)


# -------------------------------------- the scar: one corrupt row, again (§3)

def test_a_stored_row_whose_sub_objects_throw_still_parses():
    """The mutation battery caught this: the first version of this test fed
    the parser a STRING, which the isinstance check turned away before any
    builder ran, so deleting the try/except changed nothing and the test still
    passed.  These blobs are the right shape and throw INSIDE the builder — a
    date that is not a date, a version that is not a number — which is what a
    truncated write or a hand-edited record actually looks like."""
    p = shelf2_plan()
    blob = put_in_params({}, p)
    blob["_workflow"]["announce"] = {"channel": "sms", "owner_ref": OWNER,
                                     "recorded_at": "not-a-date-at-all"}
    blob["_workflow"]["undo_of"] = {"plan_id": "x", "version": "not-a-number",
                                    "effect_key": "e", "act_seq": 1}
    blob["_workflow"]["approval"] = None
    back = from_params(blob)
    assert back is not None, "a malformed row must be readable, never a throw"
    assert back.announce is None and back.undo_of is None
    assert admissible(back) == Refusal.NO_ANNOUNCE_OBLIGATION.value


def test_a_stored_row_with_a_broken_undo_plan_still_parses():
    """§3's surviving rule: 'assert_valid must never grow a rule that can be
    false for a legitimately stored row.'  One malformed row threw out of
    hear(), the event was marked error and never retried, 'and nothing was
    ever said to him about any of it.'

    So a row whose undo plan is garbage is READABLE and REFUSED — never
    unparseable."""
    p = shelf2_plan()
    blob = put_in_params({}, p)
    blob["_workflow"]["undo"] = "not an object at all"
    blob["_workflow"]["act"] = ["also", "not", "an", "object"]
    back = from_params(blob)
    assert back is not None
    assert back.undo is None and back.act is None
    assert admissible(back) == Refusal.ACT_TYPE_NOT_ADMITTED.value


def test_a_stored_succeeded_shelf2_row_is_not_re_parked_by_the_test():
    """The admissible test is a TRANSITION check, not a validity rule.  A row
    that already ran and succeeded must keep its state on the way back out of
    the database, or the cautious default manufactures an illegal plan — the
    exact mistake `_state_after_unreadable` was written to avoid."""
    p = shelf2_plan()
    blob = put_in_params({}, p)
    blob["_workflow"]["state"] = "succeeded"
    blob["_workflow"]["receipt"] = {
        "effect_key": p.effect_key, "summary": "drafted",
        "evidence": ["row deleted"], "verified": True,
        "recorded_at": NOW.isoformat(),
    }
    blob["_workflow"]["undo"] = None      # evidence lost after the fact
    back = from_params(blob)
    assert back.state is PlanState.SUCCEEDED


# --------------------------------------------------- amendment re-earns the lane

def test_amending_a_shelf2_plan_re_runs_the_test():
    """merge() invalidates approval; it must also re-decide the lane."""
    p = shelf2_plan()
    out = merge(p, expected_version=p.version, goal="draft it more politely",
                now=NOW)
    assert out.state is PlanState.QUEUED, out.reason


def test_amending_a_refused_act_does_not_promote_it_into_the_unattended_lane():
    """A HOLE, found by mutating the fix out and watching nothing fail.

    merge() recomputes the next state from the consequence alone: no missing
    facts and a Shelf 2 consequence used to mean QUEUED.  So an act that was
    refused at mint — no undo plan, a reach that disagrees, anything — could
    be handed the unattended lane by an ordinary amendment it had nothing to
    do with.  A correction to the goal is not a safety finding."""
    refused = shelf2_plan(undo=None)
    assert refused.state is PlanState.AWAITING_APPROVAL
    out = merge(refused, expected_version=refused.version,
                goal="draft it more politely", now=NOW)
    assert out.state is PlanState.AWAITING_APPROVAL, (
        "an amendment promoted a refused act into the lane that runs without "
        f"a tap: {out.reason}")
    assert out.reason == Refusal.NO_UNDO_PLAN.value, out.reason


def test_a_shelf2_plan_still_missing_a_fact_stays_a_draft():
    """The floor must not swallow the OTHER reason a plan cannot run.

    DRAFT means "I do not have enough to act and I am going to ask you";
    AWAITING_APPROVAL means "this is ready, say yes".  Conflating them puts a
    card in front of him asking him to approve a plan with a hole in it.  So
    the Shelf 2 floor only ever acts on work that was otherwise about to run,
    and a missing fact keeps its own answer."""
    p = shelf2_plan(required=("send_time",), undo=None)
    assert p.state is PlanState.DRAFT, p.reason
    assert "missing" in p.reason
    out = merge(p, expected_version=p.version, goal="draft it politely",
                now=NOW)
    assert out.state is PlanState.DRAFT, (
        "a plan that still lacks a required fact was relabelled as ready for "
        f"approval, and the Shelf 2 refusal buried the real reason: "
        f"{out.state} / {out.reason}")


def test_a_refused_act_still_runs_once_he_actually_taps():
    """The floor sends refused work to Shelf 3; Shelf 3 is not a graveyard.
    §5.2: 'the work goes to Shelf 3 and waits for a tap.'  This is that tap."""
    from brain.workflow import approve
    refused = shelf2_plan(undo=None)
    out = approve(refused, expected_version=refused.version,
                  owner_words="yeah, draft it anyway", now=NOW)
    assert out.state is PlanState.QUEUED
    assert out.approval.owner_words == "yeah, draft it anyway"


def test_lease_recovery_does_not_hand_a_row_that_lost_its_undo_back_to_the_lane():
    """A stored row can lose its undo evidence — that is the whole reason
    from_dict parses tolerantly.  Recovery from a dead executor recomputes
    QUEUED, so it is a second door into the unattended lane and needs the same
    floor across it."""
    from brain.workflow import claim, recover_expired
    p = shelf2_plan()
    running = claim(p, expected_version=p.version, actor_id="worker-1",
                    lease_seconds=5, now=NOW)
    stripped = from_params(put_in_params({}, running))
    blob = put_in_params({}, stripped)
    blob["_workflow"]["undo"] = None
    lost = from_params(blob)
    later = datetime(2026, 8, 25, 12, 30, tzinfo=timezone.utc)
    out = recover_expired(lost, now=later)
    assert out.state is PlanState.AWAITING_APPROVAL, (
        f"a row with no undo plan was recovered straight into the "
        f"unattended lane: {out.state} / {out.reason}")
    assert out.reason == Refusal.NO_UNDO_PLAN.value, out.reason


# ------------------------------------------------------- the refusal vocabulary

def test_every_refusal_reason_is_enumerated_never_free_text():
    """§11: 'Reasons are the enumerated refusal causes of §5.2 and §8.5's a–f,
    not free text.'  A shelf that refuses in prose cannot be widened on
    evidence, because nobody can count what it refused."""
    causes = {r.value for r in Refusal}
    for kwargs in ({"act": None}, {"undo": None}, {"announce": None},
                   {"lineage_seq": 0}, {"act": act(reach="read")},
                   {"act": act(act_type="gmail_draft")},
                   {"act": act(executor="browser_agent")}):
        p = shelf2_plan(**kwargs)
        assert p.reason in causes, p.reason
        assert p.reason.startswith("shelf2."), p.reason
