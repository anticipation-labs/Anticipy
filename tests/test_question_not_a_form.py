"""A question is something a person answers. A list is a form.

Live, 2026-08-21. His child said "Dad can you sign the thing for the trip,
it's due Friday". What arrived on his phone:

    Caught your plan — ready to go: Get document for trip signed. First I need:
    What trip?, What document?, Where is the document?, which document, which

Five items, comma-spliced behind a template prefix, "What document?" and
"which document" the same question asked twice in one breath, and the whole
thing stopping dead on "which". From the same session, when the model could
speak for itself:

    i'm holding a draft email to the accountant for the receipts; which
    accountant is that, and which receipts should i attach?

Two unknowns, one sentence, answerable in one reply. The gap between those two
messages is not a model problem — it is `", ".join(missing)` pasted into a
template. brain/asking.py closes it, and this file is the wall:

  * no question is asked twice,
  * at most asking.SPOKEN_LIMIT questions leave in one message,
  * the message never ends mid-word,
  * and ONE missing fact still produces one natural question — the fix must
    not buy brevity by going vague.

Both ends are pinned: asking.ask_line directly, and the real rendered text
coming out of Anticipy.hear() with no model available, which is the exact path
that produced the live failure.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import asking  # noqa: E402
from brain import pb  # noqa: E402
import brain.anticipy_core as core  # noqa: E402
from brain.anticipy_core import Anticipy  # noqa: E402
from brain.memory import Memory  # noqa: E402
from brain.orchestrator import Decision  # noqa: E402

# The list verbatim, as triage wrote it that afternoon.
THE_FORM = ["What trip?", "What document?", "Where is the document?",
            "which document", "which"]
GOAL = "Get document for trip signed"
LINE = "Dad can you sign the thing for the trip, it's due Friday"


# --------------------------------------------------------------- the words

def _questions(text: str) -> list:
    """Her asks, split the way a reader hears them."""
    tail = text.split(";", 1)[-1] if ";" in text else text
    return [p.strip() for p in tail.replace(", and ", "|").split("|")
            if p.strip()]


def test_the_same_question_is_never_asked_twice():
    """'What document?' and 'which document' are one question."""
    spoken = asking.speakable(THE_FORM)
    keys = [asking._key(s) for s in spoken]
    assert len(keys) == len(set(keys)), spoken
    lowered = [s.lower().strip("?") for s in spoken]
    assert "what document" not in lowered or "which document" not in lowered, \
        f"the duplicate pair both survived: {spoken}"


def test_a_subjectless_fragment_is_not_a_question():
    """'which' on its own is what made the live text look truncated."""
    assert asking.speakable(["which"]) == []
    assert asking.speakable(["what", "the", "?", "  "]) == []
    assert "which document" not in asking.ask_line(GOAL, ["which"])


def test_never_more_than_the_ceiling_leaves_in_one_message():
    assert asking.SPOKEN_LIMIT <= 2, \
        "three unknowns need a list, and a list is the defect"
    assert len(asking.speakable(THE_FORM)) <= asking.SPOKEN_LIMIT


def test_a_different_axis_is_a_different_question():
    """The dedupe must not swallow real questions: WHERE the document is is
    not WHICH document it is."""
    assert asking._key("Where is the document?") != asking._key("What document?")


def test_the_tail_is_dropped_whole_never_mid_word():
    line = asking.ask_line(GOAL, THE_FORM)
    assert line.endswith("?"), line
    # Every unknown that IS spoken is spoken whole (only its leading
    # interrogative is lowercased into her voice).
    for item in asking.speakable(THE_FORM):
        assert item.strip("?").lower() in line.lower(), (item, line)
    # Nothing survives as a prefix of a word it was cut out of.
    assert not line.rstrip("?").endswith(("wh", "whi", "docu", "documen"))


def test_one_missing_fact_is_still_one_natural_question():
    line = asking.ask_line("book dinner tomorrow", ["what time they want"])
    assert "what time they want" in line
    assert line.count("?") == 1 and line.endswith("?"), line
    assert ", and " not in line, f"one unknown must not be a list: {line!r}"


def test_nothing_missing_still_asks_for_the_go_ahead():
    line = asking.ask_line(GOAL, [])
    assert "say go" in line and "nothing's booked or sent yet" in line


def test_it_never_raises_on_model_shaped_junk():
    for junk in (None, "", "which", 7, [None, 7, {}], "which document",
                 ["x" * 400], {}):
        assert isinstance(asking.ask_line(GOAL, junk), str), junk


# ------------------------------------------------ the message he'd receive

class _Reply:
    def __init__(self, payload):
        self._p, self.ok = payload, True

    def json(self):
        return self._p

    def raise_for_status(self):
        return None


class Fake:
    def __init__(self):
        self.jobs = []

    def get(self, url, params=None, timeout=None, **k):
        want = [s for s in ("awaiting_confirm", "queued")
                if s in (params or {}).get("filter", "")]
        return _Reply({"items": [j for j in self.jobs
                                 if j.get("status") in want]})

    def post(self, url, json=None, timeout=None, **k):
        rec = dict(json or {})
        rec["id"] = f"j{len(self.jobs) + 1}"
        self.jobs.append(rec)
        return _Reply(rec)

    def patch(self, url, json=None, timeout=None, **k):
        jid = url.rstrip("/").rsplit("/", 1)[-1]
        for j in self.jobs:
            if j.get("id") == jid:
                j.update(json or {})
        return _Reply({})


class DeadMemory(Memory):
    def __init__(self):
        pass

    def ingest(self, *a, **k):
        return {}

    def recall(self, *a, **k):
        return []


def _anticipy(monkeypatch, missing):
    """The overheard-plan lane with no model to speak — the fallback path that
    produced the live text."""
    fake = Fake()
    monkeypatch.setattr(pb, "get", fake.get)
    monkeypatch.setattr(pb, "post", fake.post)
    monkeypatch.setattr(pb, "patch", fake.patch)
    a = Anticipy(memory=DeadMemory(), owner_id="form")
    monkeypatch.setattr(a, "_decide", lambda *args, **kw: Decision(
        decision="act", goal=GOAL, reason="a real plan",
        addressee="person", needs_confirmation=True, missing=list(missing)))
    monkeypatch.setattr(core, "check_sufficiency", lambda llm, goal: [])
    monkeypatch.setattr(core, "fill_gaps_from_memory",
                        lambda llm, mem, goal, missing_: ({}, list(missing_)))
    monkeypatch.setattr(a, "_voice", lambda *a_, **k_: None)
    sent = []
    a.notify_owner = lambda m, channel="sms": (sent.append(m), True)[1]
    return a, sent


def test_the_live_failure_cannot_be_sent_again(monkeypatch):
    """THE REGRESSION. Five items in, one answerable sentence out."""
    a, sent = _anticipy(monkeypatch, THE_FORM)
    a.hear(LINE, may_say=lambda *a_, **k_: True)
    assert len(sent) == 1, sent
    text = sent[0]

    assert "First I need:" not in text, f"still a form: {text!r}"
    # Her register, not a template's: a Capitalised prefix in front of a
    # comma-joined list is half of what made the live text read as a form.
    assert text[:1].islower(), f"template voice: {text!r}"

    asked = _questions(text)
    assert len(asked) <= asking.SPOKEN_LIMIT, f"{len(asked)} questions: {text!r}"

    keys = [asking._key(q) for q in asked]
    assert all(keys) and len(keys) == len(set(keys)), \
        f"a question was asked twice: {text!r}"

    assert text.rstrip().endswith(("?", ".")), f"cut off: {text!r}"
    assert not text.rstrip().endswith(", which"), f"the live tail: {text!r}"
    # Nothing is claimed to have happened.
    assert "nothing's booked or sent yet" in text, text


def test_one_unknown_still_reads_like_a_person(monkeypatch):
    """No-regression: the fix must not flatten the single-question case."""
    a, sent = _anticipy(monkeypatch, ["which trip is this for"])
    a.hear(LINE, may_say=lambda *a_, **k_: True)
    assert len(sent) == 1, sent
    text = sent[0]
    assert "which trip is this for" in text
    assert text.count("?") == 1 and text.rstrip().endswith("?"), text
    assert ", and " not in text, f"one unknown became a list: {text!r}"
