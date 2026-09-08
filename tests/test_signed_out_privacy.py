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


def shipping_body(signature):
    """The full declaration, without comment-only matches or character limits."""
    source = "\n".join(line for line in APP.splitlines()
                       if not line.lstrip().startswith("//"))
    start = source.index(signature)
    opening = source.index("{", start)
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if not depth:
                return source[opening + 1:index]
    raise AssertionError(f"unclosed {signature}")


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
    """Every real capture path must use the exact authenticated staging gate.

    heard no longer has a separate live POST: first-send and retry both use the
    durable outbox. Follow the caller into that real guard rather than pinning
    the old function's literal guard spelling. The Swift race runner separately
    executes these production functions against delayed in-memory transport.
    """
    heard = shipping_body("func heard(")
    assert "guard stageTranscript(" in heard
    assert heard.index("guard stageTranscript(") < heard.index("await flushUnsent()")
    assert "pushEvent" not in heard
    typed = shipping_body("func acceptTyped(")
    assert typed.index("stageTranscript(") < typed.index("Task { await flushUnsent() }")
    stage = shipping_body("private func stageTranscript(")
    gate = stage.index("guard let lease = AccountWriteLeasePolicy.begin(")
    assert "accountID: accountID, authToken: authToken, isSignedIn: isSignedIn" in stage
    assert "else { return false }" in stage
    for operation in ("readPendingLines()", "persistPendingLines(", "transcript.append("):
        assert gate < stage.index(operation)
    assert "pushEvent" not in stage and "await" not in stage
    assert "account: lease.accountID" in stage
    begin = shipping_body("static func begin(accountID: String, authToken: String,")
    assert "guard isSignedIn, !accountID.isEmpty, !authToken.isEmpty else { return nil }" in begin


def test_a_buffered_line_remembers_whose_words_it_is():
    # Matched by NAME, not by its conformance list. This split on the literal
    # "private struct BufferedLine: Codable {" and broke the day the struct
    # gained Equatable — needed so a delivered row can be removed from the
    # persisted queue by value rather than by an index that a concurrent write
    # may have invalidated. The property under test is that the row carries the
    # account that captured it; which protocols it conforms to is not that
    # property, and a test that fails on an unrelated conformance is a test
    # that will be silenced rather than read.
    import re as _re
    match = _re.search(r"private struct BufferedLine\s*:[^{]*\{", APP)
    assert match, "BufferedLine is gone or renamed"
    decl = APP[match.end():].split("}", 1)[0]
    # THE DECLARATION, not the word. `"account" in decl` passed even after the
    # field was renamed, because the struct's own doc comment says "account"
    # several times in prose — so the check was satisfied by the explanation of
    # the field rather than by the field. Verified by mutation: renaming
    # `var account` to `var acct` left it green. Matching the declaration makes
    # the rename red, which is the whole point of the test.
    import re as _re2
    assert _re2.search(r"^\s*(?:var|let)\s+account\s*:", decl, _re2.M), (
        "a queued line must carry the account that captured it")
    # every construction site stamps it
    assert "account: lease.accountID" in shipping_body("private func stageTranscript(")
    assert "account: nil" in shipping_body("private func readPendingLines()")


def test_the_queue_is_never_flushed_into_someone_elses_account():
    # This sliced the first 900 characters, which used to reach the account
    # guard. The 2026-08-24 flush rewrite put the parent-chain comment block
    # ahead of the loop and pushed the guard past the window — the guard was
    # still in the code; the test had stopped looking at it. Scope to the
    # whole function body instead, the way the other splits in this file do.
    flush = shipping_body("private func flushUnsent() async")
    assert "let lease = AccountWriteLeasePolicy.begin(accountID: accountID" in flush
    assert "authToken: authToken, isSignedIn: isSignedIn" in flush
    assert "guard original.account == lease.accountID else" in flush
    assert "let requestedBackend = backend" in flush
    assert "await requestedBackend.pushEvent(" in flush
    assert "await backend.pushEvent(" not in flush
    assert flush.count("AccountWriteLeasePolicy.isCurrent(") >= 6
    assert "$0.account == lease.accountID && $0.externalEventID == externalID" in flush


# ------------------------- venting is not an instruction

def test_the_phone_never_interprets_an_answer_as_cancellation():
    """Meaning belongs to Conversation.on_reply, not an iPhone phrase list."""
    assert "answerThatEndsTheErrand" not in APP
    assert 'trigger: "their answer read as ending it"' not in APP
    assert 'pushEvent(kind: "app_reply"' in APP


def test_every_cancellation_names_what_triggered_it():
    """"cancelled by owner" was what BOTH phone paths wrote, so when he said
    he had pressed nothing there was no way to tell a deliberate "Not now"
    from an answer misread as a refusal."""
    assert 'cancelled by owner (\\(trigger))' in APP
    assert 'trigger: "tapped Not now"' in APP
    assert 'trigger: "tapped Stop on the phone"' in APP
    assert 'trigger: "their answer read as ending it"' not in APP
