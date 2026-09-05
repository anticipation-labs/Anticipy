"""The container's boot: what it proves before it trusts a 404, and whose
archive ring it prunes.  Audit F28 and F43.

brain/container_entry.py had NO test and no gate leg of any kind, which is how
both of these survived: it is the one file in the port with no oracle, and its
failure mode is silent data loss.

F28, the shape, reproduced against R2 with real credentials on 2026-09-05:

    download_file(bucket-that-does-not-exist, key)  -> Code "404", HTTP 404
    download_file(real-bucket, key-that-is-absent)  -> Code "404", HTTP 404

boto3's download_file HEADs first and a HEAD has no body, so NoSuchBucket and
NoSuchKey arrive identical. `_is_not_found` said True to both, so one rotated
credential or one typo in the bucket name read as "new owner" for every state
file: the brain booted with an empty memory, the snapshot loop swallowed each
failed PUT as "will retry next tick", and /health kept answering ok:true with
has_s3:true. head_bucket is the one call that tells the two apart.

F43: the daily archive keys were `worker/state-<stamp>.zip` for EVERY owner —
one shared ring of 14, pruned by whoever uploaded last.
"""
import json
import os
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import brain.container_entry as C  # noqa: E402
from brain import state_backup as B  # noqa: E402


class ClientError(Exception):
    """The shape botocore hands back, which is all this code inspects."""

    def __init__(self, code, status, message="boom"):
        super().__init__(message)
        self.response = {"Error": {"Code": str(code)},
                         "ResponseMetadata": {"HTTPStatusCode": status}}


class FakeR2:
    """An R2 that can be told what each call does."""

    def __init__(self, head_bucket_error=None, download_error=None):
        self._head_bucket_error = head_bucket_error
        self._download_error = download_error
        self.head_bucket_calls = []
        self.downloads = []

    def head_bucket(self, Bucket):
        self.head_bucket_calls.append(Bucket)
        if self._head_bucket_error:
            raise self._head_bucket_error
        return {"ResponseMetadata": {"HTTPStatusCode": 200}}

    def download_file(self, bucket, key, dest):
        self.downloads.append(key)
        if self._download_error:
            raise self._download_error
        Path(dest).write_bytes(b"durable-state")


@pytest.fixture
def owner_dir(tmp_path, monkeypatch):
    """Point the module at a scratch volume for one owner."""
    root = tmp_path / "data" / "owners"
    monkeypatch.setattr(C, "STATE_ROOT", root)
    monkeypatch.setattr(C, "OWNER_REF", "qeuy6sv1raof9rw")
    monkeypatch.setattr(C, "_owner_dir", root / "qeuy6sv1raof9rw")
    monkeypatch.setattr(C, "R2_BUCKET", "anticipy-owner-state")
    return root / "qeuy6sv1raof9rw"


# ----------------------------------------------------------------- F28

def test_a_bucket_that_is_not_there_aborts_the_boot(owner_dir):
    """The whole finding. A wrong bucket answers 404 exactly like an absent
    object, so without this check the brain boots empty and then overwrites
    the real memory on its next snapshot."""
    r2 = FakeR2(head_bucket_error=ClientError("404", 404))

    with pytest.raises(RuntimeError) as caught:
        C.pull_state(r2)

    assert "anticipy-owner-state" in str(caught.value)
    assert "refusing to boot" in str(caught.value)
    assert r2.downloads == [], "no file may be read as absent before the bucket is proven"


def test_the_bucket_is_proven_before_the_first_file_is_asked_for(owner_dir):
    """Order is the property: a head_bucket AFTER the loop would have let
    every 404 through first."""
    r2 = FakeR2()

    C.pull_state(r2)

    assert r2.head_bucket_calls == ["anticipy-owner-state"]
    assert r2.downloads == ["owners/qeuy6sv1raof9rw/memory.db",
                            "owners/qeuy6sv1raof9rw/clock_state.json"]
    assert (owner_dir / "memory.db").read_bytes() == b"durable-state"


def test_bad_credentials_abort_rather_than_looking_like_a_new_owner(owner_dir):
    """Any failure of the bucket check is fatal — there is no missing bucket
    that is safe to continue past."""
    for err in (ClientError("AccessDenied", 403),
                ClientError("InvalidAccessKeyId", 403),
                ClientError("NoSuchBucket", 404),
                OSError("connection reset")):
        r2 = FakeR2(head_bucket_error=err)
        with pytest.raises(RuntimeError):
            C.pull_state(r2)
        assert r2.downloads == []


def test_a_genuinely_absent_object_is_still_a_new_owner(owner_dir):
    """The other half, and the reason the check had to move rather than the
    404 rule get stricter: once the bucket is proven, a per-key 404 IS a new
    owner and must boot cleanly on an empty dir."""
    r2 = FakeR2(download_error=ClientError("404", 404))

    C.pull_state(r2)

    assert owner_dir.is_dir()
    assert not (owner_dir / "memory.db").exists()
    assert len(r2.downloads) == 2, "a 404 on the first file must not stop the second"


def test_a_read_failure_that_is_not_a_404_still_aborts(owner_dir):
    """The safety property this file already had, pinned so the new bucket
    check cannot be mistaken for a replacement of it."""
    r2 = FakeR2(download_error=ClientError("InternalError", 500))

    with pytest.raises(RuntimeError) as caught:
        C.pull_state(r2)

    assert "NOT a 404" in str(caught.value)


# ----------------------------------------------------------------- F43

class FakePaginator:
    def __init__(self, client):
        self.client = client

    def paginate(self, **kwargs):
        prefix = kwargs["Prefix"]
        yield {"Contents": [{"Key": k} for k in sorted(self.client.objects)
                            if k.startswith(prefix)]}


class FakeArchiveS3:
    def __init__(self, objects=None):
        self.objects = dict(objects or {})
        self.deleted = []

    def upload_file(self, filename, bucket, key, ExtraArgs=None):
        self.objects[key] = {"body": Path(filename).read_bytes(),
                             "metadata": (ExtraArgs or {}).get("Metadata", {})}

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


def _make_owner_state(volume_root: Path, ref: str) -> None:
    owner = volume_root / "owners" / ref
    owner.mkdir(parents=True)
    with sqlite3.connect(owner / "memory.db") as db:
        db.execute("create table episodes (text text)")
        db.execute("insert into episodes values ('a durable memory')")
    (owner / "clock_state.json").write_text(json.dumps({"welcomed_phones": []}))


def _config(prefix="worker/", keep="14"):
    return {
        "ANTICIPY_BACKUP_S3_BUCKET": "anticipy-backups-production",
        "ANTICIPY_BACKUP_S3_ENDPOINT": "https://example.r2.cloudflarestorage.com",
        "ANTICIPY_BACKUP_S3_ACCESS_KEY": "access",
        "ANTICIPY_BACKUP_S3_SECRET": "secret",
        "ANTICIPY_STATE_BACKUP_PREFIX": prefix,
        "ANTICIPY_STATE_BACKUP_KEEP": keep,
    }


def test_each_owner_gets_a_prefix_of_their_own(monkeypatch):
    monkeypatch.setenv("ANTICIPY_STATE_BACKUP_PREFIX", "worker/")
    monkeypatch.setattr(C, "OWNER_REF", "qeuy6sv1raof9rw")
    assert C.backup_env()["ANTICIPY_STATE_BACKUP_PREFIX"] == "worker/qeuy6sv1raof9rw/"

    monkeypatch.setattr(C, "OWNER_REF", "43dl3t9oz7q34qc")
    assert C.backup_env()["ANTICIPY_STATE_BACKUP_PREFIX"] == "worker/43dl3t9oz7q34qc/"

    # An unset fleet prefix keeps the documented default as the parent.
    monkeypatch.delenv("ANTICIPY_STATE_BACKUP_PREFIX")
    assert C.backup_env()["ANTICIPY_STATE_BACKUP_PREFIX"] == "worker/43dl3t9oz7q34qc/"


def test_one_owners_daily_archive_cannot_prune_anothers(tmp_path):
    """The finding as the fleet would meet it: fourteen containers uploading
    into one ring means an owner's history is deleted by strangers. Here the
    second owner uploads with a full ring of their own AND a full ring
    belonging to somebody else; only their own oldest may go."""
    volume = tmp_path / "data"
    _make_owner_state(volume, "43dl3t9oz7q34qc")

    other = {f"worker/qeuy6sv1raof9rw/state-202609{d:02d}T000000Z.zip": {
        "body": b"x", "metadata": {}} for d in range(1, 15)}
    mine = {f"worker/43dl3t9oz7q34qc/state-202609{d:02d}T000000Z.zip": {
        "body": b"x", "metadata": {}} for d in range(1, 15)}
    s3 = FakeArchiveS3({**other, **mine})

    env = _config(prefix="worker/43dl3t9oz7q34qc/", keep="14")
    key = B.backup_state_to_s3(volume, env=env, client=s3)

    assert key.startswith("worker/43dl3t9oz7q34qc/state-")
    assert s3.deleted, "the owner's own ring is still pruned to its ceiling"
    assert all(k.startswith("worker/43dl3t9oz7q34qc/") for k in s3.deleted), (
        f"another owner's history was deleted: {s3.deleted}")
    assert all(k in s3.objects for k in other), "every stranger's archive survives"


def test_the_archive_is_rooted_where_the_restore_script_looks(tmp_path):
    """migration/workers/BRAIN.md's restore step requires `owners/<ref>/…`
    and exits FATAL without it, so the container must zip the VOLUME root,
    one level above the owners directory."""
    volume = tmp_path / "data"
    _make_owner_state(volume, "qeuy6sv1raof9rw")
    s3 = FakeArchiveS3()

    B.backup_state_to_s3(volume, env=_config(prefix="worker/qeuy6sv1raof9rw/"),
                         client=s3)

    key = next(iter(s3.objects))
    import io
    import zipfile
    with zipfile.ZipFile(io.BytesIO(s3.objects[key]["body"])) as archive:
        names = set(archive.namelist())
    assert "owners/qeuy6sv1raof9rw/memory.db" in names, sorted(names)
    assert "owners/qeuy6sv1raof9rw/clock_state.json" in names


def test_the_container_archives_the_volume_root_not_the_owners_dir():
    """The call itself, read from the source: `STATE_ROOT` alone produced
    `<ref>/memory.db`, which no restore path in the repo accepts."""
    source = Path(C.__file__).read_text()
    call = source[source.index("key = backup_state_to_s3("):]
    call = call[:call.index("\n")]
    assert "STATE_ROOT.parent" in call, call
    assert "env=backup_env()" in call, call
