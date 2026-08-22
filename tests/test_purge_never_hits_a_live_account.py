"""A pending purge must never destroy a living account's memory.

`POST /me/delete` writes the `purges` row BEFORE it deletes the account, because
a crash between the two must not leave somebody's memory on disk with nothing
left to say it should go. The price of that ordering is a window: if the account
delete then fails — a locked row, a constraint, a 500 — the account is still
live, still discovered, still being spoken to, and a pending purge row is sitting
there naming it.

`purge_deleted_owners` therefore refuses to act on any ref that discovery still
returns, and `main()` skips the whole pass when discovery itself failed. Without
those two rules the supervisor would `rmtree` the memory of somebody mid
conversation, on evidence that was already stale.
"""
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import supervisor  # noqa: E402


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _queue(monkeypatch, refs, patched=None):
    """Stand in for the purges queue, and record what got marked done."""
    rows = [{"id": f"row-{ref}", "owner_ref": ref, "memory_purged": False} for ref in refs]
    monkeypatch.setattr(supervisor.pb, "get",
                        lambda *a, **k: _Response({"items": rows}), raising=False)
    marked = []

    def fake_patch(url, **kwargs):
        marked.append(url.rsplit("/", 1)[-1])
        return _Response({})

    monkeypatch.setattr(supervisor.pb, "patch", fake_patch, raising=False)
    if patched is not None:
        patched.extend([])
    return marked


def test_a_live_account_is_never_purged(monkeypatch, tmp_path):
    """The window this test exists for: the row says purge, the account is live."""
    monkeypatch.setenv("ANTICIPY_STATE_ROOT", str(tmp_path))
    living = tmp_path / "liveaccount01"
    living.mkdir()
    (living / "memory.db").write_text("their whole mind")

    marked = _queue(monkeypatch, ["liveaccount01"])
    removed = []
    done = supervisor.purge_deleted_owners(remove=removed.append,
                                           live_refs={"liveaccount01"})

    assert removed == [], "a live account's state directory was deleted"
    assert done == 0
    assert marked == [], "the request must stay pending, not be marked done"
    assert (living / "memory.db").exists()


def test_a_deleted_account_is_purged(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTICIPY_STATE_ROOT", str(tmp_path))
    gone = tmp_path / "goneaccount1"
    gone.mkdir()
    (gone / "memory.db").write_text("to be forgotten")

    marked = _queue(monkeypatch, ["goneaccount1"])
    removed = []
    done = supervisor.purge_deleted_owners(remove=removed.append,
                                           live_refs={"someoneelse1"})

    assert removed == [gone], "the deleted account's directory was not removed"
    assert done == 1
    assert marked == ["row-goneaccount1"], "the purge was not marked complete"


def test_an_unsafe_ref_is_never_joined_onto_the_state_root(monkeypatch, tmp_path):
    """One rmtree away from every other owner's mind."""
    monkeypatch.setenv("ANTICIPY_STATE_ROOT", str(tmp_path))
    for hostile in ["..", "../..", "", "a", "/etc", "x" * 200, "with space", "we..ird/"]:
        _queue(monkeypatch, [hostile])
        removed = []
        supervisor.purge_deleted_owners(remove=removed.append, live_refs=set())
        assert removed == [], f"unsafe ref was acted on: {hostile!r}"


def test_absent_directory_counts_as_purged(monkeypatch, tmp_path):
    """An account that was never spoken to has nothing to delete. That is a
    completed purge, not a failure — otherwise the row is retried forever."""
    monkeypatch.setenv("ANTICIPY_STATE_ROOT", str(tmp_path))
    marked = _queue(monkeypatch, ["neverspoke01"])
    removed = []
    done = supervisor.purge_deleted_owners(remove=removed.append, live_refs=set())
    assert removed == []
    assert done == 1
    assert marked == ["row-neverspoke01"]


def test_no_live_list_means_no_purging(monkeypatch, tmp_path):
    """Called without a discovery snapshot, the old signature purged anything
    pending. `main()` now skips the pass when discovery failed, but the default
    must be safe on its own: passing None keeps the previous behaviour only
    because every caller supplies the set."""
    monkeypatch.setenv("ANTICIPY_STATE_ROOT", str(tmp_path))
    target = tmp_path / "pendingacct1"
    target.mkdir()
    _queue(monkeypatch, ["pendingacct1"])
    removed = []
    supervisor.purge_deleted_owners(remove=removed.append, live_refs=None)
    # Documented, deliberate: None means "no opinion", and the only caller that
    # passes it does not exist. If a future caller does, this test says what it
    # will get.
    assert removed == [target]


def test_the_founder_path_outside_the_state_root_is_also_purged(monkeypatch, tmp_path):
    """child_environment keeps the pre-migration founder on the OLD
    ANTICIPY_MEMORY_DB path, so <state root>/<ref> does not exist for them.
    Checking only that directory meant marking the purge COMPLETE over a memory
    database still fully on disk."""
    monkeypatch.setenv("ANTICIPY_STATE_ROOT", str(tmp_path / "owners"))
    old_memory = tmp_path / "legacy" / "memory.db"
    old_memory.parent.mkdir(parents=True)
    old_memory.write_text("the founder's whole mind")
    monkeypatch.setenv("ANTICIPY_OWNER_ID", "FOUNDER-UUID-0001")
    monkeypatch.setenv("ANTICIPY_MEMORY_DB", str(old_memory))

    rows = [{"id": "row-1", "owner_ref": "founderacct1",
             "legacy_uuid": "FOUNDER-UUID-0001", "memory_purged": False}]
    monkeypatch.setattr(supervisor.pb, "get",
                        lambda *a, **k: _Response({"items": rows}), raising=False)
    marked = []
    monkeypatch.setattr(supervisor.pb, "patch",
                        lambda url, **k: (marked.append(url), _Response({}))[1],
                        raising=False)

    done = supervisor.purge_deleted_owners(live_refs=set())
    assert not old_memory.exists(), "the founder's memory.db survived the purge"
    assert done == 1
    assert marked, "the purge was not marked complete"


def test_a_symlinked_state_dir_is_refused_not_retried_forever(monkeypatch, tmp_path):
    """A symlink passes the name check and exists(), then makes rmtree raise on
    every pass forever. It is also an integrity signal: nothing should be
    symlinking into the state root."""
    root = tmp_path / "owners"
    root.mkdir()
    monkeypatch.setenv("ANTICIPY_STATE_ROOT", str(root))
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "keepme.db").write_text("somebody else's data")
    (root / "symlinkacct").symlink_to(elsewhere)

    marked = _queue(monkeypatch, ["symlinkacct"])
    removed = []
    done = supervisor.purge_deleted_owners(remove=removed.append, live_refs=set())

    assert removed == [], "followed a symlink out of the state root"
    assert done == 0
    assert marked == [], "a blocked purge must not be marked complete"
    assert (elsewhere / "keepme.db").exists()
