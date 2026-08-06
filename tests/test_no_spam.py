"""Fifteen texts in sixty-five seconds. Never again.

On 2026-08-05 one stuck Zoom page produced FIFTEEN SMS in just over a minute:

    00:08:57  i'm in the zoom help page and it looks like it needs a human choice there.
    00:09:01  i have the doc open and the email drafted for the team...
    00:09:06  i've got the recording link and the email drafted, but i'm stuck...
    ...        (twelve more)
    00:10:01  i'm at that zoom page for the recording link; what's the choice you'd make there?

Every one a fresh rewording of the same sentence, because the guard compared
the BROWSER's words about what it needed against HER PARAPHRASE of them, and a
paraphrase drops most of the original words. A short, freshly-worded ask slid
under the 50%-coverage threshold every single poll.

The fix reads no wording at all. These tests pin that, and they are written so
that restoring any part of the old behaviour fails them.
"""
import os
import sys
import types
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import brain.worker as W  # noqa: E402

GOAL = "Add today's recording link to the doc and email it to the team"


def stamp(minutes_ago):
    dt = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    return dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] + "Z"


def fake_events(rows):
    """Stand in for PocketBase, and record what was actually asked for."""
    seen = {}

    def get(url, params=None, timeout=None):
        seen["filter"] = (params or {}).get("filter", "")
        return types.SimpleNamespace(ok=True, json=lambda: {"items": rows})
    return get, seen


def test_the_real_zoom_burst_is_silenced(monkeypatch):
    """The exact fifteen messages, replayed. The sixteenth must not go out."""
    said = [
        "i'm in the zoom help page and it looks like it needs a human choice there.",
        "i have the doc open and the email drafted for the team.",
        "i've got the recording link and the email drafted, but i'm stuck on the zoom support page.",
        "that zoom link seems to need a human choice. can you take a look?",
        "I opened the zoom support page. What choice should I make on it?",
    ]
    rows = [{"kind": "anticipy_says", "decision": "needs_user", "goal": GOAL,
             "text": t, "created": stamp(n)} for n, t in enumerate(said, 1)]
    get, _ = fake_events(rows)
    monkeypatch.setattr(W.pb, "get", get)
    assert W.asked_about_recently(GOAL) is True


def test_wording_is_never_consulted(monkeypatch):
    """The old guard could be defeated by rephrasing. This one cannot: an ask
    that shares NO words at all with the new one still counts."""
    rows = [{"kind": "anticipy_says", "decision": "needs_user", "goal": GOAL,
             "text": "zzz qqq", "created": stamp(2)}]
    get, _ = fake_events(rows)
    monkeypatch.setattr(W.pb, "get", get)
    assert W.asked_about_recently(GOAL) is True


def test_a_different_task_is_not_silenced(monkeypatch):
    """A guard that mutes everything is the one thing no guard may do."""
    rows = [{"kind": "anticipy_says", "decision": "needs_user",
             "goal": "Book dinner at Cactus Club", "text": "x", "created": stamp(2)}]
    get, _ = fake_events(rows)
    monkeypatch.setattr(W.pb, "get", get)
    assert W.asked_about_recently(GOAL) is False


def test_she_is_not_muted_forever(monkeypatch):
    """After the window she may raise it again — a task blocked for an hour
    with no answer deserves a second try."""
    rows = [{"kind": "anticipy_says", "decision": "needs_user", "goal": GOAL,
             "text": "x", "created": stamp(500)}]
    get, seen = fake_events(rows)
    monkeypatch.setattr(W.pb, "get", get)
    W.asked_about_recently(GOAL, minutes=45)
    # The window is enforced server-side, so prove it is actually in the query
    # rather than trusting the fixture to have filtered.
    assert "created>=" in seen["filter"]


def test_only_asks_count_not_everything_she_says(monkeypatch):
    """A chatty FYI about the same task must not silence a real question, so
    the query itself has to narrow to asks."""
    get, seen = fake_events([])
    monkeypatch.setattr(W.pb, "get", get)
    W.asked_about_recently(GOAL)
    assert 'decision="needs_user"' in seen["filter"]
    assert 'kind="anticipy_says"' in seen["filter"]


def test_no_goal_never_silences(monkeypatch):
    monkeypatch.setattr(W.pb, "get", fake_events([])[0])
    assert W.asked_about_recently("") is False
    assert W.asked_about_recently(None) is False


def test_a_backend_failure_does_not_mute_her(monkeypatch):
    """If we cannot tell whether she already asked, she asks. Going silent on
    an error is worse than one repeat: the task dies with nobody told."""
    def boom(*a, **k):
        raise RuntimeError("pb down")
    monkeypatch.setattr(W.pb, "get", boom)
    assert W.asked_about_recently(GOAL) is False

    monkeypatch.setattr(W.pb, "get", lambda *a, **k: types.SimpleNamespace(
        ok=False, json=lambda: {}))
    assert W.asked_about_recently(GOAL) is False


def test_the_guard_runs_before_the_message_is_written():
    """It used to compose the text and THEN decide whether to send it, so a
    stuck job burned one model call per poll — every few seconds — writing
    messages that were thrown away."""
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "brain", "worker.py")).read()
    # Scope to the stuck-job block; _voice is called from several places.
    block = src[src.index("def ask_about_stuck_jobs"):]
    block = block[:block.index("\ndef ", 10)]
    guard = block.index('asked_about_recently(job.get("goal", "")')
    compose = block.index("said = anticipy._voice({")
    assert guard < compose, "the cheap guard must come before the model call"
