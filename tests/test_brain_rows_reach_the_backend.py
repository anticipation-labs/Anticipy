"""Audit F04: every row the brain writes must be one the backend accepts.

THE MEASURED FAILURE, 2026-09-05, against production:

    POST https://api.anticipy.ai/api/collections/events/records
    {"device_id": "anticipy-brain", ..., "owner_ref": "…", "owner": "…"}
    -> HTTP 400 {"data":{"owner":{"code":"unknown_field",
                                  "message":"events has no field owner"}}}

The brain stamped a pre-account `owner` UUID onto every events row it wrote.
`events` has no such column on this backend — not in the Worker's column map
and not in D1 (`pragma_table_info('events')` returns nothing for it) — so the
Worker refused each row BEFORE the INSERT. Live D1 held the consequence: an
owner with 13 transcripts, 15 jobs and 9 receipts on the day, and ZERO
anticipy_says, anticipy_text or notification_status rows, ever, since the
cutover. She heard, decided and finished the errand, and the owner saw an
empty feed and got no text — because `claim_notification_attempt` only wins
the SMS fence on a 2xx from this very call, so the text was never even tried.

So the tests here are not "is the constant right". They drive the real writers
against a fake backend that enforces the REAL column map, and ask whether the
row lands. A body the Worker would reject fails here now.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import brain.worker as W  # noqa: E402


# The events columns the Worker actually has (migration/workers/src/pb/
# schema.ts). Copied deliberately rather than imported: this file is the
# brain's half of a contract with a TypeScript module, and the day somebody
# adds `owner` to one side and not the other, this list is what disagrees.
EVENTS_COLUMNS = {
    "id", "created", "updated", "device_id", "kind", "text", "decision", "goal",
    "needs_confirmation", "capture_started_at", "capture_ended_at",
    "gap_before_ms", "seq", "boot_id", "source", "backfill", "segment",
    "speaker", "owner_ref", "addressee", "spoken_at", "parent_line",
    "external_event_id", "explicit", "importance", "heard_ms", "heard_calls",
}


class _Rejected(Exception):
    """What requests.raise_for_status() does with the Worker's 400."""


class FakeWorker:
    """A backend with the real column map: unknown fields are 400s, and a
    rejected row is never stored — exactly what production did."""

    def __init__(self):
        self.rows = []
        self.rejected = []

    def post(self, _url, json=None, timeout=None, **_kw):
        body = dict(json or {})
        unknown = sorted(set(body) - EVENTS_COLUMNS)
        if unknown:
            self.rejected.append(unknown)
            return _Reply(400, {"data": {unknown[0]: {"code": "unknown_field"}}})
        self.rows.append(body)
        return _Reply(200, {"id": f"row{len(self.rows)}"})


class _Reply:
    def __init__(self, status, payload):
        self.status_code, self._payload = status, payload
        self.ok = status < 400

    def json(self):
        return self._payload

    def raise_for_status(self):
        if not self.ok:
            raise _Rejected(f"HTTP {self.status_code}: {self._payload}")


@pytest.fixture
def backend(monkeypatch):
    fake = FakeWorker()
    monkeypatch.setattr(W, "ACTIVE_OWNER_REF", "qeuy6sv1raof9rw")
    monkeypatch.setattr(W, "ACTIVE_OWNER_ID", "9558c9f6-legacy-uuid")
    monkeypatch.setattr(W.pb, "post", fake.post)
    return fake


def test_the_thing_she_said_lands_in_the_feed(backend):
    """The row that IS the record she spoke. It was 400ing in production."""
    W.post_event("anticipy_says", "Booked — you're all set for 7pm.",
                 decision="answer", goal="dinner")

    assert backend.rejected == [], f"the Worker refused: {backend.rejected}"
    assert len(backend.rows) == 1
    row = backend.rows[0]
    assert row["owner_ref"] == "qeuy6sv1raof9rw"
    assert row["device_id"] == "anticipy-brain"
    assert row["text"] == "Booked — you're all set for 7pm."


def test_no_row_the_brain_writes_carries_the_owner_column(backend):
    """Scope travels on owner_ref. `owner` is not a column here, and every
    kind the brain writes goes through this one function."""
    for kind, decision in (("anticipy_says", "welcome"),
                           ("anticipy_says", "clock"),
                           ("anticipy_text", "ask"),
                           ("notification_status", "sent")):
        W.post_event(kind, "x", decision=decision)

    assert backend.rejected == []
    assert len(backend.rows) == 4
    for row in backend.rows:
        assert "owner" not in row
        assert row["owner_ref"] == "qeuy6sv1raof9rw"


def test_the_legacy_id_is_still_accepted_and_still_never_sent(backend):
    """Callers pass owner_id everywhere and the READ side still scopes on it
    where a row carries one, so the parameter stays. It just never becomes a
    column that does not exist."""
    W.post_event("anticipy_says", "x", owner_id="some-legacy-uuid")

    assert backend.rejected == []
    assert "owner" not in backend.rows[0]


def test_an_uninvited_slot_can_actually_be_taken(backend, monkeypatch):
    """The other writer of events rows. A slot create that 400s makes the
    day's budget unprovable rather than spent, so the fence that limits
    uninvited texts could never be won either."""
    monkeypatch.setattr(W, "_uninvited_slots_today", lambda *a, **k: [])
    monkeypatch.setattr(W, "UNINVITED_SPENT_UNTIL", 0.0)

    slot = W.reserve_uninvited_text("qeuy6sv1raof9rw", "clock")

    assert backend.rejected == []
    assert isinstance(slot, str) and slot.startswith("uninvited:")
    assert len(backend.rows) == 1
    assert "owner" not in backend.rows[0]
    assert backend.rows[0]["external_event_id"] == slot


def test_the_fake_backend_would_have_caught_the_bug(backend):
    """The guard on the guard: if the brain went back to stamping `owner`,
    this fake refuses the row exactly as production did — so these tests
    cannot pass by accident on a backend that accepts anything."""
    reply = backend.post("/api/collections/events/records",
                         json={"device_id": "anticipy-brain", "kind": "x",
                               "owner_ref": "r", "owner": "legacy"})

    assert reply.status_code == 400
    assert backend.rejected == [["owner"]]
    assert backend.rows == []
    with pytest.raises(_Rejected):
        reply.raise_for_status()
