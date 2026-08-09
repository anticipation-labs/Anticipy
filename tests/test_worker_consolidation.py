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
