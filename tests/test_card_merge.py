"""A re-mention may ADD to a card; it must never bleach one out.

Live, 2026-08-09: "Book a table for 2 at Earls in West Vancouver for tomorrow
evening" was held; "I'll get that booked now" arrived as "Confirm Earls West
Van tomorrow at 7 PM" — same plan, and the merge REPLACED the goal with that
meta-wording. The booking verb, party size and venue details vanished, and
the browser agent read "Confirm …" as "send a confirmation" and opened Gmail.
"""

import json

from brain.anticipy_core import (Anticipy, exact_message_continuation,
                                explicitly_new_task,
                                progressive_action_continuation,
                                progressive_continuation)
from brain.memory import Memory
from brain.orchestrator import Decision


class _Job:
    def __init__(self, goal, params=None):
        self.rec = {"id": "job1", "goal": goal, "status": "awaiting_confirm",
                    "params": json.dumps(params or {})}


def _core(monkeypatch, job, patches):
    a = Anticipy(memory=Memory(":memory:"), llm=None, owner_id="t")
    monkeypatch.setattr(a, "_pending_jobs", lambda: [job.rec])
    import brain.anticipy_core as C

    class FakePB:
        @staticmethod
        def patch(url, json=None, timeout=10):
            patches.append(json)

        @staticmethod
        def post(url, json=None, timeout=10):
            class Response:
                @staticmethod
                def raise_for_status():
                    return None

                @staticmethod
                def json():
                    return {"id": "job2", "status": "awaiting_confirm"}

            return Response()
    monkeypatch.setattr(C, "pb", FakePB)
    return a


def test_a_meta_wording_never_overwrites_the_real_goal(monkeypatch):
    patches = []
    job = _Job("Book a table for 2 at Earls in West Vancouver for tomorrow "
               "evening, August 10th", {"source": "let's do drinks at Earls"})
    a = _core(monkeypatch, job, patches)
    a._merge_into("job1", job.rec, "Confirm Earls West Van tomorrow at 7 PM",
                  {"source": "booked now"})
    assert patches, "the new detail (7 PM) must be written somewhere"
    fields = patches[-1]
    assert "goal" not in fields, "the booking goal must survive untouched"
    params = json.loads(fields["params"])
    assert "7 PM" in params["update"]
    assert "let's do drinks at Earls" in params["source"], \
        "the original conversation must not be replaced by a fragment"
    assert "booked now" in params["source"]


def test_a_re_mention_that_names_the_venue_lands_on_the_card(monkeypatch):
    """Measured on his own 2026-08-04 dinner, 3 runs in 5.

    The card read "Confirm dinner reservation for 2 people tomorrow at 7 PM"
    and he then named the place. Judging the re-mention only by what it ERASES
    (confirm, reservation, people — three of seven, 0.43, over the third)
    refused the wording that carried the venue. The card kept no venue, she
    texted "what restaurant?" about a restaurant he had just said out loud,
    and a browser run released from that card had nowhere to go.

    What it ADDS is half the question, and here it is the deciding half.
    """
    patches = []
    job = _Job("Confirm dinner reservation for 2 people tomorrow at 7 PM",
               {"source": "let's go out tomorrow"})
    a = _core(monkeypatch, job, patches)
    named = "Book dinner for 2 at Cactus Club Park location tomorrow at 7 PM"
    a._merge_into("job1", job.rec, named, {"source": "cactus club park"})
    fields = patches[-1]
    assert fields.get("goal") == named, \
        "the wording that names the venue must become the card"
    assert "Cactus Club" in fields["goal"]


def test_a_genuinely_richer_wording_does_replace(monkeypatch):
    patches = []
    job = _Job("Book dinner at Earls tomorrow", {"source": "dinner at Earls"})
    a = _core(monkeypatch, job, patches)
    richer = "Book dinner at Earls tomorrow at 7 PM for 4 people"
    a._merge_into("job1", job.rec, richer, {"source": "make it 7 for four"})
    fields = patches[-1]
    assert fields.get("goal") == richer
    params = json.loads(fields["params"])
    assert "dinner at Earls" in params["source"]


def test_agreement_marker_plus_shared_plan_repairs_a_recognizer_split():
    first = "Open windshield claim on policy AUTO-33365 for highway stone damage"
    second = ("Schedule windshield repair for AUTO-33365 with Speedy Glass "
              "in Coquitlam next Tuesday")
    assert progressive_continuation(
        "yeah, agreed — cm crack in Coquitlam; use Speedy Glass", second, first)


def test_a_declared_separate_task_never_uses_progressive_merge():
    first = "Dispute invoice INV-49219 against PO-1173"
    second = "Send invoice INV-49219 to the finance team"
    assert not progressive_continuation(
        "Separate task, also send it to finance", second, first)


def test_explicit_new_task_language_is_a_hard_discourse_boundary():
    for line in (
        "Separate task, also submit the expense",
        "Another errand: book a second table",
        "On a separate note, send Maya the invoice",
        "Separately, renew the license",
        "This is a separate request: cancel the subscription",
    ):
        assert explicitly_new_task(line), line
    assert not explicitly_new_task("This is not a separate task; amend the first one")
    assert not explicitly_new_task("Keep working on the same task")


def test_explicit_second_task_cannot_be_merged_deduped_or_refined(monkeypatch):
    patches = []
    first = ("Submit Sofia Chen's talk Ambient AI Without Surprises to the "
             "Applied AI track as a 30-minute session")
    second = ("Submit a $100.06 client-meal expense from Lighthouse Table "
              "dated Saturday, category Meals, purpose investor product review")
    job = _Job(first, {"source": "submit the conference talk"})
    a = _core(monkeypatch, job, patches)
    a._open_plan = ("job1", __import__("time").time(), first)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("an explicit new task must bypass every merge judge")

    monkeypatch.setattr(a, "_same_plan", forbidden)
    monkeypatch.setattr(a, "_same_pending", forbidden)
    monkeypatch.setattr(a, "_refines_pending", forbidden)
    assert a._queue_job(
        second,
        {"source": "Separate task, also " + second},
        explicit=True,
    ) == "job2"
    assert patches == []
    assert a._open_plan[0] == "job2"


def test_exact_message_split_at_colon_is_reassembled_verbatim():
    assert exact_message_continuation(
        "we should get this sorted: Send Jonah Singh this exact message:",
        "yeah, agreed — I can meet after 3 PM tomorrow.") == (
            "Send Jonah Singh this exact message: I can meet after 3 PM tomorrow.")


def test_exact_message_split_survives_two_model_ignores(monkeypatch):
    a = Anticipy(memory=Memory(":memory:"), llm=None, owner_id="t")
    monkeypatch.setattr(a, "_decide", lambda *_args, **_kwargs: Decision(
        decision="ignore", goal=None, reason="model missed fragment",
        addressee="self", owes="nobody"))
    queued, notified = [], []
    monkeypatch.setattr(a, "_pending_jobs", lambda: [])
    monkeypatch.setattr(a, "_queue_job", lambda goal, params, **kwargs:
                        queued.append((goal, params, kwargs)) or "job1")
    a.notify_owner = lambda message, channel="sms": notified.append(message) or {"sent": True}

    first = "we should actually get this sorted: Send Jonah Singh this exact message:"
    second = "yeah, agreed — I can meet after 3 PM tomorrow."
    assert a.hear(first, speaker="owner")["decision"].decision == "ignore"
    result = a.hear(second, context=[first], speaker="owner")

    assert result["decision"].decision == "act"
    assert queued[0][0] == "Send Jonah Singh this exact message: I can meet after 3 PM tomorrow."
    assert len(notified) == 1


def test_exact_message_dialogue_outranks_a_false_dictation_guess(monkeypatch):
    import brain.anticipy_core as core

    a = Anticipy(memory=Memory(":memory:"), llm=None, owner_id="t")
    monkeypatch.setattr(core, "looks_like_dictation", lambda _line: True)
    monkeypatch.setattr(a, "_decide", lambda *_args, **_kwargs: Decision(
        decision="ignore", goal="", reason="mistaken for voice typing",
        addressee="dictation", owes="machine"))
    queued = []
    monkeypatch.setattr(a, "_pending_jobs", lambda: [])
    monkeypatch.setattr(a, "_queue_job", lambda goal, params, **kwargs:
                        queued.append((goal, kwargs)) or "job1")
    a.notify_owner = lambda *_args, **_kwargs: {"sent": True}

    first = "we should actually get this sorted: Send Malik Martin this exact message:"
    second = "yeah, agreed — The revised numbers are ready for review."
    a.hear(first, speaker="owner")
    result = a.hear(second, context=[first], speaker="owner")

    assert result["decision"].decision == "act"
    assert result["decision"].addressee == "person"
    assert queued == [("Send Malik Martin this exact message: "
                       "The revised numbers are ready for review.", {"hold": True})]


def test_generic_progressive_split_preserves_every_raw_detail():
    assert progressive_action_continuation(
        "we should actually get this sorted: Book Luna, a dog, for a rabies vaccination at",
        "yeah, agreed — North Shore Pet Hospital on Saturday at 4:20 PM") == (
            "Book Luna, a dog, for a rabies vaccination at North Shore Pet Hospital "
            "on Saturday at 4:20 PM")


def test_progressive_split_keeps_raw_line_after_partial_action(monkeypatch):
    """Acting on chunk one must not erase it from recognizer repair."""
    a = Anticipy(memory=Memory(":memory:"), llm=None, owner_id="t")
    calls = []
    decisions = iter([
        Decision(decision="act", goal=(
            "Open a windshield claim on policy AUTO-33365 for highway stone damage"),
            reason="partial action", addressee="self", owes="owner",
            needs_confirmation=True),
        Decision(decision="act", goal=(
            "Schedule repair with Speedy Glass in Coquitlam next Tuesday"),
            reason="partial action", addressee="self", owes="owner",
            needs_confirmation=True),
    ])
    monkeypatch.setattr(a, "_decide", lambda *_args, **_kwargs: next(decisions))
    monkeypatch.setattr(a, "_pending_jobs", lambda: [])
    monkeypatch.setattr(a, "_queue_job", lambda goal, params, **kwargs:
                        calls.append((goal, params, kwargs)) or f"job{len(calls)}")
    a.notify_owner = lambda *_args, **_kwargs: {"sent": True}

    first = ("we should actually get this sorted: Open a windshield claim on "
             "policy AUTO-33365: highway stone caused a 20")
    second = ("yeah, agreed — cm crack in Coquitlam on next Tuesday; use "
              "Speedy Glass for repair")
    assert a.hear(first, speaker="owner", source_event_id="event-1")["decision"].decision == "act"
    result = a.hear(second, context=[first], speaker="owner",
                    source_event_id="event-2")

    exact = ("Open a windshield claim on policy AUTO-33365: highway stone "
             "caused a 20 cm crack in Coquitlam on next Tuesday; use Speedy "
             "Glass for repair")
    assert result["decision"].goal == exact
    assert calls[-1][0] == exact
    assert calls[-1][1]["recognizer_continuation"] is True
    assert first in calls[-1][1]["source"]
    assert second in calls[-1][1]["source"]
    assert calls[-1][1]["source_event_ids"] == ["event-1", "event-2"]


def test_proven_recognizer_continuation_replaces_partial_paraphrase(monkeypatch):
    patches = []
    partial = "Open windshield claim AUTO-33365 for highway stone damage"
    job = _Job(partial, {"source": "highway stone caused a 20"})
    a = _core(monkeypatch, job, patches)
    a._open_plan = ("job1", __import__("time").time(), partial)
    exact = ("Open a windshield claim on policy AUTO-33365: highway stone "
             "caused a 20 cm crack in Coquitlam next Tuesday")

    assert a._queue_job(exact, {
        "source": "yeah, agreed — cm crack in Coquitlam next Tuesday",
        "recognizer_continuation": True,
    }, hold=True) == "job1"
    assert patches[-1]["goal"] == exact
    assert "; then" not in patches[-1]["goal"]


def test_explicit_reschedule_correction_amends_one_card_and_keeps_both_sources(
        monkeypatch):
    """A mutation verb cannot turn a correction into a second read-only job."""
    patches = []
    original = ("Schedule recall R23-628 for vehicle VIN 1HGCM82633A19078 at "
                "OpenRoad Honda for Thursday, August 13, 2026 at 6:45 PM")
    corrected = ("Reschedule vehicle recall R23-629 for VIN "
                 "1HGCM82633A19078 at OpenRoad Honda tomorrow at 6:45 PM")
    first_source = ("Anticipy, schedule recall R23-628 for vehicle VIN "
                    "1HGCM82633A19078 at OpenRoad Honda tomorrow at 6:45 PM")
    correction_source = ("Actually change R23-628 to R23-629; keep everything "
                         "else the same.")
    job = _Job(original, {"source": first_source})
    a = _core(monkeypatch, job, patches)
    a._open_plan = ("job1", __import__("time").time(), original)

    assert a._queue_job(corrected, {"source": correction_source},
                        explicit=True) == "job1"
    assert len(patches) == 1
    assert patches[0]["goal"] == corrected
    merged = json.loads(patches[0]["params"])
    assert first_source in merged["source"]
    assert correction_source in merged["source"]


def test_explicit_person_correction_outranks_lossy_goal_tokens(monkeypatch):
    """Common-name normalization cannot hide a named field replacement."""
    patches = []
    original = ("Give permission for Theo Reyes to attend the Science Centre "
                "trip on August 18; emergency contact Priya Reyes")
    corrected = ("Give permission for Priya Kim to attend the Science Centre "
                 "trip on August 18; emergency contact Priya Reyes")
    job = _Job(original, {"source": original})
    a = _core(monkeypatch, job, patches)
    a._open_plan = ("job1", __import__("time").time(), original)

    assert a._queue_job(corrected, {
        "source": ("Actually change Theo Reyes to Priya Kim; keep everything "
                   "else the same."),
    }, explicit=True) == "job1"
    assert patches[-1]["goal"] == corrected
    merged = json.loads(patches[-1]["params"])
    assert "Theo Reyes" in merged["source"]
    assert "Priya Kim" in merged["source"]


def test_discussion_fragment_is_not_promoted_to_an_action():
    assert progressive_action_continuation(
        "we should talk about this: sending messages is stressful",
        "yeah, agreed — especially after work") is None
