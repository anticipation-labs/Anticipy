"""A user who cannot hear her looks exactly like a user having a quiet day.

+17868735256 was sent 15 messages between 2026-08-19 and 2026-08-25 and not one
was delivered — every one failed Twilio error 30034, the sending number not
registered for A2P 10DLC. `voice_arm.text()` saw 201 Created every time, because
delivery fails asynchronously and nothing read the receipt.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "overnight"))
import does_she_reach_them as reach


def msg(to, status, error=None, direction="outbound-api"):
    return {"to": to, "status": status, "error_code": error, "direction": direction}


def test_the_recorded_failure_is_caught():
    """15 sent, 0 delivered, all 30034 — the shape that was invisible."""
    msgs = [msg("+17868735256", "undelivered", 30034) for _ in range(15)]
    bad = reach.unreachable(msgs)
    assert len(bad) == 1
    assert bad[0]["to"] == "+17868735256"
    assert bad[0]["delivered"] == 0
    assert bad[0]["errors"] == {"30034": 15}


def test_a_number_that_receives_anything_is_not_a_finding():
    """One delivery proves the channel works. The gate is about total silence,
    not about a failure rate — a flaky carrier is not an unreachable person."""
    msgs = [msg("+1555", "undelivered", 30003) for _ in range(9)]
    msgs.append(msg("+1555", "delivered"))
    assert reach.unreachable(msgs) == []


def test_messages_still_in_flight_are_never_held_against_a_number():
    """A text sent ninety seconds ago has not failed, it has not finished.
    Counting pending as failure would fire this gate on every healthy send."""
    msgs = [msg("+1555", s) for s in ("queued", "sending", "sent", "accepted")]
    assert reach.unreachable(msgs) == []


def test_one_bad_night_is_not_a_finding():
    """Below the floor nothing is reported: a phone off, a tunnel, a full inbox.
    The shape that matters is ACCUMULATION with nothing landing."""
    assert reach.unreachable([msg("+1555", "undelivered", 30003)] * 2) == []
    assert len(reach.unreachable([msg("+1555", "undelivered", 30003)] * 3)) == 1


def test_inbound_messages_are_not_deliveries_to_anyone():
    """An inbound text is somebody writing TO her. Counting it as a delivery
    would let a user who replies once mask a number she cannot reach."""
    msgs = [msg("+1555", "undelivered", 30034) for _ in range(5)]
    msgs.append(msg("+1555", "received", direction="inbound"))
    bad = reach.unreachable(msgs)
    assert len(bad) == 1 and bad[0]["delivered"] == 0


def test_two_broken_numbers_are_both_named():
    """Reporting only the worst would hide the second person indefinitely."""
    msgs = ([msg("+1555", "undelivered", 30034)] * 5
            + [msg("+1666", "failed", 21610)] * 4)
    bad = reach.unreachable(msgs)
    assert {b["to"] for b in bad} == {"+1555", "+1666"}


def test_the_gate_never_reads_a_message_body():
    """HARNESS-LAWS Law 1. This gate reads delivery receipts — status and
    error_code — and could not classify an utterance if it wanted to, because
    it never fetches a body. That is why a threshold is legal here."""
    import inspect
    src = inspect.getsource(reach)
    assert '"body"' not in src and "'body'" not in src
    assert "Body" not in src.replace("PageSize", "")


# ------------------------------------------------------------------ Sendblue

def test_sendblue_receipts_are_read_through_the_same_threshold():
    """Sendblue's rows are reshaped to the one receipt `unreachable` reads, so
    the floor is applied once and means the same thing on both vendors."""
    rows = reach.sendblue_rows([
        {"to_number": "+1555", "status": "ERROR", "error_code": 4001,
         "is_outbound": True, "date_sent": "2026-09-05T01:00:00Z"}
        for _ in range(4)])
    bad = reach.unreachable(rows)
    assert len(bad) == 1 and bad[0]["to"] == "+1555"
    assert bad[0]["delivered"] == 0 and bad[0]["errors"] == {"4001": 4}


def test_sendblue_statuses_on_the_way_are_never_held_against_a_number():
    rows = reach.sendblue_rows([{"to_number": "+1555", "status": s, "is_outbound": True}
                                for s in ("REGISTERED", "PENDING", "QUEUED",
                                          "ACCEPTED", "SENT")])
    assert reach.unreachable(rows) == []


def test_a_sendblue_delivery_or_read_clears_the_number():
    rows = reach.sendblue_rows(
        [{"to_number": "+1555", "status": "DECLINED", "is_outbound": True}] * 5
        + [{"to_number": "+1555", "status": "READ", "is_outbound": True}])
    assert reach.unreachable(rows) == []


def test_sendblue_inbound_rows_are_not_deliveries_to_anyone():
    rows = reach.sendblue_rows(
        [{"to_number": "+1555", "status": "ERROR", "is_outbound": True}] * 5
        + [{"to_number": "+1555", "status": "RECEIVED", "is_outbound": False}])
    bad = reach.unreachable(rows)
    assert len(bad) == 1 and bad[0]["delivered"] == 0


def test_the_gate_measures_every_configured_vendor(monkeypatch):
    """Both vendors configured: both legs run, and the Twilio leg is the same
    fetch it always was. Neither leg is weakened by the other's existence."""
    names = [name for name, _c, _f in reach.PROVIDERS]
    assert names == ["twilio", "sendblue"]
    for name in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN",
                 "SENDBLUE_API_KEY_ID", "SENDBLUE_API_SECRET_KEY"):
        monkeypatch.delenv(name, raising=False)
    assert not reach.twilio_configured() and not reach.sendblue_configured()
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC1")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "tok")
    assert reach.twilio_configured() and not reach.sendblue_configured()
    monkeypatch.setenv("SENDBLUE_API_KEY_ID", "k")
    monkeypatch.setenv("SENDBLUE_API_SECRET_KEY", "s")
    assert reach.sendblue_configured()
    assert reach.PROVIDERS[0][2] is reach.fetch_outbound


def test_the_sendblue_fetch_authenticates_with_headers_and_never_sends(monkeypatch):
    import json as _json
    seen: list = []

    class _R:
        def __init__(self, data):
            self._data = data

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return _json.dumps({"data": self._data}).encode()

    def fake_urlopen(req, timeout=0):
        seen.append(req)
        return _R([{"to_number": "+1555", "status": "QUEUED", "is_outbound": True}])

    monkeypatch.setenv("SENDBLUE_API_KEY_ID", "k")
    monkeypatch.setenv("SENDBLUE_API_SECRET_KEY", "s3cret")
    monkeypatch.delenv("SENDBLUE_API_BASE", raising=False)
    monkeypatch.delenv("SENDBLUE_FROM_NUMBER", raising=False)
    monkeypatch.setattr(reach.urllib.request, "urlopen", fake_urlopen)
    rows = reach.fetch_outbound_sendblue(limit=50)
    assert rows == [{"to": "+1555", "status": "queued", "error_code": None,
                     "direction": "outbound-api", "date_sent": None}]
    req = seen[0]
    assert req.get_method() == "GET"
    assert req.full_url.startswith("https://api.sendblue.com/api/v2/messages?")
    assert "is_outbound=true" in req.full_url
    assert req.get_header("Sb-api-key-id") == "k"
    assert req.get_header("Sb-api-secret-key") == "s3cret"
