"""A neighbour's errand must not become this line's errand.

MEASURED live 2026-08-21 on a real account. Two utterances, 50 seconds apart,
in DIFFERENT segments:

    s1  "oh no, I completely forgot to sort anything for dinner and the kids
         will be back by six"
          -> act, goal "Arrange dinner for the kids for 6 PM"
    s2  "honestly this whole week has just been one thing after another, I am
         wrecked"
          -> act, goal "Order dinner for kids", job queued, TEXT SENT

s2 is venting. There is no errand in it. The goal is s1's, reworded, and he
was interrupted about work he never mentioned. proof/ambient/score.py:62
weights a false ping as five misses, so this is the single most expensive
thing the product can do.

The carrier was found by replaying both lines through Anticipy.hear() with a
recording brain: the segment block was EMPTY (the segmenter is innocent), and
the dinner line arrived anyway inside "(Previous line, background: ...)" and
inside the numbered "(Recent lines, oldest first ...)" block. The prompts in
this file are that replay, verbatim.

The other half of the file matters just as much. Context is what makes "seven
works" and "yeah book it" mean anything at all, and a fix that silenced those
would be a worse bug than the one it fixed.
"""
import json
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain.orchestrator import (Brain, appended_context, inherited_errand,  # noqa: E402
                                own_words, points_outward)


class Fake:
    """Answers every call with the same payload — including the second look,
    which must never be reached once the goal has been dropped."""
    live = True

    def __init__(self, payload):
        self.payload = payload
        self.systems = []

    def chat(self, system, user, **kw):
        self.systems.append(system)
        text = (self.payload if isinstance(self.payload, str)
                else json.dumps(self.payload))
        return types.SimpleNamespace(text=text)


VENT = "honestly this whole week has just been one thing after another, I am wrecked"
DINNER = ("oh no, I completely forgot to sort anything for dinner and the kids "
          "will be back by six")

# Verbatim from the replay: what triage() was actually handed for s2.
BLED = (
    f"{VENT}\n"
    f"(Previous line, background: {DINNER})\n"
    f"(Addressee of the previous line: self)\n"
    f"(Recent lines, oldest first — say in \"continues\" which ONE this line "
    f"carries on from, or 0 if it starts something new:\n"
    f"[1] {DINNER}\n"
    f"[2] {VENT})"
)


def triage(prompt, payload, **kw):
    llm = Fake(payload)
    return Brain(llm=llm).triage(prompt, **kw), llm


# ------------------------------------------------------- the live regression

def test_a_vent_line_does_not_inherit_the_errand_beside_it():
    """The bug, exactly as it happened. The model says act and hands over a
    goal built entirely out of the previous line; nothing consequential may
    survive that."""
    d, _ = triage(BLED, {"decision": "act", "goal": "Order dinner for kids",
                         "addressee": "self", "owes": "owner",
                         "continues": 1, "reason": "dinner still needed"},
                  candidates=2)
    assert d.decision == "ignore"
    assert d.goal is None


def test_the_dropped_goal_does_not_become_the_quiet_lane():
    """An "ignore" that still carries a goal is a real state elsewhere in this
    system: score.py counts it as the quiet lane and the phone renders it
    "Looking into it.". Both would be a lie about a line with no errand in
    it, so the goal goes, and the reason says why."""
    d, _ = triage(BLED, {"decision": "act", "goal": "Order dinner for kids",
                         "owes": "owner", "reason": "dinner still needed"},
                  candidates=2)
    assert not d.goal
    assert d.needs_confirmation is False
    assert d.missing == []
    assert d.assumption is None
    assert "context" in d.reason


def test_the_second_look_cannot_flip_it_back():
    """decision=ignore WITH a goal is what wakes SECOND_LOOK. Dropping the
    goal is what keeps this fix from being undone one line later."""
    d, llm = triage(BLED, {"decision": "act", "goal": "Order dinner for kids",
                           "owes": "owner", "reason": "dinner still needed"},
                    candidates=2)
    assert d.decision == "ignore"
    assert Brain.SECOND_LOOK not in llm.systems


def test_an_inherited_question_is_dropped_too():
    """"ask" interrupts him harder than "act" does — it needs an answer."""
    d, _ = triage(BLED, {"decision": "ask", "goal": "Order dinner for kids",
                         "missing": ["which takeaway"], "owes": "owner",
                         "reason": "need to know where from"}, candidates=2)
    assert d.decision == "ignore"
    assert d.goal is None
    assert d.missing == []


# ------------------------------------------------- what must keep working

def test_a_terse_seal_still_resolves_into_the_earlier_plan():
    """"seven works" is him committing, and the plan is only in the context.
    If this ever fails, the fix above has eaten the product."""
    prompt = ("seven works\n"
              "(Earlier in this conversation: shall we do dinner at Joe's "
              "tonight | how about seven)")
    d, _ = triage(prompt, {"decision": "act",
                           "goal": "Book dinner at Joe's for 7 tonight",
                           "addressee": "person", "owes": "owner",
                           "reason": "he sealed the time"})
    assert d.decision == "act"
    assert d.goal == "Book dinner at Joe's for 7 tonight"


def test_a_bare_go_ahead_still_resolves_into_the_earlier_plan():
    prompt = ("yeah book it\n"
              "(Previous line, background: I should get a table at Cactus "
              "for Friday)")
    d, _ = triage(prompt, {"decision": "act",
                           "goal": "Book a table at Cactus Club for Friday",
                           "addressee": "assistant", "owes": "owner",
                           "reason": "he told her to book"})
    assert d.decision == "act"
    assert d.goal == "Book a table at Cactus Club for Friday"


def test_a_correction_to_a_live_plan_survives():
    """"make it eight instead" carries one detail and points at the rest."""
    prompt = ("actually make it eight instead\n"
              "(Earlier in this conversation: dinner at Joe's at seven)")
    d, _ = triage(prompt, {"decision": "act",
                           "goal": "Book dinner at Joe's for 8 tonight",
                           "owes": "owner", "reason": "he moved the time"})
    assert d.decision == "act"


def test_a_call_off_survives():
    prompt = ("scratch that\n"
              "(Previous line, background: book us dinner at Joe's tonight)")
    d, _ = triage(prompt, {"decision": "act",
                           "goal": "cancel dinner at Joe's tonight",
                           "owes": "owner", "reason": "he called it off"})
    assert d.decision == "act"
    assert d.goal == "cancel dinner at Joe's tonight"


def test_the_realisation_it_was_built_from_is_untouched():
    """s1 itself: the errand is in his own words, and it is the most valuable
    thing the product ever catches."""
    prompt = (f"{DINNER}\n"
              "(Recent lines, oldest first — say in \"continues\" which ONE "
              f"this line carries on from, or 0 if it starts something new:\n"
              f"[1] {DINNER})")
    d, _ = triage(prompt, {"decision": "act",
                           "goal": "Arrange dinner for the kids for 6 PM",
                           "owes": "owner", "continues": 0,
                           "reason": "food still has to happen"},
                  candidates=1)
    assert d.decision == "act"
    assert d.goal == "Arrange dinner for the kids for 6 PM"


def test_an_undecorated_line_is_never_touched():
    """No context, nothing to inherit from. Every caller that passes a bare
    line — which is most of the test suite — must be unaffected."""
    d, _ = triage("book us a table at Joe's for seven",
                  {"decision": "act", "goal": "Book a table at Joe's for 7",
                   "owes": "owner", "reason": "he asked"})
    assert d.decision == "act"
    assert d.goal == "Book a table at Joe's for 7"


def test_a_request_of_his_own_survives_with_no_word_in_common():
    """The four honest requests a first draft of this guard ate. Not one of
    them shares a word with the goal she wrote for it — she used a synonym —
    and every one of them is him asking for something. Filling the where and
    the when from context is exactly what TRIAGE_SYSTEM tells her to do."""
    ctx = ("\n(Earlier in this conversation: shall we do dinner at Joe's "
           "tonight | how about seven for the four of us)")
    for asked in ("can you get us a reservation", "make the booking",
                  "sort us out somewhere", "we still need a table"):
        d, _ = triage(asked + ctx,
                      {"decision": "act",
                       "goal": "Book dinner at Joe's for 4 at 7 tonight",
                       "owes": "owner", "reason": "he asked for it"})
        assert d.decision == "act", asked
        assert d.goal == "Book dinner at Joe's for 4 at 7 tonight", asked


def test_a_question_about_what_was_agreed_survives():
    """"what time did we say" is a reference to earlier speech, which is a
    pointing finger wearing a different glove — and answering it is a
    read-only errand the prompt explicitly wants caught."""
    prompt = ("what time did we say\n"
              "(Earlier in this conversation: dinner at Joe's | how about "
              "seven)")
    d, _ = triage(prompt, {"decision": "act",
                           "goal": "Confirm the agreed time for Joe's",
                           "owes": "owner", "reason": "he asked out loud"})
    assert d.decision == "act"


def test_an_ordinary_word_is_not_a_confirmation():
    """Found by battery, not by imagination: "work has been absolutely
    relentless" was surviving because "work" matched a confirming "works"
    and "absolutely" was treated as agreement. A confirmation lands as the
    whole line or at the end of it, never buried mid-sentence."""
    prompt = ("work has been absolutely relentless lately\n"
              "(Previous line, background: I need to get dinner sorted for "
              "the kids by six)")
    assert inherited_errand(prompt, "Order dinner for the kids") is True
    assert points_outward("seven works") is True
    assert points_outward("Tuesday works") is True
    assert points_outward("work has been absolutely relentless lately") is False


def test_invention_out_of_thin_air_is_left_to_its_own_check():
    """A goal whose substance is in NEITHER the line nor the context is the
    Earl's-in-Winnipeg failure, and unsupported_names already owns it with a
    reason he can read. Judging it twice, in two places, from two different
    rules is how the two answers start disagreeing."""
    prompt = ("we should go out for dinner\n"
              "(Previous line, background: long day)")
    assert inherited_errand(prompt, "Book a table at Earl's") is False


# --------------------------------------------------------- the pieces

def test_the_line_is_split_from_its_decoration():
    assert own_words(BLED) == VENT
    assert DINNER in appended_context(BLED)
    assert VENT not in appended_context(BLED).split("(Recent lines")[0]


def test_a_determiner_is_not_a_pointing_finger():
    """The whole fix turns on this. "this"/"that"/"one" in front of a noun
    name their own subject; with nothing behind them they point out of the
    line. Get it wrong in one direction and the vent line survives; get it
    wrong in the other and "do that" dies."""
    for pointing in ("do that", "book it", "that works", "this one",
                     "scratch that", "that's fine", "seven works for them"):
        assert points_outward(pointing) is True, pointing
    for standing_alone in (VENT, "this whole week has been rough",
                           "one thing after another", "I am wrecked",
                           "that dentist appointment was brutal"):
        assert points_outward(standing_alone) is False, standing_alone


# ------------------------------------------------------- the whole corpus

def _corpus():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "proof", "ambient", "corpus.json"),
              encoding="utf-8") as fh:
        rows = json.load(fh)
    convos = {}
    for r in rows:
        if r.get("convo"):
            convos.setdefault(r["convo"], []).append(r)
    for turns in convos.values():
        turns.sort(key=lambda r: r.get("turn", 0))
    return rows, convos


def _decorated(rows, convos, i):
    """The row as anticipy_core would hand it to triage: its own conversation
    in front of it, and the line before it riding along as background."""
    row = rows[i]
    earlier = [t["text"] for t in convos.get(row.get("convo") or "", [])
               if t.get("turn", 0) < row.get("turn", 0)]
    prev = earlier[-1] if earlier else (rows[i - 1]["text"] if i else None)
    prompt = row["text"]
    if earlier:
        prompt += "\n(Earlier in this conversation: " + " | ".join(earlier) + ")"
    if prev:
        prompt += f"\n(Previous line, background: {prev})"
    return prompt


def test_not_one_real_errand_in_the_corpus_loses_its_goal():
    """The measurement, kept as a test so that widening any rule above has to
    answer for it. Every gold act/ask line in proof/ambient/corpus.json,
    decorated with its real conversation: 0 of 173 judged inherited. The
    first draft of this guard ate one (amb-0318, a refusal plus a wish), and
    that is how the need-detector learned about bare "can"."""
    rows, convos = _corpus()
    eaten = [r["id"] for i, r in enumerate(rows)
             if r.get("gold") in ("act", "ask") and r.get("goal")
             and inherited_errand(_decorated(rows, convos, i), r["goal"])]
    assert eaten == [], eaten


def test_it_stops_most_manufactured_pings_across_the_corpus():
    """The other side of the same measurement: every gold IGNORE line handed
    the previous errand's goal — the exact shape of the live failure, 147
    times. 75 were stopped when this was written; the rest survive because
    they carry a bare "it" or "that" of their own, which is a reference the
    guard is not allowed to overrule. A floor, not a target: this is the
    number that must never quietly collapse to zero."""
    rows, _ = _corpus()
    stopped = total = 0
    errand = None
    for row in rows:
        if row.get("gold") in ("act", "ask") and row.get("goal"):
            errand = row
            continue
        if row.get("gold") != "ignore" or not errand:
            continue
        total += 1
        prompt = (row["text"] +
                  f"\n(Previous line, background: {errand['text']})")
        stopped += bool(inherited_errand(prompt, errand["goal"]))
    assert total > 100
    assert stopped >= 60, f"only {stopped} of {total} stopped"
