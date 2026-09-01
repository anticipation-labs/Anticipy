"""The home-screen listening marks may breathe, but may never travel.

Build 113 wrapped the whole BreathingDot and each WaveBars bar in an implicit
repeatForever animation. When Home's ScrollView settled into its final layout,
that transaction also interpolated their positions. The user's screenshots
show the exact four escaped views: one circle and three delayed capsules.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
THEME = ROOT / "app/ios/Anticipy/Theme.swift"


def _component(name: str, next_marker: str) -> str:
    source = THEME.read_text()
    start = source.index(f"struct {name}: View")
    end = source.index(next_marker, start)
    return source[start:end]


def test_wave_bars_use_no_repeating_animation_transaction():
    source = _component("WaveBars", "/// The app's heartbeat")
    assert ".repeatForever(" not in source
    assert "value: up" not in source
    assert "TimelineView(.animation(" in source
    assert "AmbientMotionPhase.unit(" in source
    assert ".scaleEffect(" in source


def test_breathing_dot_uses_no_repeating_animation_transaction():
    source = _component("BreathingDot", "// MARK: - What a field says")
    assert ".repeatForever(" not in source
    assert "value: up" not in source
    assert "TimelineView(.animation(" in source
    assert "AmbientMotionPhase.unit(" in source
    assert ".scaleEffect(" in source and ".opacity(" in source


def test_the_regression_is_held_by_the_reported_four_marks():
    wave = _component("WaveBars", "/// The app's heartbeat")
    dot = _component("BreathingDot", "// MARK: - What a field says")
    assert "ForEach(0 ..< 3" in wave
    assert "Circle()" in dot
    assert "@State private var up" not in wave + dot
