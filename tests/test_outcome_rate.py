"""The outcome rate has to be able to give a wrong answer, and be caught.

A measuring stick nobody has ever seen fail is indistinguishable from a
constant. These drive proof/outcome_rate.py's pure half with synthetic rows —
no network, no clock — and the case that matters most is the one the whole
report exists for: a line that was CORRECTLY IGNORED and a line that was
SILENCED BY A GUARD look the same from the outside, so the report may never
quietly file the second as the first.

The other half of that discipline is the invariant. Every line lands in
exactly one bucket and the buckets sum to `lines`; a line that falls out of
the fold leaves the denominator as well as its bucket, and the direction it
moves the rate is whichever way that line happened to point.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain.anticipy_core import shard_too_thin  # noqa: E402
from proof.outcome_rate import (  # noqa: E402
    OUTCOME_BUCKETS,
    SILENCE_BUCKETS,
    classify,
    echo_positions,
    job_event_ids,
    report,
)


def line(i, text="one two three four five six", decision="ignore", goal="",
         addressee="person", at=None, owner="ownerA", parent=None):
    """A transcript row in the shape production actually stores."""
    return {
        "id": f"r{i}", "kind": "transcript", "text": text,
        "decision": decision, "goal": goal, "addressee": addressee,
        "owner_ref": owner, "parent_line": parent or "", "source": "phone_mic",
        "speaker": "", "explicit": False,
        "capture_started_at": at or f"2026-08-24 10:{i:02d}:00.000Z",
        "created": at or f"2026-08-24 10:{i:02d}:00.000Z",
    }


def says(i, text, goal="", at="2026-08-24 10:00:00.000Z", owner="ownerA",
         kind="anticipy_says"):
    return {"id": f"s{i}", "kind": kind, "text": text, "goal": goal,
            "decision": "act", "owner_ref": owner, "created": at}


def job(i, event_ids=(), top_level=None, owner="ownerA"):
    """A job row. The link back to the line lives INSIDE the _workflow blob,
    which is a JSON string inside the params JSON string."""
    params = {"source": "spoken", "now": "..."}
    if event_ids is not None:
        params["_workflow"] = json.dumps({
            "plan_id": f"p{i}", "goal": "a goal", "state": "queued",
            "source_event_ids": list(event_ids),
        })
    if top_level:
        params.update(top_level)
    return {"id": f"j{i}", "goal": "a goal", "status": "queued",
            "owner_ref": owner, "params": json.dumps(params),
            "created": "2026-08-24 10:30:00.000Z"}


# --- the headline ----------------------------------------------------------

def test_an_empty_window_is_a_finding_not_a_crash():
    # Nothing arriving is exactly what a suspended app and a dead worker both
    # look like from the server. It has to be reportable.
    d = report([], [])
    assert d["lines"] == 0
    assert d["outcomes"] == 0


def test_a_deaf_window_never_reports_a_perfect_rate():
    """THE failure this file exists to prevent. Zero lines divided by zero
    lines must not come out as 1.0, and it must not come out as a number at
    all: there is no rate of a day that held nothing. `is_the_brain_live.py`
    reads only anticipy_says rows and exits 0 on a totally deaf day; a report
    that answered "100%" here would be worse than that, not better."""
    d = report([], [])
    assert d["outcome_rate"] is None, "no lines means no rate, not a perfect one"
    assert d["heard_nothing"] is True


def test_a_line_that_acted_is_an_outcome():
    rows = [line(1, decision="act", goal="book a table")]
    d = report(rows, [])
    assert d["outcomes"] == 1 and d["outcome_rate"] == 1.0
    assert d["buckets"]["acted"] == 1


def test_a_question_she_actually_asked_is_an_outcome():
    """decision="ask" survives onto the row only when she really said
    something: stamp_for() rewrites an ask that asked nothing into "ignore",
    because the app renders any "ask" as the header "Quick question for you"
    and he got that header with no question under it. So an "ask" in the
    record is a question he was genuinely handed, and it is an outcome."""
    rows = [line(1, decision="ask", goal="which night works")]
    d = report(rows, [])
    assert d["buckets"]["asked"] == 1
    assert d["outcomes"] == 1


def test_an_ask_that_kept_its_row_but_lost_its_goal_still_counts():
    # The goal is stamped separately from the decision, and the ask valve
    # returns goal="". An outcome must not depend on both being present.
    d = report([line(1, decision="ask", goal="")], [])
    assert d["buckets"]["asked"] == 1 and d["outcomes"] == 1


def test_a_quiet_goal_is_an_outcome_even_though_the_decision_says_ignore():
    """ignore + a goal is the feed's "Looking into it — I'll text you what I
    find" card, which the iOS app renders. Omar watched her research Paris
    flights behind a "Noted — nothing needed" label and concluded she did
    nothing; the goal is what says otherwise, and it is a real outcome."""
    rows = [line(1, decision="ignore", goal="find flights to paris")]
    d = report(rows, [])
    assert d["buckets"]["quiet_work"] == 1
    assert d["outcomes"] == 1


def test_a_silent_ignore_is_not_an_outcome():
    rows = [line(1, decision="ignore", goal="")]
    d = report(rows, [])
    assert d["outcomes"] == 0 and d["outcome_rate"] == 0.0
    assert d["buckets"]["unexplained_silence"] == 1


def test_the_rate_is_outcomes_over_every_line_that_arrived():
    rows = ([line(i, decision="act", goal="g") for i in range(1, 3)]
            + [line(i) for i in range(3, 11)])
    d = report(rows, [])
    assert d["lines"] == 10 and d["outcomes"] == 2
    assert d["outcome_rate"] == 0.2


# --- the invariant ---------------------------------------------------------

def test_every_line_lands_in_exactly_one_bucket():
    """The invariant behind every number this file prints. A line that
    vanishes from the buckets leaves the DENOMINATOR too, so losing one moves
    the rate in whichever direction that line happened to point — and the
    flattering direction is the one nobody goes looking for. Several shapes,
    because a bug that drops lines rarely drops all of them."""
    shapes = {
        "all silent": [line(i) for i in range(1, 4)],
        "all acted": [line(i, decision="act", goal="g") for i in range(1, 4)],
        "mixed": [line(1, decision="act", goal="g"), line(2),
                  line(3, decision="ignore", goal="quiet"), line(4, decision="")],
        "never processed": [line(i, decision="") for i in range(1, 4)],
        "in flight": [line(i, decision="processing") for i in range(1, 4)],
        "a stamp nobody planned for": [line(1, decision="refused_read_fact_ceiling"),
                                       line(2, decision="ignored_nonowner"),
                                       line(3, decision="something_new_in_2027")],
        "no decision field at all": [{"kind": "transcript", "text": "hi there",
                                      "id": "r9", "owner_ref": "ownerA"}],
        "empty text": [line(1, text=""), line(2, text="   ")],
        "no id": [{"kind": "transcript", "text": "who am i", "owner_ref": "ownerA"}],
        "two owners": [line(1, owner="ownerA"), line(2, owner="ownerB")],
    }
    for name, rows in shapes.items():
        d = report(rows, [])
        assert d["lines"] == len(rows), f"{name}: the denominator moved"
        assert d["rows_bucketed"] == len(rows), f"{name}: lines left the fold"
        assert sum(d["buckets"].values()) == len(rows), f"{name}: buckets do not sum"


def test_the_bucket_names_are_partitioned_into_outcomes_and_silences():
    # Every bucket is exactly one of the two, so `outcomes` cannot silently
    # start counting a silence (or stop counting an outcome) without a name
    # moving between these two tuples in the source.
    assert set(OUTCOME_BUCKETS) & set(SILENCE_BUCKETS) == set()
    rows = [line(1, decision="act", goal="g"), line(2)]
    d = report(rows, [])
    assert set(d["buckets"]) == set(OUTCOME_BUCKETS) | set(SILENCE_BUCKETS)


def test_a_line_is_classified_once_and_outcomes_win_over_silences():
    # A four-word line that nevertheless produced a card is an OUTCOME. The
    # order of the tests inside classify() is load-bearing: reversed, every
    # short line that worked would be filed as a silence.
    assert classify(line(1, text="book us earls tomorrow",
                         decision="act", goal="book earls"),
                    job_ids=set(), echo=False) == "acted"


# --- the half that matters: which silences can be told apart ---------------

def test_a_line_never_processed_is_not_the_same_as_a_line_ignored():
    """decision="" is the shape of a line the worker never reached — a dead
    worker, a poll that never ran, an owner nothing is polling for. Folding it
    into "ignored" would report a dead brain as a discerning one."""
    rows = [line(1, decision=""), line(2, decision="ignore")]
    d = report(rows, [])
    assert d["buckets"]["never_processed"] == 1
    assert d["buckets"]["unexplained_silence"] == 1


def test_a_line_still_in_flight_is_named_separately():
    """claim() stamps decision="processing" before any side effect. A row
    still carrying it is either in hand right now or was stranded by a restart
    — release_stranded_claims sweeps it back to "" after ten minutes. Either
    way it is not a decision, and it is not an ignore."""
    d = report([line(1, decision="processing")], [])
    assert d["buckets"]["in_flight"] == 1


def test_an_explicit_refusal_is_named_rather_than_filed_as_an_ignore():
    # worker.py stamps its own refusals: ignored_nonowner, error,
    # refused_read_fact_ceiling. Those are the brain SAYING why, which is the
    # thing the unexplained bucket does not have.
    rows = [line(1, decision="ignored_nonowner"), line(2, decision="error"),
            line(3, decision="refused_read_fact_ceiling")]
    d = report(rows, [])
    assert d["buckets"]["refused"] == 3
    assert d["buckets"]["unexplained_silence"] == 0


def test_an_unknown_decision_stamp_is_a_refusal_not_a_silence():
    # A stamp this file has never heard of is the brain having said SOMETHING.
    # Filing it as unexplained would grow the one bucket that means "we do not
    # know", every time the brain learns a new word.
    d = report([line(1, decision="a_stamp_from_a_future_commit")], [])
    assert d["buckets"]["refused"] == 1


# --- the echo guard, recomputed rather than guessed ------------------------

def test_an_echo_of_her_own_words_is_named_not_left_unexplained():
    """is_echo_of_her is the ONE of the six named guards that leaves enough
    behind to be recomputed: it reads the same anticipy_says rows this report
    already holds. Six words shared in order, at 0.6 of his line."""
    her = says(1, "the august data is ready to add in the spreadsheet",
               at="2026-08-24 10:00:00.000Z")
    his = line(5, text="the august data is ready to add in the spreadsheet",
               at="2026-08-24 10:05:00.000Z")
    assert echo_positions([his], [her]) == {0}
    d = report([his, her], [])
    assert d["buckets"]["echo_of_her"] == 1
    assert d["buckets"]["unexplained_silence"] == 0


def test_a_line_too_short_to_be_a_recognisable_echo_is_not_one():
    # The guard's first gate: fewer than six words and it does not look.
    her = says(1, "i've booked the table at earls for seven",
               at="2026-08-24 10:00:00.000Z")
    his = line(5, text="earls works", at="2026-08-24 10:05:00.000Z")
    assert echo_positions([his], [her]) == set()


def test_a_long_line_that_merely_shares_a_topic_is_not_an_echo():
    """Six shared words IN ORDER at 0.6 of his line is the threshold
    worker.py measured on real pairs: genuine echoes scored 9 and 16, and
    every non-echo — a confirmation, a correction, the same topic in his own
    words — scored 1 to 5. This pair shares two.

    Long enough to clear the length gate on purpose: with a short line the
    guard returns before the threshold is ever consulted, so a loosened
    threshold survives unnoticed. Over-claiming echoes empties the unexplained
    bucket, which is the flattering direction and therefore the one that has
    to be pinned."""
    her = says(1, "i've booked the table at earls for seven o'clock tonight",
               at="2026-08-24 10:00:00.000Z")
    his = line(5, text="we should probably leave for the table around six",
               at="2026-08-24 10:05:00.000Z")
    assert echo_positions([his], [her]) == set()


def test_an_echo_more_than_thirty_minutes_old_is_not_an_echo():
    # The worker looks back exactly thirty minutes. Reading further back would
    # let any repeated phrase in a long day be explained away as an echo.
    her = says(1, "the august data is ready to add in the spreadsheet",
               at="2026-08-24 09:00:00.000Z")
    his = line(5, text="the august data is ready to add in the spreadsheet",
               at="2026-08-24 10:05:00.000Z")
    assert echo_positions([his], [her]) == set()


def test_something_she_said_after_he_spoke_cannot_be_what_he_echoed():
    # The worker passes `before=capture_key(ev)`: only what she had ALREADY
    # said can be read back. Without the upper bound, her brand-new reply
    # explains away the very line that caused it.
    her = says(1, "the august data is ready to add in the spreadsheet",
               at="2026-08-24 10:30:00.000Z")
    his = line(5, text="the august data is ready to add in the spreadsheet",
               at="2026-08-24 10:05:00.000Z")
    assert echo_positions([his], [her]) == set()


def test_another_owner_s_message_is_not_his_echo():
    # main() binds one worker to one owner and the echo read is scoped to it.
    # Unscoped, one account's texts would explain away another account's
    # silence — the same defect the blended longest gap has in capture_day.
    her = says(1, "the august data is ready to add in the spreadsheet",
               at="2026-08-24 10:00:00.000Z", owner="ownerB")
    his = line(5, text="the august data is ready to add in the spreadsheet",
               at="2026-08-24 10:05:00.000Z", owner="ownerA")
    assert echo_positions([his], [her]) == set()


def test_a_typed_message_counts_as_something_she_said():
    # The worker reads kind="anticipy_says" OR kind="anticipy_text".
    her = says(1, "the august data is ready to add in the spreadsheet",
               at="2026-08-24 10:00:00.000Z", kind="anticipy_text")
    his = line(5, text="the august data is ready to add in the spreadsheet",
               at="2026-08-24 10:05:00.000Z")
    assert echo_positions([his], [her]) == {0}


# --- the job join: an outcome the line's own row cannot show ---------------

def test_a_line_a_job_points_at_is_an_outcome_even_when_its_row_shows_nothing():
    """Measured in production: over 168h, two lines whose own rows carried
    decision=ignore and no goal were nevertheless named by a queued job's
    source_event_ids. Counting only the row would have called those silences."""
    rows = [line(1, decision="ignore", goal="")]
    d = report(rows, [job(1, event_ids=["r1"])])
    assert d["buckets"]["job_only"] == 1
    assert d["outcomes"] == 1


def test_the_job_link_is_read_from_the_workflow_blob_not_a_top_level_key():
    """The thing this report got wrong first. A substring search for
    "source_event_id" over the params string matched 63 of 65 production jobs
    and NOT ONE of them carries that key at the top level — it lives inside
    the _workflow blob, which is itself a JSON string inside the params JSON
    string. A grep would have reported a join that does not exist."""
    assert job_event_ids([job(1, event_ids=["r1", "r2"])]) == {"r1", "r2"}
    # A top-level key is honoured too when a caller does write one, because
    # anticipy_core writes params["source_event_ids"] on the stitched path.
    plain = {"id": "j2", "params": json.dumps(
        {"source_event_ids": ["r3"], "source_event_id": "r4"})}
    assert job_event_ids([plain]) == {"r3", "r4"}


def test_a_job_naming_no_line_cannot_credit_anything():
    # 12 of 65 production jobs name no source event at all. They must not be
    # allowed to invent an outcome for some arbitrary line.
    assert job_event_ids([job(1, event_ids=[])]) == set()
    d = report([line(1)], [job(1, event_ids=[])])
    assert d["outcomes"] == 0


def test_a_blank_source_event_id_does_not_enter_the_id_set():
    """A job carrying source_event_id="" must contribute nothing. An empty
    string in the set is a key that matches any row whose own id is blank, and
    an id is a thing the server gave us — not a thing we may rely on being
    present."""
    blank = {"id": "j1", "params": json.dumps(
        {"source_event_id": "", "source_event_ids": ["", "   "],
         "_workflow": json.dumps({"source_event_ids": [""]})})}
    assert job_event_ids([blank]) == set()


def test_unreadable_job_params_do_not_take_the_report_down():
    # The report is what you reach for when something is already wrong, so it
    # may not be the second thing that breaks.
    broken = [{"id": "j1", "params": "{not json"}, {"id": "j2"},
              {"id": "j3", "params": json.dumps({"_workflow": "{not json"})},
              {"id": "j4", "params": json.dumps({"_workflow": ["wrong type"]})}]
    assert job_event_ids(broken) == set()


def test_a_job_pointing_at_a_line_that_already_worked_does_not_double_count():
    rows = [line(1, decision="act", goal="g")]
    d = report(rows, [job(1, event_ids=["r1"])])
    assert d["outcomes"] == 1
    assert d["buckets"]["acted"] == 1 and d["buckets"]["job_only"] == 0


# --- the bucket that cannot be split, and its honest bounds ----------------

def test_the_shard_bound_is_an_upper_bound_and_says_so():
    """shard_too_thin fires on a line of four words or fewer WHOSE GOAL the
    model invented — and neither the goal it would have had nor the reason it
    was dropped is stored anywhere. Four words is a NECESSARY condition, not a
    sufficient one, so this may only ever be reported as a ceiling."""
    rows = [line(1, text="at 5:15"), line(2, text="yeah"),
            line(3, text="a much longer line than that one over there")]
    d = report(rows, [])
    assert d["unexplained"]["at_most_shard_too_thin"] == 2
    assert d["unexplained"]["total"] == 3


def test_the_shard_bound_agrees_with_the_real_guard_about_length():
    """could_be_a_shard's docstring claims it uses the guard's own word count.
    Nothing checked that, and the two tokenizers genuinely differ: capture_day
    counts "at 5:15" as two words by split(), shard_too_thin counts three by
    [\\w']+. Drives both over the same lines with a goal the model plainly
    invented — the one shape that makes the real guard fire — so the claim
    stays true when either side moves."""
    from brain.orchestrator import Decision

    from proof.outcome_rate import could_be_a_shard

    invented = Decision(decision="act",
                        goal="schedule meeting monday august pricing quarterly",
                        reason="", continues=0)
    lines = ["at 5:15", "yeah", "5:15", "ok sure thing", "one two three four",
             "one two three four five",
             "i was thinking we should move the meeting to thursday",
             "", "   "]
    for text in lines:
        fires = shard_too_thin(text, invented, False, None)
        if fires:
            assert could_be_a_shard(text), \
                f"{text!r}: the guard fired and the bound did not allow it"
    # And the bound is genuinely only a CEILING: a line short enough for the
    # guard, whose goal says nothing the line did not, is not silenced by it.
    honest = Decision(decision="act", goal="book us earls tomorrow",
                      reason="", continues=0)
    assert could_be_a_shard("book us earls tomorrow")
    assert not shard_too_thin("book us earls tomorrow", honest, False, None)


def test_the_unexplained_bucket_is_broken_down_by_addressee():
    """addressee IS stored, and it is the only thing inside the unexplained
    bucket that the brain actually wrote down. "person" is the lane that is
    SUPPOSED to be silent; an empty addressee means triage never classified
    the line at all, which is a different animal."""
    rows = [line(1, addressee="person"), line(2, addressee="self"),
            line(3, addressee=""), line(4, addressee="")]
    d = report(rows, [])
    assert d["unexplained"]["by_addressee"] == {"person": 1, "self": 1,
                                                "unclassified": 2}


def test_the_report_states_the_silences_it_cannot_tell_apart():
    # capture_day prints its own blind spot; so does this. The list is data,
    # not prose, so a gate can assert on it and a future fix can shorten it.
    d = report([line(1)], [])
    blind = d["cannot_distinguish"]
    assert isinstance(blind, list) and blind
    joined = " ".join(blind).lower()
    for guard in ("shard_too_thin", "parked", "already_", "llm"):
        assert guard in joined, f"{guard} is not named in the blind spot"


def test_the_blind_spot_is_stated_once_and_not_repeated_per_owner():
    """The JSON line is what a gate greps. Repeating the paragraph inside
    every per-owner sub-report made it six times longer than the numbers in
    it, which is how a machine-readable line stops being read."""
    rows = [line(1, owner="ownerA"), line(2, owner="ownerB")]
    d = report(rows, [])
    assert d["cannot_distinguish"]
    for name, sub in d["per_owner"].items():
        assert "cannot_distinguish" not in sub, name


def test_the_blind_spot_is_stated_even_when_nothing_is_unexplained():
    # A clean window does not mean the instrument got sharper. The limits are
    # a property of what brain/ records, not of today's numbers.
    d = report([line(1, decision="act", goal="g")], [])
    assert d["cannot_distinguish"]


# --- what belongs to the denominator, and what does not --------------------

def test_anticipy_says_rows_are_not_counted_as_lines_that_arrived():
    # Her own voice is not something she heard. Counting it would let a chatty
    # day flatter its own outcome rate — the exact shape of the existing
    # liveness checker's blind spot, imported into its replacement.
    rows = [line(1), says(1, "something she said")]
    d = report(rows, [])
    assert d["lines"] == 1


def test_her_side_is_counted_separately_so_a_deaf_talkative_day_is_visible():
    """The finding this report was built for: in the 24h to 2026-08-25
    production held ZERO transcript lines and three anticipy_says rows. A
    report that only counted lines would print an empty table; one that only
    counted her would print a healthy one."""
    rows = [says(1, "a"), says(2, "b"), says(3, "c")]
    d = report(rows, [])
    assert d["lines"] == 0 and d["she_spoke"] == 3
    assert d["heard_nothing"] is True


def test_a_blank_line_is_still_a_line_that_arrived():
    # worker.py marks an empty transcript "ignore" without triaging it. It
    # arrived, it produced nothing, and dropping it would shrink the
    # denominator by exactly the lines most likely to have produced nothing.
    d = report([line(1, text="")], [])
    assert d["lines"] == 1 and d["outcomes"] == 0


# --- one owner's silence may not be filled by another's day ----------------

def test_the_rate_is_reported_per_owner_as_well_as_blended():
    """Measured in production over 168h: the blend read 9.0% while one owner
    sat at 4.5% and another at 42.9%. The blend is the headline and it cannot
    show a dead account."""
    rows = ([line(i, owner="ownerA") for i in range(1, 10)]
            + [line(20, decision="act", goal="g", owner="ownerB")])
    d = report(rows, [])
    assert d["outcome_rate"] == 0.1
    assert d["per_owner"]["ownerA"]["outcome_rate"] == 0.0
    assert d["per_owner"]["ownerB"]["outcome_rate"] == 1.0


def test_a_single_owner_window_does_not_claim_a_blend():
    d = report([line(1)], [])
    assert "per_owner" not in d


def test_an_owner_who_said_nothing_but_was_spoken_to_is_still_named():
    """The 24h production window: her three messages went to an owner with no
    transcript lines at all. An owner-blind report cannot see that, and a
    report keyed only on lines would drop the owner entirely."""
    rows = [line(1, owner="ownerA"), says(1, "hello", owner="ownerB")]
    d = report(rows, [])
    assert "ownerB" in d["spoke_to"]
    assert d["spoke_to"]["ownerB"] == 1


# --- main(): what it reads, and what it admits to -------------------------

class _FakePB:
    """Stands in for PocketBase across two collections. Records every params
    dict it was handed, so a test can see how much the report asked for."""

    def __init__(self, events, jobs=(), per_page_cap=500, report_total=True,
                 jobs_status=200):
        self.events, self.jobs = list(events), list(jobs)
        self.calls, self.per_page_cap = [], per_page_cap
        self.report_total, self.jobs_status = report_total, jobs_status

    def get(self, url, headers=None, params=None, timeout=None):
        self.calls.append({"url": url, **(params or {})})
        rows = self.jobs if "/jobs/" in url else self.events
        if "/jobs/" in url and self.jobs_status != 200:
            return _FakeResponse({}, status=self.jobs_status)
        per = min(int(params.get("perPage", 30)), self.per_page_cap)
        page = int(params.get("page", 1))
        window = rows[(page - 1) * per:(page - 1) * per + per]
        body = {"items": window, "page": page, "perPage": per}
        if self.report_total:
            body["totalItems"] = len(rows)
        return _FakeResponse(body)


class _FakeResponse:
    def __init__(self, body, status=200):
        self.body, self.status_code, self.ok = body, status, status == 200

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self.body


def _run_main(monkeypatch, fake, argv=()):
    import proof.outcome_rate as orate
    monkeypatch.setattr(orate.requests, "get", fake.get)
    monkeypatch.setattr(sys, "argv", ["outcome_rate.py", *argv])
    return orate.main()


def _last_json(out):
    return json.loads(out.strip().splitlines()[-1])


def test_the_report_reads_the_whole_window_not_the_newest_page(monkeypatch, capsys):
    """A single perPage=500 read would measure a 1300-line window as 500 and
    say nothing about the 800 it never saw — and a truncated window shifts the
    rate as well as the count, because the lines it drops are not a random
    sample of anything."""
    fake = _FakePB([line(i) for i in range(1, 1301)])
    assert _run_main(monkeypatch, fake) == 0
    out = capsys.readouterr().out
    assert len([c for c in fake.calls if "/events/" in c["url"]]) > 1
    day = _last_json(out)
    assert day["lines"] == 1300 and day["rows_unread"] == 0


def test_a_window_it_could_not_finish_reading_says_so_loudly(monkeypatch, capsys):
    fake = _FakePB([line(i) for i in range(1, 2001)])
    import proof.outcome_rate as orate
    monkeypatch.setattr(orate, "MAX_PAGES", 2)
    assert _run_main(monkeypatch, fake) == 0
    out = capsys.readouterr().out
    day = _last_json(out)
    assert day["lines"] == 1000 and day["rows_unread"] == 1000
    assert "DID NOT READ" in out.upper()


def test_an_unknown_shortfall_is_reported_as_unknown_not_as_zero(monkeypatch, capsys):
    fake = _FakePB([line(i) for i in range(1, 2001)], report_total=False)
    import proof.outcome_rate as orate
    monkeypatch.setattr(orate, "MAX_PAGES", 2)
    assert _run_main(monkeypatch, fake) == 0
    out = capsys.readouterr().out
    assert _last_json(out)["rows_unread"] is None
    assert "UNKNOWN" in out.upper()


def test_a_window_that_could_not_be_read_is_never_a_pass(monkeypatch, capsys):
    """A reader that fails silently would report a perfect day, which is the
    one wrong answer a measuring stick must never give."""
    import proof.outcome_rate as orate

    def refused(*a, **k):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(orate.requests, "get", refused)
    monkeypatch.setattr(sys, "argv", ["outcome_rate.py"])
    assert orate.main() == 1
    assert "could not read" in capsys.readouterr().out


def test_jobs_that_could_not_be_read_are_admitted_not_silently_skipped(monkeypatch, capsys):
    """Jobs are the only evidence of an outcome the line's own row cannot
    show. Reading zero of them because of a 403 and reporting the rate anyway
    would understate it — quietly, and in the alarming direction, which is the
    one that gets believed."""
    fake = _FakePB([line(1)], jobs=[job(1, event_ids=["r1"])], jobs_status=403)
    assert _run_main(monkeypatch, fake) == 0
    out = capsys.readouterr().out
    assert "COULD NOT READ THE JOBS" in out.upper()
    assert _last_json(out)["jobs_read"] is None


def test_a_deaf_window_is_shouted_about(monkeypatch, capsys):
    """The gap this file was built to close: is_the_brain_live.py exits 0 on a
    totally deaf day because every rule it has is an over-speaking rule. A
    window with no lines is the headline here, not an empty table."""
    fake = _FakePB([says(1, "she talked anyway")])
    assert _run_main(monkeypatch, fake) == 0
    out = capsys.readouterr().out
    assert "NOTHING WAS HEARD" in out.upper()
    day = _last_json(out)
    assert day["heard_nothing"] is True and day["she_spoke"] == 1


def test_a_deaf_window_fails_when_a_floor_was_asked_for(monkeypatch, capsys):
    # A measurement is not a gate — but a gate has to be able to say "she must
    # not have been deaf", and that is what --min-lines is for.
    fake = _FakePB([])
    assert _run_main(monkeypatch, fake, argv=["--min-lines", "1"]) == 1
    assert "under the floor" in capsys.readouterr().out


def test_a_rate_floor_that_was_missed_fails(monkeypatch, capsys):
    fake = _FakePB([line(i) for i in range(1, 11)])
    assert _run_main(monkeypatch, fake, argv=["--min-rate", "0.25"]) == 1
    assert "under the floor" in capsys.readouterr().out


def test_a_rate_floor_cannot_be_met_by_a_window_that_heard_nothing(monkeypatch, capsys):
    """Zero of zero is not a rate. A floor check that treated it as one would
    pass the deaf day it was written to catch — which is the existing
    checker's bug, re-implemented inside its replacement."""
    fake = _FakePB([])
    assert _run_main(monkeypatch, fake, argv=["--min-rate", "0.25"]) == 1
    assert "under the floor" in capsys.readouterr().out


def test_a_window_that_was_read_exits_zero_when_no_floor_was_asked_for(monkeypatch, capsys):
    fake = _FakePB([line(i) for i in range(1, 11)])
    assert _run_main(monkeypatch, fake) == 0


def test_a_single_owner_run_scopes_every_read_to_that_owner(monkeypatch, capsys):
    fake = _FakePB([line(1, owner="ownerA")])
    assert _run_main(monkeypatch, fake, argv=["--owner", "ownerA"]) == 0
    for call in fake.calls:
        assert 'owner_ref="ownerA"' in call["filter"], call


def test_a_multi_owner_run_says_that_it_blended_them(monkeypatch, capsys):
    rows = ([line(i, owner="ownerA") for i in range(1, 10)]
            + [line(20, decision="act", goal="g", owner="ownerB")])
    fake = _FakePB(rows)
    assert _run_main(monkeypatch, fake) == 0
    out = capsys.readouterr().out
    assert "BLEND" in out.upper()
    day = _last_json(out)
    assert day["per_owner"]["ownerA"]["outcome_rate"] == 0.0


def test_a_bucketer_that_loses_lines_is_shouted_about_not_averaged_over(monkeypatch, capsys):
    """The guard on the invariant itself. If classify() ever starts dropping
    lines, every rate goes on being printed — they just get quietly different.
    This makes that a visible disagreement in the output instead."""
    import proof.outcome_rate as orate
    monkeypatch.setattr(orate, "classify",
                        lambda row, job_ids, echo: None if row["id"] == "r2"
                        else "unexplained_silence")
    fake = _FakePB([line(1), line(2), line(3)])
    assert _run_main(monkeypatch, fake) == 0
    out = capsys.readouterr().out
    assert "LOST LINES" in out.upper()
    day = _last_json(out)
    assert day["lines"] == 3 and day["rows_bucketed"] == 2


def test_the_printed_rate_and_the_json_rate_are_the_same_number(monkeypatch, capsys):
    # A gate greps the JSON line; a person reads the table. They have
    # disagreed before in this repo, and the person is the one who stops
    # looking.
    fake = _FakePB([line(i) for i in range(1, 5)]
                   + [line(9, decision="act", goal="g")])
    assert _run_main(monkeypatch, fake) == 0
    out = capsys.readouterr().out
    assert _last_json(out)["outcome_rate"] == 0.2
    assert "20%" in out
