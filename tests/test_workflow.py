from datetime import datetime, timedelta, timezone

import pytest

from brain.workflow import (
    Consequence,
    PlanState,
    WorkflowViolation,
    approve,
    cancel,
    claim,
    fail,
    heartbeat,
    merge,
    needs_user,
    new_plan,
    from_params,
    put_in_params,
    recover_expired,
    succeed,
)


NOW = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)


def plan(consequence=Consequence.CONSEQUENTIAL, required=(), facts=None):
    return new_plan(owner_ref="owner-a", lineage_key="conversation-1",
                    goal="submit the warranty claim",
                    consequence=consequence, source_event_id="event-1",
                    required=required, facts=facts, plan_id="plan-1", now=NOW)


def approved_plan(**kwargs):
    p = plan(**kwargs)
    return approve(p, expected_version=p.version,
                   owner_words="yes, submit that claim", now=NOW)


def running_plan(**kwargs):
    p = approved_plan(**kwargs)
    return claim(p, expected_version=p.version, actor_id="chrome-a",
                 token="lease-a", lease_seconds=60, now=NOW)


def test_read_only_work_queues_without_approval():
    p = plan(consequence=Consequence.READ_ONLY)
    assert p.state == PlanState.QUEUED
    assert p.approval is None
    p.assert_valid()


def test_consequential_work_waits_for_approval():
    assert plan().state == PlanState.AWAITING_APPROVAL


def test_missing_fact_keeps_plan_in_draft():
    p = plan(required=("serial_number",))
    assert p.state == PlanState.DRAFT
    assert p.missing == ("serial_number",)


def test_approval_cannot_invent_a_required_fact():
    p = plan(required=("serial_number",))
    with pytest.raises(WorkflowViolation, match="missing required"):
        approve(p, expected_version=1, owner_words="yes")


def test_detail_and_approval_are_one_atomic_new_version():
    p = plan(required=("serial_number",))
    p = approve(p, expected_version=1, owner_words="serial 1234, go ahead",
                changes={"serial_number": "1234"}, now=NOW)
    assert p.version == 2
    assert p.state == PlanState.QUEUED
    assert p.approval.plan_version == 2
    assert p.approved_for_current_version


def test_stale_approval_is_rejected():
    p = plan()
    p = merge(p, expected_version=1, facts={"colour": "black"},
              source_event_id="event-2", now=NOW)
    with pytest.raises(WorkflowViolation, match="stale"):
        approve(p, expected_version=1, owner_words="yes")


def test_correction_invalidates_previous_approval():
    p = approved_plan()
    p = merge(p, expected_version=1, facts={"appointment": "4pm"},
              source_event_id="event-2", now=NOW)
    assert p.version == 2
    assert p.state == PlanState.AWAITING_APPROVAL
    assert p.approval is None


def test_duplicate_source_event_is_not_duplicated():
    p = plan()
    p = merge(p, expected_version=1, source_event_id="event-1", now=NOW)
    assert p.source_event_ids == ("event-1",)


def test_only_queued_work_can_be_claimed():
    with pytest.raises(WorkflowViolation, match="queued"):
        claim(plan(), expected_version=1, actor_id="chrome-a")


def test_claim_creates_one_lease_and_attempt():
    p = running_plan()
    assert p.state == PlanState.RUNNING
    assert p.lease.token == "lease-a"
    assert p.attempts == 1


def test_second_claim_cannot_run_concurrently():
    p = running_plan()
    with pytest.raises(WorkflowViolation, match="queued"):
        claim(p, expected_version=p.version, actor_id="chrome-b")


def test_wrong_actor_cannot_heartbeat():
    p = running_plan()
    with pytest.raises(WorkflowViolation, match="wrong lease"):
        heartbeat(p, lease_token="lease-b", now=NOW)


def test_heartbeat_extends_the_same_lease():
    p = running_plan()
    p = heartbeat(p, lease_token="lease-a", lease_seconds=300,
                  now=NOW + timedelta(seconds=30))
    assert p.lease.token == "lease-a"
    assert p.lease.expires_at == NOW + timedelta(seconds=330)


def test_completion_without_evidence_is_impossible():
    p = running_plan()
    with pytest.raises(WorkflowViolation, match="evidence"):
        succeed(p, lease_token="lease-a", summary="done",
                evidence=(), verified=True)


def test_completion_from_wrong_attempt_is_impossible():
    p = running_plan()
    with pytest.raises(WorkflowViolation, match="active attempt"):
        succeed(p, lease_token="old-lease", summary="done",
                evidence=("confirmation 123",), verified=True)


def test_verified_receipt_is_bound_to_the_exact_effect():
    p = running_plan()
    expected = p.effect_key
    p = succeed(p, lease_token="lease-a", summary="claim submitted",
                evidence=("claim id A-123",), verified=True, now=NOW)
    assert p.state == PlanState.SUCCEEDED
    assert p.receipt.effect_key == expected


def test_cancelled_work_cannot_be_completed():
    p = cancel(running_plan(), reason="owner said stop", now=NOW)
    with pytest.raises(WorkflowViolation):
        succeed(p, lease_token="lease-a", summary="done",
                evidence=("something",), verified=True)


def test_cancel_is_idempotent():
    p = cancel(plan(), reason="stop", now=NOW)
    assert cancel(p, reason="stop again", now=NOW) == p


def test_executor_can_park_for_a_real_question():
    p = needs_user(running_plan(), lease_token="lease-a",
                   reason="which repair location?", now=NOW)
    assert p.state == PlanState.NEEDS_USER
    assert p.lease is None


def test_failed_work_stays_visible_and_terminal():
    p = fail(running_plan(), lease_token="lease-a",
             reason="site unavailable", now=NOW)
    assert p.state == PlanState.FAILED
    assert p.reason == "site unavailable"


def test_expired_read_before_write_attempt_can_retry():
    p = running_plan()
    p = recover_expired(p, now=NOW + timedelta(seconds=61))
    assert p.state == PlanState.QUEUED
    assert p.lease is None


def test_uncertain_external_effect_never_retries_blindly():
    p = running_plan()
    p = recover_expired(p, now=NOW + timedelta(seconds=61),
                        external_effect_uncertain=True)
    assert p.state == PlanState.NEEDS_USER
    assert "verify" in p.reason


def test_retry_budget_stops_infinite_browser_loops():
    p = running_plan()
    p = recover_expired(p, now=NOW + timedelta(seconds=61))
    p = claim(p, expected_version=p.version, actor_id="chrome-a",
              token="lease-b", lease_seconds=60,
              now=NOW + timedelta(seconds=62))
    p = recover_expired(p, now=NOW + timedelta(seconds=123))
    p = claim(p, expected_version=p.version, actor_id="chrome-a",
              token="lease-c", lease_seconds=60,
              now=NOW + timedelta(seconds=124))
    p = recover_expired(p, now=NOW + timedelta(seconds=185))
    assert p.state == PlanState.FAILED
    assert p.attempts == 3


def test_plan_serialization_contains_no_implicit_authority():
    p = plan()
    data = p.as_dict()
    assert data["approval"] is None
    assert data["state"] == "awaiting_approval"
    assert data["owner_ref"] == "owner-a"


def test_cross_owner_identity_is_immutable():
    p = plan()
    changed = dict(p.as_dict(), owner_ref="owner-b")
    assert changed["owner_ref"] != p.owner_ref
    # There is intentionally no transition function that accepts owner_ref.
    assert all(fn.__name__ not in {"transfer", "change_owner"}
               for fn in (merge, approve, claim, heartbeat, needs_user,
                          succeed, fail, cancel, recover_expired))


def test_plan_round_trips_through_job_params():
    p = approved_plan()
    restored = from_params(put_in_params({"source": "heard"}, p))
    assert restored == p
    assert restored.approved_for_current_version


def test_job_fields_keep_legacy_and_canonical_states_together():
    p = approved_plan()
    fields = p.job_fields()
    assert fields["status"] == "queued"
    assert fields["workflow_state"] == "queued"
    assert fields["workflow_version"] == 1
    assert fields["approval"]
    assert not fields["receipt"]
