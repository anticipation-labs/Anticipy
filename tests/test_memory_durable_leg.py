"""The leg that proves an owner's mind is being kept.  Audit F29.

On Cloudflare the container's filesystem dies with the instance; the durable
copy of memory.db is one object in R2. Nothing in overnight/ read that object
— consolidation_gate.py globs a LOCAL directory that does not exist on this
platform, so it read green over nothing at all, and the ledger line for memory
said `NOT HERE`.

These tests drive the new leg's real functions: its verdict, its roll-up, its
reading of a real SQLite snapshot, and its refusal to call an unreadable
bucket an absent one — the confusion that made F28 possible inside the
container.
"""
import os
import sqlite3
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from overnight import is_memory_durable as M  # noqa: E402


# ------------------------------------------------------------- the verdict

def test_a_served_owner_with_no_memory_in_r2_is_red():
    """The container refuses to boot without it and the brain deploy refuses
    to ship without it; a leg that shrugged would contradict both."""
    code, _, sentence = M.owner_verdict("qeuy6sv1raof9rw", False, None, 1000.0)

    assert code == 1
    assert "NO memory.db in R2" in sentence


def test_a_stalled_snapshot_loop_is_red():
    """She decided something five minutes after the last durable write. That
    gap is what a lost container costs the owner."""
    code, _, sentence = M.owner_verdict("o", True, 1000.0, 1400.0)

    assert code == 1
    assert "behind" in sentence


def test_a_snapshot_inside_the_window_is_green():
    assert M.owner_verdict("o", True, 1000.0, 1200.0)[0] == 0


def test_a_quiet_owner_is_unproven_not_green():
    """The design's whole point: an owner who said nothing SHOULD have an old
    memory.db, and calling that green would be claiming a measurement nobody
    made."""
    code, _, sentence = M.owner_verdict("o", True, 1000.0, None)

    assert code == 2
    assert "freshness unproven" in sentence


def test_an_unreadable_bucket_is_never_a_verdict_about_an_owner():
    """UNPROVEN, not RED. A red leg nobody can act on gets muted, and this one
    is the only instrument for the organ."""
    assert M.owner_verdict("o", None, None, None)[0] == 2


def test_memory_ahead_of_the_decision_is_fine():
    """The comparison is one-directional on purpose: a snapshot NEWER than the
    newest decision means the loop is ahead, which is the healthy case."""
    assert M.owner_verdict("o", True, 2000.0, 1000.0)[0] == 0


def test_red_beats_unproven_beats_green():
    assert M.roll_up([0, 0, 0]) == 0
    assert M.roll_up([0, 2]) == 2
    assert M.roll_up([0, 2, 1]) == 1
    assert M.roll_up([]) == 2, "a run that checked nobody proves nothing"


# ------------------------------------------------------- reading real files

def test_the_newest_episode_is_read_out_of_a_real_snapshot(tmp_path):
    db = tmp_path / "memory.db"
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE episodes (id INTEGER PRIMARY KEY, ts REAL, "
                    "text TEXT)")
        con.execute("INSERT INTO episodes (ts, text) VALUES (?, ?)",
                    (1788624000.0, "an early thought"))
        con.execute("INSERT INTO episodes (ts, text) VALUES (?, ?)",
                    (1788624660.71, "the newest thought"))

    assert M.newest_episode_ts(str(db)) == pytest.approx(1788624660.71)


def test_a_snapshot_with_no_episodes_reads_as_none(tmp_path):
    db = tmp_path / "memory.db"
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE episodes (id INTEGER PRIMARY KEY, ts REAL)")

    assert M.newest_episode_ts(str(db)) is None


def test_a_file_that_is_not_a_database_reads_as_none(tmp_path):
    junk = tmp_path / "memory.db"
    junk.write_bytes(b"not a database")

    assert M.newest_episode_ts(str(junk)) is None


def test_the_query_never_asks_for_anybodys_words():
    """Law 1's licence for this file is that it cannot see the content. The
    one SQL statement in it is the proof."""
    source = open(M.__file__, encoding="utf-8").read()
    statements = [line for line in source.splitlines()
                  if "db.execute(" in line or "SELECT" in line.upper()]
    assert statements
    for line in statements:
        assert "max(ts)" in line.lower(), line
        assert "text" not in line.lower().split("--")[0].replace("context", ""), line


# ------------------------------------------------------------ the R2 read

def test_the_object_is_always_asked_for_remotely(tmp_path, monkeypatch):
    """Without --remote wrangler answers out of local storage and reports a
    miss for an object that is plainly there. That false negative would make
    this leg cry wolf about a healthy fleet."""
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        dest = cmd[cmd.index("--file") + 1]
        open(dest, "wb").write(b"x" * 32)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(M.subprocess, "run", fake_run)
    monkeypatch.setattr(M, "_wrangler", lambda: ["wrangler"])

    assert M.fetch_memory("qeuy6sv1raof9rw", str(tmp_path / "m.db")) is True
    assert "--remote" in seen["cmd"]
    assert "anticipy-owner-state/owners/qeuy6sv1raof9rw/memory.db" in seen["cmd"]
    assert "put" not in seen["cmd"] and "delete" not in seen["cmd"], (
        "this leg is read-only against a bucket holding people's memories")


def test_an_absent_object_and_an_unreadable_bucket_are_different_facts(
        tmp_path, monkeypatch):
    """The distinction audit F28 found missing inside the container, kept here
    deliberately: absent is a finding about an owner, unreadable is a finding
    about the gate."""
    monkeypatch.setattr(M, "_wrangler", lambda: ["wrangler"])

    def missing(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, "", "The specified key does not exist.")

    def refused(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, "", "Authentication error [code: 10000]")

    monkeypatch.setattr(M.subprocess, "run", missing)
    assert M.fetch_memory("o", str(tmp_path / "a.db")) is False

    monkeypatch.setattr(M.subprocess, "run", refused)
    assert M.fetch_memory("o", str(tmp_path / "b.db")) is None


def test_no_wrangler_at_all_is_unproven(monkeypatch, tmp_path):
    monkeypatch.setattr(M, "_wrangler", lambda: None)

    assert M.fetch_memory("o", str(tmp_path / "m.db")) is None


# --------------------------------------------------------- who is served

def test_the_served_owners_come_from_the_deploys_own_config(tmp_path):
    config = tmp_path / "wrangler.brain.jsonc"
    config.write_text('{\n  "vars": {\n'
                      '    // a comment\n'
                      '    "ANTICIPY_SERVE_OWNERS": "qeuy6sv1raof9rw,43dl3t9oz7q34qc",\n'
                      '    "ANTICIPY_MAX_OWNER_WORKERS": "0"\n  }\n}\n')

    assert M.served_owners(str(config)) == ["qeuy6sv1raof9rw", "43dl3t9oz7q34qc"]
    assert M.configured_cap(str(config)) == "0"


def test_a_config_that_cannot_be_read_serves_nobody_and_proves_nothing(tmp_path):
    assert M.served_owners(str(tmp_path / "nope.jsonc")) == []
    assert M.roll_up([]) == 2


def test_the_live_config_is_the_one_the_leg_reads():
    """The path is not a guess: the file must exist in this tree, or the leg
    silently checks nobody."""
    assert os.path.exists(M.BRAIN_CONFIG), M.BRAIN_CONFIG
    assert M.served_owners(), "the brain deploy names at least one served owner"


def test_the_self_test_is_intact():
    assert M.self_test() == 0
