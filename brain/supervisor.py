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
from . import worker


PB = os.environ.get("ANTICIPY_PB", "http://127.0.0.1:8090")
DISCOVERY_SECONDS = max(2, int(os.environ.get("ANTICIPY_OWNER_DISCOVERY_SECONDS", "15")))
MAX_OWNER_WORKERS = max(1, int(os.environ.get("ANTICIPY_MAX_OWNER_WORKERS", "100")))
STATE_ROOT = os.environ.get("ANTICIPY_STATE_ROOT", "/data/owners")
_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


def discover_owners() -> list[dict]:
    """Return canonical owner ids without exposing account credentials.

    EVERY discovered owner is returned; how many workers actually run is
    capped at spawn time in reconcile_children(). Truncating here made the
    cap evict people instead of turning them away: PocketBase ids are
    random, so `rows[:MAX_OWNER_WORKERS]` is an arbitrary set rather than the
    oldest, and the reconcile reads "not in this set" as "this account was
    deleted" and SIGTERMs the child. One new signup whose generated id
    happened to sort low silently stopped a live owner being heard — and the
    kill landed wherever the process was, so a half-written clock_state.json
    read back as the permissive default and wiped their outreach limit too.
    """
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
    return rows


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
    # The founder's phone number must NOT ride along into someone else's
    # worker. It was inherited verbatim from the parent environment, and a
    # phone is optional on a profile — so a second person signing up got a
    # worker bound to the founder's number: her texts about THEIR errands went
    # to him, and his replies were read as answers to their tasks. Cross-
    # account SMS in both directions, from a single missing pop().
    if not is_legacy_owner:
        env.pop("ANTICIPY_OWNER_PHONE", None)
    env["ANTICIPY_SUPERVISED"] = "1"
    # Kept for a standalone child started by hand. Nothing the supervisor
    # spawns is the webhook manager any more: the role is the supervisor's,
    # because an env var written once at spawn cannot follow a role that has
    # to move when an owner disappears.
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


def reconcile_children(children: dict, owners: list[dict],
                       spawn: Callable = spawn_owner) -> list[str]:
    """Bring the running set into line with discovery. Returns the unserved.

    Its own function because the eviction bug lived in this arithmetic and
    nothing could reach it: it was inline in an infinite loop, so the only
    way to learn who had been stopped was to run a fleet and wait for
    somebody to go quiet.
    """
    wanted = {owner["id"]: owner for owner in owners}
    for ref, child in list(children.items()):
        if ref not in wanted or child.poll() is not None:
            if ref not in wanted:
                stop_child(child)
            del children[ref]
    # The cap bounds how many workers we START. It never decides who keeps
    # running: a person already being heard is not evicted to make room for a
    # newer signup, and only an account that has genuinely disappeared from
    # discovery is stopped above.
    room = MAX_OWNER_WORKERS - len(children)
    unserved: list[str] = []
    for ref, owner in wanted.items():
        if ref in children:
            continue
        if room <= 0:
            unserved.append(ref)
            continue
        children[ref] = spawn(owner)
        room -= 1
        print(f"owner worker started · owner={ref}")
    if unserved:
        # Loudly, every pass. Silently dropping accounts is how a fleet reads
        # as healthy while somebody gets nothing at all.
        print(f"AT CAPACITY: {len(children)} workers running "
              f"(ANTICIPY_MAX_OWNER_WORKERS={MAX_OWNER_WORKERS}) — "
              f"{len(unserved)} owner(s) have no worker: "
              f"{', '.join(unserved[:10])}"
              f"{' …' if len(unserved) > 10 else ''}")
    return unserved


def main() -> None:
    children: dict[str, object] = {}
    stopping = False

    def request_stop(_signum, _frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    print(f"supervisor up · pb={PB} · isolated-owner-limit={MAX_OWNER_WORKERS}")

    last_webhook = 0.0
    while not stopping:
        # The Twilio number must keep pointing at us, and exactly one process
        # may check. That job used to be handed to the first-sorted owner's
        # CHILD, baked into its environment at spawn — so when that owner was
        # removed from discovery the role moved to a child that had already
        # been started with ANTICIPY_WEBHOOK_MANAGER=0, and NOBODY checked
        # anywhere until the supervisor itself restarted. The watchdog exists
        # because the number really was repointed at a stranger's Vercel app
        # on 2026-08-03 and every text he sent went there for a day; going
        # dark with nothing in any log saying so is the one failure it may
        # not have. Outside the try below on purpose: a backend outage must
        # not take the watchdog down with discovery.
        if time.time() - last_webhook > worker.WEBHOOK_CHECK_EVERY_SECONDS:
            last_webhook = time.time()
            worker.ensure_inbound_webhook()
        try:
            reconcile_children(children, discover_owners())
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
