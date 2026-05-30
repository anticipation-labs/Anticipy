"""Tests for the /api/timeline/recent endpoint (Phase 2 UI follow-on).

The popover polls this endpoint every 5 seconds to render the unified
timeline. These tests exercise the route via FastAPI's TestClient with
an isolated timeline path (ANTICIPY_TIMELINE_PATH points at a per-test
tmp_path) so the suite never touches ~/.anticipy/v7/timeline.jsonl and
never collides with the live engine sidecar.

Coverage:
    1. Append 5 entries, fetch them all (default n=50).
    2. Filter by kind=sms_sent only.
    3. Filter by status=wait_user only.
    4. Filter by since_ts.
    5. n hard-capped at 500.
    6. Empty timeline returns an empty list (not an error).
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Pin the engine port high before importing server so the startup port
# reclaim cannot collide with a live dev engine on 8731.
os.environ.setdefault("ANTICIPY_ENGINE_PORT", "59733")

from app.timeline import append as timeline_append  # noqa: E402


@pytest.fixture
def tmp_timeline(tmp_path, monkeypatch):
    """Point the timeline writer + reader at a fresh per-test JSONL."""
    path = tmp_path / "timeline.jsonl"
    monkeypatch.setenv("ANTICIPY_TIMELINE_PATH", str(path))
    return path


@pytest.fixture
def client(tmp_timeline):
    """A FastAPI TestClient bound to server.app, with the timeline path
    already redirected via the tmp_timeline fixture."""
    from fastapi.testclient import TestClient

    from app.product import server

    return TestClient(server.app)


def _seed_five(tmp_timeline):
    """Append the same fixed 5 entries every test starts from. Keeps
    assertions stable regardless of which test runs first.

    Layout: 2 sms_sent (one done, one wait_user), 1 email_sent done,
    1 web_action failed, 1 user_reply done. ts spaced 1s apart so
    since_ts filter has clean boundaries.
    """
    base_ts = 1_780_000_000.0
    rows = [
        {
            "ts": base_ts + 0,
            "kind": "sms_sent",
            "status": "done",
            "summary": "SMS receipt to +15551234567",
            "channel": "twilio_sms",
            "payload": {"to": "+15551234567"},
        },
        {
            "ts": base_ts + 1,
            "kind": "email_sent",
            "status": "done",
            "summary": "Drafted email to sarah@example.com",
            "channel": "chrome",
            "payload": {"to": "sarah@example.com"},
        },
        {
            "ts": base_ts + 2,
            "kind": "sms_sent",
            "status": "wait_user",
            "summary": "SMS pre-confirm: send draft? YES/NO",
            "channel": "twilio_sms",
            "payload": {"to": "+15551234567", "category": "preconfirm"},
        },
        {
            "ts": base_ts + 3,
            "kind": "web_action",
            "status": "failed",
            "summary": "Open calendar event in Google Calendar",
            "channel": "chrome",
            "payload": {"error": "ambiguous_dom"},
        },
        {
            "ts": base_ts + 4,
            "kind": "user_reply",
            "status": "done",
            "summary": "YES",
            "channel": "twilio_sms",
            "payload": {"from": "+15551234567"},
        },
    ]
    for row in rows:
        timeline_append(row)
    return rows


# ---------------------------------------------------------------------------
# 1. Default fetch: 5 entries, no filters.
# ---------------------------------------------------------------------------


def test_endpoint_returns_seeded_entries(tmp_timeline, client):
    """Append 5 rows. Endpoint returns all 5 with default n=50."""
    seeded = _seed_five(tmp_timeline)

    resp = client.get("/api/timeline/recent")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert isinstance(body["entries"], list)
    assert len(body["entries"]) == len(seeded)

    # Order matches file order (oldest first); kinds line up.
    returned_kinds = [row["kind"] for row in body["entries"]]
    expected_kinds = [row["kind"] for row in seeded]
    assert returned_kinds == expected_kinds

    # Every row carries the auto-filled goal_id + ts the writer added.
    for row in body["entries"]:
        assert row["goal_id"].startswith("g-")
        assert isinstance(row["ts"], (int, float))
        assert "summary" in row


# ---------------------------------------------------------------------------
# 2. Filter by kind.
# ---------------------------------------------------------------------------


def test_endpoint_filter_by_kind_sms(tmp_timeline, client):
    """kind=sms_sent yields only the 2 SMS rows."""
    _seed_five(tmp_timeline)

    resp = client.get("/api/timeline/recent?kind=sms_sent")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    rows = body["entries"]
    assert len(rows) == 2
    assert {row["kind"] for row in rows} == {"sms_sent"}
    summaries = {row["summary"] for row in rows}
    assert summaries == {
        "SMS receipt to +15551234567",
        "SMS pre-confirm: send draft? YES/NO",
    }


def test_endpoint_filter_by_kind_no_match(tmp_timeline, client):
    """A kind that exists nowhere returns an empty list, not an error."""
    _seed_five(tmp_timeline)

    resp = client.get("/api/timeline/recent?kind=voice_call")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["entries"] == []


# ---------------------------------------------------------------------------
# 3. Filter by status.
# ---------------------------------------------------------------------------


def test_endpoint_filter_by_status_wait_user(tmp_timeline, client):
    """status=wait_user yields only the SMS pre-confirm row."""
    _seed_five(tmp_timeline)

    resp = client.get("/api/timeline/recent?status=wait_user")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    rows = body["entries"]
    assert len(rows) == 1
    assert rows[0]["status"] == "wait_user"
    assert rows[0]["kind"] == "sms_sent"
    assert rows[0]["summary"] == "SMS pre-confirm: send draft? YES/NO"


def test_endpoint_filter_combined_kind_and_status(tmp_timeline, client):
    """kind=sms_sent AND status=done yields just the receipt row."""
    _seed_five(tmp_timeline)

    resp = client.get(
        "/api/timeline/recent?kind=sms_sent&status=done"
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    rows = body["entries"]
    assert len(rows) == 1
    assert rows[0]["kind"] == "sms_sent"
    assert rows[0]["status"] == "done"


# ---------------------------------------------------------------------------
# 4. Filter by since_ts.
# ---------------------------------------------------------------------------


def test_endpoint_filter_since_ts(tmp_timeline, client):
    """since_ts greater than the third row's ts returns only the last 2."""
    _seed_five(tmp_timeline)

    # The fixture spaces rows 1s apart starting at 1_780_000_000.0. The
    # third row (sms wait_user) lands at 1_780_000_002.0; ask for rows
    # at or after 1_780_000_003.0 to skip rows 0, 1, 2.
    cutoff = 1_780_000_003.0
    resp = client.get(f"/api/timeline/recent?since_ts={cutoff}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    rows = body["entries"]
    assert len(rows) == 2
    assert [row["kind"] for row in rows] == ["web_action", "user_reply"]
    assert all(row["ts"] >= cutoff for row in rows)


def test_endpoint_since_ts_future_returns_empty(tmp_timeline, client):
    """A since_ts far in the future returns an empty list."""
    _seed_five(tmp_timeline)

    future = time.time() + 86400
    resp = client.get(f"/api/timeline/recent?since_ts={future}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["entries"] == []


# ---------------------------------------------------------------------------
# 5. n parameter: default, cap, and zero.
# ---------------------------------------------------------------------------


def test_endpoint_n_caps_at_500(tmp_timeline, client):
    """n above the hard cap is silently truncated to 500."""
    # Seed 12 rows. Asking for 9999 returns at most 500; in practice it
    # returns all 12 since that's fewer than the cap.
    for i in range(12):
        timeline_append({
            "kind": "note",
            "status": "done",
            "summary": f"note {i}",
            "channel": "popover",
        })

    resp = client.get("/api/timeline/recent?n=9999")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # All 12 fit comfortably under the 500 cap.
    assert len(body["entries"]) == 12

    # Asking for the last 3 returns the 3 most recent in file order.
    resp = client.get("/api/timeline/recent?n=3")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    rows = body["entries"]
    assert len(rows) == 3
    assert [r["summary"] for r in rows] == ["note 9", "note 10", "note 11"]


def test_endpoint_n_zero_returns_empty(tmp_timeline, client):
    """n=0 short-circuits to an empty list without reading the file."""
    _seed_five(tmp_timeline)

    resp = client.get("/api/timeline/recent?n=0")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["entries"] == []


# ---------------------------------------------------------------------------
# 6. Empty timeline (no file yet).
# ---------------------------------------------------------------------------


def test_endpoint_empty_timeline_returns_ok(tmp_timeline, client):
    """When the timeline file does not exist, the route returns
    ok=true with an empty entries list, not a 500."""
    # Do not append anything; the file at tmp_timeline does not exist.
    assert not tmp_timeline.exists()

    resp = client.get("/api/timeline/recent")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["entries"] == []


# ---------------------------------------------------------------------------
# 7. Unknown filter values are passed through to the reader and yield
#    an empty list because no row matches (does not 500).
# ---------------------------------------------------------------------------


def test_endpoint_unknown_status_returns_empty(tmp_timeline, client):
    """A status value not in VALID_STATUSES yields no matches."""
    _seed_five(tmp_timeline)

    resp = client.get("/api/timeline/recent?status=in_orbit")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["entries"] == []
