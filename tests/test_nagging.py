"""Twice with no answer is an answer.

The same Cactus dinner, five times across three days, every one of them
sailing past every guard that existed:

  Aug 4 15:02  "just checking in about our plan to go to Cactus today..."
  Aug 4 21:32  "Just confirming for the dinner reservation, what date and time..."
  Aug 5 01:57  "just confirming for tomorrow night, what time and where..."
  Aug 5 21:35  "Just confirming for dinner tomorrow at Cactus Park location at 7"
  Aug 6 01:37  "Just confirming for tomorrow: Cactus Club Park Royal at 2:07 PM?"

Every existing guard was same-day, or keyed on an open loop's ID. A loop gets
a FRESH id each time the subject comes up in conversation, so the same dinner
was a brand-new loop each day and each guard waved it through, correctly by
its own terms.

The rule that generalises is not about dinner, or about days, or about ids:
how many times have I put this to him, ever, and got nowhere. Two is one more
chance than one. A third is nagging.
"""
import os
import sys
import re
import types
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import brain.worker as W  # noqa: E402

GOAL = "Confirm dinner reservation at Cactus Club Park Royal"

# Verbatim, from the events table.
THE_FIVE = [
    "Hey, just checking in about our plan to go to Cactus today. Are we still on?",
    "Just confirming for the dinner reservation, what date and time are you thinking?",
    "Hey, just confirming for tomorrow night, what time and where were you thinking for dinner?",
    "Just confirming for dinner tomorrow at Cactus Club Park location at 7 PM.",
    "Just confirming for tomorrow: Cactus Club Cafe Park Royal at 2:07 PM?",
]


def says(texts, goal=GOAL, days_ago=1):
    when = (datetime.now(timezone.utc) - timedelta(days=days_ago))
    return [{"kind": "anticipy_says", "goal": goal, "text": t,
             "created": when.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] + "Z"} for t in texts]


def backend(rows):
    """A stand-in that HONOURS the created>= filter.

    The first version returned every row regardless, which quietly made the
    24-hour guard look like it could see three-day-old messages. Mutation
    testing caught it: deleting the nag guard entirely left the gate test
    green, because the old guard was answering in its place on rows it should
    never have been shown."""
    seen = {}

    def get(url, params=None, timeout=None):
        filt = (params or {}).get("filter", "")
        seen["filter"] = filt
        out = rows
        m = re.search(r'created>="([^"]+)"', filt)
        if m:
            out = [r for r in rows if r.get("created", "") >= m.group(1)]
        return types.SimpleNamespace(ok=True, json=lambda: {"items": out})
    return get, seen


def test_the_third_cactus_message_never_goes_out(monkeypatch):
    monkeypatch.setattr(W.pb, "get", backend(says(THE_FIVE[:2]))[0])
    assert W.raised_and_ignored(GOAL) is True


def test_a_different_wording_still_counts(monkeypatch):
    """Every one of the five was worded differently. Keying on her wording is
    what let all five out."""
    monkeypatch.setattr(W.pb, "get", backend(says(THE_FIVE[:2]))[0])
    assert W.raised_and_ignored("Confirm the Cactus Club Park Royal dinner reservation") is True


def test_a_new_loop_id_does_not_reset_it(monkeypatch):
    """The actual mechanism of the bug: nothing here reads an id at all."""
    rows = says([THE_FIVE[0]], goal="Confirm dinner plans", days_ago=2) + \
        says([THE_FIVE[1]], goal="Confirm the dinner reservation at Cactus", days_ago=1)
    monkeypatch.setattr(W.pb, "get", backend(rows)[0])
    assert W.raised_and_ignored(GOAL) is True


def test_once_is_not_nagging(monkeypatch):
    monkeypatch.setattr(W.pb, "get", backend(says(THE_FIVE[:1]))[0])
    assert W.raised_and_ignored(GOAL) is False


def test_a_different_subject_is_never_silenced(monkeypatch):
    """The one thing no guard may do."""
    monkeypatch.setattr(W.pb, "get", backend(says(THE_FIVE))[0])
    assert W.raised_and_ignored("Send Marcus the quarterly numbers") is False
    assert W.raised_and_ignored("Renew the car insurance before it lapses") is False


def test_it_looks_back_over_days_not_hours(monkeypatch):
    get, seen = backend([])
    monkeypatch.setattr(W.pb, "get", get)
    W.raised_and_ignored(GOAL)
    assert "created>=" in seen["filter"]
    assert W.NAG_WINDOW_DAYS >= 7, "same-day windows are exactly what failed"


def test_no_goal_never_silences(monkeypatch):
    monkeypatch.setattr(W.pb, "get", backend(says(THE_FIVE))[0])
    assert W.raised_and_ignored("") is False
    assert W.raised_and_ignored(None) is False


def test_a_backend_failure_lets_her_speak(monkeypatch):
    """If we cannot tell, she speaks. Going silent on an error would make her
    mute about real things exactly when the backend is unwell."""
    def boom(*a, **k):
        raise RuntimeError("pb down")
    monkeypatch.setattr(W.pb, "get", boom)
    assert W.raised_and_ignored(GOAL) is False
    monkeypatch.setattr(W.pb, "get", lambda *a, **k: types.SimpleNamespace(
        ok=False, json=lambda: {}))
    assert W.raised_and_ignored(GOAL) is False


def test_the_gate_actually_consults_it(monkeypatch):
    """SPEAK_ONCE is the one door all unprompted speech goes through.

    The prior messages are THREE DAYS old on purpose. The existing same-day
    guard cannot see them, so if this passes it is because the nag limit
    fired — caught by mutation testing, where deleting the nag guard left the
    original version of this test green because already_raised was answering
    for it."""
    monkeypatch.setattr(W.pb, "get", backend(says(THE_FIVE[:2], days_ago=3))[0])
    assert W.SPEAK_ONCE("Just confirming tomorrow at 7?", goal=GOAL, kind="clock") is False


def test_two_shared_words_is_the_floor_that_protects_other_subjects(monkeypatch):
    """Which half of the check is load-bearing, made explicit.

    Mutation testing showed that dropping the ratio to zero silenced nothing,
    because the absolute floor still stood. That is worth knowing rather than
    hiding: on real data unrelated subjects share ZERO words with the goal, so
    the floor is what protects them and the ratio only sharpens the edge."""
    monkeypatch.setattr(W.pb, "get", backend(says(THE_FIVE))[0])
    for unrelated in ("Send Marcus the quarterly numbers",
                      "Renew the car insurance before it lapses",
                      "Research noise cancelling headphones under 400 dollars"):
        want = W._content_words(unrelated)
        for row in says(THE_FIVE):
            said = W._content_words((row["goal"] or "") + " " + row["text"])
            assert len(want & said) < 2, f"{unrelated!r} shares too much to be safe"
        assert W.raised_and_ignored(unrelated) is False


def test_the_gate_still_lets_a_first_word_through(monkeypatch):
    monkeypatch.setattr(W.pb, "get", backend([])[0])
    assert W.SPEAK_ONCE("Heads up, the invoice is due Friday",
                        goal="Remind about the Friday invoice") is True


def test_a_blocking_question_is_never_nagging(monkeypatch):
    """The regression this fix caused, hours after shipping.

    He said "I've gotta email Priya the invoice". The sufficiency check
    correctly asked WHICH Priya — and the nag limit swallowed the question,
    because "Priya", "email" and "invoice" had come up twice already that day.
    He got a card reading "Quick question for you" and no question.

    Nagging is outreach SHE started. A question blocking work HE started
    seconds ago is the opposite: silencing it does not stop nagging, it
    strands the task.
    """
    # THREE DAYS old, so the same-day guard cannot be the thing answering
    # here. If this passes it is because the nag limit stood aside for a
    # blocking question, which is the whole point.
    monkeypatch.setattr(W.pb, "get", backend(
        says(THE_FIVE, goal="Email Priya the invoice", days_ago=3))[0])
    assert W.SPEAK_ONCE("Quick question — who is Priya?",
                        goal="Email Priya the invoice", kind="ask") is True


def test_speech_she_started_is_still_limited(monkeypatch):
    """The half that must keep working. All five Cactus messages were clock."""
    monkeypatch.setattr(W.pb, "get", backend(says(THE_FIVE[:2], days_ago=3))[0])
    assert W.SPEAK_ONCE("Just confirming tomorrow at 7?", goal=GOAL, kind="clock") is False


def test_a_fresh_overheard_plan_is_never_nagging(monkeypatch):
    """Live, 2026-08-09: he made a brand-new dinner plan out loud — held card,
    "I'll text you what I find" — and no text ever came, because days-old
    messages about a PREVIOUS dinner had spent the nag quota for the subject.
    Worse, the no-silent-cards rule then cancelled the card. A plan he just
    spoke is work HE started; her one text about it is a receipt, not a nag.
    The 24-hour same-plan guard is what stops a repeated mention texting twice.
    """
    monkeypatch.setattr(W.pb, "get", backend(says(THE_FIVE, days_ago=3))[0])
    assert W.SPEAK_ONCE("Caught your plan — dinner at Earls tomorrow at 7.",
                        goal="Book dinner for tomorrow at Earls in West Van",
                        kind="ambient_act") is True


def test_a_new_card_speaks_even_when_yesterdays_plan_rhymed_with_it(monkeypatch):
    """Third live silence in one day, third different guard: after the nag
    limit was fixed, the 24-hour word-overlap dedupe caught the NEXT fresh
    dinner ("Confirm dinner at Earls West End tomorrow" vs the morning's
    "Book dinner at Earls...") — silenced the text and cancelled the card.

    Word overlap against her past texts is the wrong key for this kind: a
    brand-new dinner plan will always share most of its words with the last
    one. The pending-card merge in _queue_job is the real dedupe — a
    re-mention of a plan she is HOLDING never reaches SPEAK_ONCE at all
    (test_a_repeat_of_a_card_he_already_knows_about_is_left_alone) — so a
    goal that DOES reach it is a genuinely new card, and a new card speaks.
    """
    monkeypatch.setattr(W.pb, "get", backend(says(
        ["Caught your plan — dinner at Earls in West Van tomorrow."],
        goal="Book dinner for tomorrow at Earls in West Van",
        days_ago=0.1))[0])
    assert W.SPEAK_ONCE("Ready to book Earls in West Van for tomorrow.",
                        goal="Confirm dinner at Earls West End tomorrow",
                        kind="ambient_act") is True
