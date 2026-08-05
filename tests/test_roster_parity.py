"""The Swift roster and the Python roster must never drift apart.

VoiceRoster exists twice: proof/voice_roster.py (the reference, where the
thresholds were measured) and app/ios/.../VoiceRoster.swift (what actually
runs on his phone). Two copies of a safety rule is exactly how a corrected
threshold gets fixed in one place and left wrong in the other — and the
wrong direction here means a stranger gets called Omar and their promises
become his commitments.

This reads the Swift source and asserts the numbers still match.
"""
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SWIFT = os.path.join(ROOT, "app", "ios", "Anticipy", "Audio", "VoiceRoster.swift")


def _swift_constant(name: str) -> float:
    src = open(SWIFT).read()
    m = re.search(rf"static let {name}: Float = ([0-9.]+)", src)
    assert m, f"{name} not found in VoiceRoster.swift"
    return float(m.group(1))


@pytest.mark.skipif(not os.path.exists(SWIFT), reason="iOS sources absent")
def test_match_threshold_matches_the_reference():
    from proof.voice_roster import MATCH
    assert _swift_constant("match") == MATCH


@pytest.mark.skipif(not os.path.exists(SWIFT), reason="iOS sources absent")
def test_margin_matches_the_reference():
    from proof.voice_roster import MARGIN
    assert _swift_constant("margin") == MARGIN


@pytest.mark.skipif(not os.path.exists(SWIFT), reason="iOS sources absent")
def test_the_unsafe_060_never_comes_back():
    """0.60 let a third voice (0.667 against the owner) pass as the owner."""
    assert _swift_constant("match") >= 0.75


@pytest.mark.skipif(not os.path.exists(SWIFT), reason="iOS sources absent")
def test_swift_keeps_the_drift_and_the_ambiguity_guard():
    src = open(SWIFT).read()
    # Same 85/15 profile drift as the reference.
    assert "0.85" in src and "0.15" in src
    # Ambiguous audio must never be learned as a new person.
    assert "ambiguous" in src
    # And an unclaimable voice must be reported as unknown, not guessed.
    assert '"unknown"' in src
