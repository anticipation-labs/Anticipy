"""One isolated Anticipy mind per account.

The historical worker held its Memory database, conversation, clock, caches,
and owner identity in module globals.  Running that loop once against a shared
PocketBase meant every account was interpreted as the configured founder.

This supervisor is the deliberately small multi-tenant boundary: it discovers
accounts through a service-authenticated backend route and runs one OS process
per account.  A child can crash or mutate a cache without touching another
person's state, while the existing, heavily-tested worker loop stays intact.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
from typing import Callable

from . import pb


PB = os.environ.get("ANTICIPY_PB", "http://127.0.0.1:8090")
DISCOVERY_SECONDS = max(2, int(os.environ.get("ANTICIPY_OWNER_DISCOVERY_SECONDS", "15")))
MAX_OWNER_WORKERS = max(1, int(os.environ.get("ANTICIPY_MAX_OWNER_WORKERS", "100")))
STATE_ROOT = os.environ.get("ANTICIPY_STATE_ROOT", "/data/owners")
_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


def discover_owners() -> list[dict]:
    """Return canonical owner ids without exposing account credentials."""
    rows: list[dict] = []
    page = 1
    while True:
        response = pb.get(
            f"{PB}/worker/owners",
            params={"page": page, "perPage": 200},
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
        items = payload.get("items", [])
        for item in items:
            ref = str(item.get("id") or "").strip()
            if _SAFE_ID.fullmatch(ref):
                rows.append({
                    "id": ref,
                    "legacy_uuid": str(item.get("legacy_uuid") or "").strip(),
                })
        if page >= int(payload.get("totalPages") or 1):
            break
        page += 1
    rows.sort(key=lambda item: item["id"])
    return rows[:MAX_OWNER_WORKERS]


def child_environment(owner: dict, base: dict | None = None,
                      webhook_manager: bool = False) -> dict:
    """Build an account-bound environment with a private durable state path."""
    env = dict(os.environ if base is None else base)
    ref = str(owner.get("id") or "").strip()
    if not _SAFE_ID.fullmatch(ref):
        raise ValueError("invalid owner id")
    legacy = str(owner.get("legacy_uuid") or "").strip()
    owner_dir = Path(env.get("ANTICIPY_STATE_ROOT", STATE_ROOT)) / ref

    # Preserve the founder's existing durable mind during the migration.  New
    # accounts never inherit that path, even though the parent has it in env.
    configured_legacy = str(env.get("ANTICIPY_OWNER_ID") or "").strip()
    is_legacy_owner = bool(legacy and configured_legacy and legacy == configured_legacy)
    old_memory = str(env.get("ANTICIPY_MEMORY_DB") or "").strip()
    old_clock = str(env.get("ANTICIPY_CLOCK_STATE") or "").strip()

    env["ANTICIPY_OWNER_REF"] = ref
    env["ANTICIPY_OWNER_ID"] = legacy or ref
    env["ANTICIPY_MEMORY_DB"] = (
        old_memory if is_legacy_owner and old_memory else str(owner_dir / "memory.db")
    )
    env["ANTICIPY_CLOCK_STATE"] = (
        old_clock if is_legacy_owner and old_clock else str(owner_dir / "clock_state.json")
    )
    env["ANTICIPY_SUPERVISED"] = "1"
    env["ANTICIPY_WEBHOOK_MANAGER"] = "1" if webhook_manager else "0"
    return env


def ensure_state_directory(env: dict) -> None:
    for key in ("ANTICIPY_MEMORY_DB", "ANTICIPY_CLOCK_STATE"):
        value = str(env.get(key) or "")
        if value and value != ":memory:":
            Path(value).parent.mkdir(parents=True, exist_ok=True, mode=0o700)


def spawn_owner(owner: dict, *, webhook_manager: bool = False,
                popen: Callable = subprocess.Popen):
    env = child_environment(owner, webhook_manager=webhook_manager)
    ensure_state_directory(env)
    return popen([sys.executable, "-m", "brain.worker"], env=env)


def stop_child(child) -> None:
    if child.poll() is not None:
        return
    child.terminate()
    try:
        child.wait(timeout=10)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait(timeout=5)


def main() -> None:
    children: dict[str, object] = {}
    stopping = False

    def request_stop(_signum, _frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    print(f"supervisor up · pb={PB} · isolated-owner-limit={MAX_OWNER_WORKERS}")

    while not stopping:
        try:
            owners = discover_owners()
            wanted = {owner["id"]: owner for owner in owners}
            for ref, child in list(children.items()):
                if ref not in wanted or child.poll() is not None:
                    if ref not in wanted:
                        stop_child(child)
                    del children[ref]
            manager_ref = owners[0]["id"] if owners else ""
            for ref, owner in wanted.items():
                if ref not in children:
                    children[ref] = spawn_owner(
                        owner, webhook_manager=(ref == manager_ref))
                    print(f"owner worker started · owner={ref}")
        except Exception as exc:
            print(f"owner discovery failed (retrying): {exc}")

        deadline = time.monotonic() + DISCOVERY_SECONDS
        while not stopping and time.monotonic() < deadline:
            time.sleep(min(1, deadline - time.monotonic()))

    for child in list(children.values()):
        stop_child(child)
    print("supervisor down")


if __name__ == "__main__":
    main()
