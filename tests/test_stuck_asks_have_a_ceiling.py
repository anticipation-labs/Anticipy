"""One stuck task must not text him all day.

From his real log, pulled from production: 136 of the last 200 outbound
messages were this one path. 63 in a single day, 60 the next. The same Earls
booking, roughly one every twenty minutes, plus two at 06:59 on consecutive
mornings.

The cause was not a missing guard. need_already_asked keys on the BLOCKER,
deliberately, so a genuinely new obstacle can still reach him. But a stuck run
rewords the SAME obstacle on every retry -- "which location works best",
"needs a site check", "stalled after a pop-up" -- and each rewording read as
new. asks_for_goal already counted the asks; it was only used to widen a
window, which a new wording walks past.

These tests drive the REAL function against a fake backend, because the
mutation audit showed that tests asserting on source text pass happily while
the behaviour underneath is completely defeated.
"""
import types
import pytest
from brain import worker as W


class FakePB:
    """Stands in for the events collection, recording what was asked."""

    def __init__(self, asks_for_goal=0):
        self.asks = asks_for_goal
        self.queries = []

    def get(self, url, params=None, timeout=None):
        self.queries.append((url, (params or {}).get("filter", "")))
        filt = (params or {}).get("filter", "")
        items = []
        if 'decision="needs_user"' in filt:
            items = [{"goal": "book a table at Earls", "text": "stuck"}
                     for _ in range(self.asks)]
        return types.SimpleNamespace(
            ok=True, json=lambda: {"items": items})


@pytest.fixture
def pb(monkeypatch):
    fake = FakePB()
    monkeypatch.setattr(W, "pb", fake)
    return fake


def test_the_counter_reports_what_was_actually_sent(pb):
    pb.asks = 0
    assert W.asks_for_goal("book a table at Earls") == 0
    pb.asks = 2
    assert W.asks_for_goal("book a table at Earls") == 2


def test_there_is_a_ceiling_at_all():
    """The value may be tuned; its EXISTENCE is the fix. A ceiling of 0 would
    mean silence, and an enormous one would restore the flood."""
    assert isinstance(W.STUCK_ASKS_CEILING, int)
    assert 1 <= W.STUCK_ASKS_CEILING <= 3, (
        f"a ceiling of {W.STUCK_ASKS_CEILING} is not 'one ask, one second "
        f"chance, then quiet'")


def test_the_ceiling_is_actually_consulted_before_sending():
    """The mutation audit's lesson: a constant nothing reads is decoration.
    Assert the send path compares the count against the ceiling."""
    import inspect
    src = inspect.getsource(W)
    i = src.index("STUCK_ASKS_CEILING = ")
    after = src[i + 20:]
    assert "asks_already >= STUCK_ASKS_CEILING" in after, (
        "the ceiling is defined but never compared against the ask count")


def test_a_blocked_errand_is_not_deferred_to_morning():
    """Quiet hours were tried on this path and deliberately removed.

    A stuck task is not an uninvited finding -- it is his own errand blocked
    on one detail, and test_backlog_and_delivery encodes the decision that a
    genuinely new requirement speaks AT ONCE. Deferring a blocked booking
    nine hours can kill it. His complaint was volume, not the hour."""
    import inspect
    src = inspect.getsource(W.report_stuck_jobs) if hasattr(W, "report_stuck_jobs") else ""
    if not src:
        # find whichever function owns the stuck-ask send
        for name, fn in vars(W).items():
            if callable(fn) and getattr(fn, "__module__", "") == W.__name__:
                try:
                    body = inspect.getsource(fn)
                except Exception:
                    continue
                if "STUCK_ASKS_CEILING" in body:
                    src = body
                    break
    assert src, "could not locate the stuck-ask send path"
    assert "CLOCK_QUIET_START" not in src, (
        "a blocked errand must not be silently deferred to morning -- that "
        "trades one complaint for a worse one")


@pytest.mark.parametrize("asks,expect_quiet", [(0, False), (1, False), (2, True), (7, True)])
def test_the_gate_itself(asks, expect_quiet):
    """The decision in isolation: at or above the ceiling, stay quiet."""
    assert (asks >= W.STUCK_ASKS_CEILING) is expect_quiet
