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


def test_tokenless_claim_refuses_an_owner_ref_it_cannot_verify():
    """SUPERSEDES an earlier rule of mine, and the reason matters.

    On 2026-08-14 a real stranger could not pair because the tokenless
    allowlist rejected the app's body, so I added owner_ref to it. That was
    the wrong repair: nothing on the tokenless path can verify an owner_ref,
    and the adversarial hunt (2026-08-16) traced the whole attack — pair
    codes are six digits with no rate limit, so a stranger walks them, reads
    a real owner id off any unpaired agent row, registers their own agent
    (no credential required), and claims it against the VICTIM's account.
    From that moment their browser receives the victim's jobs.

    The pairing failure that prompted the original fix is handled properly
    instead: the app sets authToken and accountID together at sign-in, so its
    claim carries an Authorization header and takes the signed-in branch,
    which binds owner_ref === authId. A claim arriving with no usable session
    now fails LOUDLY and tells the person to pair from the signed-in app,
    rather than pairing them to a stranger.
    """
    source = (ROOT / "backend/pb_hooks/guard.pb.js").read_text()
    tokenless = source.split("// 3. Claiming", 1)[1]
    allowed = tokenless.split("const allowed = {", 1)[1].split("}", 1)[0]
    assert "owner_ref" not in allowed, (
        "an owner_ref that nothing can verify must not be tokenlessly writable")
    assert '"owner_ref" in b' in tokenless and "pair from the signed-in app" in tokenless, (
        "and the refusal must say what to do instead")
    for k in ("owner: 1", "paired: 1", "last_seen: 1", "browser: 1"):
        assert k in allowed, f"{k} must stay claimable so pairing still works"
    assert "b.owner_ref === authId" in source, (
        "the signed-in path remains the one honest way to accept an owner_ref")


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
