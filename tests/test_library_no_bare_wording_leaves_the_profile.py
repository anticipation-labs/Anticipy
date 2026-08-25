"""A dead fact's own wording may not leave `profile_facts` beside its retirement.

RULING 2 (brain/memory.py:278-282) says the retirement is written INTO the
fact's own text, "not hung off a sibling key. A sibling key is how
briefing_facts once laundered `source` — it projected the key away and handed
imported text to the prompt as established fact."

`profile_facts` then grew exactly such a sibling key: `"text": r[1]`, the BARE
wording, so `_profile_recall` could count query relevance over what he said
instead of over the seven words `_retired_note` writes around a dead row. The
relevance fix was right. Carrying the bare sentence out of the store in a
public dict to get it was not.

MEASURED by the reviewer who refused the diff: adding ONE line to
`_profile_recall.line()` — `"text": f["text"],` — propagates the un-retired
wording into every row `recall()` returns, into every speech sink, and the
whole suite stays green. brain/orchestrator.py:1244 already holds the idiom
pointed at these dicts: `f"- {f.get('fact') or f.get('text') or ''}"`. No sink
reads it today. It was one refactor from "no longer true — retired 30 days
ago: home is 4 Maple St" arriving in a prompt as "home is 4 Maple St".

THE FIX IS THE KEY'S REMOVAL, not a guard in front of it. `_profile_recall`
is the only reader, it already has the row id, and it now reads the wording
straight out of the store into a local — so there is no key for a sink to
find and no projection for a refactor to make. Unrepresentable beats detected.

THIS FILE IS THE CLASS LEG behind that. It does not name `text`: it walks
EVERY key of EVERY row the three public read seams return — `profile_facts`,
`recall` and `briefing_facts` — and fails if any string value carries a
retired fact's wording without the retirement in the same value. A sibling key
added next month under any name is caught by the same assert.
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from brain.memory import (RETIRED_QUOTED, Memory,  # noqa: E402
                          _retired_note)
from llm_fakes import FakeLLM  # noqa: E402

DAY = 86400.0
DEAD = "home is 4 Maple St"
LIVE = "home is 18 Rowan Ave"


def _moved_store(now: float) -> Memory:
    """The §7 broadband scenario through the real consolidation pass."""
    llm = FakeLLM(
        consolidations=[
            {"facts": [{"fact": DEAD, "importance": 5,
                        "episode_ids": [1], "kind": "stable"}]},
            {"facts": [{"fact": LIVE, "importance": 5,
                        "episode_ids": [2], "kind": "stable"}]},
        ],
        relations=["replaces"],
    )
    m = Memory(":memory:", llm=llm)
    m.ingest("Our place at 4 Maple St.", ts=now - 40 * DAY)
    m.consolidate(now=now - 40 * DAY)
    m.ingest("We moved to 18 Rowan Ave last week.", ts=now - 2 * DAY)
    m.consolidate(now=now - 2 * DAY)
    return m


def _retirement_head(now: float) -> str:
    """The words `_retired_note` writes in FRONT of a dead fact, read off the
    renderer rather than copied from it, and taken only as far as the
    age-dependent part so it holds for a row of any age."""
    rendered = _retired_note("ZZQQXX", now, now)
    assert "retired" in rendered, rendered
    head = rendered.split("retired")[0]
    assert "ZZQQXX" not in head, rendered
    return head


def _rows_of_every_read_seam(m: Memory, now: float) -> list[tuple[str, dict]]:
    """Every dict the module hands out on the speech lane, labelled by where
    it came from so a failure names the seam."""
    rows: list[tuple[str, dict]] = []
    for f in m.profile_facts(retired=RETIRED_QUOTED):
        rows.append(("profile_facts", f))
    for q in ("is that still true", "what was our maple address",
              "what is our rowan address", "where do we live"):
        for f in m.recall(q, retired=RETIRED_QUOTED):
            rows.append((f"recall({q!r})", f))
    for f in m.briefing_facts(since_ts=now - 365 * DAY)["profile"]:
        rows.append(("briefing_facts", f))
    return rows


# ------------------------------------------------------------------- the leg

def test_the_setup_really_does_retire_the_old_address():
    """Guard on the scenario: with nothing retired these legs pass by having
    nothing to look at."""
    now = time.time()
    rows = dict(_moved_store(now).db.execute(
        "SELECT fact, retired_ts IS NOT NULL FROM profile_facts"))
    assert rows == {DEAD: 1, LIVE: 0}


def test_no_key_of_any_read_seam_carries_a_dead_fact_bare():
    """THE CLASS LEG. Not "the `text` key is gone" — no VALUE anywhere may
    hold the dead wording unless the retirement is in the same value."""
    now = time.time()
    m = _moved_store(now)
    head = _retirement_head(now)
    leaks = []
    for where, row in _rows_of_every_read_seam(m, now):
        for key, value in row.items():
            if not isinstance(value, str):
                continue
            if DEAD.lower() in value.lower() and head not in value:
                leaks.append((where, key, value))
    assert not leaks, leaks


def test_the_live_fact_is_still_carried_plainly():
    """The mutation guard on the leg above: a leg that passes because the
    seams return nothing is not a leg. The LIVE address must still arrive,
    bare and unwrapped, everywhere."""
    now = time.time()
    m = _moved_store(now)
    seen = {where for where, row in _rows_of_every_read_seam(m, now)
            for value in row.values()
            if isinstance(value, str) and LIVE.lower() in value.lower()}
    assert "profile_facts" in seen, seen
    assert "briefing_facts" in seen, seen
    assert any(s.startswith("recall(") for s in seen), seen


def test_the_dead_fact_is_still_reachable_as_history():
    """And the other half: removing the key must not remove the FACT. The §7
    answer needs the old address to come back when he asks about it, wearing
    its retirement."""
    now = time.time()
    m = _moved_store(now)
    hits = m.recall("what was our maple address", retired=RETIRED_QUOTED)
    dead = [h for h in hits if h.get("retired_ts") is not None]
    assert dead, hits
    assert dead[0]["salience"] > 0.0, dead
    assert DEAD in dead[0]["fact"] and _retirement_head(now) in dead[0]["fact"]
