"""Two privacy P0s from the adversarial hunt, both confirmed by independent
refuters, both about speech captured with no owner to own it.

1. signOut() cleared the credentials and nothing else. The AVAudioEngine tap
   stayed installed, so the phone kept transcribing the room while showing
   the sign-in door — and the views that normally stop the microphone are
   torn down the instant isSignedIn flips, so nothing was left to do it.
   Reached by an ordinary expired token: refresh() 401s and calls signOut().

2. The unsent-line queue is @AppStorage and survives sign-out by design,
   while pushEvent stamps owner_ref from whoever is signed in AT FLUSH TIME.
   One person's private speech, buffered while offline, was posted into the
   NEXT person's account when they signed in on the same phone — a path the
   sign-up flow explicitly allows.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent
APP = (ROOT / "app/ios/Anticipy/AnticipyApp.swift").read_text()


def test_signing_out_stops_the_microphone():
    body = APP.split("func signOut() {", 1)[1].split("}", 1)[0]
    assert "listener.stop()" in body, (
        "signing out must close the ears, not just drop the credentials")
    assert 'authToken = ""' in body and 'accountID = ""' in body


def test_keep_listening_stays_the_persons_own_preference():
    # Stopping the mic must not silently flip their standing choice off; it is
    # honoured again when they sign back in.
    body = APP.split("func signOut() {", 1)[1].split("}", 1)[0]
    assert "keepListening = false" not in body


def test_nothing_is_captured_without_an_owner():
    heard = APP.split("try await backend.pushEvent(kind: \"transcript\"", 1)[0]
    tail = heard[-600:]
    assert 'guard !accountID.isEmpty else { return }' in tail, (
        "a line spoken with no signed-in account must not be pushed or queued")


def test_a_buffered_line_remembers_whose_words_it_is():
    decl = APP.split("private struct BufferedLine: Codable {", 1)[1].split("}", 1)[0]
    assert "account" in decl, "a queued line must carry the account that captured it"
    # every construction site stamps it
    for frag in ("account: accountID", "account: nil"):
        assert frag in APP


def test_the_queue_is_never_flushed_into_someone_elses_account():
    flush = APP.split("private func flushUnsent() async {", 1)[1][:900]
    assert "!accountID.isEmpty" in flush, "no owner, no flush"
    assert "line.account == accountID" in flush, (
        "only lines captured by THIS account may be posted to it")


# ------------------------- venting is not an instruction

def test_a_decline_must_be_the_message_not_a_word_inside_one():
    """Live 2026-08-16: the browser asked which Earls location, he never saw
    it (she could not text), he said out loud how sick of it he was — and the
    job came back cancelled. He had pressed nothing he remembered pressing.

    The matcher substring-searched for "no", "leave it", "stop it" ANYWHERE
    in the text, so a mouthful of frustration about the assistant could kill
    work he still wanted. Ending an errand is a decision and needs the
    brevity of one; anything longer belongs to the brain, which reads meaning
    rather than characters.
    """
    body = APP.split("static func answerThatEndsTheErrand", 1)[1].split("\n    }", 1)[0]
    # This asserted "wordCount <= 8" — the shape of the FIRST fix, not the
    # requirement. Length turned out to be the wrong condition entirely: the
    # sentences that actually killed live errands are all SHORT ("leave it
    # with the concierge", "drop it off at reception", "stop it from
    # auto-renewing"), so a word cap let every one of them through while
    # rejecting harmless long ones.
    #
    # The condition is POSITION: a stop leads its clause and nothing but
    # filler follows it. Verified behaviourally against all of the above
    # before this assertion was changed — the matcher now gets every one of
    # them right, which the word cap never did.
    assert "clause" in body.lower() or "hasPrefix" in body, (
        "a stop must be anchored at the front of a clause, not found "
        "anywhere inside a sentence")
    assert "wordCount" not in body, (
        "length was never the condition — short instructions like 'leave it "
        "with the concierge' are exactly what a word cap lets through")
    # the short forms still work — those are real refusals
    for phrase in ('"never mind"', '"forget it"', '"skip it"'):
        assert phrase in body
    # and a negated phrase must not read as proof he did it himself
    assert "not already" in body or "negat" in body.lower(), (
        "\"it's not already booked yet, go ahead\" must not file as handled")


def test_every_cancellation_names_what_triggered_it():
    """"cancelled by owner" was what BOTH phone paths wrote, so when he said
    he had pressed nothing there was no way to tell a deliberate "Not now"
    from an answer misread as a refusal."""
    assert 'cancelled by owner (\\(trigger))' in APP
    assert 'trigger: "tapped Not now"' in APP
    assert 'trigger: "their answer read as ending it"' in APP
