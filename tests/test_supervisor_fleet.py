"""Two ways the fleet quietly stopped serving somebody.

  1. MAX_OWNER_WORKERS was enforced by truncating an id-sorted list inside
     discover_owners, and main() reads "not in that list" as "this account
     was deleted". PocketBase ids are random, so past the cap ONE new signup
     whose generated id sorted low evicted a live owner: SIGTERM, no log
     line, no retry. They simply stopped being heard, while every other
     account kept working — and the kill landed wherever the process was,
     so a half-written clock_state.json read back as the permissive default
     and wiped their outreach limit with it.

  2. The Twilio webhook watchdog was assigned to the first-sorted owner's
     CHILD, through an env var written once at spawn. Remove that owner and
     the role moved to a child that had already been started with
     ANTICIPY_WEBHOOK_MANAGER=0 — so nothing checked the number anywhere
     until the supervisor itself restarted. That watchdog exists because the
     number really was repointed at a stranger's Vercel app on 2026-08-03.
"""
import types
import json

import pytest

from brain import supervisor as S
from brain import worker as W


class FakeChild:
    def __init__(self, ref):
        self.ref = ref
        self.stopped = False

    def poll(self):
        return None

    def terminate(self):
        self.stopped = True

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.stopped = True


@pytest.fixture
def fleet(monkeypatch):
    started = []

    def spawn(owner, **kw):
        started.append(owner["id"])
        return FakeChild(owner["id"])
    return types.SimpleNamespace(spawn=spawn, started=started)


def oid(label):
    """A realistic PocketBase id: 15 random-looking chars, sortable by the
    label so a test can say which one sorts low."""
    return label + "0" * (15 - len(label))


def owners(*labels):
    return [{"id": oid(x), "legacy_uuid": ""} for x in sorted(labels)]


def test_a_new_signup_never_evicts_a_live_owner(monkeypatch, fleet):
    """The cap is reached, then somebody signs up with a low-sorting id. The
    person already being heard must keep their worker."""
    monkeypatch.setattr(S, "MAX_OWNER_WORKERS", 2)
    children = {}
    S.reconcile_children(children, owners("mmm", "zzz"), spawn=fleet.spawn)
    live = dict(children)
    assert set(live) == {oid("mmm"), oid("zzz")}

    unserved = S.reconcile_children(children, owners("aaa", "mmm", "zzz"),
                                    spawn=fleet.spawn)
    assert unserved == [oid("aaa")], "the newcomer waits; nobody is evicted"
    for ref, child in live.items():
        assert not child.stopped, f"{ref} was killed to make room"
    assert set(children) == {oid("mmm"), oid("zzz")}


def test_an_account_that_actually_disappears_is_still_stopped(monkeypatch, fleet):
    """The cap must not become a reason to keep a deleted account running."""
    monkeypatch.setattr(S, "MAX_OWNER_WORKERS", 5)
    children = {}
    S.reconcile_children(children, owners("aaa", "bbb"), spawn=fleet.spawn)
    gone = children[oid("bbb")]
    S.reconcile_children(children, owners("aaa"), spawn=fleet.spawn)
    assert gone.stopped and oid("bbb") not in children


def test_a_freed_slot_goes_to_someone_who_was_waiting(monkeypatch, fleet):
    monkeypatch.setattr(S, "MAX_OWNER_WORKERS", 2)
    children = {}
    S.reconcile_children(children, owners("mmm", "zzz"), spawn=fleet.spawn)
    S.reconcile_children(children, owners("aaa", "mmm", "zzz"), spawn=fleet.spawn)
    assert S.reconcile_children(children, owners("aaa", "mmm"),
                                spawn=fleet.spawn) == []
    assert set(children) == {oid("aaa"), oid("mmm")}


def test_discovery_reports_everyone_it_found(monkeypatch):
    """Truncating here is what made the cap an eviction: main() cannot tell
    "over the cap" from "deleted" if discovery hides the difference."""
    monkeypatch.setattr(S, "MAX_OWNER_WORKERS", 1)
    payload = {"items": [{"id": "aaaaaaaa1", "legacy_uuid": "a"},
                         {"id": "bbbbbbbb2", "legacy_uuid": "b"},
                         {"id": "cccccccc3", "legacy_uuid": "c"}],
               "totalPages": 1}
    monkeypatch.setattr(S.pb, "get", lambda *a, **k: types.SimpleNamespace(
        ok=True, json=lambda: payload, raise_for_status=lambda: None))
    assert [o["id"] for o in S.discover_owners()] == [
        "aaaaaaaa1", "bbbbbbbb2", "cccccccc3"]


# ------------------------------------------------ the webhook watchdog role

def test_no_child_is_ever_the_webhook_manager(monkeypatch, fleet):
    """A role written into a child's environment at spawn cannot follow the
    role when the owner holding it disappears — the child that inherits it
    was started with the flag already off."""
    monkeypatch.setattr(S, "MAX_OWNER_WORKERS", 10)
    seen = []

    def spawn(owner, **kw):
        seen.append(S.child_environment(owner, base={"ANTICIPY_OWNER_ID": "x"},
                                        **kw))
        return FakeChild(owner["id"])
    S.reconcile_children({}, owners("aaa", "bbb"), spawn=spawn)
    assert seen and all(env["ANTICIPY_WEBHOOK_MANAGER"] == "0" for env in seen)


def test_the_supervisor_itself_checks_the_number():
    """Singular by construction: there is exactly one supervisor, so the role
    cannot be lost by an owner going away."""
    import inspect
    src = inspect.getsource(S.main)
    assert "worker.ensure_inbound_webhook()" in src
    assert "worker.WEBHOOK_CHECK_EVERY_SECONDS" in src, "on a timer, not per pass"
    # ...and it must not be inside the discovery try/except, or a backend
    # outage would take the watchdog down with it.
    assert src.index("worker.ensure_inbound_webhook()") < src.index("try:")


def test_a_standalone_worker_still_checks_its_own_number():
    """Nothing above may turn the watchdog off for a single-process
    deployment, which is what every non-supervised install is."""
    import inspect
    src = inspect.getsource(W.main)
    assert 'os.environ.get("ANTICIPY_SUPERVISED") != "1"' in src
    assert "ensure_inbound_webhook()" in src


def test_clock_state_write_failure_preserves_the_last_valid_state(tmp_path, monkeypatch):
    """SIGTERM during json.dump must not replace a valid outreach clock with
    a half-written file that _clock_state reads as permissive defaults."""
    path = tmp_path / "clock_state.json"
    previous = {"last_outreach_ts": 123, "reached_loop_ids": ["kept"]}
    path.write_text(json.dumps(previous))
    monkeypatch.setattr(W, "CLOCK_STATE", str(path))

    def interrupted_dump(_state, handle):
        handle.write('{"last_outreach_ts":')
        raise RuntimeError("terminated mid-write")

    monkeypatch.setattr(W.json, "dump", interrupted_dump)
    W._save_clock_state({"last_outreach_ts": 999})

    assert json.loads(path.read_text()) == previous
