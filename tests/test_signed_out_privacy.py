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
