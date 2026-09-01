"""Exact PocketBase 0.30.4 integration gate for atomic profile first-writes.

The fast JSVM stand-in pins failure branches. This gate supplies the part a
stand-in cannot honestly prove: two callbacks released at the same instant
through PocketBase's real HTTP router, JSVM pool, transaction implementation,
and SQLite unique index. The backend image downloads this same pinned release;
the official archive checksum is fixed here so the test dependency cannot drift.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import socket
import sqlite3
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.30.4"
FIXTURE = ROOT / "tests/fixtures/owner_profile_pocketbase/1000_bootstrap.js"
HOOK = ROOT / "backend/pb_hooks/owner_profile_upsert.pb.js"
PHONE_REMOVE_HOOK = ROOT / "backend/pb_hooks/phone_remove.pb.js"
MIGRATION = ROOT / "backend/pb_migrations/1700000054_owner_profile_canonical.js"
CHECKSUMS = {
    ("darwin", "amd64"): "50cca082eb0afba6ac542c7dc72a95dc2c0ad9a36b518dcbb095dba3e2384aa5",
    ("darwin", "arm64"): "2941dec1b520febbbe51ef80a126c9a3ca021ff5543b388157513be76c8d2ee7",
    ("linux", "amd64"): "d62a9247e775c59fa1ef5154f43a0bd868c6bfb2bcee5cdeef05cf14f657bc83",
    ("linux", "arm64"): "5716c6f02c8f8bdd10912f32c8fc3a5b613b0c8c858b3063597ac30a19e1ae78",
}


def _platform_asset() -> tuple[str, str, str]:
    system = platform.system().lower()
    machine = platform.machine().lower()
    arch = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64"}.get(machine)
    if not arch or (system, arch) not in CHECKSUMS:
        raise AssertionError(f"PocketBase runtime gate has no pinned archive for {system}/{machine}")
    return system, arch, CHECKSUMS[(system, arch)]


def _pocketbase(tmp_path: Path) -> Path:
    supplied = os.environ.get("ANTICIPY_TEST_POCKETBASE", "").strip()
    if supplied:
        binary = Path(supplied)
        version = subprocess.run(
            [str(binary), "--version"], check=True, capture_output=True, text=True
        ).stdout.strip()
        assert version == f"pocketbase version {VERSION}"
        return binary

    system, arch, checksum = _platform_asset()
    archive = tmp_path / "pocketbase.zip"
    url = (
        "https://github.com/pocketbase/pocketbase/releases/download/"
        f"v{VERSION}/pocketbase_{VERSION}_{system}_{arch}.zip"
    )
    with urllib.request.urlopen(url, timeout=30) as response, archive.open("wb") as target:
        shutil.copyfileobj(response, target)
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == checksum
    with zipfile.ZipFile(archive) as bundle:
        bundle.extract("pocketbase", tmp_path)
    binary = tmp_path / "pocketbase"
    binary.chmod(0o755)
    return binary


def _post(base: str, path: str, body: dict, token: str = "") -> tuple[int, dict]:
    request = urllib.request.Request(
        base + path,
        data=json.dumps(body).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    if token:
        request.add_header("Authorization", token)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def _free_port() -> int:
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    listener.close()
    return port


def test_exact_pocketbase_migrates_and_serializes_simultaneous_partial_first_writes(
    tmp_path: Path,
) -> None:
    binary = _pocketbase(tmp_path)
    migrations = tmp_path / "migrations"
    hooks = tmp_path / "hooks"
    data = tmp_path / "data"
    migrations.mkdir()
    hooks.mkdir()
    data.mkdir()
    shutil.copy2(FIXTURE, migrations / "1000_bootstrap.js")
    shutil.copy2(MIGRATION, migrations / "2000_owner_profile_canonical.js")
    shutil.copy2(HOOK, hooks / HOOK.name)
    shutil.copy2(PHONE_REMOVE_HOOK, hooks / PHONE_REMOVE_HOOK.name)

    migrated = subprocess.run(
        [
            str(binary),
            "migrate",
            "up",
            "--dir",
            str(data),
            "--migrationsDir",
            str(migrations),
            "--hooksDir",
            str(hooks),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    migration_output = migrated.stdout + migrated.stderr
    assert "removed 1 duplicate(s)" in migration_output

    database = sqlite3.connect(data / "data.db")
    seeded = database.execute(
        "SELECT id, phone, email, first_name FROM owner_profile"
    ).fetchall()
    assert seeded == [("profilezzz00002", "", "", "Newest")]
    [index_sql] = [
        sql
        for (name, sql) in database.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type='index' AND tbl_name='owner_profile'"
        )
        if name == "idx_owner_profile_owner_ref"
    ]
    assert "CREATE UNIQUE INDEX" in index_sql
    database.close()

    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    server = subprocess.Popen(
        [
            str(binary),
            "serve",
            "--http",
            f"127.0.0.1:{port}",
            "--dir",
            str(data),
            "--migrationsDir",
            str(migrations),
            "--hooksDir",
            str(hooks),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        deadline = time.monotonic() + 10
        while True:
            try:
                with urllib.request.urlopen(base + "/api/health", timeout=1) as response:
                    if response.status == 200:
                        break
            except (OSError, urllib.error.URLError):
                pass
            if server.poll() is not None:
                output = server.stdout.read() if server.stdout else ""
                raise AssertionError(f"PocketBase exited before readiness:\n{output}")
            if time.monotonic() >= deadline:
                raise AssertionError("PocketBase did not become ready within 10 seconds")
            time.sleep(0.05)

        status, created = _post(
            base,
            "/api/collections/owners/records",
            {
                "email": "concurrent@example.com",
                "password": "password12345",
                "passwordConfirm": "password12345",
                "phone": "+12025550144",
                "legacy_uuid": "concurrent-device",
            },
        )
        assert status == 200, created
        status, authenticated = _post(
            base,
            "/api/collections/owners/auth-with-password",
            {"identity": "concurrent@example.com", "password": "password12345"},
        )
        assert status == 200, authenticated
        token = authenticated["token"]
        owner_ref = authenticated["record"]["id"]

        barrier = threading.Barrier(3)
        writes: dict[str, tuple[int, dict]] = {}
        write_lock = threading.Lock()

        def write(label: str, body: dict) -> None:
            barrier.wait(timeout=5)
            result = _post(base, "/me/profile/upsert", body, token)
            with write_lock:
                writes[label] = result

        workers = [
            threading.Thread(
                target=write,
                args=(
                    "details",
                    {
                        "first_name": "Omar",
                        "last_name": "Ebrahim",
                        "email": "founder@example.test",
                        "timezone": "America/Vancouver",
                    },
                ),
            ),
            threading.Thread(
                target=write,
                args=("phone", {"phone": "+12025550144"}),
            ),
        ]
        for worker in workers:
            worker.start()
        barrier.wait(timeout=5)
        for worker in workers:
            worker.join(timeout=15)
            assert not worker.is_alive()

        assert set(writes) == {"details", "phone"}
        assert {result[0] for result in writes.values()} == {200}

        query = urllib.parse.urlencode(
            {
                "filter": f'owner_ref="{owner_ref}"',
                "sort": "-updated",
                "perPage": 10,
            }
        )
        request = urllib.request.Request(
            base + "/api/collections/owner_profile/records?" + query,
            headers={"Authorization": token},
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            listed = json.loads(response.read())
        assert listed["totalItems"] == 1
        [profile] = listed["items"]
        assert profile["owner_ref"] == owner_ref
        assert profile["owner_id"] == "concurrent-device"
        assert profile["first_name"] == "Omar"
        assert profile["last_name"] == "Ebrahim"
        assert profile["email"] == "founder@example.test"
        assert profile["phone"] == "+12025550144"
        assert profile["timezone"] == "America/Vancouver"

        status, refused = _post(
            base,
            "/me/profile/upsert",
            {"owner_ref": "somebody-else", "phone": "+16045559999"},
            token,
        )
        assert status == 400, refused
        assert refused["ok"] is False

        status, legacy_profile = _post(
            base,
            "/api/collections/owner_profile/records",
            {
                "owner_id": "concurrent-device",
                "phone": "+12025550144",
                "first_name": "Unclaimed residue",
            },
            token,
        )
        assert status == 200, legacy_profile
        status, foreign_profile = _post(
            base,
            "/api/collections/owner_profile/records",
            {
                "owner_id": "somebody-elses-device",
                "phone": "+12025550144",
                "first_name": "Foreign",
            },
            token,
        )
        assert status == 200, foreign_profile

        status, removed = _post(base, "/me/phone/remove", {}, token)
        assert status == 200, removed
        assert removed == {"ok": True, "phone": "", "clearedProfiles": 2}

        request = urllib.request.Request(
            base + "/api/collections/owner_profile/records?perPage=10",
            headers={"Authorization": token},
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            after_removal = json.loads(response.read())
        phones_by_id = {item["id"]: item["phone"] for item in after_removal["items"]}
        assert phones_by_id[profile["id"]] == ""
        assert phones_by_id[legacy_profile["id"]] == ""
        assert phones_by_id[foreign_profile["id"]] == "+12025550144"
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)
