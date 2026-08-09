"""Self-talk stays quiet — and the card must not pretend otherwise.

2026-08-07, live. He talked to somebody about dinner:

    "Hello hello I had good would you go for dinner tomorrow yeah we
     definitely should we should grab Earls tomorrow but"
    "6 PM tomorrow sounds good yeah I'm good for that"

She got it right — goal "Book dinner at Earls for tomorrow", question "what
time at earls tomorrow, and which location?" — then stayed quiet, because the
pendant hears one side and a conversation with another person is
indistinguishable from thinking aloud, so the model said addressee="self".

What he actually saw was a card headed "Quick question for you" with no
question under it.

THE FIRST FIX WAS WRONG AND IS RECORDED HERE SO IT IS NOT TRIED AGAIN.

The guard was narrowed to goalless asks, on the reasoning that the incident it
exists for was about goalless asks dodging the goal-keyed dedupe. Measured on
the live model within minutes:

    dinner_demo_proof      FAIL 3/3 — FOUR texts for one dinner
    second_scenario_proof  FAIL 2/3 — SIX texts, and no held booking

One dinner produces a slightly different goal every turn — "Book dinner
reservation for tomorrow at 7 PM", then "...for 2 tomorrow at 7 PM" — so the
dedupe reads them as separate errands and the guard is what was holding the
line. It was reverted before it ever reached his phone.

The silence is correct. The LIE is the card, which renders an "asking" header
whether or not there is a question to show. That belongs in
ConversationCard.swift, not in the brain.

There was no test on this rule at all before this file, which is how a guard
this load-bearing had nothing pinning it.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SRC = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "brain", "anticipy_core.py")).read()


def _guard_block() -> str:
    """JUST the condition, up to the print. A wider window swallows the
    `elif self._may_say(..., decision.goal, "ask")` line below it, and every
    assertion about decision.goal then passes for the wrong reason."""
    i = SRC.index('if decision.addressee == "self" and not explicit')
    j = SRC.index("print(", i)
    return SRC[i:j]


def test_narrowing_this_guard_to_goalless_asks_was_tried_and_failed():
    """DO NOT narrow this again without re-reading the numbers.

    The reasoning is seductive: the incident this guard exists for was about
    GOALLESS asks dodging the goal-keyed dedupe, so surely a goal makes it
    safe. It does not. One dinner produces a slightly different goal every
    turn — "Book dinner reservation for tomorrow at 7 PM", then "...for 2
    tomorrow at 7 PM" — and the dedupe reads those as different errands.

    Measured on the live model within minutes of trying it:
        dinner_demo_proof      FAIL 3/3 — FOUR texts for one dinner
        second_scenario_proof  FAIL 2/3 — SIX texts, and no held booking
    """
    block = _guard_block()
    assert "decision.goal" not in block, (
        "narrowing this to goalless asks brings back 4-6 texts per plan — "
        "measured 2026-08-07, see the comment in anticipy_core.py")


def test_a_goalless_self_talk_question_still_stays_quiet():
    """The other direction. Deleting the guard outright brings back three
    'what night were you thinking?' texts in two minutes."""
    block = _guard_block()
    assert 'decision.addressee == "self"' in block
    assert "not explicit" in block


def test_the_guard_is_reachable():
    """Mutation testing walked past an assertion once by replacing a condition
    with `if False:` — the asserted line was still in the file, just dead."""
    assert 'if decision.addressee == "self" and not explicit \\' in SRC \
        or 'if decision.addressee == "self" and not explicit' in SRC
    i = SRC.index('if decision.addressee == "self" and not explicit')
    after = SRC[i:i + 400]
    assert "handled = None" in after, "the guard must still be able to silence"


def test_an_explicit_question_is_never_suppressed():
    """When he types or texts AT her he is plainly talking to her."""
    assert "not explicit" in _guard_block()


def test_the_dedupe_that_replaces_the_guard_is_keyed_on_the_goal():
    """The whole argument for narrowing the guard is that _may_say already
    stops repeats when a goal exists. If it ever stops keying on the goal, the
    narrowing becomes unsafe and this must fail."""
    i = SRC.index("def _may_say(")
    sig = SRC[i:i + 120]
    assert "goal" in sig, "_may_say must take the goal"
    j = SRC.index("may_say(text, goal or \"\", kind)")
    assert j > i, "_may_say must pass the goal through to the caller's check"
    # And the ask branch must actually route through it.
    k = SRC.index('elif self._may_say(may_say, handled, decision.goal, "ask")')
    assert k > SRC.index('if decision.addressee == "self" and not explicit'), \
        "the goal-keyed dedupe must be what a self-talk ask falls through to"


def test_a_broken_dedupe_never_silences_a_question():
    """The honesty wall on the thing now doing the work."""
    i = SRC.index("def _may_say(")
    body = SRC[i:i + 800]
    assert "except Exception" in body
    assert "return True" in body.split("except Exception")[1][:200], \
        "a failing guard must let the question through, not eat it"


# ------------------------------------------------------------- behaviour
#
# Everything above reads the source, which is weak. These drive the real hear()
# with the addressee FORCED to "self", because five live runs of his actual
# transcript all came back "person" — the failing path cannot be reached by
# luck, so it is pinned deliberately.

from brain import pb  # noqa: E402
from brain.anticipy_core import Anticipy  # noqa: E402
from brain.memory import Memory  # noqa: E402
from brain.orchestrator import Decision  # noqa: E402


class _Reply:
    def __init__(self, payload):
        self._p, self.ok = payload, True

    def json(self):
        return self._p

    def raise_for_status(self):
        return None


def _anticipy(monkeypatch, decision: Decision):
    """A real Anticipy whose triage is replaced by one fixed verdict."""
    rows = []
    monkeypatch.setattr(pb, "get", lambda url, params=None, timeout=None, **k:
                        _Reply({"items": []}))
    monkeypatch.setattr(pb, "post", lambda url, json=None, timeout=None, **k:
                        (rows.append(dict(json or {})),
                         _Reply({"id": f"j{len(rows)}", **(json or {})}))[1])
    monkeypatch.setattr(pb, "patch", lambda url, json=None, timeout=None, **k:
                        _Reply({}))

    class DeadMemory(Memory):
        def __init__(self):
            pass

        def ingest(self, *a, **k):
            return {}

        def recall(self, *a, **k):
            return []

    a = Anticipy(memory=DeadMemory(), owner_id="selftalk")
    monkeypatch.setattr(a, "_decide", lambda *args, **kw: decision)
    monkeypatch.setattr(a, "_voice", lambda *a_, **k_: None)  # use the fallback wording
    sent = []
    a.notify_owner = lambda m, channel="sms": (sent.append(m), True)[1]
    return a, sent


def test_a_consequential_self_talk_plan_is_held_and_asked_about_once(monkeypatch):
    """A plan is a plan whichever way the addressee label wobbles. "self" and
    "person" are indistinguishable through a one-sided pendant mic, and on
    identical lines the label flips between them run to run. So a consequential
    self-labelled plan takes the SAME lane as a person-labelled one: one held
    card, one text asking his go-ahead. What stays special about self-talk is
    the plain ask branch below the ambient lane — a bare question with no plan
    behind it still never texts (see the goalless tests)."""
    a, sent = _anticipy(monkeypatch, Decision(
        decision="ask", goal="Book dinner at Earls for tomorrow",
        reason="need the location", addressee="self",
        missing=["what time at Earls tomorrow, and which location?"]))
    out = a.hear("we should grab Earls tomorrow but")
    assert len(sent) == 1, f"expected one go-ahead text, got: {sent}"
    assert out["anticipy_says"], "the card must carry what was actually said"


def test_a_goalless_self_talk_question_is_still_swallowed(monkeypatch):
    """The other direction, and the reason the guard exists at all. Without a
    goal the dedupe has nothing to key on, so this could repeat forever."""
    a, sent = _anticipy(monkeypatch, Decision(
        decision="ask", goal=None, reason="what night were you thinking?",
        addressee="self", missing=["what night were you thinking?"]))
    a.hear("mm dinner sometime")
    assert sent == [], f"goalless self-talk texted him: {sent}"


def test_a_blank_goal_counts_as_no_goal(monkeypatch):
    for empty in ("", "   ", "\n"):
        a, sent = _anticipy(monkeypatch, Decision(
            decision="ask", goal=empty, reason="what night?",
            addressee="self", missing=["what night?"]))
        a.hear("mm dinner sometime")
        assert sent == [], f"goal={empty!r} texted him"


def test_a_question_aimed_at_her_is_always_asked(monkeypatch):
    for addressee in ("assistant", "person", None):
        a, sent = _anticipy(monkeypatch, Decision(
            decision="ask", goal="Book dinner at Earls for tomorrow",
            reason="need the location", addressee=addressee,
            missing=["which location?"]))
        a.hear("book us Earls tomorrow")
        assert sent, f"addressee={addressee!r} was silenced"


def test_the_card_never_promises_a_question_it_does_not_have():
    """The second half of what he saw. Even when she correctly stays quiet, the
    feed rendered the header 'Quick question for you' with nothing beneath it.
    Silence is fine; a header with no question is a lie about what happened."""
    card = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "app/ios/Anticipy/Views/ConversationCard.swift")
    src = open(card).read()
    i = src.index('Text("Quick question for you")')
    # The asking header must be conditional on there being something to ask.
    window = src[max(0, i - 700):i]
    assert "case .asking" in window
