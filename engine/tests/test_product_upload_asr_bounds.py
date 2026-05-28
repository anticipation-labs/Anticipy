import asyncio
import time

from app.product import server


def test_uploaded_audio_asr_timeout_returns_json_instead_of_hanging(monkeypatch):
    def slow_worker(*args, **kwargs):
        time.sleep(0.1)
        return 200, {"ok": True}

    monkeypatch.setattr(server, "_upload_asr_timeout_seconds", lambda: 0.01)
    monkeypatch.setattr(server, "_transcribe_uploaded_audio_sync", slow_worker)

    status, payload = asyncio.run(
        server._transcribe_uploaded_audio_bounded(
            b"audio", "audio/aiff", "upload.aiff", feed_pipeline=True
        )
    )

    assert status == 504
    assert payload["ok"] is False
    assert "timed out" in payload["error"]
    assert payload["source"] == "upload-asr"
