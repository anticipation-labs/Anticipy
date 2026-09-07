from brain.runtime_status import health


def status(**overrides):
    args = dict(running=True, snapshot_at=990, snapshot_error=False, now=1000, interval=60)
    return health(**(args | overrides))


def test_live_process_and_current_snapshot_are_both_required():
    assert status()["ok"]
    assert len(status()["source_sha256"]) == 64
    assert not status(running=False)["ok"]
    assert not status(snapshot_at=None)["ok"]
    assert not status(snapshot_at=700)["ok"]
    assert not status(snapshot_error=True)["ok"]
