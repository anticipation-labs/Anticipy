"""Facts that expire — the last unbuilt part of the LIBRARY card.

`_decay` already sinks a fact's SALIENCE with age and the fact stays TRUE. This
is the other thing: a fact that stops being true. "Dana is in Montreal Friday to
Sunday" is not less interesting on Monday, it is false on Monday — and until now
every time-bounded fact in this store was a permanent fact with a sinking score,
still eligible to fill a gap in a plan.

See docs/superpowers/specs/2026-08-25-facts-that-expire.md. The design point a
naive version misses is in there and is tested here: an expiring fact is often an
ERRAND, not a deletion (Brief moment 8, the parking permit), so the horizon has
to be readable AFTER it passes rather than swept away.
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))

from brain.memory import Memory  # noqa: E402

DAY = 86400.0


def _store(now: float) -> Memory:
    return Memory(":memory:", llm=None)


def test_a_horizon_in_the_past_retires_the_fact():
    now = time.time()
    m = _store(now)
    rid = m.remember_fact("Dana is in Montreal", importance=3, ts=now - 5 * DAY,
                          kind="situation", valid_until=now - DAY)
    assert rid
    assert m.expire_stale(now=now) == 1
    assert m._is_retired(rid)


def test_a_horizon_in_the_future_is_untouched():
    """The fact is still true. Expiring early is how a live fact vanishes."""
    now = time.time()
    m = _store(now)
    rid = m.remember_fact("permit runs to next month", importance=4, ts=now,
                          kind="situation", valid_until=now + 20 * DAY)
    assert m.expire_stale(now=now) == 0
    assert not m._is_retired(rid)


def test_no_horizon_is_never_an_expiry():
    """The honesty wall. A model that says nothing has not said 'expired' —
    guessing a horizon is worse than having none, because it makes a true fact
    disappear on a date nobody stated."""
    now = time.time()
    m = _store(now)
    rid = m.remember_fact("the cabin wifi is trout2024", importance=3,
                          ts=now - 400 * DAY, kind="stable")
    assert m.expire_stale(now=now) == 0
    assert not m._is_retired(rid)


def test_an_expired_fact_is_absent_from_the_profile():
    now = time.time()
    m = _store(now)
    m.remember_fact("Dana is in Montreal", importance=5, ts=now - 5 * DAY,
                    kind="situation", valid_until=now - DAY)
    m.expire_stale(now=now)
    assert all("Montreal" not in f["fact"] for f in m.profile_facts())


def test_an_expired_fact_is_kept_for_audit_not_deleted():
    """Nothing in this store deletes. 'The old facts aren't deleted — they're
    retired' (Brief moment 35) is the rule for horizons too."""
    now = time.time()
    m = _store(now)
    rid = m.remember_fact("Dana is in Montreal", importance=3, ts=now - 5 * DAY,
                          kind="situation", valid_until=now - DAY)
    m.expire_stale(now=now)
    rows = m.db.execute("SELECT fact FROM profile_facts WHERE id=?", (rid,)).fetchall()
    assert rows and "Montreal" in rows[0][0]


def test_an_expired_fact_cannot_settle_a_gap_in_an_approved_plan():
    """The load-bearing one. A dead fact reaching fill_gaps_from_memory becomes
    a typed value on a form the browser fills."""
    now = time.time()
    m = _store(now)
    m.remember_fact("Dana is in Montreal", importance=5, ts=now - 5 * DAY,
                    kind="situation", valid_until=now - DAY)
    m.expire_stale(now=now)
    # default lane is RETIRED_EXCLUDED — the same read the action path makes
    assert all("Montreal" not in f["fact"] for f in m.profile_facts())


def test_expiry_is_distinguishable_from_supersession():
    """Two different answers to 'why did she stop believing this'. A horizon
    that passed has no superseding row, so retired_by stays NULL."""
    now = time.time()
    m = _store(now)
    rid = m.remember_fact("Dana is in Montreal", importance=3, ts=now - 5 * DAY,
                          kind="situation", valid_until=now - DAY)
    m.expire_stale(now=now)
    ts, by = m.db.execute(
        "SELECT retired_ts, retired_by FROM profile_facts WHERE id=?", (rid,)).fetchone()
    assert ts is not None
    assert by is None


def test_the_horizon_survives_expiry_so_the_errand_is_still_readable():
    """Brief moment 8: the parking permit expiring IS the errand. A sweep that
    erased the horizon would delete the most actionable fact in the store on the
    day it mattered most."""
    now = time.time()
    m = _store(now)
    rid = m.remember_fact("parking permit expires this month", importance=4,
                          ts=now - 2 * DAY, kind="situation", valid_until=now - DAY)
    m.expire_stale(now=now)
    (vu,) = m.db.execute(
        "SELECT valid_until FROM profile_facts WHERE id=?", (rid,)).fetchone()
    assert vu is not None and abs(vu - (now - DAY)) < 1.0


def test_the_sweep_is_idempotent():
    """Run twice, retire once. A second retirement would move retired_ts and
    make 'retired N days ago' lie."""
    now = time.time()
    m = _store(now)
    rid = m.remember_fact("Dana is in Montreal", importance=3, ts=now - 5 * DAY,
                          kind="situation", valid_until=now - DAY)
    assert m.expire_stale(now=now) == 1
    first = m.db.execute("SELECT retired_ts FROM profile_facts WHERE id=?", (rid,)).fetchone()[0]
    assert m.expire_stale(now=now + 10) == 0
    second = m.db.execute("SELECT retired_ts FROM profile_facts WHERE id=?", (rid,)).fetchone()[0]
    assert first == second


def test_a_garbage_horizon_is_no_verdict_and_never_raises():
    """A model returning a string, a negative, or nonsense must leave the fact
    permanent rather than crash the nightly pass or expire it at epoch zero."""
    now = time.time()
    m = _store(now)
    for bad in ("soon", "", None, float("nan"), float("inf"), -1, 0):
        rid = m.remember_fact(f"fact about {bad!r}", importance=3, ts=now,
                              kind="situation", valid_until=bad)
        # Assert the STORED value, not merely that nothing expired. A NaN
        # horizon never expires anything either way, because NaN <= now is
        # False — so a test that only watched the sweep would pass with no
        # sanitiser at all. Verified: it did, until this line was added.
        (stored,) = m.db.execute(
            "SELECT valid_until FROM profile_facts WHERE id=?", (rid,)).fetchone()
        assert stored is None, f"{bad!r} was stored as a horizon: {stored!r}"
        assert not m._is_retired(rid), f"{bad!r} should not expire anything"
    assert m.expire_stale(now=now) == 0


def test_a_stable_fact_is_never_expired_by_a_horizon():
    """If the model says a birthday expires, that is no verdict. 'stable' is the
    kind that means 'this does not stop being true'."""
    now = time.time()
    m = _store(now)
    rid = m.remember_fact("his birthday is 29 August", importance=5, ts=now - 400 * DAY,
                          kind="stable", valid_until=now - DAY)
    assert m.expire_stale(now=now) == 0
    assert not m._is_retired(rid)
