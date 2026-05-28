import json
import os

os.environ.setdefault("ANTICIPY_ENGINE_PORT", "18732")
os.environ.setdefault("ANTICIPY_PORT", "18732")

from app.product import server


def test_process_utterance_writes_v7_boundary_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_v7_artifact_root", lambda: tmp_path)
    monkeypatch.setattr(server, "_write_decline_receipt", lambda rec: None)
    monkeypatch.setattr(server, "_sync_resolution_trace", lambda rec: {"ok": False, "skipped": True})
    monkeypatch.setattr(server, "_surface_fired_proactive_items", lambda: {"ok": True, "fired": []})
    monkeypatch.setitem(server._SESS, "profile_obj", object())
    monkeypatch.setitem(server._SESS, "profile", {})
    with server._LISTEN["lock"]:
        server._LISTEN["windows"] = 0
        server._LISTEN["recent"] = []
        server._LISTEN["pending"] = None

    rec = server._process_utterance(
        "After my renewal call add a follow-up in HubSpot for Friday morning saying I promised SOC2 summary.",
        0.1,
        "upload-asr",
        {
            "content_type": "audio/mpeg",
            "filename": "proof.mp3",
            "bytes": 123,
            "raw_asr_transcript": "After my renewal call add a follow-up in HubSpot for Friday morning saying I promised SOC2 summary.",
            "asr_normalized": False,
            "asr_normalizations": [],
            "mean_confidence": 0.99,
        },
    )

    assert rec["v7_artifacts"]["normalized_inputs"]
    assert rec["v7_artifacts"]["inference_events"]
    assert rec["v7_artifacts"]["decisions"]
    assert rec["v7_decision"]["schema"] == "anticipy.decision.v7"
    assert rec["v7_normalized_input"]["input_mode"] == "mp3_upload"

    normalized_path = tmp_path / "normalized_inputs.jsonl"
    decision_path = tmp_path / "decisions.jsonl"
    normalized = json.loads(normalized_path.read_text().splitlines()[-1])
    decision = json.loads(decision_path.read_text().splitlines()[-1])
    assert normalized["ingest_id"] == rec["ingest_id"]
    assert normalized["capture"]["content_type"] == "audio/mpeg"
    assert decision["decision"]["mode"] == "decline"
