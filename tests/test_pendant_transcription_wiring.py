from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_long_lived_deepgram_key_never_enters_ios_source():
    swift = "\n".join(
        path.read_text() for path in (ROOT / "app/ios/Anticipy").rglob("*.swift"))
    assert "DEEPGRAM_API_KEY" not in swift
    assert "connect(accessToken:" in swift
    assert 'setValue("Bearer ' in swift


def test_token_exchange_requires_a_signed_in_owner_and_is_short_lived():
    hook = (ROOT / "backend/pb_hooks/transcription_token.pb.js").read_text()
    assert "if (!e.auth)" in hook
    assert "/v1/auth/grant" in hook
    assert "ttl_seconds: 60" in hook
    assert "access_token" in hook


def test_pendant_frames_reach_transcriber_and_final_text_reaches_brain():
    app = (ROOT / "app/ios/Anticipy/AnticipyApp.swift").read_text()
    pendant = (ROOT / "app/ios/Anticipy/BLE/PendantManager.swift").read_text()
    assert "onOpusFrame?(frame)" in pendant
    assert "transcriber.send(opusFrame: frame)" in app
    assert "pendantTranscriber.onTranscript" in app
    assert "await self?.heard(line)" in app


def test_ui_no_longer_claims_connected_pendant_drops_audio():
    content = (ROOT / "app/ios/Anticipy/Views/ContentView.swift").read_text()
    assert "Pendant · not capturing" not in content
    assert "Pendant · listening" in content
    assert "Deepgram" in content
