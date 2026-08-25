"""The nightly consolidation hook in the worker (roadmap §1, brief 05).

The guardrails live outside the model, like the clock's: quiet hours only,
once per night, and a Memory with no LLM is skipped without a trace.
"""
import time
from datetime import datetime

from brain import worker
from brain.memory import Memory
from llm_fakes import FakeLLM


def _at(hour: int) -> float:
    return datetime(2026, 8, 4, hour, 30, tzinfo=worker.CLOCK_TZ).timestamp()


def test_daytime_never_consolidates():
    fake = FakeLLM(consolidations=[{"facts": []}])
    m = Memory(llm=fake)
    m.ingest("a daytime line", ts=time.time())
    worker.run_nightly_consolidation(m, now=_at(12))
    assert fake.consolidation_calls() == []
    assert m.last_consolidation_ts() == 0.0


def test_night_runs_once_per_night():
    fake = FakeLLM(consolidations=[
        {"facts": [{"fact": "building Anticipy", "importance": 3,
                    "episode_ids": [1]}]},
        {"facts": []},
    ])
    m = Memory(llm=fake)
    m.ingest("Anticipy again, all evening", ts=time.time())

    night = _at(3)
    worker.run_nightly_consolidation(m, now=night)
    assert len(fake.consolidation_calls()) == 1
    assert len(m.profile_facts()) == 1
    assert m.last_consolidation_ts() == night

    # Ten minutes later, same night: the gap guard holds.
    worker.run_nightly_consolidation(m, now=night + 600)
    assert len(fake.consolidation_calls()) == 1

    # The next night it runs again — over the new day's episodes only.
    m.ingest("a brand new day of talk", ts=night + 12 * 3600)
    worker.run_nightly_consolidation(m, now=night + 24 * 3600)
    assert len(fake.consolidation_calls()) == 2
    assert "brand new day" in fake.consolidation_calls()[1]
    assert "all evening" not in fake.consolidation_calls()[1]


def test_no_llm_is_skipped_entirely():
    m = Memory()
    m.ingest("a line with no model behind it", ts=time.time())
    worker.run_nightly_consolidation(m, now=_at(3))
    assert m.profile_facts() == []
    assert m.last_consolidation_ts() == 0.0


def test_consolidation_failure_never_raises():
    fake = FakeLLM(consolidations=[RuntimeError("model fell over")])
    m = Memory(llm=fake)
    m.ingest("a line", ts=time.time())
    worker.run_nightly_consolidation(m, now=_at(3))   # must not raise
    assert m.profile_facts() == []
    # Nothing advanced: the next night re-reads the same episode.
    assert m.last_consolidation_ts() == 0.0


def test_failed_night_retries_gently_not_per_tick():
    """Only success stamps last_run_ts, and the hook runs every poll tick —
    so a flaky model must be held to the attempt gap, not called until dawn."""
    fake = FakeLLM(consolidations=[
        RuntimeError("model fell over"),
        {"facts": [{"fact": "building Anticipy", "importance": 3,
                    "episode_ids": [1]}]},
    ])
    m = Memory(llm=fake)
    m.ingest("Anticipy all night", ts=time.time())

    night = _at(2)
    worker.run_nightly_consolidation(m, now=night)          # fails
    worker.run_nightly_consolidation(m, now=night + 2)      # next tick: held
    worker.run_nightly_consolidation(m, now=night + 60)     # still held
    assert len(fake.consolidation_calls()) == 1

    # Past the retry gap, still night: it tries again and succeeds.
    worker.run_nightly_consolidation(
        m, now=night + worker.CONSOLIDATE_RETRY_SECONDS + 1)
    assert len(fake.consolidation_calls()) == 2
    assert len(m.profile_facts()) == 1


# ------------- I4 / LAW 3: the precondition for the whole decay half, measured
#
# `grep -rn "consolidat" overnight/*.py` is EMPTY. The kind/decay half of the
# profile ranker — the half that fixes the measured 6x shellfish inversion —
# writes nothing until a nightly consolidation pass runs WITH A LIVE MODEL,
# because consolidate() is the only writer of `kind` anywhere in the store.
# The chain that has to hold, end to end, is four links long:
#
#   1. worker.py hands Memory an llm ONLY when `llm.live`
#   2. Memory.consolidate() refuses without one
#   3. run_nightly_consolidation() returns immediately on `memory.llm is None`,
#      and additionally needs quiet hours and a once-per-night gap
#   4. the `kind` the model returns has to survive into profile_facts()
#
# Every link was individually plausible and none of them was asserted from the
# other end, so "the fix shipped" and "the fix can ever fire" were different
# statements with nothing measuring the difference. The legs below make links
# 2 and 4 non-silent and prove 3 does not swallow a live night.
#
# WHAT THESE LEGS CANNOT DO, said plainly rather than implied away: none of
# this is evidence that consolidation has EVER run against a live model in
# production. Law 3 wants that measured against LIVE, and the leg for it
# belongs in overnight/ where the gates live — this file cannot reach the
# deployed store. Its assertion, written down here so it is not re-derived:
#
#   NIGHTLY CONSOLIDATION ACTUALLY RUNS — red until, against the LIVE store,
#   (a) `last_run_ts` is within the last 48 hours, and (b) at least one
#   profile_facts row carries a non-null `kind` written by source
#   'consolidation'. (a) alone passes on a store with nothing to distill;
#   (b) alone passes on a single ancient pass. Until both hold, the decay
#   half is inert in production however green this file is.


class _DeadLLM(FakeLLM):
    """The shape worker.py guards against three thousand lines from here:
    credentials missing, so the client exists but cannot answer."""
    live = False


def test_a_model_that_is_not_live_is_refused_before_the_night_is_spent():
    """Link 2, which had no assertion at all. `llm if llm.live else None` in
    worker.py was the only thing between this method and a dead model, and a
    precondition enforced only at a call site three thousand lines away is a
    precondition that gets dropped by the next edit to that call site."""
    dead = _DeadLLM(consolidations=[{"facts": []}])
    m = Memory(llm=dead)
    m.ingest("a line worth distilling", ts=time.time())
    out = m.consolidate()
    assert out["ran"] is False
    assert "live" in out["reason"]
    assert dead.consolidation_calls() == [], \
        "a nightly pass was spent calling a model that cannot answer"


def test_with_no_model_at_all_the_kind_half_writes_nothing_and_says_so():
    """Link 2's other half, and the honest statement of the shipped state:
    with no live model the decay fix is not merely unexercised, it is
    unreachable, because consolidate() is the only writer of `kind`."""
    m = Memory(llm=None)
    m.ingest("a line worth distilling", ts=time.time())
    out = m.consolidate()
    assert out == {"ran": False, "reason": "no llm", "episodes": 0,
                   "new": 0, "merged": 0, "remaining": 0}
    assert m.profile_facts() == []


def test_one_live_night_puts_a_kind_on_the_profile_where_the_ranker_reads_it():
    """Links 3 and 4 together, from the worker hook the deployment actually
    calls through to the field the ranker actually reads. This is the leg that
    goes red if any part of the chain quietly stops carrying `kind` — which is
    the failure mode the wave-1 report could only describe in prose."""
    fake = FakeLLM(consolidations=[
        {"facts": [{"fact": "allergic to shellfish", "importance": 5,
                    "kind": "stable", "episode_ids": [1]}]},
        {"facts": []},
    ])
    m = Memory(llm=fake)
    m.ingest("no shellfish for me, ever", ts=time.time())
    worker.run_nightly_consolidation(m, now=_at(3))
    assert fake.consolidation_calls(), "the live night never called the model"
    facts = m.profile_facts()
    assert [f["fact"] for f in facts] == ["allergic to shellfish"]
    assert facts[0]["kind"] == "stable", \
        "the model's kind never reached the ranker, so decay is still uniform"
