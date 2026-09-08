"""Unavailable SMS ownership is retryable, never permission or a rejection."""
import contextlib
from types import SimpleNamespace

import pytest

from brain import worker as W

PHONE = "+16045550101"
NEW_PHONE = "+16045550202"


@pytest.fixture
def rig(monkeypatch):
    seen = {"marks": [], "claims": [], "replies": [], "connections": [], "events": []}
    monkeypatch.setattr(W, "mark_processed", lambda eid, decision, **kw: seen["marks"].append((eid, decision)))
    monkeypatch.setattr(W, "claim", lambda eid: seen["claims"].append(eid) or True)
    monkeypatch.setattr(W, "post_event", lambda *a, **kw: seen["events"].append(a))
    monkeypatch.setattr(W, "connection_command", lambda *a: seen["connections"].append(a) or "not_for_us")
    monkeypatch.setattr(W.backend, "get", lambda *a, **kw: pytest.fail("offline test attempted backend access"))

    def on_reply(phone, text):
        seen["replies"].append((phone, text))
        return {"intent": "chat", "reply": "Recorded."}

    convo = SimpleNamespace(on_reply=on_reply, reply_in_app=contextlib.nullcontext)
    owner = SimpleNamespace(owner_ref="owner-one", owner_phone=PHONE)
    event = {"id": "sms-one", "kind": "sms_reply", "text": "yes", "goal": PHONE,
             "owner_ref": "owner-one"}
    return owner, event, convo, seen


@pytest.mark.parametrize("cached", [PHONE, ""])
def test_unknown_owner_phone_leaves_the_original_sms_unclaimed_and_retryable(monkeypatch, rig, cached):
    owner, event, convo, seen = rig
    owner.owner_phone = cached
    monkeypatch.setattr(W, "fetch_owner_phone", lambda ref: None)

    assert W.handle_inbound(event, convo, owner) == "unclaimed"

    assert owner.owner_phone == "", "an unverifiable outbound cache stays disabled"
    assert all(not actions for actions in seen.values())


def test_profile_recovery_processes_the_same_sms_once(monkeypatch, rig):
    owner, event, convo, seen = rig
    answers = iter([None, PHONE])
    reads = []

    def canonical(ref):
        reads.append(ref)
        return next(answers)

    monkeypatch.setattr(W, "fetch_owner_phone", canonical)
    assert W.handle_inbound(event, convo, owner) == "unclaimed"
    assert W.handle_inbound(event, convo, owner) == "chat"
    assert reads == [owner.owner_ref, owner.owner_ref]
    assert seen["claims"] == [event["id"]]
    assert seen["marks"] == [(event["id"], "chat")]
    assert seen["replies"] == [(PHONE, "yes")]


@pytest.mark.parametrize("canonical", ["", NEW_PHONE])
def test_verified_revocation_or_mismatch_cannot_use_a_stale_cached_match(monkeypatch, rig, canonical):
    owner, event, convo, seen = rig
    monkeypatch.setattr(W, "fetch_owner_phone", lambda ref: canonical)

    assert W.handle_inbound(event, convo, owner) == "ignored_nonowner"

    assert seen["marks"] == [(event["id"], "ignored_nonowner")]
    assert not seen["claims"] and not seen["replies"] and not seen["connections"]


def test_new_canonical_number_is_allowed_before_the_periodic_cache_refresh(monkeypatch, rig):
    owner, event, convo, seen = rig
    event["goal"] = NEW_PHONE
    monkeypatch.setattr(W, "fetch_owner_phone", lambda ref: NEW_PHONE)

    assert W.handle_inbound(event, convo, owner) == "chat"
    assert seen["replies"] == [(NEW_PHONE, "yes")]


def test_sms_without_sender_cannot_borrow_the_canonical_owner_number(monkeypatch, rig):
    owner, event, convo, seen = rig
    event["goal"] = ""
    monkeypatch.setattr(W, "fetch_owner_phone", lambda ref: PHONE)

    assert W.handle_inbound(event, convo, owner) == "ignored_nonowner"
    assert not seen["claims"] and not seen["replies"]


def test_signed_in_app_reply_has_no_phone_lookup_dependency(monkeypatch, rig):
    owner, event, convo, seen = rig
    event.update(kind="app_reply", goal="")
    owner.owner_phone = ""
    monkeypatch.setattr(W, "fetch_owner_phone", lambda ref: pytest.fail("app identity is not a phone lookup"))

    assert W.handle_inbound(event, convo, owner) == "chat"
    assert seen["replies"] == [("app:owner-one", "yes")]
