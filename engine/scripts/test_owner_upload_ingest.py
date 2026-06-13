"""Owner upload intake test.

Uploaded text/audio files must feed the same owner card pipeline as typed
transcripts. Audio uses the cached sidecar seam here so the test is deterministic
and does not need a real recording.
"""
import os
import tempfile
from pathlib import Path

os.environ.setdefault("ANTICIPY_MODEL_PROVIDER", "stub")
os.environ.setdefault("ANTICIPY_HANDS_MODE", "mock")
os.environ.setdefault("ANTICIPY_TICK_SECONDS", "0")
os.environ.setdefault("ANTICIPY_INBOUND_POLL_SECONDS", "0")
os.environ["ANTICIPY_DATA_DIR"] = tempfile.mkdtemp(prefix="anticipy-upload-api-")

from fastapi.testclient import TestClient  # noqa: E402

from anticipy_engine.main import app  # noqa: E402


TRANSCRIPT = """
[08:04] Maya: school moved pickup to 3 today, please remind me before I forget.
[09:12] Sam needs the revised deck before Friday; I told him I'd send it.
[11:22] that water-table thing for Leila's birthday, put it in the cart if you find it, don't buy it.
"""


def _post(client, file_path: Path, *, filename: str) -> dict:
    res = client.post(
        "/owner/ingest-file",
        json={
            "path": str(file_path),
            "filename": filename,
            "source": "upload",
            "execute_actions": False,
            "meta": {"test": "owner_upload_ingest"},
        },
    )
    assert res.status_code == 200, res.text
    return res.json()


def main():
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-upload-files-"))
    text_path = tmp / "omar-day.txt"
    text_path.write_text(TRANSCRIPT, encoding="utf-8")

    audio_path = tmp / "omar-day.mp3"
    audio_path.write_bytes(b"not-real-audio-because-sidecar-is-the-contract")
    audio_path.with_suffix(".transcript").write_text(TRANSCRIPT, encoding="utf-8")

    with TestClient(app) as client:
        text_out = _post(client, text_path, filename="omar-day.txt")
        audio_out = _post(client, audio_path, filename="omar-day.mp3")

    for out, expected_source in ((text_out, "text_upload"), (audio_out, "audio_upload")):
        assert out["source"] == expected_source, out
        assert len(out["observed_lines"]) == 3, out
        assert len(out["cards"]) >= 3, out
        assert any(card["route"] == "api" for card in out["cards"]), out
        assert any(card["route"] == "voice_text" for card in out["cards"]), out
        assert any(card["route"] == "browser" for card in out["cards"]), out

    print("PASS owner_upload_ingest: uploaded text/audio sidecar -> same owner task cards")


if __name__ == "__main__":
    main()
