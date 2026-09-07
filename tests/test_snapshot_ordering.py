"""Adversarial ordering at the real snapshot function's S3 boundary."""
import sqlite3
import threading
from pathlib import Path

from brain import container_entry as entry


def test_an_older_snapshot_cannot_finish_after_and_replace_a_newer_one(tmp_path, monkeypatch):
    monkeypatch.setattr(entry, "_owner_dir", tmp_path)
    memory = tmp_path / "memory.db"
    with sqlite3.connect(memory) as db:
        db.execute("CREATE TABLE remembered (revision INTEGER)")
        db.execute("INSERT INTO remembered VALUES (1)")
    first_upload = threading.Event()
    release_first = threading.Event()
    second_done = threading.Event()
    errors = []

    class S3:
        uploads = 0
        body = None
        lock = threading.Lock()

        def upload_file(self, filename, bucket, key):
            body = Path(filename).read_bytes()
            with self.lock:
                self.uploads += 1
                first = self.uploads == 1
            if first:
                first_upload.set()
                assert release_first.wait(5), "test failed to release first upload"
            self.body = body

    s3 = S3()

    def snapshot(done=None):
        try:
            entry.snapshot_once(s3)
        except Exception as error:
            errors.append(error)
        finally:
            if done:
                done.set()

    first = threading.Thread(target=snapshot)
    first.start()
    assert first_upload.wait(5)
    with sqlite3.connect(memory) as db:
        db.execute("UPDATE remembered SET revision = 2")
    second = threading.Thread(target=snapshot, args=(second_done,))
    second.start()
    try:
        overtook = second_done.wait(0.2)
    finally:
        release_first.set()
        first.join(5)
        second.join(5)
    assert not first.is_alive() and not second.is_alive()
    assert errors == []
    restored = tmp_path / "restored.db"
    restored.write_bytes(s3.body)
    with sqlite3.connect(restored) as db:
        assert db.execute("SELECT revision FROM remembered").fetchone()[0] == 2, \
            "the older upload completed last and erased the newer durable memory"
    assert not overtook, "two snapshots shared a temporary file and upload stream"
