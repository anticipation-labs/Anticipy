"""Tests for the unified timeline writer + reader.

Phase 2 gate (ARCHITECTURE.md section 3 + 14). Each test owns its own
temporary jsonl path via the ``ANTICIPY_TIMELINE_PATH`` env var so the
suite never touches the real ``~/.anticipy/v7/timeline.jsonl``.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.timeline import reader, writer  # noqa: E402  (sys.path setup)
from app.timeline.writer import append, new_goal_id  # noqa: E402


@pytest.fixture
def tmp_timeline(tmp_path, monkeypatch):
    """Point the writer + reader at a fresh per-test jsonl path."""
    path = tmp_path / "timeline.jsonl"
    monkeypatch.setenv("ANTICIPY_TIMELINE_PATH", str(path))
    return path


def _read_lines(path: Path) -> list[dict]:
    """Helper that reads every JSONL line into a dict list."""
    if not path.exists():
        return []
    out: list[dict] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


# ---------------------------------------------------------------------------
# Writer tests
# ---------------------------------------------------------------------------


def test_append_writes_jsonl(tmp_timeline):
    """A single append produces exactly one JSONL line with the full row."""
    append({
        "kind": "sms_sent",
        "channel": "twilio_sms",
        "status": "done",
        "summary": "Confirmed lunch with Sarah",
        "payload": {"to": "+16047245161"},
    })
    rows = _read_lines(tmp_timeline)
    assert len(rows) == 1
    row = rows[0]
    assert row["kind"] == "sms_sent"
    assert row["channel"] == "twilio_sms"
    assert row["status"] == "done"
    assert row["summary"] == "Confirmed lunch with Sarah"
    assert row["payload"] == {"to": "+16047245161"}
    # Auto-filled fields are present and well-formed.
    assert isinstance(row["ts"], (int, float))
    assert row["goal_id"].startswith("g-")


def test_required_fields_validated(tmp_timeline):
    """Missing ``kind`` (or any other required field) raises ValueError."""
    with pytest.raises(ValueError):
        append({"status": "done", "summary": "no kind"})
    with pytest.raises(ValueError):
        append({"kind": "note", "summary": "no status"})
    with pytest.raises(ValueError):
        append({"kind": "note", "status": "done"})  # no summary
    with pytest.raises(ValueError):
        append({
            "kind": "bogus_kind",
            "status": "done",
            "summary": "invalid kind",
        })
    with pytest.raises(ValueError):
        append({
            "kind": "note",
            "status": "in_orbit",
            "summary": "invalid status",
        })
    # Nothing should have landed on disk.
    assert _read_lines(tmp_timeline) == []


def test_auto_goal_id_when_omitted(tmp_timeline):
    """Two appends without goal_id produce two distinct generated ids."""
    append({"kind": "note", "status": "done", "summary": "first"})
    append({"kind": "note", "status": "done", "summary": "second"})
    rows = _read_lines(tmp_timeline)
    assert len(rows) == 2
    g1 = rows[0]["goal_id"]
    g2 = rows[1]["goal_id"]
    assert g1.startswith("g-") and g2.startswith("g-")
    assert g1 != g2
    # An explicit goal_id is preserved verbatim.
    append({
        "kind": "note", "status": "done", "summary": "third",
        "goal_id": "g-fixed-id",
    })
    rows = _read_lines(tmp_timeline)
    assert rows[-1]["goal_id"] == "g-fixed-id"


def test_auto_ts_when_omitted(tmp_timeline):
    """ts is auto-filled when missing and preserved when supplied."""
    before = time.time()
    append({"kind": "note", "status": "done", "summary": "auto ts"})
    after = time.time()
    rows = _read_lines(tmp_timeline)
    assert before <= rows[0]["ts"] <= after
    # Explicit ts (including float in the past) is preserved verbatim.
    append({
        "kind": "note", "status": "done", "summary": "fixed ts",
        "ts": 1234567890.5,
    })
    rows = _read_lines(tmp_timeline)
    assert rows[-1]["ts"] == 1234567890.5


def test_thread_safe_concurrent_append(tmp_timeline):
    """10 threads * 100 appends each must produce exactly 1000 valid lines."""
    n_threads = 10
    per_thread = 100

    def worker(tid: int) -> None:
        for i in range(per_thread):
            append({
                "kind": "web_action",
                "channel": "chrome",
                "status": "done",
                "summary": f"thread {tid} entry {i}",
                "payload": {"tid": tid, "i": i},
            })

    threads = [
        threading.Thread(target=worker, args=(tid,))
        for tid in range(n_threads)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    rows = _read_lines(tmp_timeline)
    assert len(rows) == n_threads * per_thread, (
        f"expected {n_threads * per_thread} rows, got {len(rows)}"
    )
    # Every line must be valid JSON with the required fields (proves no
    # interleaved / torn writes).
    seen: set[tuple[int, int]] = set()
    for row in rows:
        assert row["kind"] == "web_action"
        assert row["status"] == "done"
        seen.add((row["payload"]["tid"], row["payload"]["i"]))
    assert len(seen) == n_threads * per_thread


def test_rotation_at_100mb(tmp_timeline, monkeypatch):
    """When the active file exceeds the threshold, the next append
    rotates the old file to ``timeline.jsonl.<DATE>.bak`` and writes
    into a fresh active file."""
    # Shrink the rotation threshold so we don't need a real 100 MB file.
    monkeypatch.setattr(writer, "MAX_BYTES_BEFORE_ROTATE", 200)

    # First write: lands in the active file.
    append({"kind": "note", "status": "done", "summary": "before"})
    assert tmp_timeline.exists()

    # Pad the file past the threshold so the next append triggers
    # rotation. We write directly to avoid emitting more rows.
    with open(tmp_timeline, "ab") as fh:
        fh.write(b"x" * 500)
    assert tmp_timeline.stat().st_size > 200

    # The next append should rotate the old file out and start fresh.
    append({"kind": "note", "status": "done", "summary": "after rotation"})

    # The new active file holds only the post-rotation row.
    rows = _read_lines(tmp_timeline)
    assert len(rows) == 1
    assert rows[0]["summary"] == "after rotation"

    # A dated .bak file exists alongside the active file.
    bak_files = list(tmp_timeline.parent.glob("timeline.jsonl.*.bak"))
    assert bak_files, (
        f"expected rotated .bak file in {tmp_timeline.parent}, "
        f"found {list(tmp_timeline.parent.iterdir())}"
    )


# ---------------------------------------------------------------------------
# Reader tests
# ---------------------------------------------------------------------------


def test_reader_tail(tmp_timeline):
    """tail(n) returns the last n rows in file order."""
    # Empty case.
    assert reader.tail(10) == []

    for i in range(20):
        append({
            "kind": "note", "status": "done",
            "summary": f"entry {i}", "payload": {"i": i},
        })

    last5 = reader.tail(5)
    assert len(last5) == 5
    assert [r["payload"]["i"] for r in last5] == [15, 16, 17, 18, 19]

    # Asking for more than exists returns everything.
    all20 = reader.tail(100)
    assert len(all20) == 20
    assert all20[0]["payload"]["i"] == 0
    assert all20[-1]["payload"]["i"] == 19

    # Zero / negative is a no-op.
    assert reader.tail(0) == []
    assert reader.tail(-1) == []


def test_reader_filter_by_kind(tmp_timeline):
    """filter_by(kind=...) only yields matching rows."""
    append({"kind": "sms_sent", "status": "done",
            "summary": "sms 1", "channel": "twilio_sms"})
    append({"kind": "email_sent", "status": "done",
            "summary": "email 1", "channel": "chrome"})
    append({"kind": "sms_sent", "status": "failed",
            "summary": "sms 2", "channel": "twilio_sms"})
    append({"kind": "web_action", "status": "done",
            "summary": "web 1", "channel": "chrome"})

    sms_rows = list(reader.filter_by(kind="sms_sent"))
    assert len(sms_rows) == 2
    assert {r["summary"] for r in sms_rows} == {"sms 1", "sms 2"}

    # Combine with status.
    failed_sms = list(reader.filter_by(kind="sms_sent", status="failed"))
    assert len(failed_sms) == 1
    assert failed_sms[0]["summary"] == "sms 2"

    # No-match filter returns empty iterator.
    assert list(reader.filter_by(kind="voice_call")) == []


def test_reader_filter_by_goal_id(tmp_timeline):
    """filter_by(goal_id=...) groups every row tied to that goal."""
    gid = "g-test-goal-12345"
    append({"kind": "sms_sent", "status": "wait_user",
            "summary": "ask user", "goal_id": gid})
    append({"kind": "user_reply", "status": "done",
            "summary": "YES", "goal_id": gid})
    append({"kind": "web_action", "status": "done",
            "summary": "executed", "goal_id": gid})
    # Unrelated entries that must NOT appear in the filtered view.
    append({"kind": "note", "status": "done", "summary": "other goal"})
    append({"kind": "note", "status": "done", "summary": "another"})

    rows = list(reader.filter_by(goal_id=gid))
    assert len(rows) == 3
    assert all(r["goal_id"] == gid for r in rows)
    assert [r["kind"] for r in rows] == [
        "sms_sent", "user_reply", "web_action",
    ]

    # since_ts also works in combination.
    cutoff = time.time() + 60  # nothing in the future
    assert list(reader.filter_by(goal_id=gid, since_ts=cutoff)) == []
    past = 0.0
    assert len(list(reader.filter_by(goal_id=gid, since_ts=past))) == 3
