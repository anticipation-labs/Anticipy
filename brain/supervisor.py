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
import shutil
import subprocess
import sys
import time
from typing import Callable

from . import pb
from . import state_backup
from . import worker


PB = os.environ.get("ANTICIPY_PB", "http://127.0.0.1:8090")
DISCOVERY_SECONDS = max(2, int(os.environ.get("ANTICIPY_OWNER_DISCOVERY_SECONDS", "15")))
MAX_OWNER_WORKERS = max(1, int(os.environ.get("ANTICIPY_MAX_OWNER_WORKERS", "100")))
STATE_ROOT = os.environ.get("ANTICIPY_STATE_ROOT", "/data/owners")
STATE_VOLUME_ROOT = os.environ.get("ANTICIPY_STATE_VOLUME_ROOT", "/data")
STATE_BACKUP_SECONDS = max(300, int(os.environ.get("ANTICIPY_STATE_BACKUP_SECONDS", "86400")))
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


def owner_state_dir(owner_ref: str) -> Path:
    """Where one account's durable mind lives. Same arithmetic as
    child_environment, kept as its own function so the purge cannot drift from
    the thing it deletes."""
    return Path(os.environ.get("ANTICIPY_STATE_ROOT", STATE_ROOT)) / owner_ref


def purge_deleted_owners(*, remove: Callable = shutil.rmtree,
                         live_refs: set[str] | None = None) -> int:
    """Finish the deletions PocketBase could not.

    `POST /me/delete` clears every owner-scoped row synchronously, but memory is
    a per-owner SQLite file on THIS volume and PocketBase cannot reach it. So it
    leaves a `purges` row behind and this drains the queue.

    Why here and not in the worker: by the time a purge exists the account is
    gone from discovery, so reconcile_children has already SIGTERMed that
    owner's child. Asking a reaped process to clean up after itself is asking
    for the file to survive forever.

    ONLY EVER PURGES AN ACCOUNT DISCOVERY SAYS IS GONE, and that guard is the
    important line in this function. The endpoint writes the purge row BEFORE it
    deletes the account, because a crash between the two must not leave memory
    on disk with nothing left to say it should go. The cost of that ordering is
    a window: if the account delete then fails — a locked row, a constraint, a
    500 — the account is still live, still discovered, still being spoken to,
    and a pending purge row is sitting there naming it. Without this check the
    next pass would rmtree the memory of somebody mid-conversation.

    `live_refs` is passed in rather than fetched so the decision is made against
    the SAME discovery snapshot reconcile_children just acted on; refetching
    here would reintroduce the race in a smaller window.

    Retried until it succeeds. `memory_purged` is only set once the directory is
    actually gone, because a delete that reports success while the data is still
    on disk is the one outcome that turns a privacy promise into a lie.
    """
    done = 0
    try:
        response = pb.get(f"{PB}/api/collections/purges/records",
                          params={"filter": "memory_purged=false", "perPage": 50},
                          timeout=10)
        response.raise_for_status()
        rows = response.json().get("items", [])
    except Exception as exc:
        print(f"purge queue unreadable (retrying): {exc}")
        return 0

    for row in rows:
        ref = str(row.get("owner_ref") or "").strip()
        # An account that still exists has not been deleted, whatever the queue
        # says. Left pending on purpose: if the delete is retried and succeeds,
        # the account leaves discovery and the next pass finishes the job.
        if live_refs is not None and ref in live_refs:
            print(f"purge deferred: account {ref} is still live")
            continue
        # The same guard discovery uses. A blank or hostile id must never be
        # joined onto the state root — that path is one rmtree away from every
        # other owner's mind.
        if not _SAFE_ID.fullmatch(ref):
            print(f"purge skipped, unsafe owner ref: {ref!r}")
            continue
        # EVERY path this account's mind could live at, not just the tidy one.
        #
        # child_environment keeps the pre-migration founder on the OLD
        # ANTICIPY_MEMORY_DB / ANTICIPY_CLOCK_STATE paths when their
        # legacy_uuid matches ANTICIPY_OWNER_ID, so for that one account
        # <state root>/<ref> does not exist. Checking only that directory meant
        # taking the "nothing to remove" branch and then marking the purge
        # COMPLETE over a memory database still fully on disk — precisely the
        # lie this function's docstring forbids. The purges row carries
        # legacy_uuid for exactly this case and nothing read it.
        legacy = str(row.get("legacy_uuid") or "").strip()
        targets = [owner_state_dir(ref)]
        configured = str(os.environ.get("ANTICIPY_OWNER_ID") or "").strip()
        if legacy and configured and legacy == configured:
            for key in ("ANTICIPY_MEMORY_DB", "ANTICIPY_CLOCK_STATE"):
                value = str(os.environ.get(key) or "").strip()
                if value and value != ":memory:":
                    targets.append(Path(value))

        failed_target = False
        for target in targets:
            # A symlink AT the target passes the name check, passes exists()
            # (which follows it), and then makes rmtree raise "Cannot call
            # rmtree on a symbolic link" on every pass, forever. It is also an
            # integrity signal in its own right: nothing should be symlinking
            # into the state root.
            if target.is_symlink():
                print(f"PURGE BLOCKED: {target} is a symlink — refusing to follow it")
                failed_target = True
                break
            try:
                if target.is_dir():
                    remove(target)
                    print(f"purged durable memory · owner={ref} · {target}")
                elif target.exists():
                    target.unlink()
                    print(f"purged durable file · owner={ref} · {target}")
            except Exception as exc:
                print(f"purge failed for {ref} at {target} (will retry): {exc}")
                failed_target = True
                break
        if failed_target:
            continue
        # Nothing left anywhere is a completed purge, not a failure: the account
        # may simply never have been spoken to.
        try:
            pb.patch(f"{PB}/api/collections/purges/records/{row.get('id')}",
                     json={"memory_purged": True,
                           "purged_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
                     timeout=10).raise_for_status()
            done += 1
        except Exception as exc:
            # The directory is gone but the row still says pending. The next
            # pass finds nothing to delete and marks it — which is why "already
            # absent" counts as success above.
            print(f"purge mark failed for {ref} (harmless, will retry): {exc}")
    return done


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
    # Wait for owner children to start before the first snapshot. A failed
    # upload retries in fifteen minutes; a missing configuration is an
    # intentional no-op so this image can safely precede its credentials.
    next_state_backup = time.monotonic() + 30
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
        # One discovery snapshot, used for BOTH decisions. Fetching it twice
        # would let an account disappear between the two calls and have its
        # memory purged on evidence the reconcile never saw.
        owners = None
        try:
            owners = discover_owners()
            reconcile_children(children, owners)
        except Exception as exc:
            print(f"owner discovery failed (retrying): {exc}")
        # After reconcile, so the child owning that directory has already been
        # stopped and cannot rewrite the file we are about to remove. Skipped
        # entirely when discovery failed: with no trustworthy list of who is
        # live, "this account is gone" is a guess, and the cost of guessing
        # wrong is a live person's memory. Its own try — a failed purge must
        # not stop anyone being heard.
        if owners is not None:
            try:
                purge_deleted_owners(live_refs={o["id"] for o in owners})
            except Exception as exc:
                print(f"purge pass failed (retrying): {exc}")

        if time.monotonic() >= next_state_backup:
            try:
                uploaded = state_backup.backup_state_to_s3(STATE_VOLUME_ROOT)
                if uploaded:
                    print(f"worker state backup verified · key={uploaded}")
                next_state_backup = time.monotonic() + STATE_BACKUP_SECONDS
            except Exception as exc:
                # A backup failure must be visible and retried, but it must not
                # stop owner workers or the webhook watchdog.
                print(f"WORKER STATE BACKUP FAILED (retrying): {exc}")
                next_state_backup = time.monotonic() + min(900, STATE_BACKUP_SECONDS)

        deadline = time.monotonic() + DISCOVERY_SECONDS
        while not stopping and time.monotonic() < deadline:
            time.sleep(min(1, deadline - time.monotonic()))

    for child in list(children.values()):
        stop_child(child)
    print("supervisor down")


if __name__ == "__main__":
    main()
