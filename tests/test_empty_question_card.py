"""A card must never promise a question that was never asked.

2026-08-07, live. He planned dinner out loud with another person. The pendant
hears one side, so it read as thinking aloud, and the self-talk rule held the
question back. Holding it is CORRECT — loosening that rule the same afternoon
produced four texts for one dinner and six for the Earls plan, and was
reverted.

But the transcript row was still stamped decision="ask", and the feed renders
any "ask" as the header "Quick question for you". He got that header with
nothing under it and no text:

    self-talk question stays unasked: 'what time at earls tomorrow, and which location?'
    heard: '...we should grab Earls tomorrow but' -> ask (Book dinner at Earls for tomorrow)

The silence was right. The card was the lie.

The fix uses the stamp that already exists for this. decision="ignore" carrying
a goal has meant "quiet work" since the Paris-flights incident, and the app has
rendered it as "Looking into it" ever since — so this needs no app update and
is correct on the build already on his phone.

    ask + a question   -> "ask"      "Quick question for you" + the question
    ask + no question  -> "ignore"   "Looking into it" (goal) / "Noted" (none)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKER = open(os.path.join(ROOT, "brain", "worker.py")).read()


from brain.worker import stamp_for  # noqa: E402


# --------------------------------------------------- the rule, executed

def test_an_ask_that_asked_nothing_files_as_quiet_work():
    """THE LIVE FAILURE. He got 'Quick question for you' and no question."""
    assert stamp_for("ask", None) == "ignore"
    assert stamp_for("ask", "") == "ignore"
    assert stamp_for("ask", "   ") == "ignore"
    assert stamp_for("ask", "\n\t ") == "ignore"


def test_a_real_question_is_still_a_question():
    """The opposite mistake would be worse: every genuine question would stop
    rendering as one."""
    assert stamp_for("ask", "what time at Earls tomorrow?") == "ask"
    assert stamp_for("ask", "  which location?  ") == "ask"


def test_no_other_decision_is_ever_touched():
    for d in ("act", "ignore", "answer", "clock", "", "needs_user", "stalled"):
        for said in (None, "", "something"):
            assert stamp_for(d, said) == d, (d, said)


def test_a_non_string_question_is_not_a_question():
    """anticipy_says is model-shaped. A number or a dict is not something he
    can read, and must never keep the 'ask' header alive."""
    for junk in (0, 1, 123, [], {}, ["hi"], True, object()):
        assert stamp_for("ask", junk) == "ignore", junk


def test_it_never_raises():
    for d in (None, "", "ask", 7):
        for said in (None, "", "x", 3, [], {}):
            try:
                stamp_for(d, said)
            except Exception as e:
                raise AssertionError(f"stamp_for({d!r}, {said!r}) raised {e}")


def test_the_worker_actually_routes_through_it():
    i = WORKER.index("decision = stamp_for(")
    j = WORKER.index('mark_processed(ev["id"], decision', i)
    assert j > i, "the stamp must be computed before the row is written"
    call = WORKER[i:j]
    assert 'out["decision"].decision' in call
    assert 'out.get("anticipy_says")' in call


def test_the_goal_still_rides_along():
    """decision=ignore ALONE renders 'Noted — nothing needed'. It is the goal
    beside it that makes the app say 'Looking into it'. Losing the goal here
    would turn a held plan into a line claiming nothing happened."""
    i = WORKER.index('mark_processed(ev["id"], decision')
    call = WORKER[i:i + 320]
    assert "goal=getattr(out[\"decision\"], \"goal\", \"\")" in call


def test_the_question_event_is_still_only_written_when_there_is_one():
    i = WORKER.index('if out.get("anticipy_says"):')
    block = WORKER[i:i + 200]
    assert 'post_event("anticipy_says"' in block


def test_nothing_server_side_reads_ask_off_a_transcript_row():
    """The safety argument for restamping. If something ever starts filtering
    transcripts on decision="ask", this change silently breaks it."""
    import glob
    offenders = []
    for path in glob.glob(os.path.join(ROOT, "brain", "*.py")):
        src = open(path).read()
        for needle in ('kind="transcript"', "kind='transcript'"):
            k = 0
            while True:
                k = src.find(needle, k)
                if k < 0:
                    break
                window = src[k:k + 400]
                if 'decision="ask"' in window:
                    offenders.append(os.path.basename(path))
                k += 1
    assert offenders == [], \
        f"these filter transcripts on the ask stamp: {sorted(set(offenders))}"


# ------------------------------------------------- the app end of the wire

APP = os.path.join(ROOT, "app/ios/Anticipy/Views")


def test_the_app_renders_the_three_stamps_this_relies_on():
    """Pins the contract on the phone's side. If any of these renderings goes
    away, the server-side fix stops being correct."""
    content = open(os.path.join(APP, "ContentView.swift")).read()
    i = content.index('switch line.decision')
    block = content[i:i + 2200]
    assert 'case "ask":' in block and "Quick question for you" in block
    assert 'case "ignore":' in block
    assert "Looking into it" in block, "the quiet-work rendering must exist"
    assert "Noted — nothing needed" in block
    # And "Looking into it" must be the branch guarded by a goal.
    j = block.index('case "ignore":')
    ig = block[j:j + 700]
    assert "goal?.isEmpty == false" in ig, \
        "quiet work is decision=ignore AND a goal — the goal is what tells them apart"


def test_the_group_header_follows_the_same_stamp():
    """HeardGroup picks the card's register from the same string, so a
    restamped row must also stop the whole conversation reading as 'asking'."""
    hg = open(os.path.join(APP, "HeardGroup.swift")).read()
    assert 'lines.contains(where: { $0.decision == "ask" }) { return .asking }' in hg
    assert 'lines.contains(where: { ($0.goal ?? "").isEmpty == false }) { return .looking }' in hg
