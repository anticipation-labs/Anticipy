"""An outage must keep his words, not bury them.

The transcript loop answered every exception the same way: stamp the event
"error" and move on. fetch_unprocessed only ever selects decision="", so that
stamp is a tombstone — the line is never retried, and nothing anywhere says
so. The path is short and entirely real: OpenRouter answers 402 the moment
the credit runs out, brain/llm.py calls raise_for_status with no retry and no
fallback, Brain.triage catches only a JSON parse error, so the HTTP error
lands in that handler. Once per line, for as long as the balance is zero.

Two separate failures were happening at once, and this file pins both:

  1. THE WORDS DIED. An hour of a person's day, gone, because the machine
     that understands them was briefly absent. Nothing was wrong with the
     words. release_stranded_claims already existed to hand back a line left
     at "processing" by a restart — an outage is the same class of event, and
     the handler was throwing that recovery away by stamping over the claim.

  2. HE WAS TOLD NOTHING. A print() to a Railway log is not a person. The
     difference between "she is quiet" and "she cannot hear me" is the whole
     product, and he had no way to tell them apart.

What must NOT change: a defect in our own code still gets the tombstone. A
KeyError in our parsing is deterministic — the same words through the same
code fail identically forever — so holding it would retry it every ten
minutes for the life of the account and hold the head of the queue while it
did.
"""
import os
import re
import sys

import httpx
import pytest
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import brain.worker as W  # noqa: E402


# --------------------------------------------------- the decision itself

# The classifier is the whole fix. It is deliberately a type check and not a
# reading of the error's prose: "is this retryable", answered by string
# matching on a provider's wording, is the pattern-match HARNESS-LAWS.md
# LAW 1 exists to keep out of this codebase.

@pytest.mark.parametrize("exc", [
    httpx.HTTPStatusError("402 payment required", request=None, response=None),
    httpx.ConnectTimeout("timed out"),
    httpx.ReadTimeout("timed out"),
    httpx.ConnectError("no route"),
    requests.exceptions.ConnectionError("pocketbase refused"),
    requests.exceptions.Timeout("pocketbase slow"),
    ConnectionResetError("peer hung up"),
    TimeoutError("waited"),
    OSError("dns"),
])
def test_a_machine_we_could_not_reach_is_held(exc):
    assert W.unreachable_model(exc) is True, (
        f"{type(exc).__name__} is a machine being absent, and his line must "
        "wait for it rather than be buried")


@pytest.mark.parametrize("exc", [
    KeyError("candidates"),
    ValueError("could not parse"),
    TypeError("NoneType is not subscriptable"),
    AttributeError("decision"),
    IndexError("0"),
    ZeroDivisionError("nope"),
])
def test_a_defect_in_us_still_gets_the_tombstone(exc):
    """The important half. Retrying identical input through identical code
    cannot help, and a held line retries every ten minutes forever."""
    assert W.unreachable_model(exc) is False, (
        f"{type(exc).__name__} is our bug, not an outage — holding it would "
        "park a poisoned line at the head of the queue for good")


def test_a_402_from_the_real_client_shape_is_held():
    """Not a hand-built exception: the shape httpx actually raises from
    raise_for_status, which is what brain/llm.py calls."""
    request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    response = httpx.Response(402, request=request, text="insufficient credits")
    with pytest.raises(httpx.HTTPStatusError) as caught:
        response.raise_for_status()
    assert W.unreachable_model(caught.value) is True


# --------------------------------------------- what it does about it

# record_failure is the whole handler, extracted for exactly this reason: the
# first version of these tests read the source and asserted the branch looked
# right, and it passed cleanly against a branch neutered to `if False and
# unreachable_model(e)`. A guard nobody can DRIVE is a guard the next edit
# gets to delete for free.

def _stamps(monkeypatch):
    marked: list[tuple[str, str]] = []
    monkeypatch.setattr(W, "mark_processed",
                        lambda event_id, decision, **k:
                        marked.append((event_id, decision)) or True)
    monkeypatch.setattr(W, "DEAF_STREAK", 0)
    return marked


def test_an_outage_stamps_nothing_at_all(monkeypatch):
    """The regression, directly. fetch_unprocessed selects decision="", so
    any stamp here is a tombstone: the line is never asked for again."""
    marked = _stamps(monkeypatch)
    verdict = W.record_failure("ev1", "book dinner thursday",
                               httpx.ConnectError("no route"))
    assert verdict == "held"
    assert marked == [], (
        "the claim must stand so release_stranded_claims can hand the line "
        "back — stamping it here is what made an hour of his day unrecoverable")


def test_our_own_defect_is_still_recorded(monkeypatch):
    """And the other half must not regress into leaving poison at the head of
    the queue forever."""
    marked = _stamps(monkeypatch)
    verdict = W.record_failure("ev2", "book dinner thursday",
                               KeyError("candidates"))
    assert verdict == "error"
    assert marked == [("ev2", "error")]


def test_a_held_line_counts_toward_telling_him(monkeypatch):
    marked = _stamps(monkeypatch)
    W.record_failure("ev3", "line one", httpx.ReadTimeout("slow"))
    W.record_failure("ev4", "line two", httpx.ReadTimeout("slow"))
    assert W.DEAF_STREAK == 2
    assert marked == []


def test_our_own_defect_does_not_count_as_deafness(monkeypatch):
    """She can hear perfectly well; one line broke her. Counting it would
    have her announce an outage that is not happening."""
    _stamps(monkeypatch)
    W.record_failure("ev5", "line", ValueError("bad json"))
    assert W.DEAF_STREAK == 0


def test_the_loop_uses_it(monkeypatch):
    """A tested decision that main() does not consult is a comment."""
    source = open(W.__file__, encoding="utf-8").read()
    handler = source[source.index("except Exception as e:",
                                  source.index("out = anticipy.hear(")):]
    handler = handler[:handler.index("note_heard(True)")]
    assert "record_failure(ev[\"id\"], line, e)" in handler, (
        "the transcript loop must route its failures through the tested "
        "decision, not re-implement one inline")
    assert "mark_processed" not in handler, (
        "no stamping inline — that is the branch this fix removed")


def test_the_sweep_is_what_brings_it_back():
    """The held line is only safe because something hands it back. If this
    call ever leaves the loop, the fix silently becomes the old bug with a
    politer log line."""
    source = open(W.__file__, encoding="utf-8").read()
    assert "release_stranded_claims(anticipy.owner_ref)" in source
    assert source.index("release_stranded_claims(anticipy.owner_ref)") < \
        source.index("for ev in fetch_unprocessed("), \
        "the hand-back must run before new work is asked for"


# -------------------------------------------------- the streak

def test_one_failure_is_a_blip_and_three_is_a_state(monkeypatch):
    monkeypatch.setattr(W, "DEAF_STREAK", 0)
    W.note_heard(False)
    assert W.DEAF_STREAK == 1
    W.note_heard(False)
    W.note_heard(False)
    assert W.DEAF_STREAK == 3


def test_hearing_one_line_clears_it(monkeypatch):
    """Recovery needs no announcement and no timer: the next line she
    actually understands is the evidence."""
    monkeypatch.setattr(W, "DEAF_STREAK", 9)
    W.note_heard(True)
    assert W.DEAF_STREAK == 0


# -------------------------------------------------- telling him

class FakeOwner:
    """Only what report_deafness is allowed to touch."""

    def __init__(self, reachable=True, sends=True):
        self._reachable = reachable
        self._sends = sends
        self.said: list[str] = []
        self.composed = 0

    def can_notify_owner(self):
        return self._reachable

    def notify_owner(self, text):
        self.said.append(text)
        return self._sends

    def _voice(self, _payload):          # pragma: no cover - must never run
        self.composed += 1
        return "composed"


def _quiet_backend(monkeypatch, rows=()):
    """PocketBase up, model down — the actual shape of a credit outage.

    Returns the list of event rows posted, so the durable record can be
    asserted rather than assumed.
    """
    posted: list[dict] = []

    class Reply:
        ok = True

        @staticmethod
        def json():
            return {"items": list(rows)}

    monkeypatch.setattr(W.pb, "get", lambda *a, **k: Reply())
    monkeypatch.setattr(W, "post_event",
                        lambda kind, text, decision="", goal="", **k:
                        posted.append({"kind": kind, "text": text,
                                       "decision": decision, "goal": goal}))
    monkeypatch.setattr(W, "_SENT_RECENTLY", {})
    return posted


def test_below_the_threshold_she_says_nothing(monkeypatch):
    posted = _quiet_backend(monkeypatch)
    monkeypatch.setattr(W, "DEAF_STREAK", W.DEAF_STREAK_BEFORE_TELLING - 1)
    owner = FakeOwner()
    W.report_deafness(owner)
    assert owner.said == [], "one swallowed line is a blip, not an announcement"
    assert posted == []


def test_at_the_threshold_he_is_told_once(monkeypatch):
    posted = _quiet_backend(monkeypatch)
    monkeypatch.setattr(W, "DEAF_STREAK", W.DEAF_STREAK_BEFORE_TELLING)
    owner = FakeOwner()
    W.report_deafness(owner)
    assert len(owner.said) == 1
    said = owner.said[0]
    assert "keeping" in said, (
        "the one thing he needs from this text is that his words are not lost")
    assert "\u2014" not in said and "\u2013" not in said, \
        "no dash a person reads on a screen"
    assert said == said.lower() or said[0].islower(), \
        "her voice is lowercase, like the rest of what she sends"
    assert posted and posted[0]["decision"] == "deaf" \
        and posted[0]["goal"] == W.DEAF_GOAL, \
        "the durable record is what stops a redeploy re-announcing it"


def test_she_does_not_pay_the_model_to_describe_the_model_being_down(monkeypatch):
    """Every other notice in worker.py composes its sentence. This one cannot:
    the condition it reports IS the compose failing, and paying for it is the
    can_reach_owner bug wearing a new name."""
    _quiet_backend(monkeypatch)
    monkeypatch.setattr(W, "DEAF_STREAK", W.DEAF_STREAK_BEFORE_TELLING)
    owner = FakeOwner()
    W.report_deafness(owner)
    assert owner.composed == 0


def test_the_durable_record_stops_the_second_text(monkeypatch):
    """A redeploy mid-outage resets the process, so the guard that matters is
    the one read back off the events table."""
    already = [{"text": "something's wrong on my end", "goal": W.DEAF_GOAL,
                "decision": "deaf"}]
    _quiet_backend(monkeypatch, rows=already)
    monkeypatch.setattr(W, "DEAF_STREAK", 40)
    owner = FakeOwner()
    W.report_deafness(owner)
    assert owner.said == [], (
        "she already told him; a second identical text is the spam channel "
        "this repo has three separate guards against")


def test_a_process_local_guard_covers_a_write_outage(monkeypatch):
    """already_raised reads the row post_event writes AFTER the text goes out.
    When that write fails, the durable half believes nothing was said — the
    exact shape that re-sent a stall notice every two seconds."""
    _quiet_backend(monkeypatch)
    monkeypatch.setattr(W, "DEAF_STREAK", 40)
    owner = FakeOwner()
    W.report_deafness(owner)
    W.report_deafness(owner)
    assert len(owner.said) == 1


def test_nobody_to_text_means_nothing_is_composed_or_sent(monkeypatch):
    _quiet_backend(monkeypatch)
    monkeypatch.setattr(W, "DEAF_STREAK", 40)
    owner = FakeOwner(reachable=False)
    W.report_deafness(owner)
    assert owner.said == [] and owner.composed == 0


def test_a_failed_send_is_not_recorded_as_a_send(monkeypatch):
    """If it did not leave, she must be free to try again — the same rule
    report_stalled_work follows when notify_owner returns False."""
    posted = _quiet_backend(monkeypatch)
    monkeypatch.setattr(W, "DEAF_STREAK", 40)
    owner = FakeOwner(sends=False)
    W.report_deafness(owner)
    assert posted == [], "nothing was delivered, so nothing may be claimed"
    assert not W.sent_moments_ago("deaf")


def test_it_is_wired_into_the_tick():
    """A reporter nobody calls is a comment."""
    source = open(W.__file__, encoding="utf-8").read()
    assert re.search(r"\n\s+report_deafness\(anticipy\)", source), \
        "report_deafness must run in main()'s loop, beside the other honesty duties"
