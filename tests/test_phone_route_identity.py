"""A phone authority check must retain the complete international identity.

All numbers here are synthetic; transport and backend operations are doubled.
These checks prove comparison/authorization behavior, not handset delivery.
"""
from types import SimpleNamespace

import pytest

from brain import worker as W
from brain.conversation import MessageTransport


@pytest.mark.parametrize("first,second", [
    ("+11234567890", "+441234567890"),
    ("+331234567890", "+441234567890"),
    ("0011234567890", "+441234567890"),
])
def test_different_international_prefixes_never_share_authority(first, second):
    assert not W.same_phone(first, second)
    assert not W.same_phone(second, first)


@pytest.mark.parametrize("formatted,canonical", [
    ("+16045550101", "+16045550101"),
    (" +1 (604) 555-0101 ", "+16045550101"),
    ("+44 20 7946 0123", "+442079460123"),
    ("001 604 555 0101", "+16045550101"),
    ("+1.604.555.0101", "+16045550101"),
])
def test_complete_international_numbers_allow_harmless_formatting(formatted, canonical):
    assert W.same_phone(formatted, canonical)
    assert W.same_phone(canonical, formatted)


@pytest.mark.parametrize("malformed", [
    "", None, 16045550101, "6045550101", "16045550101", "+6045550",
    "+016045550101", "+1604555010112345", "++16045550101",
    "+1+6045550101", "+1 (604) 555-0101 ext 8", "tel:+16045550101",
    "+١٦٠٤٥٥٥٠١٠١", "+1\n6045550101", "owner", "app:owner-one",
])
def test_unknown_or_malformed_number_cannot_authorize_even_itself(malformed):
    assert not W.same_phone(malformed, malformed)
    assert not W.same_phone(malformed, "+16045550101")
    assert not W.same_phone("+16045550101", malformed)


def test_final_transport_guard_rejects_changed_country_with_same_local_suffix(monkeypatch):
    old = "+11234567890"
    owner = SimpleNamespace(owner_ref="phone-identity-owner", owner_phone=old)
    monkeypatch.setattr(W, "fetch_owner_phone", lambda ref: "+441234567890")
    sends = []
    arm = SimpleNamespace(text=lambda *a, **kw: sends.append((a, kw)))
    transport = MessageTransport(arm, before_send=lambda destination:
        W.canonical_phone_allows_effect(owner, destination))

    assert transport.send(old, "Synthetic test reply") is None
    assert sends == []
    assert owner.owner_phone == "+441234567890"


def test_final_transport_guard_preserves_full_number_formatting(monkeypatch):
    owner = SimpleNamespace(owner_ref="phone-identity-owner", owner_phone="")
    monkeypatch.setattr(W, "fetch_owner_phone", lambda ref: "+16045550101")
    sends = []
    arm = SimpleNamespace(text=lambda *a, **kw: sends.append((a, kw)) or {"sid": "fixture-only"})
    transport = MessageTransport(arm, before_send=lambda destination:
        W.canonical_phone_allows_effect(owner, destination))

    assert transport.send("+1 (604) 555-0101", "Synthetic test reply") == {"sid": "fixture-only"}
    assert len(sends) == 1


def test_inbound_same_suffix_from_other_country_stops_before_claim_or_reasoning(monkeypatch):
    owner = SimpleNamespace(owner_ref="phone-identity-owner", owner_phone="+441234567890")
    monkeypatch.setattr(W, "fetch_owner_phone", lambda ref: owner.owner_phone)
    marks = []
    monkeypatch.setattr(W, "mark_processed", lambda eid, state, **kw: marks.append((eid, state)))
    monkeypatch.setattr(W, "claim", lambda *a: pytest.fail("wrong sender was claimed"))
    monkeypatch.setattr(W, "connection_command", lambda *a: pytest.fail("wrong sender reached connections"))
    convo = SimpleNamespace(on_reply=lambda *a: pytest.fail("wrong sender reached reasoning"))
    event = {"id": "phone-country-collision", "kind": "sms_reply",
             "owner_ref": owner.owner_ref, "goal": "+11234567890",
             "text": "Synthetic test input"}

    assert W.handle_inbound(event, convo, owner) == "ignored_nonowner"
    assert marks == [(event["id"], "ignored_nonowner")]
