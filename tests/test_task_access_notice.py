"""Connection offers share the durable task notice and quiet-hour semantics."""
from types import SimpleNamespace
import pytest
from brain import worker as W


@pytest.mark.parametrize("available", [True, False])
def test_offer_or_fallback_is_saved_once_without_nighttime_send(monkeypatch, available):
    stored = {}
    calls = []
    job = {"id": "access-notice-available" if available else "access-notice-outage", "status": "queued"}
    owner = SimpleNamespace(owner_ref="owner1", backend_url="https://fixture.invalid",
                            _voice=lambda _: "Check your browser connection.")

    def post(url, *, json, timeout):
        calls.append((url, json))
        return SimpleNamespace(status_code=200 if available else 503,
                               json=lambda: {"line": "Connect the account to read your brief: https://fixture.invalid/c/test"})

    monkeypatch.setattr(W.pb, "post", post)
    monkeypatch.setattr(W, "delivered_stall_notice", lambda _: stored.get("note"))
    monkeypatch.setattr(W, "persist_stall_notice", lambda _, line: stored.setdefault("note", {"text": line}))
    monkeypatch.setattr(W, "sent_moments_ago", lambda _: False)
    monkeypatch.setattr(W, "mark_sent", lambda _: None)
    monkeypatch.setattr(W, "CLOCK_QUIET_START", 0)
    monkeypatch.setattr(W, "record_stall_notification_status", lambda _, status: stored.setdefault("status", status))
    for _ in range(2):
        W.publish_stall_notice(owner, job, "Browser unavailable", "Fallback", offer_access=True)
    assert calls == [("https://fixture.invalid/worker/task-access", {"owner_ref": "owner1", "job_id": job["id"]})]
    assert stored["status"] == "sms_deferred"
    assert stored["note"]["text"] == ("Connect the account to read your brief: https://fixture.invalid/c/test"
                                      if available else "Check your browser connection.")
    assert job["status"] == "queued"
