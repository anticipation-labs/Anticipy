from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_long_lived_deepgram_key_never_enters_ios_source():
    swift = "\n".join(
        path.read_text() for path in (ROOT / "app/ios/Anticipy").rglob("*.swift"))
    assert "DEEPGRAM_API_KEY" not in swift
    assert "connect(accessToken:" in swift
    assert 'setValue("Bearer ' in swift


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


def test_pendant_frames_reach_transcriber_and_final_text_reaches_brain():
    app = (ROOT / "app/ios/Anticipy/AnticipyApp.swift").read_text()
    pendant = (ROOT / "app/ios/Anticipy/BLE/PendantManager.swift").read_text()
    assert "onOpusFrame?(frame)" in pendant
    assert "transcriber.send(opusFrame: frame)" in app
    assert "pendantTranscriber.onTranscript" in app
    # Pinned the exact call text, so tagging the line with WHERE it came from
    # ("from: .pendant") read as the wiring being torn out. What matters is
    # that a pendant transcript still reaches heard() — not its argument list.
    import re
    assert re.search(r"await self\?\.heard\(line[^)]*\)", app), (
        "a pendant transcript must still reach heard()")
    assert "from: .pendant" in app, (
        "and it must say it came from the pendant, not the phone mic")


def test_ui_no_longer_claims_connected_pendant_drops_audio():
    content = (ROOT / "app/ios/Anticipy/Views/ContentView.swift").read_text()
    assert "Pendant · not capturing" not in content
    assert "Pendant · listening" in content
    assert "Deepgram" in content
