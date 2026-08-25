"""A guest's promise is not the owner's errand.

`Memory.ingest` took `(text, ts)` and nothing else, so every line the pendant
heard entered the store as if the owner had said it. `hear()` already holds the
phone's voice verdict for that line and triage already returns its own verdict
on whose obligation the sentence expresses — both were computed and dropped on
the floor one call before memory saw the words.

The live consequence, reproduced against the shipped code: a guest at the
owner's table says "I'll send you the pitch deck tomorrow morning." It becomes
an open commitment in the owner's memory, the clock's authority check reads it
as a real errand of somebody's, and `clock_tick` may mint a browser job from
it. The owner is then chased about a promise somebody else made.

    open_loops after a GUEST's sentence:
      [{'id': 3, 'what': 'send you the pitch deck tomorrow morning',
        'source': "I'll send you the pitch deck tomorrow morning."}]
      clock may mint a goal from it? True

THE HONESTY WALL IS THE POINT OF THESE TESTS, not a footnote. Live speaker
coverage is 0%: `anticipy_core` records the measurement at the roster
normalisation — 200 tagged lines, 195 distinct identities, 97% seen exactly
once, the owner recognised twice. A fence keyed on "the speaker is not
positively the owner" would refuse to prepare anything at all. So only a
POSITIVE not-his verdict fences, from either sensor, and no verdict must
change nothing. Half of what follows tests that nothing changed.
"""
import json
import sqlite3

from brain.anticipy_core import Anticipy
from brain.memory import Memory
from brain.orchestrator import (Decision, PARTY_YES, PARTY_NO, PARTY_UNASKED,
                                PARTY_UNANSWERED)
from llm_fakes import FakeExtractor, licence_reply

GUEST_LINE = "I'll send you the pitch deck tomorrow morning."
KOWALSKI_LINE = "The reservation should be under the name Kowalski, obviously."


# ------------------------------------------ where these tests' facts come from
#
# THESE TESTS ARE ABOUT WHO SPOKE, not about extraction — and until 2026-08-25
# thirty-five of them got their commitment for free from `_rule_extract`, the
# capitalisation regex in brain/memory.py that decided who a person was, what a
# promise was, and WHO IT HAD BEEN PROMISED TO whenever no model answered. That
# is HARNESS-LAW 1's forbidden question answered by a pattern; it is deleted
# (audit item 43), and `_extract` returns NO VERDICT instead, which writes
# nothing at all into the graph.
#
# Not one of these tests ever tested that regex — `grep -rn "_rule_extract"
# tests/` returned nothing. They leaned on it as an implicit test double. So
# they get a real one, and it is explicit about what it claims: `FakeExtractor`
# lives in tests/llm_fakes.py and brain/ never imports it, which
# tests/test_library_nobody_looked_is_not_nothing_here.py pins.
_EXTRACTIONS = {
    GUEST_LINE: {"topics": ["pitch deck"],
                 "commitment": "send you the pitch deck tomorrow morning"},
    KOWALSKI_LINE: {"people": ["Kowalski"], "topics": ["reservation"]},
}


def _store(*args, **kw):
    """A Memory whose extractor ANSWERS, so that a test about attribution
    cannot quietly turn into a test of whether anything was extracted."""
    kw.setdefault("llm", FakeExtractor(per_line=_EXTRACTIONS))
    return Memory(*args, **kw)


# ------------------------------------------------- the store records who spoke

def test_a_guests_promise_is_recorded_as_someone_elses():
    m = _store(":memory:")
    m.ingest(GUEST_LINE, speaker="other")
    loop = m.open_loops()[0]
    assert loop["speaker"] == "other", \
        "the promise carries no attribution, so nothing downstream can refuse it"


def test_the_owners_own_promise_is_recorded_as_his():
    m = _store(":memory:")
    m.ingest(GUEST_LINE, speaker="owner")
    assert m.open_loops()[0]["speaker"] == "owner"


def test_no_verdict_is_stored_as_no_verdict():
    """Not "owner". The 97% of lines that carry no voice verdict must be
    distinguishable from the ones the roster actually placed."""
    m = _store(":memory:")
    m.ingest(GUEST_LINE)
    assert m.open_loops()[0]["speaker"] is None
    m2 = _store(":memory:")
    m2.ingest(GUEST_LINE, speaker="unknown")
    assert m2.open_loops()[0]["speaker"] is None, \
        "a build that says 'unknown' out loud means the same as saying nothing"


def test_the_line_itself_keeps_the_verdict():
    """On the episode, not only on the commitment: the episode is the record
    of what was said, and a promise is one thing that can be derived from it."""
    m = _store(":memory:")
    mem = m.ingest(GUEST_LINE, speaker="other")
    row = m.db.execute("SELECT speaker FROM episodes WHERE id=?",
                       (mem["episode_id"],)).fetchone()
    assert row[0] == "other"


# ------------------------------------------- the model's verdict is kept too

def test_triage_saying_someone_else_owes_it_is_kept_on_the_promise():
    """The sensor that actually fires today. Voice coverage is 0%; `owes` is
    produced on every triaged line by a model with the whole conversation."""
    m = _store(":memory:")
    mem = m.ingest(GUEST_LINE)
    m.attribute_commitment(mem["commitment_id"], owes="other")
    assert m.open_loops()[0]["owes"] == "other"


def test_a_no_verdict_call_never_erases_a_verdict_already_stored():
    """C1, AT THE LAYER WHERE THE DAMAGE HAPPENED. `owes=None` used to pop the
    key, and _upsert_node hands back the SAME commitment node every time the
    same sentence is extracted again — so the second hearing of one guest
    sentence, triaged with no verdict at all, erased the mark the first hearing
    got right. The erase path is gone: absence is not an answer, exactly as it
    is not for a voice tag or a fact's kind."""
    m = _store(":memory:")
    mem = m.ingest(GUEST_LINE)
    m.attribute_commitment(mem["commitment_id"], owes="other")
    m.attribute_commitment(mem["commitment_id"], owes=None)
    assert m.open_loops()[0]["owes"] == "other", \
        "a no-verdict call popped the mark and unfenced the guest's promise"
    m.attribute_commitment(mem["commitment_id"], owes="")
    assert m.open_loops()[0]["owes"] == "other"


def test_a_no_verdict_call_on_an_unmarked_promise_still_writes_nothing():
    """The other half of the same contract: writing nothing is not writing
    "owner". A promise nobody judged must stay unjudged, or the clock starts
    reading the absence of an answer as an answer."""
    m = _store(":memory:")
    mem = m.ingest(GUEST_LINE)
    m.attribute_commitment(mem["commitment_id"], owes=None)
    assert m.open_loops()[0]["owes"] is None


# --------------------------------------------------- hear() stops dropping it

def _brain(monkeypatch, **kw):
    m = _store(":memory:")
    a = Anticipy(memory=m, llm=None, owner_id="t", owner_phone=None, **kw)
    monkeypatch.setattr(a, "_queue_job", lambda *a_, **k_: "job")
    return a, m


def test_hear_threads_the_phones_verdict_into_the_store(monkeypatch):
    """THE BEHAVIOURAL LEG. Unit-testing the fence alone would stay green
    through the entire bug, because the verdict was correct and simply never
    arrived — the shape of 8849df15."""
    a, m = _brain(monkeypatch)
    a.hear(GUEST_LINE, speaker="other:Sarah")
    assert m.open_loops()[0]["speaker"] == "other"


def test_hear_does_not_invent_a_verdict_from_an_unplaceable_voice(monkeypatch):
    """"other:v215" is the roster failing to recognise a voice, not
    recognising a different one — 195 identities on 200 lines. hear() already
    reduces it to no verdict for triage; memory must see the same thing."""
    a, m = _brain(monkeypatch)
    a.hear(GUEST_LINE, speaker="other:v215")
    assert m.open_loops()[0]["speaker"] is None


def test_hear_with_no_verdict_stores_none(monkeypatch):
    a, m = _brain(monkeypatch)
    a.hear(GUEST_LINE)
    assert m.open_loops()[0]["speaker"] is None


def _triaging_brain(monkeypatch, owes, party=PARTY_NO, decision="act",
                    goal="send the pitch deck"):
    """hear() with triage scripted. `_decide` is stubbed rather than driven
    through a fake model because the verdict under test is what hear() DOES
    with `owes`, not how the model arrives at it.

    `party` is one of the four PARTY_* states, never a bool. It used to be a
    bool, and that is precisely the bug C1 turned out to be: a test that can
    only say True or False cannot say "the call failed", so no test in this
    file could express the case that broke the fence."""
    import brain.anticipy_core as core
    from brain.orchestrator import Decision
    m = _store(":memory:")
    a = Anticipy(memory=m, llm=None, owner_id="t", owner_phone=None)
    monkeypatch.setattr(a, "_queue_job", lambda *a_, **k_: "job")
    monkeypatch.setattr(a, "_decide", lambda *a_, **k_: Decision(
        decision=decision, goal=goal, reason="scripted",
        addressee="person", owes=owes))
    _script_party(monkeypatch, core, party)
    return a, m


def _script_party(monkeypatch, core, party):
    """Script the reversal. Guards against the bool it used to be: `True`
    silently means neither PARTY_YES nor PARTY_NO under the new contract, and
    a test that passed one would go quietly green testing nothing."""
    assert party in (PARTY_YES, PARTY_NO, PARTY_UNASKED, PARTY_UNANSWERED), \
        f"party must be one of the four PARTY_* states, got {party!r}"
    monkeypatch.setattr(core, "party_verdict", lambda *a_, **k_: party)


def _retriage(monkeypatch, a, owes, decision="act", goal="send the pitch deck"):
    """Re-script triage for the NEXT hearing of the same sentence."""
    from brain.orchestrator import Decision
    monkeypatch.setattr(a, "_decide", lambda *a_, **k_: Decision(
        decision=decision, goal=goal, reason="scripted",
        addressee="person", owes=owes))


def test_hear_writes_triages_verdict_back_onto_the_promise(monkeypatch):
    """THE BEHAVIOURAL LEG for the half that fires today. hear() already
    refused to start work on this line; the loop it left behind was unmarked,
    so clock_tick could mint the same work an hour later."""
    a, m = _triaging_brain(monkeypatch, owes="other")
    a.hear(GUEST_LINE)
    assert m.open_loops()[0]["owes"] == "other"


def test_hear_clears_the_mark_when_the_owner_turns_out_to_be_a_party(monkeypatch):
    a, m = _triaging_brain(monkeypatch, owes="other", party=PARTY_YES)
    a.hear(GUEST_LINE)
    assert m.open_loops()[0]["owes"] is None, \
        "the loop stayed fenced on a verdict owner_is_party had withdrawn"


# ------------------------------------------------ C1: the fence unmarks itself
#
# The first draft of the write above passed `"other" if owes == "other" else
# None`, and attribute_commitment(id, None) POPPED the key. _upsert_node
# returns the same commitment node whenever the same sentence is extracted
# again, so every later hearing that did not say "other" erased the fence —
# and the whole suite stayed green through it, because nothing here ever heard
# the same sentence twice.


def test_a_second_hearing_with_no_verdict_does_not_unmark_the_promise(monkeypatch):
    """THE CHECK THAT WOULD HAVE CAUGHT C1. The guest closes the topic with
    the same sentence verbatim — or the worker restarts between hear() and
    mark_processed and re-polls the event — and this time triage times out, so
    _decide() falls through to Decision(decision="ignore", goal=None) with
    owes=None. That is NO VERDICT, and the honesty wall hear() states sixty
    lines further down says no verdict changes nothing."""
    a, m = _triaging_brain(monkeypatch, owes="other")
    a.hear(GUEST_LINE)
    assert m.open_loops()[0]["owes"] == "other"
    _retriage(monkeypatch, a, owes=None, decision="ignore", goal=None)
    a.hear(GUEST_LINE)
    assert m.open_loops()[0]["owes"] == "other", \
        ("a triage timeout on the second hearing erased the mark — the guest's "
         "promise is unfenced and the clock is free to mint the browser job")


def test_a_later_contrary_triage_verdict_does_not_unmark_it_either(monkeypatch):
    """Triage is measured wrong in exactly one direction here — six for six
    filing the owner's own dinner under the friend — so its own second opinion
    is the weakest possible reason to drop a fence. party_verdict(), asked
    that one question alone, is the only thing that may withdraw the mark."""
    a, m = _triaging_brain(monkeypatch, owes="other")
    a.hear(GUEST_LINE)
    _retriage(monkeypatch, a, owes="owner")
    a.hear(GUEST_LINE)
    assert m.open_loops()[0]["owes"] == "other"


# ------------- C1, the other way round: the fence that could not be lowered
#
# The fix above was right and incomplete. It removed the accidental way down
# without building the deliberate one, and `owner_is_party` returned a bare
# bool — so a timeout, a 5xx, a rate limit and an unparseable reply all came
# back as the same False that a model saying "no, he is not a party" comes
# back as, and that False wrote a mark nothing could clear. Reproduced on the
# recorded dinner line before the fix:
#
#     hearing 1 (party call FAILED -> False):  owes = other
#     hearing 2 (party call WORKS  -> True):   owes = other
#     hearing 3 (triage itself says 'owner'):  owes = other
#     briefing sees: other
#
# One flaky call and the owner's own dinner belonged to his friend in every
# briefing forever, because nothing ever closes a guest-attributed commitment.
#
# THE ROOT IS TESTED AT THE ROOT. Every hear() leg below scripts
# `core.party_verdict`, so not one of them ever runs the real function — and
# the entire fix rests on it answering PARTY_UNANSWERED rather than PARTY_NO
# when a call blows up. Mutation-proven: collapsing PARTY_UNANSWERED back into
# PARTY_NO inside party_verdict — which IS the original bug, exactly — left
# every hear() leg green. A check that cannot fail is not a check.


class _PartyLLM:
    """A live model whose one reply is under the test's control."""
    live = True

    def __init__(self, text=None, raises=None):
        self._text, self._raises = text, raises

    def chat(self, *_a, **_k):
        if self._raises:
            raise self._raises
        class R:
            text = self._text
        return R()


def _party(**kw):
    from brain.orchestrator import party_verdict
    return party_verdict(_PartyLLM(**kw), GUEST_LINE, "send the pitch deck")


def test_a_party_call_that_raises_is_unanswered_not_a_no():
    """THE ROOT CHECK FOR C1. A timeout, a 5xx and a rate limit all arrive
    here as an exception, and returning PARTY_NO for them is what wrote a
    permanent, unremovable mark off a transient fault."""
    for boom in (TimeoutError("gateway timeout"),
                 RuntimeError("429 rate limited"),
                 ValueError("500 from the provider")):
        assert _party(raises=boom) == PARTY_UNANSWERED, \
            f"{boom!r} was recorded as the model saying 'no, not a party'"


def test_a_reply_that_cannot_be_read_is_unanswered_not_a_no():
    """A live model that replied without the key, with a non-boolean, or with
    prose did not say "no" — it said nothing this code can read. Same
    treatment as the timeout, for the same reason."""
    for text in ("not json at all", "{}", '{"owner_is_party": null}',
                 '{"owner_is_party": "yes"}', '{"other_key": true}', "[]"):
        assert _party(text=text) == PARTY_UNANSWERED, f"read a verdict out of {text!r}"


def test_a_real_answer_is_still_a_real_answer():
    assert _party(text='{"owner_is_party": true}') == PARTY_YES
    assert _party(text='{"owner_is_party": false}') == PARTY_NO


def test_nothing_to_ask_is_a_different_state_from_a_call_that_failed():
    """The distinction the whole fix turns on. No live model is the documented
    inert mode and must keep writing triage's verdict exactly as it always
    did; a LIVE model that could not answer must not write at all. Collapsing
    these two puts the product back on one of the two bugs whichever way it
    is collapsed."""
    from brain.orchestrator import party_verdict
    assert party_verdict(None, GUEST_LINE, "send the pitch deck") == PARTY_UNASKED
    assert party_verdict(_PartyLLM(text="{}"), GUEST_LINE, "") == PARTY_UNASKED

    class _Dead:
        live = False
        def chat(self, *_a, **_k):
            raise AssertionError("a dead model must never be called")
    assert party_verdict(_Dead(), GUEST_LINE, "send the pitch deck") == PARTY_UNASKED


def test_the_four_party_states_are_four_distinct_values():
    """Cheap, and it catches the one-character edit that makes every leg above
    pass while meaning nothing."""
    assert len({PARTY_YES, PARTY_NO, PARTY_UNASKED, PARTY_UNANSWERED}) == 4


def test_hear_calls_the_real_reversal_and_not_a_stale_alias():
    """The legs below script `core.party_verdict`. If hear() ever called
    something else — a stale import, a renamed sibling — every one of them
    would go green while testing nothing at all."""
    import brain.anticipy_core as core
    import brain.orchestrator as orch
    assert core.party_verdict is orch.party_verdict


def test_a_reversal_that_could_not_be_answered_writes_no_verdict(monkeypatch):
    """THE CHECK THAT WOULD HAVE CAUGHT C1. A live model was asked and the
    call blew up. Nothing about the world was learned, so nothing is written:
    the block's own stated rule is that the write takes the HIGHER of its two
    readers' bars, and a call that failed does not clear a bar. This is the
    one leg the old bool signature made impossible to write — a test that can
    only say True or False cannot say "the call failed"."""
    a, m = _triaging_brain(monkeypatch, owes="other", party=PARTY_UNANSWERED)
    a.hear(GUEST_LINE)
    assert m.open_loops()[0]["owes"] is None, \
        ("a timeout was recorded as a verdict — and since nothing can clear "
         "it, the owner's own plan is his friend's in every briefing forever")


def test_a_failed_reversal_may_not_lower_a_fence_either(monkeypatch):
    """The same rule pointed the other way, and the half that keeps this fix
    from becoming the bug it replaces. A failed call is not evidence the
    promise is his, so it must not touch a mark an earlier hearing wrote."""
    a, m = _triaging_brain(monkeypatch, owes="other")
    a.hear(GUEST_LINE)
    assert m.open_loops()[0]["owes"] == "other"
    _script_party(monkeypatch, _core(), PARTY_UNANSWERED)
    a.hear(GUEST_LINE)
    assert m.open_loops()[0]["owes"] == "other", \
        "a call that failed erased a verdict a working call had got right"


def test_a_mark_written_without_a_real_no_can_be_withdrawn_later(monkeypatch):
    """THE FENCE CAN BE LOWERED. Hearing 1 has no live model to ask, so the
    documented inert path writes triage's verdict — and triage is measured
    wrong six for six in exactly this direction. Hearing 2 reaches a live
    model, which says on its own that the owner IS a party. That is the only
    verdict allowed to withdraw a mark, and it now does."""
    a, m = _triaging_brain(monkeypatch, owes="other", party=PARTY_UNASKED,
                           decision="say", goal=None)
    a.hear(GUEST_LINE)
    assert m.open_loops()[0]["owes"] == "other"
    _script_party(monkeypatch, _core(), PARTY_YES)
    a.hear(GUEST_LINE)
    assert m.open_loops()[0]["owes"] is None, \
        ("the mark is unlowerable: a working reversal saying he is a party "
         "cannot undo one written when nothing was asked")


def test_a_withdrawal_is_recorded_on_the_promise_not_just_applied(monkeypatch):
    """A silent erase is indistinguishable from a promise nobody ever judged,
    and that ambiguity is what made the erase a weapon last time. The store
    keeps that a verdict was made and taken back, and why."""
    a, m = _triaging_brain(monkeypatch, owes="other", party=PARTY_UNASKED,
                           decision="say", goal=None)
    a.hear(GUEST_LINE)
    _script_party(monkeypatch, _core(), PARTY_YES)
    a.hear(GUEST_LINE)
    attrs = json.loads(m.db.execute(
        "SELECT attrs FROM nodes WHERE id=?",
        (m.open_loops()[0]["id"],)).fetchone()[0])
    assert attrs.get("owes_withdrawn", {}).get("reason"), \
        "the verdict vanished with no record that anything was withdrawn"
    assert attrs["owes_withdrawn"]["ts"] > 0


def test_a_withdrawal_survives_the_same_sentence_being_heard_again():
    """The withdrawal record rides in the SAME attrs blob as `owes`, so it
    rests on _upsert_node updating only last_seen_ts and never rewriting
    attrs. That property was verified by reading and pinned by nothing; it is
    load-bearing for two features now, so it is pinned here. If it ever
    changes, a re-heard sentence silently resurrects a verdict that was
    deliberately taken back."""
    m = _store(":memory:")
    mem = m.ingest(GUEST_LINE)
    m.attribute_commitment(mem["commitment_id"], owes="other")
    assert m.withdraw_attribution(mem["commitment_id"], "the reversal says he "
                                  "is a party") is True
    again = m.ingest(GUEST_LINE)
    assert again["commitment_id"] == mem["commitment_id"], \
        "the same sentence produced a second node — the premise is gone"
    assert m.open_loops()[0]["owes"] is None, \
        "re-hearing the sentence resurrected a withdrawn verdict"
    attrs = json.loads(m.db.execute(
        "SELECT attrs FROM nodes WHERE id=?",
        (mem["commitment_id"],)).fetchone()[0])
    assert attrs.get("owes_withdrawn", {}).get("reason")


def _core():
    import brain.anticipy_core as core
    return core


# ------------------------------------- the named erase, at its own layer


def test_withdrawing_an_attribution_needs_a_reason(monkeypatch):
    """The difference between this method and the falsy-argument erase it
    replaces is not the SQL. It is that a caller must know they are erasing:
    a correction with no reason is reachable from every path that happens to
    hold an empty variable, which is exactly how the last one fired."""
    m = _store(":memory:")
    mem = m.ingest(GUEST_LINE)
    m.attribute_commitment(mem["commitment_id"], owes="other")
    assert m.withdraw_attribution(mem["commitment_id"], "") is False
    assert m.withdraw_attribution(mem["commitment_id"], "   ") is False
    assert m.withdraw_attribution(mem["commitment_id"], None) is False
    assert m.open_loops()[0]["owes"] == "other", \
        "a reasonless call erased the verdict — the old bug under a new name"


def test_withdrawing_reports_whether_it_actually_removed_anything():
    """A caller must not be able to read "there was nothing to withdraw" as
    "the withdrawal worked" — that is how a fix goes green while doing
    nothing."""
    m = _store(":memory:")
    mem = m.ingest(GUEST_LINE)
    assert m.withdraw_attribution(mem["commitment_id"], "no mark yet") is False
    m.attribute_commitment(mem["commitment_id"], owes="other")
    assert m.withdraw_attribution(
        mem["commitment_id"], "the reversal says he is a party") is True
    assert m.open_loops()[0]["owes"] is None
    assert m.withdraw_attribution(None, "no id at all") is False


def _clock_against(memory, loop_id):
    """clock_tick over a REAL Memory, with the model naming the loop that
    memory actually holds — the ids a live store hands out are not the ones a
    stand-in invents, and a model naming a loop that is not there gets its
    goal dropped by the authority check one block earlier. A leg that means
    to test the fence has to reach the fence."""
    class _NamesIt:
        owner_zone = "America/Vancouver"
        # LIVE, and routing on the prompt. clock_tick asks a SECOND question
        # before it prepares anything — work_is_licensed() — and a double that
        # answers every system prompt with its one canned clock reply answers
        # that one with something unreadable, which refuses. These legs are
        # about the GUEST fence, so the licence is granted and the guest fence
        # is left as the only thing that can stop the job.
        live = True

        def chat(self, system="", *_a, **_k):
            reply = licence_reply(system) or json.dumps({
                "initiate": True,
                "say": "Want me to get that pitch deck ready?",
                "goal": "draft the pitch deck email",
                "loop_ids": [loop_id],
            })

            class R:
                text = reply
            return R()

    queued = []
    clock = Anticipy(memory=memory, llm=_NamesIt(), owner_phone=None)
    clock._queue_job = lambda goal, params, hold=False, **_k: (
        queued.append(goal) or "job")
    return clock.clock_tick(now=memory.open_loops()[0]["ts"] + 7200), queued


def test_the_clock_still_refuses_after_a_no_verdict_second_hearing(monkeypatch):
    """THE BEHAVIOURAL LEG — the failure itself, not the field it turns on.
    Asserting the stored mark alone would go green the moment somebody made
    the pop conditional somewhere else; what must never come back is the
    browser job that chases the owner about the guest's promise."""
    a, m = _triaging_brain(monkeypatch, owes="other")
    a.hear(GUEST_LINE)
    _retriage(monkeypatch, a, owes=None, decision="ignore", goal=None)
    a.hear(GUEST_LINE)

    out, queued = _clock_against(m, m.open_loops()[0]["id"])
    assert (out or {}).get("goal") is None, \
        "the owner is being chased about the guest's promise again"
    assert queued == []


def test_that_clock_really_would_have_minted_the_job_without_the_mark(monkeypatch):
    """THE CONTROL. Without it the leg above passes for whatever reason the
    clock happens to stay quiet — and it very nearly did: the goal was being
    dropped by the unevidenced-source check, not the fence, because the model
    was naming a loop id the real store had never issued. Same store, same
    sentence, only the mark absent: the job appears."""
    a, m = _triaging_brain(monkeypatch, owes="owner")
    a.hear(GUEST_LINE)
    assert m.open_loops()[0]["owes"] is None
    out, queued = _clock_against(m, m.open_loops()[0]["id"])
    assert out["goal"] == "draft the pitch deck email"
    assert queued == ["draft the pitch deck email"]


def test_the_clock_starts_working_again_once_a_stuck_mark_is_withdrawn(
        monkeypatch):
    """THE BEHAVIOURAL LEG FOR THE LOWERING, asserted where the owner feels
    it. A mark written with no live model to ask made clock_tick refuse this
    loop permanently. After a working reversal withdraws it, his own work is
    prepared again — which is the whole difference between a fence and a
    wall, and it is not visible from the stored field alone."""
    a, m = _triaging_brain(monkeypatch, owes="other", party=PARTY_UNASKED,
                           decision="say", goal=None)
    a.hear(GUEST_LINE)
    stuck, _ = _clock_against(m, m.open_loops()[0]["id"])
    assert (stuck or {}).get("goal") is None, "control: the fence was up"

    _script_party(monkeypatch, _core(), PARTY_YES)
    a.hear(GUEST_LINE)
    out, queued = _clock_against(m, m.open_loops()[0]["id"])
    assert out["goal"] == "draft the pitch deck email", \
        "the fence stayed up after the only verdict allowed to lower it"
    assert queued == ["draft the pitch deck email"]


# ----------------------------------- I2: an explicit line is not second-guessed


def test_an_explicit_line_is_not_second_guessed_by_the_reversal(monkeypatch):
    """THE CHECK THAT WOULD HAVE CAUGHT I2. The routing branch exempts
    explicit lines on a stated principle — "he is the one asking, and no
    second opinion overrides him" — and the write did not honour it.
    Reproduced before the fix:

        explicit=True  owner_is_party=True  -> owes=None    party calls=1
        explicit=True  owner_is_party=False -> owes='other' party calls=1

    Failure scenario: he texts her "Bob said he'll send the deck tomorrow —
    keep an eye on it." Triage is RIGHT that Bob owes it. The reversal, shown
    only the line and the task, says True because it is his deck, the mark is
    suppressed, and that night the clock mints a browser job to draft the deck
    email — through the one path the code says must not be second-guessed."""
    a, m = _triaging_brain(monkeypatch, owes="other", party=PARTY_YES)
    a.hear(GUEST_LINE, explicit=True)
    assert m.open_loops()[0]["owes"] == "other", \
        ("a second opinion overrode the owner on a line he typed AT her — "
         "and the clock is now free to prepare Bob's promise as his errand")


def test_an_explicit_line_does_not_even_pay_for_the_reversal(monkeypatch):
    """The mark being right is not enough — it must be right for the stated
    reason. If the call still fires, the exemption is a coincidence of which
    way the model answered, and it reverts the first time it answers the
    other way."""
    import brain.anticipy_core as core
    calls = []
    m = _store(":memory:")
    a = Anticipy(memory=m, llm=None, owner_id="t", owner_phone=None)
    monkeypatch.setattr(a, "_queue_job", lambda *a_, **k_: "job")
    monkeypatch.setattr(a, "_decide", lambda *a_, **k_: Decision(
        decision="act", goal="send the pitch deck", reason="scripted",
        addressee="assistant", owes="other"))
    monkeypatch.setattr(core, "party_verdict",
                        lambda *a_, **k_: calls.append(1) or PARTY_NO)
    a.hear(GUEST_LINE, explicit=True)
    assert calls == [], \
        "the reversal was asked about a line the owner typed at her himself"



# ------------------------- I3: the mark reaches the briefing, so it takes the
#                               higher of its two readers' bars
#
# clock_tick refuses to PREPARE work off the mark — a wrong "other" costs one
# lost job and her `say` still carries. briefing_facts() feeds BRIEFING_SYSTEM,
# which is told "other" means somebody else made the promise and to never say
# the owner did — a wrong "other" there tells him his own dinner belongs to his
# friend, or drops it from the briefing entirely. The reversal used to run only
# on act/ask, so a `say` or `ignore` verdict wrote an uncorrected mark straight
# into the prompt.


def test_a_say_verdict_asks_the_reversal_before_marking_the_promise(monkeypatch):
    """The recorded dinner failure, routed the way it was actually routed.
    The friend says "I'll text you a time" at a dinner the owner plainly
    agreed to; triage files it under the friend and decides to SAY something.
    owner_is_party is the model that gets this right, and it must be asked
    before the store — and therefore the briefing — believes triage."""
    a, m = _triaging_brain(monkeypatch, owes="other", party=PARTY_YES,
                           decision="say", goal=None)
    a.hear(GUEST_LINE)
    assert m.open_loops()[0]["owes"] is None, \
        ("the briefing will now be told the owner's own plan is somebody "
         "else's, and told never to say he promised it")


def test_an_ignore_verdict_asks_the_reversal_too(monkeypatch):
    a, m = _triaging_brain(monkeypatch, owes="other", party=PARTY_YES,
                           decision="ignore", goal=None)
    a.hear(GUEST_LINE)
    assert m.open_loops()[0]["owes"] is None


def test_an_ignore_verdict_still_marks_a_promise_that_really_is_the_guests(
        monkeypatch):
    """THE NEGATIVE CONTROL THE `ignore` LEG WAS MISSING. Its `say` sibling
    has had one since it was written; this one asserted only that the mark was
    ABSENT, which is equally true if the write never fires for `ignore` at
    all. Mutation-proven: gating the write on `decision.decision != "ignore"`
    left the whole file green.

    That is not a cosmetic gap. `ignore` is the lane where OVERHEARD GUEST
    SPEECH ACTUALLY LANDS — a guest says "I'll send you the pitch deck
    tomorrow", triage routes it ambient as `ignore` with owes="other", and
    ingest() has already created the commitment. An unmarked commitment there
    is the original brief's failure, on the busiest path to it."""
    a, m = _triaging_brain(monkeypatch, owes="other", party=PARTY_NO,
                           decision="ignore", goal=None)
    a.hear(GUEST_LINE)
    assert m.open_loops()[0]["owes"] == "other", \
        ("the ambient lane wrote no mark, so the clock is free to mint the "
         "browser job from a promise somebody else made")


def test_a_say_verdict_still_marks_a_promise_that_really_is_the_guests(monkeypatch):
    """The other direction, and the one that matters more: raising the bar for
    writing the mark must not lower the fence. owner_is_party says no, so the
    guest's promise is marked exactly as before, on a decision that never
    reached the reversal at all until now."""
    a, m = _triaging_brain(monkeypatch, owes="other", party=PARTY_NO,
                           decision="say", goal=None)
    a.hear(GUEST_LINE)
    assert m.open_loops()[0]["owes"] == "other"


def test_the_briefing_never_sees_an_attribution_the_code_has_withdrawn(monkeypatch):
    """The sink, asserted at the sink. briefing_facts() is what BRIEFING_SYSTEM
    is handed, so this is the leg that says the owner is not told his own
    dinner was somebody else's."""
    a, m = _triaging_brain(monkeypatch, owes="other", party=PARTY_YES,
                           decision="say", goal=None)
    a.hear(GUEST_LINE)
    loop = m.briefing_facts(since_ts=0)["open_loops"][0]
    assert loop["owes"] is None


def test_hear_marks_nothing_when_triage_says_the_promise_is_his(monkeypatch):
    a, m = _triaging_brain(monkeypatch, owes="owner")
    a.hear(GUEST_LINE)
    assert m.open_loops()[0]["owes"] is None


def test_the_briefing_is_handed_the_attribution_and_told_what_it_means():
    """The clock is not the only thing that reads an open loop. `briefing()`
    JSON-dumps the whole loop record into BRIEFING_SYSTEM, so telling him he
    promised something a guest promised is the same lie one layer up — and a
    key in the payload that the prompt never explains is evidence the model
    has to guess at."""
    from brain.anticipy_core import BRIEFING_SYSTEM
    m = _store(":memory:")
    m.ingest(GUEST_LINE, speaker="other")
    loop = m.briefing_facts(since_ts=0)["open_loops"][0]
    assert loop["speaker"] == "other"
    assert "owes" in loop
    assert "speaker" in BRIEFING_SYSTEM and '"owes"' in BRIEFING_SYSTEM


# ------------------------------------------------------- the clock's refusal

class _Loops:
    """Just enough Memory for clock_tick — the same stand-in
    tests/test_clock_authority.py uses, plus the attribution."""

    def __init__(self, **extra):
        self.loop = {"id": 7, "what": "send the pitch deck",
                     "source": "I'll send you the pitch deck tomorrow morning.",
                     "ts": 1000, "speaker": None, "owes": None}
        self.loop.update(extra)

    def open_loops(self):
        return [dict(self.loop)]


class _LLM:
    owner_zone = "America/Vancouver"
    # See _NamesIt above: live, and the licence question answered as its own
    # question so these legs measure the guest fence and nothing else.
    live = True

    def chat(self, system="", *_a, **_k):
        reply = licence_reply(system) or json.dumps({
            "initiate": True,
            "say": "Want me to get that pitch deck ready?",
            "goal": "draft the pitch deck email",
            "loop_ids": [7],
        })

        class R:
            text = reply
        return R()


def _clock(**extra):
    a = Anticipy(memory=_Loops(**extra), llm=_LLM(), owner_phone=None)
    queued = []
    a._queue_job = lambda goal, params, hold=False, **_k: queued.append(
        (goal, hold)) or "job"
    return a.clock_tick(now=2000), queued


def test_the_clock_will_not_prepare_work_off_a_guests_promise():
    out, queued = _clock(speaker="other")
    assert out["goal"] is None, \
        "the clock minted a job from a promise somebody else made"
    assert queued == []
    assert out["say"], "the reminder survives — this fences the action, not her voice"


def test_the_model_saying_someone_else_owes_it_fences_the_clock_too():
    out, queued = _clock(owes="other")
    assert out["goal"] is None
    assert queued == []


def test_no_verdict_leaves_the_clock_exactly_as_it_was():
    """THE HONESTY WALL. This is the leg that stops the fix from deleting the
    product on the 100% of live lines that carry no voice verdict."""
    out, queued = _clock()
    assert out["goal"] == "draft the pitch deck email"
    assert queued and queued[0][0] == "draft the pitch deck email"


def test_the_owners_own_promise_still_prepares_work():
    out, queued = _clock(speaker="owner")
    assert out["goal"] == "draft the pitch deck email"
    assert queued


# ----------------------------- I2: WHICH loops does the goal actually rest on
#
# `selected` is `[l for l in fresh if not loop_ids or l["id"] in loop_ids]`, so
# a model that omits `loop_ids` — the field CLOCK_SYSTEM does not require, and
# the field :3421 silently empties when an id is not a digit string — makes it
# EVERY fresh loop in the store. Asking `any()` over the whole store means one
# guest promise fences every goal the clock will ever prepare, and nothing ever
# closes a guest's commitment, so it fences them again every night forever.


class _ManyLoops:
    """A store with more than one open loop, which is the ordinary case and
    the case the single-loop stand-in above could never express."""

    def __init__(self, *loops):
        self.loops = list(loops)

    def open_loops(self):
        return [dict(loop) for loop in self.loops]


def _loop(id_, what, source, **extra):
    row = {"id": id_, "what": what, "source": source, "ts": 1000,
           "speaker": None, "owes": None}
    row.update(extra)
    return row


HIS = _loop(1, "book the Earls table for Friday",
            "I need to book the Earls table for Friday", owes="owner")
GUESTS = _loop(7, "send the pitch deck",
               "I'll send you the pitch deck tomorrow morning.", owes="other")


def _clock_over(loops, goal, loop_ids=None, licence_needs=None):
    """clock_tick against a multi-loop store, with the model's reply — and in
    particular whether it named any loop_ids — under the test's control.

    `licence_needs` scripts the SECOND question clock_tick asks before it
    prepares anything (orchestrator.work_is_licensed): the stand-in grants the
    licence only if that string is among the quotes it was actually handed.
    That is how a scope test stays a scope test now that no regex reads the
    quotes — a loop beyond the payload cap cannot license work precisely
    because its words never reach the model. Left None, the licence is granted
    and the guest fence below is the only thing that can stop the job."""
    reply = {"initiate": True, "say": "Want me to sort that?", "goal": goal}
    if loop_ids is not None:
        reply["loop_ids"] = loop_ids

    class _Reply:
        owner_zone = "America/Vancouver"
        live = True

        def chat(self, system="", user="", **_k):
            if licence_reply(system) is not None:
                body = licence_reply(
                    system, licence_needs is None or licence_needs in user)
            else:
                body = json.dumps(reply)

            class R:
                text = body
            return R()

    a = Anticipy(memory=_ManyLoops(*loops), llm=_Reply(), owner_phone=None)
    queued = []
    a._queue_job = lambda g, params, hold=False, **_k: queued.append(g) or "job"
    return a.clock_tick(now=2000), queued


def test_a_guest_promise_elsewhere_in_the_store_does_not_disable_his_own_goal():
    """THE CHECK THAT WOULD HAVE CAUGHT I2. The owner says "I need to book the
    Earls table for Friday" and a guest at the same dinner says "I'll send you
    the pitch deck tomorrow". That night the clock acts on the Earls booking
    and names no loop_ids. His own booking must still be prepared."""
    out, queued = _clock_over([HIS, GUESTS], "book the Earls table for Friday")
    assert out["goal"] == "book the Earls table for Friday", \
        ("one guest promise disabled every clock-prepared goal — and since "
         "nothing ever closes a guest's commitment, it does so every night")
    assert queued == ["book the Earls table for Friday"]


def test_a_named_guest_loop_fences_even_beside_one_of_his():
    """When the model DOES say which loops it is acting on, those are the
    loops the goal rests on and one not-his verdict among them is enough. The
    job is keyed to loop_ids[0], so this is the set the work is bound to."""
    out, queued = _clock_over([HIS, GUESTS], "send the pitch deck",
                              loop_ids=[1, 7])
    assert out["goal"] is None
    assert queued == []
    assert out["say"], "the fence takes the action, never her voice"


def test_a_named_loop_of_his_beside_a_guests_still_prepares_work():
    out, queued = _clock_over([HIS, GUESTS], "book the Earls table for Friday",
                              loop_ids=[1])
    assert out["goal"] == "book the Earls table for Friday"
    assert queued


def test_an_unnamed_goal_over_nothing_but_guest_promises_is_still_fenced():
    """The original brief's failure, with the model naming nothing. Every
    candidate loop is somebody else's, so the goal can only have come from
    somebody else's — narrowing the set must not lose this."""
    other_guest = _loop(9, "drop off the keys",
                        "I'll drop the keys off on Sunday.", owes="other")
    out, queued = _clock_over([GUESTS, other_guest], "draft the pitch deck email")
    assert out["goal"] is None
    assert queued == []


def test_a_loop_from_before_attribution_existed_still_prepares_work():
    """Every commitment already in every owner's database has no attribution
    key at all. Reading a missing key as "not his" would silently retire every
    loop she has ever recorded."""
    a = Anticipy(memory=_Loops(), llm=_LLM(), owner_phone=None)
    a.memory.loop.pop("speaker")
    a.memory.loop.pop("owes")
    queued = []
    a._queue_job = lambda goal, params, hold=False, **_k: queued.append(goal) or "job"
    out = a.clock_tick(now=2000)
    assert out["goal"] == "draft the pitch deck email"
    assert queued


# ------------- I4: the fence must range over the loops the model was SHOWN,
#                   and an unreadable answer is not an answer
#
# The payload has always been capped at ten loops while every check below ran
# over the whole of `fresh`, so a loop the model could not have acted on —
# because it never saw it — voted on whether the goal was somebody else's, and
# on whether any quote licensed preparing work at all. And `raw.get("loop_ids",
# [])` plus the isdigit() filter turned [3.0] or ["seven"] silently into [],
# the same value a model that named nothing produces, dropping the goal into
# the unnamed branch whose all() only fences when EVERY open loop in the store
# belongs to somebody else.


def test_the_not_his_fence_only_ranges_over_the_loops_the_model_was_shown():
    """THE CHECK THAT WOULD HAVE CAUGHT I4's first half. Ten guest promises
    are shown; an eleventh loop, his own, sits beyond the cap where the model
    never saw it. The goal can only have come from a loop the model was shown,
    and every one of those is somebody else's. Before the fix the hidden loop
    made `all()` false and the guest-derived job was prepared."""
    guests = [_loop(i, f"guest promise {i}", f"I'll send you thing {i}.",
                    owes="other") for i in range(1, 11)]
    hidden = _loop(99, "book the Earls table",
                   "I need to book the Earls table", owes="owner")
    out, queued = _clock_over(guests + [hidden], "draft the pitch deck email")
    assert out["goal"] is None, \
        ("a loop beyond the ten the model was shown lifted the fence on a "
         "goal it could not possibly have come from")
    assert queued == []


def test_a_loop_the_model_never_saw_cannot_authorise_preparing_work():
    """The same drift in the authority check one block up, which reads the
    same set. Ten shown loops carry no owner-authored obligation; an eleventh,
    beyond the cap, does. Before the fix that invisible quote licensed work the
    model had no evidence for."""
    bland = [_loop(i, f"loop {i}", f"the weather was fine on day {i}.")
             for i in range(1, 11)]
    authored = _loop(99, "book the table", "I need to book the Earls table")
    out, queued = _clock_over(bland + [authored], "draft the pitch deck email",
                              licence_needs="book the Earls table")
    assert out["goal"] is None, \
        "a quote the model never saw authorised the work it prepared"
    assert queued == []
    # THE CONTROL. Without it this leg passes for whatever reason the licence
    # happens to be refused. Same store, same goal, the authoring quote now
    # inside the cap: the work is prepared, so the leg above is measuring the
    # cap and not something else.
    out, queued = _clock_over([authored] + bland[:9], "draft the pitch deck email",
                              licence_needs="book the Earls table")
    assert out["goal"] == "draft the pitch deck email"
    assert queued == ["draft the pitch deck email"]


def test_loop_ids_that_cannot_be_read_drop_the_goal_instead_of_guessing():
    """THE CHECK THAT WOULD HAVE CAUGHT I4's second half. The model named
    loops and we cannot tell which. That is not "it named nothing" — it is an
    answer we cannot read, and the honesty wall this whole file stands on says
    an answer nobody gave is not an answer. Reproduced before the fix on the
    ordinary two-loop store: both malformed shapes prepared the guest's job."""
    # Every shape here must be unreadable for the RIGHT reason. "7" as a bare
    # string is not one of them: it coerces to a readable [7], and the goal
    # would then be dropped by the not-his fence instead — the assertion would
    # pass while testing nothing, which is the disease this wave exists to
    # find. Loop 1 is the OWNER's, so if any shape here were readable as [1]
    # the goal would survive and this leg would go red.
    for mangled in ([3.0], ["seven"], [None], ["1x"], [{"id": 1}]):
        out, queued = _clock_over([HIS, GUESTS], "draft the pitch deck email",
                                  loop_ids=mangled)
        assert out["goal"] is None, \
            f"an unreadable loop_ids ({mangled!r}) was guessed at, not refused"
        assert queued == []
        assert out["say"], "the fence takes the action, never her voice"


def test_an_unreadable_loop_ids_is_not_read_as_naming_nothing():
    """The distinction, stated where it can regress. A model that named
    nothing keeps the permissive unnamed branch — that is the leg above this
    one, and it must not be collateral damage. Same store, same goal, the only
    difference being whether the field was present and unreadable."""
    named_nothing, queued = _clock_over(
        [HIS, GUESTS], "book the Earls table for Friday", loop_ids=None)
    assert named_nothing["goal"] == "book the Earls table for Friday"
    assert queued == ["book the Earls table for Friday"]
    unreadable, queued = _clock_over(
        [HIS, GUESTS], "book the Earls table for Friday", loop_ids=[3.0])
    assert unreadable["goal"] is None


def test_the_clock_prompt_requires_the_loops_a_goal_rests_on():
    """The residual the unnamed branch leaves open cannot be closed by a
    stricter operator here — that only rebuilds "one guest promise disables
    every goal forever". It closes when the MODEL says which loop it acted on,
    so the prompt has to ask for that rather than merely accept it. Whether it
    obeys is not knowable from the repo; it waits on LIVE."""
    from brain.anticipy_core import CLOCK_SYSTEM
    assert "loop_ids" in CLOCK_SYSTEM
    assert "MUST" in CLOCK_SYSTEM, \
        "the prompt accepts loop_ids without ever asking for them"


# ------------------------------------------------------------- the migration

_PRE_SPEAKER_SCHEMA = """
CREATE TABLE episodes (
    id INTEGER PRIMARY KEY,
    ts REAL NOT NULL,
    text TEXT NOT NULL
);
CREATE TABLE nodes (
    id INTEGER PRIMARY KEY,
    type TEXT NOT NULL,
    name TEXT NOT NULL,
    attrs TEXT NOT NULL DEFAULT '{}',
    status TEXT,
    created_ts REAL NOT NULL,
    last_seen_ts REAL NOT NULL,
    UNIQUE(type, name)
);
CREATE TABLE profile_facts (
    id INTEGER PRIMARY KEY,
    fact TEXT NOT NULL,
    importance INTEGER NOT NULL DEFAULT 3,
    confidence REAL NOT NULL DEFAULT 0.6,
    source TEXT NOT NULL DEFAULT 'consolidation',
    provenance TEXT NOT NULL DEFAULT '[]',
    first_seen_ts REAL NOT NULL,
    last_seen_ts REAL NOT NULL
);
"""


def _old_database(tmp_path):
    db = tmp_path / "mem.db"
    conn = sqlite3.connect(db)
    conn.executescript(_PRE_SPEAKER_SCHEMA)
    conn.execute("INSERT INTO episodes(ts, text) VALUES (1.0, 'an old line')")
    conn.execute("INSERT INTO profile_facts(fact, first_seen_ts, last_seen_ts) "
                 "VALUES ('partner is Sarah', 1.0, 1.0)")
    conn.commit()
    conn.close()
    return db


def test_an_existing_owners_database_gains_the_column(tmp_path):
    """`CREATE TABLE IF NOT EXISTS` reaches an old database with a new TABLE
    and never with a new COLUMN. Every current owner has a file already."""
    db = _old_database(tmp_path)
    m = _store(path=db)
    assert m.db.execute("SELECT COUNT(*) FROM episodes").fetchone()[0] == 1
    assert len(m.profile_facts()) == 1
    m.ingest(GUEST_LINE, speaker="other")
    assert m.open_loops()[0]["speaker"] == "other"


def test_opening_the_same_database_twice_is_not_an_error(tmp_path):
    """The retrofit runs on every open. The second one finds the column
    already there, and that is the normal case, not a failure."""
    db = _old_database(tmp_path)
    _store(path=db).ingest(GUEST_LINE, speaker="other")
    m = _store(path=db)
    assert m.open_loops()[0]["speaker"] == "other"


class _AlterRefused:
    """A connection whose ALTER statements fail the way a locked or damaged
    file fails — with the same OperationalError that "duplicate column name"
    arrives as. Everything else is a real SQLite connection."""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, *a):
        if sql.lstrip().upper().startswith("ALTER TABLE"):
            raise sqlite3.OperationalError("database is locked")
        return self._conn.execute(sql, *a)

    def __getattr__(self, name):
        return getattr(self._conn, name)


def test_a_retrofit_that_cannot_run_fails_the_open_instead_of_degrading(
        tmp_path, monkeypatch):
    """"duplicate column name" is the ordinary case and is swallowed. A locked
    or damaged file raises the SAME exception class, and swallowing THAT would
    leave the store one column short for good while every later read of it
    failed somewhere far away with no clue why. The open is the only place
    that knows what went wrong, so it is the place that says so."""
    import pytest

    import brain.memory as memory_module
    db = _old_database(tmp_path)
    real = memory_module.sqlite3.connect
    monkeypatch.setattr(memory_module.sqlite3, "connect",
                        lambda *a, **k: _AlterRefused(real(*a, **k)))
    with pytest.raises(sqlite3.OperationalError):
        Memory(path=db)


def _columns(db, table):
    return {r[1]: r[2] for r in
            db.execute(f"PRAGMA table_info({table})").fetchall()}


def test_a_retrofitted_database_has_the_same_shape_as_a_fresh_one(tmp_path):
    """The column is written down twice — once in SCHEMA for new databases,
    once in the retrofit list for old ones. Two declarations drift; this is
    the check that notices."""
    fresh = Memory(":memory:")
    migrated = Memory(path=_old_database(tmp_path))
    for table in ("episodes", "profile_facts"):
        assert _columns(fresh.db, table) == _columns(migrated.db, table), table


# ====================================== the DESTRUCTIVE decisions hear it too
# `episodes.speaker` was stored, was carried onto every commitment and into
# briefing_facts, and was dropped at exactly the two places where a line can
# KILL a fact or put a value into a form. LAW 5 order: the sense exists and is
# captured, and the destructive decision was the one place it was not passed
# along.
#
# Reproduced against the shipped code, ONE scenario, TWO doors:
#
#   episodes: (1,'owner','Dana and I are heading to Lisbon.')
#             (2,'other',"Oh, didn't you hear? Omar and Dana broke up.")
#   listing the model saw: "[2] Oh, didn't you hear? Omar and Dana broke up."
#   live profile: ['broke up with Dana']
#   retired:      ('partner is Dana', ..., source='consolidation')
#
#   recall(...) -> src_type='episode' source=<absent> — trusted half of
#   memory_notes, unfenced, and eligible to settle a gap in an approved plan.
#
# One tag closes both: memory.OVERHEARD is in _UNTRUSTED_SOURCES, so the fence
# every consumer already keys on does the rest.

import time  # noqa: E402

from brain.anticipy_core import _UNTRUSTED_SOURCES, memory_notes  # noqa: E402
from brain.memory import OVERHEARD, RETIRED_EXCLUDED  # noqa: E402
from llm_fakes import FakeLLM  # noqa: E402

DAY = 86400.0


def _breakup_overheard(now, speaker):
    """The owner says one thing forty days ago; somebody in earshot
    contradicts it yesterday. `speaker` is the phone's verdict on THAT second
    line and is the only thing that varies."""
    llm = FakeLLM(
        consolidations=[
            {"facts": [{"fact": "partner is Dana", "importance": 5,
                        "episode_ids": [1], "kind": "stable"}]},
            {"facts": [{"fact": "broke up with Dana", "importance": 3,
                        "episode_ids": [2]}]},
        ],
        relations=["replaces"])
    m = Memory(":memory:", llm=llm)
    m.ingest("Dana and I are heading to Lisbon.", ts=now - 40 * DAY,
             speaker="owner")
    m.consolidate(now=now - 40 * DAY)
    m.ingest("Oh, didn't you hear? Omar and Dana broke up.", ts=now - DAY,
             speaker=speaker)
    m.consolidate(now=now - DAY)
    return m, llm


def test_the_consolidation_listing_says_who_spoke():
    """The listing was f"[{r[0]}] {r[2]}" — id and text. The judgement stays
    with the model that can see the whole day; what changed is that it is no
    longer being asked blind."""
    now = time.time()
    _m, llm = _breakup_overheard(now, "other")
    shown = llm.consolidation_calls()[-1]
    assert "NOT them" in shown, shown
    _m2, llm2 = _breakup_overheard(now, "owner")
    assert "(them)" in llm2.consolidation_calls()[-1]


def test_an_unattributed_line_is_listed_exactly_as_it_always_was():
    """The honesty wall, at the prompt. Live roster coverage is 0%, so almost
    every line carries no verdict; a tag on every line would teach the model
    that an untagged line is unusual, and it is the ordinary case."""
    now = time.time()
    _m, llm = _breakup_overheard(now, None)
    shown = llm.consolidation_calls()[-1]
    assert shown == "[2] Oh, didn't you hear? Omar and Dana broke up.", shown


def test_a_line_the_phone_says_was_not_the_owner_cannot_retire_what_he_said():
    """The harm, end to end. A colleague, a guest or a television says "they
    broke up" in earshot and the fact the OWNER stated dies. The fact still
    lands — it just does not get to kill anything, exactly as a mailed one
    does not."""
    now = time.time()
    m, _llm = _breakup_overheard(now, "other")
    live = sorted(f["fact"] for f in m.profile_facts())
    assert live == ["broke up with Dana", "partner is Dana"], live
    assert m.db.execute(
        "SELECT COUNT(*) FROM profile_facts WHERE retired_ts IS NOT NULL"
    ).fetchone()[0] == 0


def test_the_owners_own_line_still_retires_what_he_said_before():
    """The direction that must NOT be fenced, or the feature is off. Same
    scenario, same model verdict; only the voice tag differs."""
    now = time.time()
    m, _llm = _breakup_overheard(now, "owner")
    assert [f["fact"] for f in m.profile_facts()] == ["broke up with Dana"]


def test_an_unattributed_line_still_retires():
    """And absence is not a verdict. With 0% roster coverage, reading "we do
    not know who said this" as "not him" would turn supersession off for every
    owner the product has."""
    now = time.time()
    m, _llm = _breakup_overheard(now, None)
    assert [f["fact"] for f in m.profile_facts()] == ["broke up with Dana"]


def test_a_fact_distilled_only_from_other_peoples_lines_is_labelled():
    """The tag is on the ROW, so every consumer of _UNTRUSTED_SOURCES sees it
    without being told about voices — the provenance window, the briefing, the
    prompt fence, the gap filler."""
    now = time.time()
    m, _llm = _breakup_overheard(now, "other")
    got = dict(m.db.execute("SELECT fact, source FROM profile_facts"))
    assert got["broke up with Dana"] == OVERHEARD, got
    assert got["partner is Dana"] == "consolidation", got
    assert OVERHEARD in _UNTRUSTED_SOURCES


def test_one_line_of_his_in_the_evidence_is_enough_to_make_it_ordinary():
    """EVERY contributing line has to be a positive "not the owner". A fact
    the owner's own words are part of is not a stranger's report, and neither
    is one built partly from lines nobody could place."""
    now = time.time()
    llm = FakeLLM(consolidations=[{"facts": [
        {"fact": "the Devon deal closes Friday", "importance": 3,
         "episode_ids": [1, 2]}]}])
    m = Memory(":memory:", llm=llm)
    m.ingest("Devon said Friday.", ts=now - DAY, speaker="other")
    m.ingest("Yes, Friday works for me.", ts=now, speaker="owner")
    m.consolidate(now=now)
    assert [f["source"] for f in m.profile_facts()] == ["consolidation"]


# ------------------------------------------- and the same tag, at the prompt


def _overheard_store(now, speaker):
    m = _store(":memory:")
    m.ingest(KOWALSKI_LINE,
             ts=now - 2 * DAY, speaker=speaker)
    return m


def test_an_overheard_line_is_fenced_when_it_reaches_a_prompt():
    """I6, confirmed open in the §7 run: an episode row carried no `source`
    key at all, so `str(f.get("source") or "")` read "" — not in
    _UNTRUSTED_SOURCES — and a stranger's sentence landed in the TRUSTED half
    of memory_notes with no fence around it."""
    now = time.time()
    m = _overheard_store(now, "other")
    got = m.recall("reservation name", retired=RETIRED_EXCLUDED)
    assert got, "recall came back empty; the fixture is not exercising it"
    assert all(f.get("source") == OVERHEARD for f in got), got
    notes = memory_notes(got, budget=900)
    assert "UNTRUSTED" in notes, notes
    assert "Kowalski" in notes, notes


def test_the_edge_derived_from_an_overheard_line_is_fenced_too():
    """THE THIRD DOOR, found while checking the second. An edge is derived
    from ONE episode and carries its authority: fencing the episode row alone
    moved the same content one row down — "Kowalski —about→ reservation" —
    and let it through unfenced, and the gap filler still answered off it."""
    now = time.time()
    m = _overheard_store(now, "other")
    got = m.recall("reservation name", retired=RETIRED_EXCLUDED)
    edges = [f for f in got if f["src_type"] not in ("episode", "profile")]
    assert edges, [f["src_type"] for f in got]
    assert all(f.get("source") == OVERHEARD for f in edges), edges


def test_an_overheard_line_cannot_settle_a_gap_in_an_approved_plan():
    """fill_gaps_from_memory excludes untrusted text rather than fencing it,
    because the answer becomes a value the browser agent types into a real
    form. extension/agent_loop.js states the invariant: "a sentence she
    overheard could put a value into a form that spends his money." Asserted
    on the model never being ASKED — the safe branch is that she asks HIM."""
    import types

    from brain.orchestrator import fill_gaps_from_memory

    now = time.time()
    m = _overheard_store(now, "other")
    seen = {}

    class _LLM:
        live = True

        def chat(self, system, user, **kw):
            seen["known"] = user
            return types.SimpleNamespace(text=json.dumps({"answer": "Kowalski"}))

    filled, remaining = fill_gaps_from_memory(
        _LLM(), m, "book the table", ["reservation name"])
    assert filled == {}, filled
    assert remaining == ["reservation name"], remaining
    assert "known" not in seen, seen


def test_the_owners_own_line_still_settles_a_gap():
    """The direction that must not be fenced. His own words, and lines nobody
    could place, reach the gap filler exactly as they always have — otherwise
    this fence turns the feature off for every owner alive, since live roster
    coverage is 0% and almost every line carries no verdict.

    ASSERTED ROW BY ROW, not only on the outcome. Written as "the gap still
    got filled" this went GREEN against a mutation that fenced absence: recall
    returns the episode AND the edge derived from it, the mutation reached one
    of them, and the survivor answered the question. An outcome assertion over
    a set of rows cannot tell "nothing was fenced" from "not everything
    was"."""
    import types

    from brain.orchestrator import fill_gaps_from_memory

    now = time.time()
    for speaker in ("owner", None):
        m = _overheard_store(now, speaker)
        got = m.recall("reservation name", retired=RETIRED_EXCLUDED)
        assert len(got) >= 2, (speaker, got)   # episode AND derived edge
        assert [f.get("source") for f in got] == [""] * len(got), (speaker, got)
        assert "UNTRUSTED" not in memory_notes(got, budget=900), speaker
        seen = {}

        class _LLM:
            live = True

            def chat(self, system, user, **kw):
                seen["known"] = user
                return types.SimpleNamespace(
                    text=json.dumps({"answer": "Kowalski"}))

        filled, _rest = fill_gaps_from_memory(
            _LLM(), m, "book the table", ["reservation name"])
        assert filled == {"reservation name": "Kowalski"}, (speaker, filled)
        assert "Kowalski" in seen["known"], (speaker, seen)
