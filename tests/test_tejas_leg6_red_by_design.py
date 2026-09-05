"""Leg 6 stays red, and stops prescribing the thing that kills TestFlight.
Audit F30.

The gate said:

    [6] FAIL THE SPEAKER TAGGER IS LINKED
        packageProductDependencies is an EMPTY LIST … speaker stays empty on
        every event until somebody adds the package product to the target
    NOT DONE - first failing leg: 6

CLAUDE.md tells every agent to run the scoreboards and believe them. This one
instructed the reader to re-link the sherpa-onnx/onnxruntime binary
xcframework — and app/ios/project.yml:683-731, docs/BRIEF.html and
research/2026-09-04-omi-port-coverage.md:82-91 all record what happens when
somebody does: builds 46/47 and 76-80 carried it and VANISHED during App Store
Connect processing. The gate and the ledgers disagreed, and the gate was the
one being read.

The predicate is untouched — softening a leg to reach green is exactly what
Law 3 forbids, and speaker really is empty on every event. What changed is
that the failure text now says what the ledger says, and the summary line
labels the leg red-by-design the way tape_gate.py labels its leg 2, so nobody
reads it as the next thing to fix.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from overnight import tejas_gate as T  # noqa: E402


def test_leg_6_is_still_red_on_this_tree():
    """Not softened. The engine is unlinked and the leg says so."""
    with pytest.raises(T.LegFailed) as caught:
        T.leg_6_speaker_linked()

    assert "packageProductDependencies is EMPTY" in str(caught.value)


def test_the_failure_text_agrees_with_the_ledger():
    """The finding: the remedy it prescribed is the action the ledgers record
    as fatal to distribution."""
    with pytest.raises(T.LegFailed) as caught:
        T.leg_6_speaker_linked()
    message = str(caught.value)

    assert "RED BY DESIGN" in message
    assert "do NOT re-link" in message
    assert "App Store Connect" in message
    assert "project.yml" in message
    assert "omi-port-coverage" in message
    # And it names the precondition, so the leg is not simply unreachable.
    assert "Precondition to go green" in message


def test_the_summary_labels_it_rather_than_pointing_at_it(capsys):
    """`first failing leg: 6` read as "fix this next". It now reads as
    "this one is red on purpose", and the exit code is unchanged."""
    code = T.main()

    out = capsys.readouterr().out
    assert code == 1, "a red leg is still red; the gate does not pass"
    assert "first failing leg: 6" in out
    assert "red by design" in out
    assert 6 in T.RED_BY_DESIGN


def test_the_predicate_still_passes_when_the_engine_is_really_linked(tmp_path,
                                                                     monkeypatch):
    """The direction pin. A label is not a mute button: the day the package is
    genuinely linked — after somebody reads the ASC rejection — this leg goes
    green on its own evidence."""
    pbx = tmp_path / "project.pbxproj"
    pbx.write_text("""
        packageProductDependencies = (
            AAAA1111 /* sherpa-onnx */,
        );
    """)
    monkeypatch.setattr(T, "PBX", str(pbx))

    assert "linked" in T.leg_6_speaker_linked()


def test_a_linked_package_that_is_not_the_engine_is_still_red(tmp_path,
                                                              monkeypatch):
    """The other half of the original predicate, unchanged."""
    pbx = tmp_path / "project.pbxproj"
    pbx.write_text("packageProductDependencies = (\n  BBBB2222 /* Sentry */,\n);")
    monkeypatch.setattr(T, "PBX", str(pbx))

    with pytest.raises(T.LegFailed) as caught:
        T.leg_6_speaker_linked()

    assert "not the speech/speaker engine" in str(caught.value)


def test_only_leg_6_carries_the_label():
    """A red-by-design marker that spread would hide a real regression."""
    assert T.RED_BY_DESIGN == {6}
