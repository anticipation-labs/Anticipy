"""The pure halves of proof/e2e_cloudflare.py, driven with fakes. No network.

Three things must hold or the live run proves the wrong thing:
  * the body it posts is the phone's body, omissions included;
  * "column absent" and "not stamped" are reported as different facts;
  * the design table's exit code is 0 only when every hop that CAN be proven
    from this machine is proven, and the two that cannot never vote.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from proof import e2e_cloudflare as e2e  # noqa: E402

T0 = dt.datetime(2026, 9, 5, 14, 30, 12, 345000, tzinfo=dt.timezone.utc)
T1 = T0 + dt.timedelta(seconds=3, milliseconds=200)


# ------------------------------------------------------ the phone-shaped body

def test_body_is_the_phones_body_field_for_field():
    body = e2e.phone_body("my dentist moved to Thursdays at 3", "qeuy6sv1raof9rw", T0, T1)
    # Exactly the keys AnticipyBackend.pushEvent sends for an ambient spoken
    # line with no voice verdict — nothing more, nothing less.
    assert set(body) == {"device_id", "kind", "text", "decision", "goal",
                         "capture_started_at", "spoken_at", "capture_ended_at",
                         "source", "owner_ref"}
    assert body["kind"] == "transcript"
    assert body["decision"] == "" and body["goal"] == ""
    assert body["device_id"] == "e2e-phone-2026-09-05"
    assert body["source"] == "phone_mic"
    assert body["owner_ref"] == "qeuy6sv1raof9rw"


def test_capture_envelope_writes_the_start_under_both_names():
    body = e2e.phone_body("x", "qeuy6sv1raof9rw", T0, T1)
    assert body["capture_started_at"] == "2026-09-05T14:30:12.345Z"
    assert body["spoken_at"] == body["capture_started_at"]
    assert body["capture_ended_at"] == "2026-09-05T14:30:15.545Z"


def test_omissions_are_the_phones_omissions():
    body = e2e.phone_body("x", "qeuy6sv1raof9rw", T0, T1)
    for never_on_speech in ("speaker", "explicit", "parent_line", "external_event_id",
                            "importance", "boot_id", "seq", "gap_before_ms"):
        assert never_on_speech not in body
    typed = e2e.phone_body("x", "qeuy6sv1raof9rw", T0, T1, explicit=True, speaker="owner",
                           parent_line="abc123", external_event_id="app:1")
    assert typed["explicit"] is True
    assert typed["speaker"] == "owner"
    assert typed["parent_line"] == "abc123"
    assert typed["external_event_id"] == "app:1"
    # explicit=False must not appear as a key at all — the Swift only sets it when true.
    assert "explicit" not in e2e.phone_body("x", "o", T0, T1, explicit=False)
    # an unknown ear is left OFF, never sent as ""
    assert "source" not in e2e.phone_body("x", "o", T0, T1, source="")


def test_body_is_json_serialisable_as_posted():
    body = e2e.phone_body("x", "qeuy6sv1raof9rw", T0, T1)
    assert json.loads(json.dumps(body)) == body


def test_pb_stamp_is_the_filterable_form():
    assert e2e.pb_stamp(T0) == "2026-09-05 14:30:12.345Z"
    assert e2e.parse_pb_ts("2026-09-05 14:30:12.345Z") == T0
    assert e2e.parse_pb_ts("2026-09-05T14:30:12.345Z") == T0
    assert e2e.parse_pb_ts("") is None
    assert e2e.parse_pb_ts("yesterday") is None


# ------------------------------------------ column absent vs not stamped

def test_decision_states():
    assert e2e.decision_state({"decision": ""}) == "unheard"
    assert e2e.decision_state({}) == "unheard"
    assert e2e.decision_state({"decision": "processing"}) == "processing"
    assert e2e.decision_state({"decision": "ignore"}) == "stamped"
    assert e2e.decision_state({"decision": "act", "goal": "open example.com"}) == "stamped"


def test_heard_absent_is_not_heard_unstamped():
    # D1 without the ALTER: the Worker's row carries no such key.
    assert e2e.heard_state({"decision": "ignore"}) == "absent"
    assert e2e.heard_state({"decision": "ignore", "heard_ms": None}) == "absent"
    # The columns exist and the worker that decided did not measure.
    assert e2e.heard_state({"decision": "ignore", "heard_ms": 0, "heard_calls": 0}) == "unstamped"
    # Measured.
    assert e2e.heard_state({"decision": "act", "heard_ms": 4210, "heard_calls": 3}) == "measured:4210/3"
    assert e2e.heard_state({"decision": "act", "heard_ms": 4210.0, "heard_calls": 3.0}) == "measured:4210/3"
    # Nothing was expected on an undecided row, whatever the columns say.
    assert e2e.heard_state({"decision": "", "heard_ms": 0}) == "unheard"
    assert e2e.heard_state({"decision": "processing"}) == "unheard"


# ------------------------------------------------------------ the hop table

def test_exit_zero_only_when_every_provable_hop_is_proven():
    t = e2e.HopTable()
    assert t.exit_code() == 2
    for hop in ("ears -> API", "API -> brain", "brain -> mouth", "brain -> hands", "hands"):
        t.proven(hop, f"row for {hop}")
    # The two rows this machine cannot prove never vote.
    t.not_proven("hands -> mouth", "fictional number")
    t.not_proven("memory", "tomorrow")
    assert t.exit_code() == 0


def test_one_unproven_provable_hop_is_unproven():
    t = e2e.HopTable()
    for hop in ("ears -> API", "API -> brain", "brain -> mouth", "brain -> hands"):
        t.proven(hop, "x")
    t.not_proven("hands", "job queued, no arm beating")
    assert t.exit_code() == 2
    lines = "\n".join(t.lines())
    assert "hands            NOT PROVEN  job queued, no arm beating" in lines
    assert "hands -> mouth   NOT HERE" in lines
    assert "memory           NOT HERE" in lines


def test_table_has_one_row_per_design_hop_in_order():
    names = [n for n, _ in e2e.HOPS]
    assert names == ["ears -> API", "API -> brain", "brain -> mouth", "brain -> hands",
                     "hands", "hands -> mouth", "memory"]
    t = e2e.HopTable()
    assert [l.split()[0] for l in t.lines()][:2] == ["ears", "API"]


# --------------------------------------------------------- the beating arm

def test_paired_is_not_live():
    now = dt.datetime(2026, 9, 5, 14, 0, 0, tzinfo=dt.timezone.utc)
    fresh = {"paired": True, "last_seen": "2026-09-05 13:59:30.000Z"}
    stale = {"paired": True, "last_seen": "2026-09-05 13:40:00.000Z"}
    unpaired = {"paired": False, "last_seen": "2026-09-05 13:59:59.000Z"}
    assert e2e.is_beating(fresh, now=now)
    assert not e2e.is_beating(stale, now=now)
    assert not e2e.is_beating(unpaired, now=now)
    assert not e2e.is_beating({"paired": True, "last_seen": ""}, now=now)


# ------------------------------------------------------- the audit ledger

def test_audit_sql_refuses_anything_but_an_owner_id_and_a_stamp():
    sql = e2e.audit_sql("qeuy6sv1raof9rw", "2026-09-05 14:30:11.345Z")
    assert "WHERE owner_ref = 'qeuy6sv1raof9rw' AND created >= '2026-09-05 14:30:11.345Z'" in sql
    assert sql.startswith("SELECT ")
    with pytest.raises(ValueError):
        e2e.audit_sql("qeuy6sv1raof9rw' OR 1=1 --", "2026-09-05 14:30:11.345Z")
    with pytest.raises(ValueError):
        e2e.audit_sql("qeuy6sv1raof9rw", "2026-09-05T14:30:11Z")


def test_audit_summary_reads_both_caps():
    row = {"id": "kct8y7f2hjmorjp", "created": "2026-09-05 12:55:17.407Z",
           "agent_id": "2bcebc6e", "provider": "openrouter",
           "model": "google/gemini-3.1-pro-preview", "provider_model": "google/gemini-3.1-pro-preview",
           "status": "ok", "http_status": 200, "duration_ms": 5412,
           "client_request_json": json.dumps({"model": "m", "max_tokens": 300}),
           "provider_request_json": json.dumps({"model": "m", "max_tokens": 512})}
    s = e2e.audit_summary(row)
    assert s["max_tokens_client"] == 300
    assert s["max_tokens_provider"] == 512
    assert s["provider"] == "openrouter" and s["status"] == "ok"
    # unreadable JSON is None, never a crash
    assert e2e.audit_summary({"client_request_json": "{not json"})["max_tokens_client"] is None


# ------------------------------------------------------------- the inputs

def test_the_three_lines_are_the_design_moments():
    keys = [k for k, _, _ in e2e.LINES]
    assert keys == ["a", "b", "c"]
    a, b, c = (t for _, _, t in e2e.LINES)
    assert "dentist" in a and "Thursdays at 3" in a and "Broadway" in a
    # (b) names the browser so job_lane keeps it on the browser lane, and a
    # site a job on https://example.com/ can satisfy
    assert "browser" in b and "example.com" in b
    # (c) is addressed to her and punctuated as the phone punctuates
    assert b.startswith("Anticipy") and c.startswith("Anticipy") and c.endswith("?")


def test_env_root_walks_up_to_a_dotenv(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTICIPY_ENV_ROOT", raising=False)
    (tmp_path / ".env.local").write_text("X=1\n")
    deep = tmp_path / ".claude" / "worktrees" / "agent-x"
    deep.mkdir(parents=True)
    assert e2e.env_root(str(deep)) == str(tmp_path)
    monkeypatch.setenv("ANTICIPY_ENV_ROOT", "/elsewhere")
    assert e2e.env_root(str(deep)) == "/elsewhere"
