"""Restoring corrupt or partial remote state must preserve the local checkpoint."""
import json
import sqlite3
from pathlib import Path

import pytest

from brain import container_entry as entry


def database(path, revision):
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE remembered (revision INTEGER)")
        db.execute("INSERT INTO remembered VALUES (?)", (revision,))
    return path.read_bytes()


@pytest.mark.parametrize("failure", ["corrupt_memory", "invalid_clock", "clock_read_failure"])
def test_failed_restore_does_not_publish_either_download(tmp_path, monkeypatch, failure):
    owner = tmp_path / "owner"
    owner.mkdir()
    old_memory = database(owner / "memory.db", 1)
    old_clock = b'{"last_outreach_ts": 100}'
    (owner / "clock_state.json").write_bytes(old_clock)
    remote_memory = database(tmp_path / "remote.db", 2)
    monkeypatch.setattr(entry, "_owner_dir", owner)

    class Remote:
        def head_bucket(self, **_):
            return {}

        def download_file(self, bucket, key, destination):
            path = Path(destination)
            if key.endswith("memory.db"):
                path.write_bytes(b"corrupt" if failure == "corrupt_memory" else remote_memory)
            elif failure == "clock_read_failure":
                path.write_bytes(b"partial")
                raise OSError("connection lost while downloading clock")
            else:
                path.write_text('[]' if failure == "invalid_clock" else '{"last_outreach_ts": 200}')

    with pytest.raises(RuntimeError):
        entry.pull_state(Remote())
    assert (owner / "memory.db").read_bytes() == old_memory
    assert (owner / "clock_state.json").read_bytes() == old_clock


def test_validated_restore_replaces_the_checkpoint(tmp_path, monkeypatch):
    remote = database(tmp_path / "remote.db", 2)
    owner = tmp_path / "owner"
    monkeypatch.setattr(entry, "_owner_dir", owner)

    class Remote:
        def head_bucket(self, **_):
            return {}

        def download_file(self, bucket, key, destination):
            Path(destination).write_bytes(remote if key.endswith("memory.db") else b'{"last_outreach_ts": 200}')

    entry.pull_state(Remote())
    with sqlite3.connect(owner / "memory.db") as db:
        assert db.execute("SELECT revision FROM remembered").fetchone()[0] == 2
    assert json.loads((owner / "clock_state.json").read_text())["last_outreach_ts"] == 200
