"""The pairing claim must accept the app's real request shape and refuse
blank owners — on both the guard and the phone.

Found live 2026-08-14, first real stranger day-zero run: the iPhone app has
always claimed a pair code with {owner, owner_ref, paired}, but the guard's
tokenless claim allowlist did not include owner_ref, so any claim arriving
without live account auth died 403 — silently, from the customer's chair.
Separately, a claim naming an empty owner "succeeded" into a record the
extension can never match a job against: phone paired, browser orphaned.

Behavior was verified live against a service-token rig (register -> blank
claim 403 -> named claim passes -> re-claim-after-paired 403 -> heartbeat
still allowed). These asserts pin the load-bearing lines so a refactor that
drops them fails fast.
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_tokenless_claim_allowlist_accepts_the_apps_real_body():
    source = (ROOT / "backend/pb_hooks/guard.pb.js").read_text()
    tokenless = source.split("// 3. Claiming", 1)[1]
    assert "owner_ref: 1" in tokenless, (
        "the app sends {owner, owner_ref, paired}; without owner_ref in the "
        "allowlist no tokenless claim can ever succeed")


def test_blank_owner_claims_are_refused_everywhere():
    source = (ROOT / "backend/pb_hooks/guard.pb.js").read_text()
    signed_in = source.split("who has actually signed in", 1)[1].split("// 3. Claiming", 1)[0]
    tokenless = source.split("// 3. Claiming", 1)[1]
    for name, part in (("signed-in", signed_in), ("tokenless", tokenless)):
        assert 'b.owner.trim() !== ""' in part, (
            f"the {name} claim path no longer bans blank owners — the "
            "phone-paired/browser-orphaned split-brain is back")


def test_paired_records_still_cannot_be_reclaimed_tokenlessly():
    source = (ROOT / "backend/pb_hooks/guard.pb.js").read_text()
    tokenless = source.split("// 3. Claiming", 1)[1]
    assert '!rec.getBool("paired")' in tokenless
    assert '"owner" in b || "paired" in b' in tokenless


def test_phone_verifies_the_claim_it_just_made():
    source = (ROOT / "app/ios/Anticipy/Backend/AnticipyBackend.swift").read_text()
    pair = source.split("func pairAgent", 1)[1].split("func unpairAgent", 1)[0]
    assert "guard !owner.isEmpty" in pair, "a blank owner must fail loudly on the phone too"
    assert 'saved["owner"] as? String == owner' in pair, (
        "pairAgent must read the record back — paired is illegal without evidence")
    assert 'saved["paired"] as? Bool == true' in pair
