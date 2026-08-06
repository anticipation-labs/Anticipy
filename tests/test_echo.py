"""Her own words, read back at her, are not an instruction.

Omar reads her messages out loud constantly while testing, and every time she
has treated it as a fresh order. Three times on 2026-08-05 alone:

  she texted : "hey, the August data is ready to add in the spreadsheet
                whenever you want to jump in"
  he said    : "OK that one I got a text saying hey the August data is ready
                to add in the spreadsheet whenever you want to jump in"
  she did    : minted a SECOND job, 27 seconds after the first

  she texted : "hey, i don't have your mother's contact info. can you send
                that over?"
  he said    : "I don't have your mother's contact can you send it over"
  she did    : made a job to go and get his mother's contact

The measure is a long UNBROKEN run of shared words, not overlap. Overlap is
the wrong instrument: "yeah Cactus Club at 7" shares plenty with "got it,
booking Cactus Club Park Royal for two at 7" and is a genuine confirmation
that must never be silenced. Reading aloud is different in kind — it produces
a long run, because that is what reading is.

A guard that silences him is far worse than the bug it fixes, so most of this
file is about what must NOT be caught.
"""
import os
import sys
import types
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import brain.worker as W  # noqa: E402


def said(*texts):
    now = datetime.now(timezone.utc)
    return [{"kind": "anticipy_text",
             "text": t,
             "created": (now - timedelta(minutes=2)).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] + "Z"}
            for t in texts]


def backend(rows):
    seen = {}

    def get(url, params=None, timeout=None):
        seen["filter"] = (params or {}).get("filter", "")
        return types.SimpleNamespace(ok=True, json=lambda: {"items": rows})
    return get, seen


# --------------------------------------------------- the real incidents

def test_the_august_data_echo(monkeypatch):
    monkeypatch.setattr(W.pb, "get", backend(said(
        "hey, the August data is ready to add in the spreadsheet whenever you want to jump in"))[0])
    assert W.is_echo_of_her(
        "OK that one I got a text saying hey the August data is ready to add in "
        "the spreadsheet whenever you want to jump in") is True


def test_the_mothers_contact_echo(monkeypatch):
    monkeypatch.setattr(W.pb, "get", backend(said(
        "hey, i don't have your mother's contact info. can you send that over?"))[0])
    assert W.is_echo_of_her("I don't have your mother's contact can you send it over") is True


def test_the_team_email_echo(monkeypatch):
    monkeypatch.setattr(W.pb, "get", backend(said(
        "i'll put that together, then send it to you before it goes out to the team"))[0])
    assert W.is_echo_of_her(
        "I got a text message saying hey I'll put that together then send it to "
        "you before it goes out to the team") is True


# ------------------------------------------- what must NEVER be silenced

def test_a_genuine_confirmation_is_not_an_echo(monkeypatch):
    """The most dangerous false positive: he agrees, in words she just used."""
    monkeypatch.setattr(W.pb, "get", backend(said(
        "got it, booking Cactus Club Park Royal for two at 7 PM tomorrow."))[0])
    for reply in ("yeah Cactus Club at 7",
                  "yes book it",
                  "Cactus Club Park Royal works",
                  "make it 7:30 instead",
                  "actually four of us not two"):
        assert W.is_echo_of_her(reply) is False, reply


def test_talking_about_the_same_topic_is_not_an_echo(monkeypatch):
    monkeypatch.setattr(W.pb, "get", backend(said(
        "i've got the budget spreadsheet open and i'm adding the august numbers now"))[0])
    assert W.is_echo_of_her(
        "I still need to get the August numbers into the budget spreadsheet today") is False


def test_the_same_words_rearranged_are_not_an_echo(monkeypatch):
    """The case that separates a run from plain overlap, and the reason the
    measure is a run at all. Found by mutation testing: swapping the unbroken
    run for word overlap left every other test in this file green, because
    none of them had many shared words in a different ORDER. A person picking
    up her words and answering in their own sentence is not reading aloud."""
    hers = "i've got the budget spreadsheet open and i'm adding the august numbers now"
    monkeypatch.setattr(W.pb, "get", backend(said(hers))[0])
    his = "the august numbers, the budget — adding those now, i've got the spreadsheet open"
    shared = len(set(W._words(his)) & set(W._words(hers)))
    assert shared >= W.ECHO_RUN, "the fixture must actually share enough words to matter"
    assert W.longest_shared_run(his, hers) < W.ECHO_RUN
    assert W.is_echo_of_her(his) is False


def test_a_short_line_is_never_an_echo(monkeypatch):
    monkeypatch.setattr(W.pb, "get", backend(said("book a table for two at seven"))[0])
    for short in ("book a table", "yes", "seven works", "book a table for two"):
        assert W.is_echo_of_her(short) is False, short


def test_nothing_she_said_means_nothing_is_an_echo(monkeypatch):
    monkeypatch.setattr(W.pb, "get", backend([])[0])
    assert W.is_echo_of_her("I don't have your mother's contact can you send it over") is False


def test_a_backend_failure_never_silences_him(monkeypatch):
    """If we cannot tell, he is heard. Silencing on an error would make her
    deaf exactly when the backend is struggling."""
    def boom(*a, **k):
        raise RuntimeError("pb down")
    monkeypatch.setattr(W.pb, "get", boom)
    assert W.is_echo_of_her("I don't have your mother's contact can you send it over") is False

    monkeypatch.setattr(W.pb, "get", lambda *a, **k: types.SimpleNamespace(
        ok=False, json=lambda: {}))
    assert W.is_echo_of_her("anything at all here that is long enough") is False


def test_only_her_own_messages_count(monkeypatch):
    get, seen = backend([])
    monkeypatch.setattr(W.pb, "get", get)
    W.is_echo_of_her("some line long enough to be considered here")
    assert 'kind="anticipy_says"' in seen["filter"]
    assert 'kind="anticipy_text"' in seen["filter"]
    assert "transcript" not in seen["filter"], "his own speech must never be the mirror"
    assert "created>=" in seen["filter"], "and only recently"


# ------------------------------------------------------ the measure itself

def test_the_run_must_be_unbroken():
    a = "alpha bravo charlie delta echo foxtrot"
    assert W.longest_shared_run(a, a) == 6
    # Same words, order scrambled: not reading, not an echo.
    assert W.longest_shared_run(a, "foxtrot alpha delta bravo echo charlie") < 6
    # A shared prefix that then diverges.
    assert W.longest_shared_run(a, "alpha bravo charlie golf hotel india") == 3


def test_the_measure_is_safe_on_junk():
    assert W.longest_shared_run("", "") == 0
    assert W.longest_shared_run("hello", "") == 0
    assert W.longest_shared_run(None, "hello") == 0
    assert W.longest_shared_run("hello", None) == 0


def test_it_runs_before_triage_not_after():
    """The point is to spend a cheap read instead of a model call, and to keep
    an echo from ever reaching the part that mints jobs."""
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "brain", "worker.py")).read()
    echo = src.index("if is_echo_of_her(line):")
    hear = src.index("out = anticipy.hear(line")
    assert echo < hear, "the echo check must come before hear()"
