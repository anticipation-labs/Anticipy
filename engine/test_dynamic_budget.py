"""Unit tests for app.dynamic_budget."""

from __future__ import annotations

import pytest

from app.dynamic_budget import ContinueDecision, DynamicBudget


# ────────────────────────────────────────────────────────────────────────
# Construction
# ────────────────────────────────────────────────────────────────────────


def test_construction_uses_defaults():
    b = DynamicBudget()
    assert b.soft_cap == 30
    assert b.hard_cap == 200


def test_construction_with_custom_caps():
    b = DynamicBudget(soft_cap=10, hard_cap=50)
    assert b.soft_cap == 10
    assert b.hard_cap == 50


def test_construction_rejects_zero_soft_cap():
    with pytest.raises(ValueError):
        DynamicBudget(soft_cap=0, hard_cap=10)


def test_construction_rejects_negative_soft_cap():
    with pytest.raises(ValueError):
        DynamicBudget(soft_cap=-1, hard_cap=10)


def test_construction_rejects_hard_cap_below_soft_cap():
    with pytest.raises(ValueError):
        DynamicBudget(soft_cap=20, hard_cap=10)


def test_construction_allows_hard_cap_equal_soft_cap():
    """Edge case: when caps equal, every step >= cap fires hard-cap stop."""
    b = DynamicBudget(soft_cap=5, hard_cap=5)
    assert b.soft_cap == 5
    assert b.hard_cap == 5


def test_step_outcome_rejects_zero_step():
    b = DynamicBudget()
    with pytest.raises(ValueError):
        b.step_outcome(0, made_progress=True)


def test_step_outcome_rejects_negative_step():
    b = DynamicBudget()
    with pytest.raises(ValueError):
        b.step_outcome(-1, made_progress=True)


# ────────────────────────────────────────────────────────────────────────
# Short happy path
# ────────────────────────────────────────────────────────────────────────


def test_short_happy_path_5_steps():
    """5-step task with progress every step → all continue, no nudge."""
    b = DynamicBudget(soft_cap=30, hard_cap=200)
    for step in range(1, 6):
        d = b.step_outcome(step, made_progress=True)
        assert isinstance(d, ContinueDecision)
        assert d.should_continue is True
        assert d.nudge is None


# ────────────────────────────────────────────────────────────────────────
# Long happy path
# ────────────────────────────────────────────────────────────────────────


def test_long_happy_path_50_steps():
    """50 progress steps with soft_cap=30 → soft nudge fires once at step 30,
    then continue all the way through 50."""
    b = DynamicBudget(soft_cap=30, hard_cap=200)

    nudge_count = 0
    for step in range(1, 51):
        d = b.step_outcome(step, made_progress=True)
        assert d.should_continue is True
        if d.nudge is not None:
            nudge_count += 1
            # The nudge fires exactly when we hit step 30 (the soft cap).
            assert step == 30, (
                f"nudge fired at step {step}, expected step 30"
            )

    assert nudge_count == 1, f"expected 1 nudge, got {nudge_count}"


def test_nudge_text_is_actionable():
    """The nudge text should tell the LLM what to do, not just warn."""
    b = DynamicBudget(soft_cap=3, hard_cap=200)
    for s in (1, 2):
        b.step_outcome(s, made_progress=True)
    d = b.step_outcome(3, made_progress=True)
    assert d.nudge is not None
    # Substantive: mentions abort/done so the LLM has a clear instruction.
    nudge = d.nudge.lower()
    assert "abort" in nudge or "done" in nudge or "step" in nudge


# ────────────────────────────────────────────────────────────────────────
# No-progress trigger
# ────────────────────────────────────────────────────────────────────────


def test_no_progress_triggers_at_exactly_5():
    """Steps 1-4 no-progress → continue. Step 5 no-progress → stop."""
    b = DynamicBudget(soft_cap=30, hard_cap=200)

    for step in range(1, 5):
        d = b.step_outcome(step, made_progress=False)
        assert d.should_continue is True, (
            f"step {step} should continue (only {step} consecutive no-progress)"
        )

    d = b.step_outcome(5, made_progress=False)
    assert d.should_continue is False
    assert "no progress" in d.reason.lower()


def test_progress_resets_no_progress_counter():
    """After 4 no-progress, a single progress step resets the counter."""
    b = DynamicBudget(soft_cap=30, hard_cap=200)

    for step in range(1, 5):
        b.step_outcome(step, made_progress=False)

    # Progress at step 5 resets the streak.
    d = b.step_outcome(5, made_progress=True)
    assert d.should_continue is True

    # Now we can have another 4 no-progress without stopping.
    for step in range(6, 10):
        d = b.step_outcome(step, made_progress=False)
        assert d.should_continue is True

    # Step 10 (5th consecutive no-progress since reset) → stop.
    d = b.step_outcome(10, made_progress=False)
    assert d.should_continue is False
    assert "no progress" in d.reason.lower()


def test_no_progress_streak_with_mixed():
    """Mixed progress/no-progress within a long run never trips the streak."""
    b = DynamicBudget(soft_cap=100, hard_cap=200)

    pattern = [True, False, False, True, False, False, True, False, False, True]
    for step, prog in enumerate(pattern, start=1):
        d = b.step_outcome(step, made_progress=prog)
        assert d.should_continue is True


# ────────────────────────────────────────────────────────────────────────
# Hard cap
# ────────────────────────────────────────────────────────────────────────


def test_hard_cap_fires():
    """Hitting hard_cap stops the loop with a clear reason."""
    b = DynamicBudget(soft_cap=5, hard_cap=10)

    # Run 1-9 with progress so we don't trip no-progress.
    for step in range(1, 10):
        d = b.step_outcome(step, made_progress=True)
        assert d.should_continue is True

    # Step 10 == hard_cap → stop.
    d = b.step_outcome(10, made_progress=True)
    assert d.should_continue is False
    assert "hard ceiling" in d.reason.lower()
    assert d.nudge is None


def test_hard_cap_extension_recoverable():
    """After a hard-cap hit, caller can extend and continue."""
    b = DynamicBudget(soft_cap=5, hard_cap=10)

    for step in range(1, 11):
        b.step_outcome(step, made_progress=True)

    # Extend the cap.
    b.extend_hard_cap(20)

    d = b.step_outcome(11, made_progress=True)
    assert d.should_continue is True


def test_extend_hard_cap_rejects_lower_value():
    b = DynamicBudget(soft_cap=5, hard_cap=10)
    with pytest.raises(ValueError):
        b.extend_hard_cap(5)
    with pytest.raises(ValueError):
        b.extend_hard_cap(10)  # equal is also rejected


# ────────────────────────────────────────────────────────────────────────
# Soft-cap nudge fires exactly once
# ────────────────────────────────────────────────────────────────────────


def test_soft_cap_nudge_fires_only_once():
    """Once the nudge fires, future steps don't fire it again."""
    b = DynamicBudget(soft_cap=5, hard_cap=200)

    nudges = []
    for step in range(1, 20):
        d = b.step_outcome(step, made_progress=True)
        if d.nudge is not None:
            nudges.append(step)
            assert d.should_continue is True

    # Exactly one nudge, at step 5 (when we hit the soft cap).
    assert nudges == [5]


def test_reset_soft_cap_re_enables_nudge():
    """After reset_soft_cap, the nudge can fire again at the new boundary."""
    b = DynamicBudget(soft_cap=5, hard_cap=200)

    # Burn through to step 7 with the first nudge at step 5.
    for step in range(1, 8):
        b.step_outcome(step, made_progress=True)

    b.reset_soft_cap(15)

    # Steps 8-14 no nudge.
    for step in range(8, 15):
        d = b.step_outcome(step, made_progress=True)
        assert d.nudge is None

    # Step 15 fires nudge again.
    d = b.step_outcome(15, made_progress=True)
    assert d.nudge is not None


def test_reset_soft_cap_rejects_zero():
    b = DynamicBudget()
    with pytest.raises(ValueError):
        b.reset_soft_cap(0)


# ────────────────────────────────────────────────────────────────────────
# Reason string is always populated
# ────────────────────────────────────────────────────────────────────────


def test_reason_is_set_after_each_call():
    b = DynamicBudget(soft_cap=5, hard_cap=10)
    assert b.reason() == ""  # initial

    b.step_outcome(1, made_progress=True)
    assert b.reason() != ""

    d = b.step_outcome(2, made_progress=True)
    assert b.reason() == d.reason


# ────────────────────────────────────────────────────────────────────────
# Hard cap takes precedence over no-progress
# ────────────────────────────────────────────────────────────────────────


def test_hard_cap_takes_precedence_over_no_progress():
    """If hard_cap < no_progress_limit, hard_cap wins."""
    b = DynamicBudget(soft_cap=2, hard_cap=3)

    b.step_outcome(1, made_progress=False)
    b.step_outcome(2, made_progress=False)
    d = b.step_outcome(3, made_progress=False)
    assert d.should_continue is False
    # 3 hits hard_cap before 5 no-progress → hard_cap wins.
    assert "hard ceiling" in d.reason.lower()
