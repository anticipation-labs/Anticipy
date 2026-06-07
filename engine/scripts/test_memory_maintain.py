"""Piece 4 (unit): MAINTAIN — the cold sweep (supersede + consolidate + decay).

Asserts a sweep: supersedes a changed fact (timestamped) while leaving coexisting
facts alone, consolidates near-duplicate episodes into one durable item, and
decays an old low-importance episode while a fresh one survives. Zero model calls.

Run:  PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_memory_maintain.py
"""
import tempfile
from pathlib import Path

from anticipy_engine.live_memory.maintain import Maintainer
from anticipy_engine.memory import Memory
from anticipy_engine.shared.schema import MemoryItem, now_ts

DAY = 86400.0


def main():
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-mnt-"))
    m = Memory(data_dir=tmp)
    now = now_ts()

    # SUPERSEDE: an older employer fact + a newer one; a name fact must coexist
    old_job = m.profile.write(MemoryItem(kind="profile_fact", text="I work at OldCo Inc", timestamp=now - 5 * DAY))
    new_job = m.profile.write(MemoryItem(kind="profile_fact", text="I work at NewCo Labs", timestamp=now - 10))
    name = m.profile.write(MemoryItem(kind="profile_fact", text="My name is Jordan", timestamp=now - 3 * DAY))

    # CONSOLIDATE: three near-duplicate episodes
    for t in (now - 300, now - 200, now - 100):
        m.history.write(MemoryItem(kind="history", text="Reviewed the quarterly budget spreadsheet.",
                                   status="active", timestamp=t))

    # DECAY: old + low-importance episode archives; a fresh one survives
    stale = m.history.write(MemoryItem(kind="history", text="Idle chatter from weeks ago.",
                                       status="active", importance=0.2, timestamp=now - 40 * DAY))
    fresh = m.history.write(MemoryItem(kind="history", text="Chatted about lunch plans today.",
                                       status="active", importance=0.5, timestamp=now - 50))

    res = Maintainer(m).sweep()
    assert res["ran"] and res["smart_calls"] == 0, res

    # supersede: old employer fact superseded + re-timestamped; new active; name untouched
    assert m.profile.get(old_job.id).status == "superseded"
    assert m.profile.get(new_job.id).status != "superseded"
    assert m.profile.get(old_job.id).updated_at > old_job.timestamp     # stamped at sweep time
    assert m.profile.get(name.id).status not in ("superseded", "archived")

    # consolidate: exactly one of the dups remains active, importance bumped
    dup_active = [h for h in m.history.all()
                  if h.text == "Reviewed the quarterly budget spreadsheet." and h.status == "active"]
    assert len(dup_active) == 1 and dup_active[0].importance > 0.5
    assert res["consolidated"] == 2

    # decay: stale archived, fresh survives
    assert m.history.get(stale.id).status == "archived"
    assert m.history.get(fresh.id).status == "active"

    print("PASS piece 4: maintain supersedes changed facts (timestamped, coexisting facts safe), "
          "consolidates dup episodes -> one durable, decays stale (fresh survives), zero model calls")


if __name__ == "__main__":
    main()
