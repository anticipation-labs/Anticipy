"""The meeting posture, end to end at the core: acts overheard mid-meeting
hold their tongue, and ONE digest speaks after.

The recorded failure this locks in place: 2026-08-23, a 28-minute call,
six acts, four texts — one of them a question about the call he was still
on. The fix is not "act less"; it is "speak later, once".

Offline and deterministic: LLM() with no API keys runs the heuristic path,
and pb calls are monkeypatched into a dead in-memory backend, the same
pattern as overnight/evaluate.py.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import brain.pb as pb
from brain.anticipy_core import Anticipy
from brain.llm import LLM


class _Resp:
    ok = True
    def __init__(self, payload=None):
        self._payload = payload or {"items": [], "id": "job1"}
    def json(self):
        return self._payload


def _dead_backend(monkeypatch):
    # Every write "succeeds" so hear() walks its real path; nothing persists.
    monkeypatch.setattr(pb, "get", lambda *a, **k: _Resp())
    monkeypatch.setattr(pb, "post", lambda *a, **k: _Resp({"id": "job1"}))
    monkeypatch.setattr(pb, "patch", lambda *a, **k: _Resp())


def _anticipy(monkeypatch, sent):
    _dead_backend(monkeypatch)
    for key in ("GEMINI_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    a = Anticipy(llm=LLM(), backend_url="http://dead")
    monkeypatch.setattr(a, "notify_owner",
                        lambda text, channel="sms": sent.append(text) or {"ok": 1})
    return a


def test_meeting_holds_tongue_and_digest_speaks_once(monkeypatch):
    sent = []
    a = _anticipy(monkeypatch, sent)
    # Force the held-card shape regardless of what the offline heuristic
    # decides about the line: seed _meeting_held the way the ambient branch
    # does, then check the digest contract — one text, everything named,
    # drained after.
    a._meeting_held.append(("job1", "dinner Thursday at 7pm for four"))
    a._meeting_held.append(("job2", "set up the Tuesday call"))
    text = a.meeting_digest()
    assert text is not None
    assert "dinner Thursday at 7pm for four" in text
    assert "set up the Tuesday call" in text
    assert "2 things" in text
    # Drained: the second call has nothing to say — a digest never repeats.
    assert a.meeting_digest() is None


def test_empty_meeting_digests_nothing(monkeypatch):
    sent = []
    a = _anticipy(monkeypatch, sent)
    assert a.meeting_digest() is None


def test_in_meeting_hear_never_texts(monkeypatch):
    """A line heard with in_meeting=True may prepare work, but nothing may
    reach notify_owner during the meeting — the digest owns the speaking."""
    sent = []
    a = _anticipy(monkeypatch, sent)
    a.hear("let's do dinner Thursday at seven with the team",
           context=["so Thursday works for everyone?"],
           may_say=lambda *args, **kw: True,
           in_meeting=True)
    assert sent == [], f"texted mid-meeting: {sent!r}"


def test_shard_cannot_act_even_outside_meetings(monkeypatch):
    """The shard tape, at the hear() level: 'At 5:15' may be remembered,
    never acted on, meeting or no meeting."""
    sent = []
    a = _anticipy(monkeypatch, sent)
    out = a.hear("At 5:15", may_say=lambda *args, **kw: True)
    assert out["decision"].decision != "act"
    assert sent == []
