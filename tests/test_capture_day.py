"""The day report has to be able to give a wrong answer, and be caught.

A measuring stick nobody has ever seen fail is indistinguishable from a
constant. These drive proof/capture_day.py's pure half with synthetic rows —
no network, no clock — and the case that matters most is the stitching: a
`ceiling` flush cuts a sentence at eight seconds and marks the next line as its
continuation, so counting raw rows scores one long thought as three shards and
would report the cut-marking fix as a regression.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from proof.capture_day import report, stitch  # noqa: E402


def line(i, text, parent=None, speaker="", src="phone_mic", at=None):
    return {
        "id": f"r{i}", "kind": "transcript", "text": text,
        "parent_line": parent or "", "speaker": speaker, "source": src,
        "capture_started_at": at or f"2026-08-24 10:{i:02d}:00.000Z",
    }


def test_an_empty_day_is_a_finding_not_a_crash():
    # Nothing arriving is exactly what a suspended app and a deaf recognizer
    # both look like from the server. It has to be reportable.
    d = report([])
    assert d["lines"] == 0 and d["thoughts"] == 0
    assert d["shard_rate"] == 0.0 and d["speaker_coverage"] == 0.0


def test_a_stitched_chain_counts_as_one_thought_not_three():
    """THE measurement. Three rows, two of them continuations, is ONE thought
    of fifteen words — not three shards. Counting rows would report the
    cut-marking work as having made things worse."""
    rows = [
        line(1, "so the thing about the pricing tier we discussed"),
        line(2, "is that it assumes the enterprise seats", parent="r1"),
        line(3, "actually close this quarter", parent="r2"),
    ]
    assert len(stitch(rows)) == 1
    d = report(rows)
    assert d["lines"] == 3
    assert d["thoughts"] == 1
    assert d["shard_thoughts"] == 0, "a long stitched thought is not a shard"


def test_the_raw_rate_is_reported_too_so_the_stitching_can_be_audited():
    # Both numbers, always. If the stitched rate is wonderful and the raw rate
    # is unchanged, the phone is still cutting sentences and only the counting
    # got better — which is worth being able to see.
    rows = [line(1, "at"), line(2, "5:15", parent="r1")]
    d = report(rows)
    assert d["thoughts"] == 1
    assert d["raw_shard_rate"] == 1.0, "both rows are short on their own"


def test_a_genuinely_short_thought_still_counts_as_a_shard():
    # The fix must not launder real shards away. "At 5:15" standing alone is
    # the recorded failure: two words that minted a meeting with Dr. Evans.
    rows = [line(1, "at 5:15"), line(2, "yeah"), line(3, "okay sure")]
    d = report(rows)
    assert d["thoughts"] == 3 and d["shard_thoughts"] == 3
    assert d["shard_rate"] == 1.0


def test_a_parent_we_do_not_have_starts_its_own_thought():
    # Rotated away, another day, a deleted row. An orphan is a head, never
    # silently dropped: dropping it would quietly shrink the denominator and
    # flatter the rate.
    rows = [line(1, "carries on from yesterday", parent="gone-from-this-window")]
    assert len(stitch(rows)) == 1
    assert report(rows)["thoughts"] == 1


def test_a_cycle_cannot_hang_the_report():
    # The report is what you reach for when something is already wrong, so it
    # may not be the second thing that breaks.
    a, b = line(1, "one", parent="r2"), line(2, "two", parent="r1")
    assert len(stitch([a, b])) >= 0  # returns rather than spinning


def test_speaker_coverage_is_the_share_of_lines_with_any_verdict():
    # 3% on build 75 — 97% carried none — which is why an unattributed line
    # may not mint an action today.
    rows = [line(1, "a", speaker="owner"), line(2, "b"), line(3, "c", speaker="other:v1")]
    assert report(rows)["speaker_coverage"] == round(2 / 3, 3)


def test_the_longest_gap_uses_spoken_time_not_arrival():
    """Ordering a flushed backlog by arrival invents gaps that never happened.
    Same rule as brain/worker.py's capture_key, for the same reason."""
    rows = [
        line(1, "first", at="2026-08-24 10:00:00.000Z"),
        line(2, "an hour later", at="2026-08-24 11:00:00.000Z"),
    ]
    # Arrival order deliberately reversed: the rows came back newest-first.
    assert report(list(reversed(rows)))["longest_gap_seconds"] == 3600


def test_non_transcript_rows_are_not_counted_as_things_heard():
    # anticipy_says rows are HER voice. Counting them as capture would score a
    # chatty day as a well-heard one.
    rows = [line(1, "he said this"),
            {"id": "s1", "kind": "anticipy_says", "text": "she said this back"}]
    d = report(rows)
    assert d["lines"] == 1 and d["words"] == 3


def test_which_ear_is_reported():
    rows = [line(1, "a", src="phone_mic"), line(2, "b", src="pendant"),
            line(3, "c", src="phone_mic")]
    assert report(rows)["sources"] == {"phone_mic": 2, "pendant": 1}
