"""The day report has to be able to give a wrong answer, and be caught.

A measuring stick nobody has ever seen fail is indistinguishable from a
constant. These drive proof/capture_day.py's pure half with synthetic rows —
no network, no clock — and the case that matters most is the stitching: a
`ceiling` flush cuts a sentence at eight seconds and marks the next line as its
continuation, so counting raw rows scores one long thought as three shards and
would report the cut-marking fix as a regression.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from proof.capture_day import report, spoken_at, stitch  # noqa: E402


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


# --- finding 1: a parent with two children ---------------------------------

def test_no_row_leaves_the_fold():
    """The invariant behind every rate this file prints. A row that vanishes
    from the chains leaves BOTH the numerator and the denominator, so a lost
    row moves the shard rate in whichever direction it happened to point — and
    the flattering direction is the one nobody notices. Several shapes, because
    the bug that shipped only fired on one of them."""
    shapes = {
        "flat": [line(1, "a"), line(2, "b"), line(3, "c")],
        "one chain": [line(1, "a"), line(2, "b", parent="r1"),
                      line(3, "c", parent="r2")],
        "two children of one parent": [
            line(1, "right", at="2026-08-24 10:00:01.000Z"),
            line(2, "so", parent="r1", at="2026-08-24 10:00:03.000Z"),
            line(3, "i was thinking we should move the meeting to thursday",
                 parent="r1", at="2026-08-24 10:00:05.000Z")],
        "three children of one parent": [
            line(1, "head"), line(2, "a", parent="r1"),
            line(3, "b", parent="r1"), line(4, "c", parent="r1")],
        "children of children": [
            line(1, "head"), line(2, "a", parent="r1"),
            line(3, "b", parent="r1"), line(4, "c", parent="r2"),
            line(5, "d", parent="r2"), line(6, "e", parent="r3")],
        "orphan parents": [line(1, "a", parent="gone"), line(2, "b", parent="gone")],
        "self-parent": [line(1, "a", parent="r1")],
        "cycle": [line(1, "a", parent="r2"), line(2, "b", parent="r1")],
        "cycle with a tail": [line(1, "a", parent="r2"), line(2, "b", parent="r1"),
                              line(3, "c", parent="r2")],
        "long chain past the old guard": (
            [line(1, "head")]
            + [line(i, f"w{i}", parent=f"r{i-1}") for i in range(2, 260)]),
        # stitch() tracks rows by position for these two: an id is a thing the
        # server gave us, not a thing we may rely on to be unique or present.
        "repeated id": [line(1, "a"), line(1, "a again"), line(2, "b", parent="r1")],
        "no id at all": [{"kind": "transcript", "text": "who am i"},
                         {"kind": "transcript", "text": "me neither"},
                         line(1, "named", parent="")],
    }
    for name, rows in shapes.items():
        chains = stitch(rows)
        landed = [r for c in chains for r in c]
        assert len(landed) == len(rows), f"{name}: rows went missing"
        assert {id(r) for r in landed} == {id(r) for r in rows}, \
            f"{name}: a row was duplicated or swapped, not just counted"
        assert report(rows)["lines"] == len(rows)


def test_a_second_child_of_one_parent_heads_its_own_thought():
    """A cut has exactly ONE continuation, so two children is a broken pointer
    (pushEvent returns "" for a successful post whose id is unreadable, so
    lastTranscriptEventID never advances and two lines name the same parent).
    The measured failure: the long child fell out of the fold entirely and a
    day whose one thought ran 13 words reported 100% short thoughts."""
    rows = [
        line(1, "right", at="2026-08-24 10:00:01.000Z"),
        line(2, "so", parent="r1", at="2026-08-24 10:00:03.000Z"),
        line(3, "i was thinking we should move the meeting to thursday afternoon",
             parent="r1", at="2026-08-24 10:00:05.000Z"),
    ]
    chains = stitch(rows)
    ids = [[r["id"] for r in c] for c in chains]
    assert ids == [["r1", "r2"], ["r3"]], \
        "earliest child resumes the cut; the later one inherited a stale pointer"
    d = report(rows)
    assert d["thoughts"] == 2
    assert d["shard_thoughts"] == 1, "the 11-word child is not a shard"
    assert d["shard_rate"] == 0.5


def test_a_dropped_sibling_cannot_flatter_the_rate():
    """The other direction, which is the dangerous one: two short children of a
    long parent. Losing them removed a shard from the numerator and reported
    0.0 for a day that held two one-word lines."""
    rows = [
        line(1, "i was thinking we should move the meeting to thursday afternoon",
             at="2026-08-24 10:00:01.000Z"),
        line(2, "yeah", parent="r1", at="2026-08-24 10:00:03.000Z"),
        line(3, "ok", parent="r1", at="2026-08-24 10:00:05.000Z"),
    ]
    d = report(rows)
    assert d["thoughts"] == 2
    assert d["shard_thoughts"] == 1, '"ok" standing alone is a shard'
    assert d["shard_rate"] == 0.5


def test_siblings_are_ordered_by_when_they_were_spoken_not_by_arrival():
    # The phone flushes a backlog, so the row that arrived first is not the one
    # that resumed the cut. Whichever sibling was SPOKEN first continues it.
    rows = [
        line(1, "head", at="2026-08-24 10:00:01.000Z"),
        line(2, "spoken second", parent="r1", at="2026-08-24 10:00:09.000Z"),
        line(3, "spoken first", parent="r1", at="2026-08-24 10:00:03.000Z"),
    ]
    assert [[r["id"] for r in c] for c in stitch(rows)] == [["r1", "r3"], ["r2"]]


# --- finding 2: the clock-skew clamp ---------------------------------------

def test_a_phone_with_a_reset_clock_cannot_reorder_his_day():
    """Measured before the clamp existed here: one row stamped 2026-01-01 by a
    phone whose clock had been reset, next to a normal row, reported
    longest_gap_seconds = 20307630 — 235 days of silence on a day that held two
    lines thirty seconds apart. brain/worker.py has stopped believing such a
    stamp since capture_key was written; this file had not."""
    reset_clock = dict(line(1, "hello there", at="2026-01-01 09:00:00.000Z"),
                       created="2026-08-24 10:00:00.000Z")
    normal = dict(line(2, "and again", at="2026-08-24 10:00:30.000Z"),
                  created="2026-08-24 10:00:30.000Z")
    assert report([reset_clock, normal])["longest_gap_seconds"] == 30


def test_spoken_at_is_the_same_rule_as_the_worker_s_capture_key():
    """The docstring claims these agree. Nothing checked it, and they did not:
    the worker clamps an implausible stamp back to arrival time and this file
    did not. Drives both over the same rows so the claim stays true when
    either side moves."""
    from brain.worker import capture_key  # the original, not a copy of it

    cases = [
        {"capture_started_at": "2026-08-24 10:00:00.000Z",
         "created": "2026-08-24 10:00:02.000Z"},                  # normal
        {"spoken_at": "2026-08-24 10:00:00.000Z",
         "created": "2026-08-24 10:00:02.000Z"},                  # legacy column
        {"created": "2026-08-24 10:00:02.000Z"},                  # no stamp at all
        {"capture_started_at": "2026-01-01 09:00:00.000Z",
         "created": "2026-08-24 10:00:00.000Z"},                  # clock reset back
        {"capture_started_at": "2027-01-01 09:00:00.000Z",
         "created": "2026-08-24 10:00:00.000Z"},                  # clock reset forward
        {"capture_started_at": "2026-08-24 04:00:00.000Z",
         "created": "2026-08-24 10:00:00.000Z"},                  # 6h: right on the edge
        {"capture_started_at": "2026-08-24 03:59:00.000Z",
         "created": "2026-08-24 10:00:00.000Z"},                  # 6h01m: over it
    ]
    for row in cases:
        mine = spoken_at(row)
        assert mine is not None, row
        assert mine.timestamp() == capture_key(row), row


def test_a_row_with_no_usable_stamp_at_all_is_not_dragged_to_1970():
    # capture_key returns 0.0 when nothing parses, and 0.0 is a real instant:
    # feeding it to the gap would report 56 years of silence. Here it is None,
    # and report() skips the pair rather than inventing a gap.
    assert spoken_at({"id": "r1"}) is None
    rows = [{"id": "r1", "kind": "transcript", "text": "no stamp anywhere"},
            line(2, "stamped", at="2026-08-24 10:00:30.000Z")]
    assert report(rows)["longest_gap_seconds"] == 0


# --- finding 3: a cycle may not eat rows -----------------------------------

def test_a_cycle_reports_its_rows_instead_of_losing_them():
    """The old check was `assert len(stitch([a, b])) >= 0`, which is true of
    every list ever made. What it hid, measured: two rows in, `chains == []`,
    `thoughts == 0`, `shard_rate == 0.0` — a perfect day reported from total
    row loss, which is this file's own named sin."""
    a, b = line(1, "one", parent="r2"), line(2, "two", parent="r1")
    chains = stitch([a, b])
    assert sum(len(c) for c in chains) == 2, "a cycle may not swallow its rows"
    d = report([a, b])
    assert d["lines"] == 2 and d["thoughts"] >= 1
    assert d["shard_rate"] == 1.0, "two one-word rows are not a perfect day"


def test_a_long_thought_is_not_truncated_at_two_hundred_rows():
    """The old `guard < 200` could not fire on a cycle (a cycle has no head, so
    the loop was never entered); the only thing it ever did was silently cut a
    legitimate chain. Measured: 259 rows in, 201 out, 58 gone."""
    rows = ([line(1, "head")]
            + [line(i, f"w{i}", parent=f"r{i-1}") for i in range(2, 260)])
    chains = stitch(rows)
    assert len(chains) == 1 and len(chains[0]) == 259
    assert report(rows)["thoughts"] == 1


def test_stitching_terminates_on_a_cycle_within_the_rows_it_was_given():
    # The report is what you reach for when something is already wrong, so it
    # may not be the second thing that breaks. The bound is that no row is
    # visited twice, so the walk cannot outrun the rows it was handed.
    rows = [line(i, f"w{i}", parent=f"r{(i % 50) + 1}") for i in range(1, 51)]
    chains = stitch(rows)
    assert sum(len(c) for c in chains) == 50


# --- findings 4, 5, 6: what main() reads, and what it admits to ------------

class _FakePB:
    """Stands in for PocketBase. Records every params dict it was handed, so a
    test can see how much of the day the report actually asked for."""

    def __init__(self, rows, per_page_cap=500, report_total=True):
        self.rows, self.calls = rows, []
        self.per_page_cap, self.report_total = per_page_cap, report_total

    def get(self, url, headers=None, params=None, timeout=None):
        self.calls.append(dict(params or {}))
        per = min(int(params.get("perPage", 30)), self.per_page_cap)
        page = int(params.get("page", 1))
        ordered = self.rows if params.get("sort") == "created" else self.rows[::-1]
        window = ordered[(page - 1) * per:(page - 1) * per + per]
        body = {"items": window, "page": page, "perPage": per}
        if self.report_total:
            body["totalItems"] = len(self.rows)
            body["totalPages"] = max(1, -(-len(self.rows) // per))
        return _FakeResponse(body)


class _FakeResponse:
    def __init__(self, body): self.body = body
    def raise_for_status(self): pass
    def json(self): return self.body


def _run_main(monkeypatch, fake, argv=()):
    import proof.capture_day as cd
    monkeypatch.setattr(cd.requests, "get", fake.get)
    monkeypatch.setattr(sys, "argv", ["capture_day.py", *argv])
    code = cd.main()
    return code


def _day_rows(n, owner="ownerA", start=0):
    out = []
    for i in range(start, start + n):
        out.append({"id": f"r{i}", "kind": "transcript", "text": "one two three four five",
                    "parent_line": "", "speaker": "", "source": "phone_mic",
                    "owner_ref": owner,
                    "capture_started_at": "2026-08-24 %02d:%02d:00.000Z" % (i // 60, i % 60),
                    "created": "2026-08-24 %02d:%02d:00.000Z" % (i // 60, i % 60)})
    return out


def test_the_report_reads_the_whole_day_not_the_newest_page(monkeypatch, capsys):
    """Measured before pagination: 1300 transcript rows on the server, one HTTP
    call, `lines that arrived  500` printed under the banner WHAT THE EARS
    DELIVERED, exit 0, and not a word about the 800 it never read. This file
    exists to replace a belief with a measurement; measuring an undisclosed
    subset is the one failure it may not have."""
    fake = _FakePB(_day_rows(1300))
    assert _run_main(monkeypatch, fake) == 0
    out = capsys.readouterr().out
    assert len(fake.calls) > 1, "one call cannot read 1300 rows 500 at a time"
    day = json.loads(out.strip().splitlines()[-1])
    assert day["lines"] == 1300
    assert day["rows_unread"] == 0


def test_a_day_it_could_not_finish_reading_says_so_loudly(monkeypatch, capsys):
    # If it ever cannot read the whole window, silence is the defect. The count
    # goes in the printed table AND in the JSON line, because the JSON line is
    # what a gate greps.
    fake = _FakePB(_day_rows(2000))
    import proof.capture_day as cd
    monkeypatch.setattr(cd, "MAX_PAGES", 2)          # stop after 1000 rows
    assert _run_main(monkeypatch, fake) == 0
    out = capsys.readouterr().out
    day = json.loads(out.strip().splitlines()[-1])
    assert day["lines"] == 1000
    assert day["rows_unread"] == 1000
    assert "1000" in out and "DID NOT READ" in out.upper()


def test_a_multi_owner_run_says_that_it_blended_them(monkeypatch, capsys):
    """--owner defaults to every owner, and a blended timeline cannot show a
    dead day: owner B's one afternoon line fills owner A's twelve-hour silence
    and the blended longest gap reports 21600s instead of A's real 43200s."""
    rows = (_day_rows(1, owner="ownerA", start=540)      # A at 09:00
            + _day_rows(1, owner="ownerB", start=900)    # B at 15:00
            + _day_rows(1, owner="ownerA", start=1260))  # A at 21:00
    fake = _FakePB(rows)
    assert _run_main(monkeypatch, fake) == 0
    out = capsys.readouterr().out
    day = json.loads(out.strip().splitlines()[-1])
    assert day["owners"] == ["ownerA", "ownerB"]
    assert day["longest_gap_seconds"] == 21600, "the blend, still reported"
    assert day["per_owner"]["ownerA"]["longest_gap_seconds"] == 43200, \
        "A's real dead half-day, which the blend hides"
    assert "ownerA" in out and "ownerB" in out
    assert "BLEND" in out.upper()


def test_a_single_owner_run_names_the_owner_and_does_not_claim_a_blend(monkeypatch, capsys):
    fake = _FakePB(_day_rows(3, owner="ownerA"))
    assert _run_main(monkeypatch, fake, argv=["--owner", "ownerA"]) == 0
    out = capsys.readouterr().out
    day = json.loads(out.strip().splitlines()[-1])
    assert day["owners"] == ["ownerA"]
    assert "per_owner" not in day
    assert "BLEND" not in out.upper()
    assert 'owner_ref="ownerA"' in fake.calls[0]["filter"]


def test_a_day_that_could_not_be_read_is_never_a_pass(monkeypatch, capsys):
    """The module docstring said "With no floor it always exits 0 — a
    measurement is not a gate". It does not, and it must not: a read that threw
    is not a day with no words in it, and exiting 0 there is the silent failure
    this file exists to make impossible."""
    import proof.capture_day as cd

    def refused(*a, **k):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(cd.requests, "get", refused)
    monkeypatch.setattr(sys, "argv", ["capture_day.py"])   # no --min-words
    assert cd.main() == 1
    assert "could not read the day" in capsys.readouterr().out


def test_a_day_that_was_read_exits_zero_when_no_floor_was_asked_for(monkeypatch, capsys):
    # The other half of the contract the docstring now states: with no floor,
    # a day that was READ is never a failure however thin it is.
    fake = _FakePB([])
    assert _run_main(monkeypatch, fake) == 0
    assert "NOTHING ARRIVED" in capsys.readouterr().out


def test_a_floor_that_was_missed_fails(monkeypatch, capsys):
    fake = _FakePB(_day_rows(2))          # 10 words
    assert _run_main(monkeypatch, fake, argv=["--min-words", "100"]) == 1
    assert "under the floor" in capsys.readouterr().out


def test_an_unknown_shortfall_is_reported_as_unknown_not_as_zero(monkeypatch, capsys):
    # A server that sends no totalItems and a read that stopped at the page cap
    # means we do not know what we missed. Printing "0 unread" there would be a
    # guess, and it would be a guess in the flattering direction.
    fake = _FakePB(_day_rows(2000), report_total=False)
    import proof.capture_day as cd
    monkeypatch.setattr(cd, "MAX_PAGES", 2)
    assert _run_main(monkeypatch, fake) == 0
    out = capsys.readouterr().out
    assert json.loads(out.strip().splitlines()[-1])["rows_unread"] is None
    assert "UNKNOWN" in out


def test_a_stitcher_that_loses_rows_is_shouted_about_not_averaged_over(monkeypatch, capsys):
    """The guard on the invariant itself. If stitch() ever starts dropping rows
    again, the rates go on being printed — they just get quietly nicer. This
    makes that a visible disagreement in the output instead."""
    import proof.capture_day as cd
    monkeypatch.setattr(cd, "stitch", lambda rows: [[r] for r in rows[:-1]])
    fake = _FakePB(_day_rows(3))
    assert _run_main(monkeypatch, fake) == 0
    out = capsys.readouterr().out
    assert "STITCHING LOST ROWS" in out
    day = json.loads(out.strip().splitlines()[-1])
    assert day["lines"] == 3 and day["rows_stitched"] == 2
