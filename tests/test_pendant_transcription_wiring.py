from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def code(text: str) -> str:
    """`text` with whole-line comments removed.

    THE SAME RULE overnight/no_vendor_ears.py USES, and for the same reason it
    gives: "this file's own explanation names Deepgram nine times, and a gate
    that could not survive being described would be unusable." Every assertion
    below is about what the app DOES; a comment explaining why it no longer
    does it must not be able to fail the check that says so. Half the sentences
    this file forbids now appear, quoted, in the comments that removed them.

    LINE-BASED, deliberately, rather than stripping from `//` to end of line.
    A vendor URL is `"wss://host/..."`, and cutting at the first `//` would
    leave `"wss:` and HIDE the hostname from the very check that hunts it. A
    line that merely ENDS in a comment is still read in full; only a line whose
    first non-space characters open a comment is dropped."""
    return "\n".join(
        line for line in text.splitlines()
        if not line.lstrip().startswith(("//", "*", "/*")))


def test_long_lived_deepgram_key_never_enters_ios_source():
    """The vendor's long-lived key must never reach a phone. That was true when
    the cloud lane existed — the server held the key and minted 60-second JWTs —
    and it is trivially true now that the lane is gone. It stays here anyway:
    the cheapest moment to catch a key being pasted into a client is before it
    ships, and this assertion costs nothing to keep forever.

    THE OTHER TWO ASSERTIONS THIS TEST USED TO MAKE ARE GONE, and that is the
    point of the edit. They read:

        assert "connect(accessToken:" in swift
        assert 'setValue("Bearer ' in swift

    which asserted that the websocket client EXISTED and that it attached a
    bearer credential to its request — a test requiring the presence of a
    design/LOCAL-FIRST.md rule 1 violation:

        "RAW AUDIO NEVER LEAVES A DEVICE. Not to Deepgram, not to anyone. If a
         capability needs better ears, find a better local model."

    A suite that encodes what shipped rather than what was intended will defend
    anything, including a thing an architecture law forbids. This is the third
    instance found in this repo in one night — a test asserting a hook still
    called the vendor's /v1/auth/grant, a test asserting the verb list that ate
    a research query, and these. The replacement assertions below say what the
    phone must NOT be able to do, which is a claim that stays true as the code
    moves."""
    swift = code("\n".join(
        path.read_text() for path in (ROOT / "app/ios/Anticipy").rglob("*.swift")))
    assert "DEEPGRAM_API_KEY" not in swift, "a vendor key is in the client"
    # Not the hostname alone: overnight/no_vendor_ears.py owns that check across
    # the whole repo. What is specific to the phone is the MECHANISM — nothing
    # in the app may hold a socket that could carry audio anywhere.
    assert "URLSessionWebSocketTask" not in swift, (
        "the app can open a websocket again; the audio lane was the only one "
        "that ever existed and it is closed")
    assert "connect(accessToken:" not in swift, (
        "the vendor transcriber client is back")


def test_the_token_endpoint_mints_nothing_and_says_why():
    """This test used to assert the hook still called Deepgram's /v1/auth/grant,
    which pinned a design/LOCAL-FIRST.md rule 1 violation in place:

        "RAW AUDIO NEVER LEAVES A DEVICE. Not to Deepgram, not to anyone."

    The endpoint exchanged a server-held vendor key for a 60-second JWT so the
    phone could stream the pendant's raw Opus frames to a websocket. Closed in
    49b04481. It cost nothing that worked — events with source="pendant" in
    production: ZERO, ever, against 229 from the phone microphone.

    The route is KEPT, refusing, rather than deleted: a 404 reads as "wrong URL"
    and gets debugged, while a refusal that names its reason gets obeyed. And it
    answers 410 GONE rather than 502/503, because those mean "try again later"
    and the phone's catch block schedules a retry on them — a
    temporary-sounding refusal would spin a reconnect loop forever against a
    permanent decision."""
    hook = (ROOT / "backend/pb_hooks/transcription_token.pb.js").read_text()
    assert "if (!e.auth)" in hook, "an unauthenticated caller must still be refused first"
    assert "/v1/auth/grant" not in hook, "the vendor exchange is back"
    assert "DEEPGRAM_API_KEY" not in hook, "the vendor key is being read again"
    assert "410" in hook, "a permanent refusal must not read as a transient one"
    assert "LOCAL-FIRST" in hook, "the refusal must name the law it obeys"


def test_the_pendant_lane_is_inert_and_forwards_nothing():
    """Was `test_pendant_frames_reach_transcriber_and_final_text_reaches_brain`,
    and it asserted the violation directly:

        assert "transcriber.send(opusFrame: frame)" in app
        assert "pendantTranscriber.onTranscript" in app

    That is "the phone must forward the pendant's raw Opus frames to a speech
    vendor", written as a passing test. The lane it protected is closed
    (LOCAL-FIRST rule 1), and closing it cost nothing that worked: events with
    source="pendant" in production is ZERO, ever, against 229 from the phone
    microphone. This lane never delivered a single row in its life.

    The invariant is now the opposite one, and it is worth more than the old
    one was: frames must be dropped AT THE SOURCE. `onOpusFrame` is left nil so
    the BLE layer's audio goes nowhere at all — not into a queue, not into a
    buffer something later decides what to do with. Audio that is never held
    cannot later be sent, which is a much cheaper thing to keep true than a
    promise never to send what you are holding.

    The BLE half deliberately still stands: `PendantManager` continues to
    assemble and offer frames, because an ON-DEVICE transcriber will need
    exactly that. What has gone is every consumer that took them off the phone.

    WHAT WOULD MAKE THE PENDANT SPEAK AGAIN, so this docstring does not read as
    a eulogy: app/ios/Anticipy/Audio/LocalTranscriber.swift, which is 43 lines
    with zero call sites and wants AVAudioPCMBuffer while the pendant emits
    Opus Data, with no Opus decoder in the target. That decoder is the real
    work and it is not done."""
    app = code((ROOT / "app/ios/Anticipy/AnticipyApp.swift").read_text())
    pendant = code((ROOT / "app/ios/Anticipy/BLE/PendantManager.swift").read_text())
    # The BLE layer still produces frames — that half is not the violation.
    assert "onOpusFrame?(frame)" in pendant, (
        "the pendant radio stopped offering frames; an on-device transcriber "
        "will need them")
    # And nothing consumes them.
    assert "onOpusFrame = nil" in app, (
        "frames must be dropped at the source, not held for something to "
        "decide about later")
    assert "send(opusFrame:" not in app, "pendant audio is being forwarded again"
    assert "pendantTranscriber" not in app, "the vendor transcriber is back"
    assert "transcription/token" not in app, (
        "the app is asking for a vendor credential again; that endpoint answers "
        "410 GONE and a client that retries it spins forever")


def test_the_ui_tells_the_owner_what_is_actually_true_about_the_pendant():
    """Was `test_ui_no_longer_claims_connected_pendant_drops_audio`, ending in:

        assert "Deepgram" in content

    A test REQUIRING that the interface name a speech vendor to the owner. It
    was written to stop the UI lying in one direction and became the thing
    holding the lie in place once the lane closed.

    This is the half that matters most. Those sentences were privacy promises
    rendered in the product — "Your pendant audio is being securely transcribed
    by Deepgram", "its Opus audio goes to Deepgram to become text" — and the
    moment the lane closed they became FALSE. A false privacy promise is worse
    than the violation it described: it tells someone their audio goes
    somewhere it does not, and tells them nothing about wherever it went
    instead.

    So the sentences were rewritten, not deleted. Silence where a promise used
    to be is its own failure — a stranger reading Settings deserves the current
    answer in the place the old one was.

    Note what else had to go, because `overnight/no_vendor_ears.py` cannot see
    it: "Pendant · starting transcription" and "I'm opening its secure
    transcription stream" never named the vendor, so that gate reads them as
    clean. They were the branches that ACTUALLY RENDERED once `pendantCapturing`
    could never become true, and they promised a stream that was never coming.
    A gate that greps for a vendor's name cannot catch a lie told without it."""
    content = code((ROOT / "app/ios/Anticipy/Views/ContentView.swift").read_text())
    settings = code((ROOT / "app/ios/Anticipy/Views/SettingsView.swift").read_text())
    ui = content + settings

    assert "Deepgram" not in ui, "the interface names the vendor again"
    # A Listening label over silence is the original sin this file's old name
    # was about, and it is still forbidden — just from the other side now.
    assert "Pendant · listening" not in content, (
        "the pendant cannot hear; a label saying it does is a Listening label "
        "over silence")
    for lie in ("starting transcription",
                "opening its secure transcription stream",
                "transcription stream is not live yet",
                "short-lived token"):
        assert lie not in ui, f"the interface still promises a closed lane: {lie!r}"

    # And it must not have gone quiet instead.
    assert "nothing I do with sound leaves this phone" in settings, (
        "Settings no longer answers where pendant sound goes; deleting the "
        "promise and leaving a blank was explicitly not the fix")
    assert "can't turn its sound into words yet" in content, (
        "the pendant chip no longer says why it is silent")
