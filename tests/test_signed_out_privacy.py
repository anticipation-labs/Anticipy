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
    """The guard must run before anything leaves, and nothing may leave between.

    This asserted the guard sat within the last 600 CHARACTERS before the push.
    That is a proxy for "close to it", and on 2026-08-25 it went red because
    legitimate capture-envelope work was added in between — the guard was
    untouched, still first, still returning early. A distance check reads a
    reformat as a privacy regression, which is expensive in exactly the wrong
    direction: it cries wolf on safe edits, and a real leak that happened to fit
    inside 600 characters would have passed.

    So the intent is asserted directly instead. The guard precedes every exit,
    and NOTHING between the guard and the push can itself push or queue — which
    is the property the distance was standing in for, and it holds however the
    code is laid out.
    """
    # Scoped to heard() ONLY. Splitting the whole file on the transcript push
    # sweeps in every earlier function that legitimately pushes — the profile
    # upsert, the app_reply write — and reads them as leaks.
    # COMMENTS STRIPPED FIRST. Searching raw source means a guard commented
    # OUT still reads as present — a mutation proved exactly that on
    # 2026-08-25, and the check this replaced had the same hole. The shell
    # runners in app/ios/Tests already do this (`code()`); this now matches.
    live = "\n".join(l for l in APP.split("\n")
                     if not l.lstrip().startswith("//"))
    heard = live.split("func heard(", 1)[1]
    heard = heard.split("try await backend.pushEvent(kind: \"transcript\"", 1)[0]
    guard = 'guard !accountID.isEmpty else { return }'
    assert guard in heard, (
        "a line spoken with no signed-in account must not be pushed or queued")

    # Nothing may reach the wire, or the on-disk queue, BEFORE the owner check.
    before = heard[:heard.index(guard)]
    for leak in ("pushEvent", "queueUnsent", "unsentLines"):
        assert leak not in before, (
            f"{leak} runs before the signed-out guard — a line spoken with no "
            "owner would leave the phone")

    # And nothing between the guard and the push may leave either: the guard is
    # the LAST word before the wire, not merely somewhere above it.
    between = heard[heard.index(guard) + len(guard):]
    for leak in ("pushEvent", "queueUnsent"):
        assert leak not in between, (
            f"{leak} sits between the owner check and the push, so a path "
            "exists that the guard does not cover")


def test_a_buffered_line_remembers_whose_words_it_is():
    decl = APP.split("private struct BufferedLine: Codable {", 1)[1].split("}", 1)[0]
    assert "account" in decl, "a queued line must carry the account that captured it"
    # every construction site stamps it
    for frag in ("account: accountID", "account: nil"):
        assert frag in APP


def test_the_queue_is_never_flushed_into_someone_elses_account():
    # This sliced the first 900 characters, which used to reach the account
    # guard. The 2026-08-24 flush rewrite put the parent-chain comment block
    # ahead of the loop and pushed the guard past the window — the guard was
    # still in the code; the test had stopped looking at it. Scope to the
    # whole function body instead, the way the other splits in this file do.
    flush = APP.split("private func flushUnsent() async {", 1)[1] \
               .split("\n    }", 1)[0]
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
