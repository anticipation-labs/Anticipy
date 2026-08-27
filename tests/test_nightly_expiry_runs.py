"""The nightly pass must actually RUN the expiry sweep.

`Memory.expire_stale` was written, tested by `test_memory_expiry.py`, and
called by nothing: `grep -rn expire_stale brain/` returned exactly one line,
its own definition. Eleven passing tests over a function the product never
invoked — the same shape as `CallPresencePolicy` (44 checks, zero call sites)
and the finale that had three endings and always rendered one.

So the thing worth testing here is NOT what `expire_stale` returns. That is
already covered. It is that `run_nightly_consolidation` calls it at all, and
calls it BEFORE consolidating, because a fact past its horizon is wrong rather
than faded and consolidation writes the profile layer that answers questions.
"""
from datetime import datetime, timedelta

from brain import worker


class _Spy:
    """A memory stand-in that records the order it was asked to do things."""

    def __init__(self, expired=0, boom=False):
        self.calls = []
        self._expired = expired
        self._boom = boom
        # The pass skips outright with no live model, so the spy must look
        # like it has one. It is never called: `consolidate` is stubbed.
        self.llm = object()
        self._nightly_attempt_ts = 0.0

    def last_consolidation_ts(self):
        # Never consolidated, so the once-a-night gate lets this through.
        return 0.0

    def expire_stale(self, now=None):
        self.calls.append("expire")
        if self._boom:
            raise RuntimeError("sweep exploded")
        return self._expired

    def consolidate(self, now=None):
        self.calls.append("consolidate")
        # One pass, nothing left, so the batch loop stops immediately.
        return {"ran": True, "episodes": 0, "new": 0, "merged": 0,
                "remaining": 0}


def _quiet_hour_timestamp() -> float:
    """An instant that really is inside quiet hours, computed from the
    module's own constants rather than a number that happened to work when
    this was written. If somebody moves the window, this test follows it."""
    base = datetime.now(worker.CLOCK_TZ).replace(
        hour=worker.CLOCK_QUIET_START, minute=30, second=0, microsecond=0)
    ts = base.timestamp()
    hour = datetime.fromtimestamp(ts, worker.CLOCK_TZ).hour
    assert worker.CLOCK_QUIET_START <= hour or hour < worker.CLOCK_QUIET_END, (
        "the computed instant is not inside quiet hours; the constants moved")
    return ts


def _run(spy, now=None):
    worker.run_nightly_consolidation(spy, now=now or _quiet_hour_timestamp())


def test_the_nightly_pass_calls_the_expiry_sweep():
    """The whole point. Delete the call in worker.py and this goes red."""
    spy = _Spy()
    _run(spy)
    assert "expire" in spy.calls, (
        "run_nightly_consolidation never called expire_stale — the sweep is "
        "back to being a function nobody runs")


def test_expiry_runs_before_consolidation():
    """Ordering is the argument, not a preference.

    Consolidation reads facts and writes the profile layer. Expiring
    afterwards would distil a fact that is already wrong into the layer that
    answers questions, then retire the source and leave the conclusion
    standing.
    """
    spy = _Spy()
    _run(spy)
    assert spy.calls.index("expire") < spy.calls.index("consolidate"), (
        f"expiry must precede consolidation, got {spy.calls}")


def test_a_failing_sweep_does_not_take_consolidation_down():
    """The night's memory is worth more than the night's expiry.

    This runs on a poll tick and distillation is why the pass exists, so a
    sweep that throws must cost the expiry only.
    """
    spy = _Spy(boom=True)
    _run(spy)
    assert "consolidate" in spy.calls, (
        "a throwing expire_stale prevented consolidation from running at all")
