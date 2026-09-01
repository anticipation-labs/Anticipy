"""Consistent, encrypted-at-rest off-volume backups of worker state.

PocketBase has its own backup engine.  The brain does not: every owner has a
private SQLite database on the worker volume, plus a small JSON clock file.
Copying a live SQLite file byte-for-byte can capture a database between writes,
so each database is copied through SQLite's online backup API and checked
before anything is uploaded.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from typing import Iterable
import zipfile


REQUIRED_ENV = (
    "ANTICIPY_BACKUP_S3_BUCKET",
    "ANTICIPY_BACKUP_S3_ENDPOINT",
    "ANTICIPY_BACKUP_S3_ACCESS_KEY",
    "ANTICIPY_BACKUP_S3_SECRET",
)


def backup_config(env: dict | None = None) -> dict | None:
    """Return a complete S3 configuration, or None when it is wholly absent.

    A partial configuration is an operational error, not an opt-out.  Treating
    it as disabled would leave production saying nothing while backups stopped.
    """
    values = os.environ if env is None else env
    present = {name: str(values.get(name) or "").strip() for name in REQUIRED_ENV}
    supplied = [name for name, value in present.items() if value]
    if not supplied:
        if str(values.get("ANTICIPY_BACKUP_REQUIRED") or "").strip() == "1":
            raise RuntimeError("worker backups are required but S3 configuration is absent")
        return None
    missing = [name for name, value in present.items() if not value]
    if missing:
        raise RuntimeError("partial backup configuration; missing " + ", ".join(missing))
    return {
        "bucket": present["ANTICIPY_BACKUP_S3_BUCKET"],
        "endpoint_url": present["ANTICIPY_BACKUP_S3_ENDPOINT"],
        "aws_access_key_id": present["ANTICIPY_BACKUP_S3_ACCESS_KEY"],
        "aws_secret_access_key": present["ANTICIPY_BACKUP_S3_SECRET"],
        "region_name": str(values.get("ANTICIPY_BACKUP_S3_REGION") or "auto").strip(),
    }


def state_files(root: Path) -> Iterable[Path]:
    """Yield only durable state files, rejecting links out of the volume."""
    root = root.resolve()
    if not root.is_dir():
        raise RuntimeError(f"state root does not exist: {root}")
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise RuntimeError(f"state backup blocked by symlink: {path.relative_to(root)}")
        if path.is_file() and path.suffix.lower() in {".db", ".json"}:
            yield path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _snapshot_sqlite(source: Path, target: Path) -> None:
    source_uri = f"file:{source}?mode=ro"
    with sqlite3.connect(source_uri, uri=True) as live, sqlite3.connect(target) as copy:
        live.backup(copy)
        verdict = copy.execute("PRAGMA quick_check").fetchone()
        if not verdict or verdict[0] != "ok":
            raise RuntimeError(f"SQLite backup check failed for {source.name}: {verdict}")


def build_archive(root: Path, destination: Path, *, created_at: datetime | None = None) -> dict:
    """Create a verified archive and return its manifest."""
    root = root.resolve()
    created_at = created_at or datetime.now(timezone.utc)
    manifest = {
        "format": 1,
        "created_at": created_at.astimezone(timezone.utc).isoformat(),
        "files": [],
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="anticipy-state-snapshot-") as temp_name:
        snapshot_root = Path(temp_name)
        for source in state_files(root):
            relative = source.relative_to(root)
            target = snapshot_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.suffix.lower() == ".db":
                _snapshot_sqlite(source, target)
            else:
                raw = source.read_bytes()
                json.loads(raw)
                target.write_bytes(raw)
            manifest["files"].append({
                "path": relative.as_posix(),
                "bytes": target.stat().st_size,
                "sha256": _sha256(target),
            })

        manifest_path = snapshot_root / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED,
                             compresslevel=6) as archive:
            for path in sorted(snapshot_root.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(snapshot_root).as_posix())

    with zipfile.ZipFile(destination) as archive:
        bad = archive.testzip()
        if bad:
            raise RuntimeError(f"state archive CRC check failed: {bad}")
    return manifest


def _client(config: dict):
    import boto3
    return boto3.client(
        "s3",
        endpoint_url=config["endpoint_url"],
        aws_access_key_id=config["aws_access_key_id"],
        aws_secret_access_key=config["aws_secret_access_key"],
        region_name=config["region_name"],
    )


def _prune(client, bucket: str, prefix: str, keep: int) -> None:
    paginator = client.get_paginator("list_objects_v2")
    objects = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        objects.extend(item for item in page.get("Contents", [])
                       if str(item.get("Key") or "").endswith(".zip"))
    objects.sort(key=lambda item: str(item.get("Key") or ""), reverse=True)
    stale = objects[max(2, keep):]
    if stale:
        client.delete_objects(
            Bucket=bucket,
            Delete={"Objects": [{"Key": item["Key"]} for item in stale], "Quiet": True},
        )


def backup_state_to_s3(root: Path | str, *, env: dict | None = None,
                       client=None, now: datetime | None = None) -> str | None:
    """Snapshot all worker state, upload it to S3/R2, and return its key."""
    config = backup_config(env)
    if config is None:
        return None
    values = os.environ if env is None else env
    now = now or datetime.now(timezone.utc)
    stamp = now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    prefix = str(values.get("ANTICIPY_STATE_BACKUP_PREFIX") or "worker/").strip("/") + "/"
    key = f"{prefix}state-{stamp}.zip"
    keep = max(2, int(values.get("ANTICIPY_STATE_BACKUP_KEEP") or "14"))
    s3 = client or _client(config)

    with tempfile.TemporaryDirectory(prefix="anticipy-state-upload-") as temp_name:
        archive = Path(temp_name) / "state.zip"
        manifest = build_archive(Path(root), archive, created_at=now)
        digest = _sha256(archive)
        s3.upload_file(
            str(archive), config["bucket"], key,
            ExtraArgs={
                "ServerSideEncryption": "AES256",
                "Metadata": {
                    "sha256": digest,
                    "format": str(manifest["format"]),
                    "file-count": str(len(manifest["files"])),
                },
            },
        )
        head = s3.head_object(Bucket=config["bucket"], Key=key)
        metadata = {str(k).lower(): str(v) for k, v in head.get("Metadata", {}).items()}
        if int(head.get("ContentLength") or -1) != archive.stat().st_size:
            raise RuntimeError("uploaded state backup has the wrong size")
        if metadata.get("sha256") != digest:
            raise RuntimeError("uploaded state backup is missing its SHA-256 proof")

    _prune(s3, config["bucket"], prefix, keep)
    return key
