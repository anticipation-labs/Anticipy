from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import zipfile

import pytest

from brain import state_backup as B


class FakePaginator:
    def __init__(self, client):
        self.client = client

    def paginate(self, **kwargs):
        prefix = kwargs["Prefix"]
        yield {"Contents": [{"Key": key} for key in sorted(self.client.objects)
                            if key.startswith(prefix)]}


class FakeS3:
    def __init__(self):
        self.objects = {}
        self.deleted = []

    def upload_file(self, filename, bucket, key, ExtraArgs):
        self.objects[key] = {
            "body": Path(filename).read_bytes(),
            "metadata": ExtraArgs["Metadata"],
            "encryption": ExtraArgs["ServerSideEncryption"],
        }

    def head_object(self, Bucket, Key):
        row = self.objects[Key]
        return {"ContentLength": len(row["body"]), "Metadata": row["metadata"]}

    def get_paginator(self, name):
        assert name == "list_objects_v2"
        return FakePaginator(self)

    def delete_objects(self, Bucket, Delete):
        keys = [row["Key"] for row in Delete["Objects"]]
        self.deleted.extend(keys)
        for key in keys:
            self.objects.pop(key, None)


def configured():
    return {
        "ANTICIPY_BACKUP_S3_BUCKET": "private-backups",
        "ANTICIPY_BACKUP_S3_ENDPOINT": "https://example.r2.cloudflarestorage.com",
        "ANTICIPY_BACKUP_S3_ACCESS_KEY": "access",
        "ANTICIPY_BACKUP_S3_SECRET": "secret",
        "ANTICIPY_BACKUP_S3_REGION": "auto",
        "ANTICIPY_STATE_BACKUP_KEEP": "2",
    }


def make_state(root: Path):
    owner = root / "owners" / "owner00000000001"
    owner.mkdir(parents=True)
    with sqlite3.connect(owner / "memory.db") as db:
        db.execute("create table episodes (text text)")
        db.execute("insert into episodes values ('a durable memory')")
    (owner / "clock_state.json").write_text(json.dumps({"last_seen": 7}))


def test_archive_is_a_consistent_restorable_snapshot(tmp_path):
    state = tmp_path / "state"
    make_state(state)
    archive = tmp_path / "state.zip"

    manifest = B.build_archive(
        state, archive, created_at=datetime(2026, 8, 31, tzinfo=timezone.utc))

    assert [row["path"] for row in manifest["files"]] == [
        "owners/owner00000000001/clock_state.json",
        "owners/owner00000000001/memory.db",
    ]
    with zipfile.ZipFile(archive) as zipped:
        assert zipped.testzip() is None
        zipped.extractall(tmp_path / "restored")
    restored = tmp_path / "restored" / "owners" / "owner00000000001" / "memory.db"
    with sqlite3.connect(restored) as db:
        assert db.execute("pragma quick_check").fetchone() == ("ok",)
        assert db.execute("select text from episodes").fetchone() == ("a durable memory",)


def test_upload_is_encrypted_verified_and_retained(tmp_path):
    state = tmp_path / "state"
    make_state(state)
    s3 = FakeS3()
    s3.objects["worker/state-20260828T000000Z.zip"] = {"body": b"old", "metadata": {}}
    s3.objects["worker/state-20260829T000000Z.zip"] = {"body": b"less old", "metadata": {}}

    key = B.backup_state_to_s3(
        state, env=configured(), client=s3,
        now=datetime(2026, 8, 31, 3, 4, 5, tzinfo=timezone.utc))

    assert key == "worker/state-20260831T030405Z.zip"
    uploaded = s3.objects[key]
    assert uploaded["encryption"] == "AES256"
    assert uploaded["metadata"]["sha256"] == hashlib.sha256(uploaded["body"]).hexdigest()
    assert uploaded["metadata"]["file-count"] == "2"
    assert s3.deleted == ["worker/state-20260828T000000Z.zip"]


def test_missing_configuration_is_quiet_but_partial_configuration_is_loud(tmp_path):
    assert B.backup_state_to_s3(tmp_path, env={}) is None
    with pytest.raises(RuntimeError, match="required"):
        B.backup_config({"ANTICIPY_BACKUP_REQUIRED": "1"})
    with pytest.raises(RuntimeError, match="ANTICIPY_BACKUP_S3_ENDPOINT"):
        B.backup_config({"ANTICIPY_BACKUP_S3_BUCKET": "only-one-field"})


def test_links_cannot_escape_the_private_state_root(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    (state / "memory.db").symlink_to(tmp_path / "somewhere-else.db")
    with pytest.raises(RuntimeError, match="symlink"):
        list(B.state_files(state))
