"""Research results reach his hand — one FYI text, her words, right hours.

2026-08-05, Omar: "It should text you the results." He watched her research
Paris flights and dinner spots and saw only 'Noted — nothing needed';
finished quiet work was indistinguishable from being dead.
"""
import os
import sys
import types
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import brain.worker as W  # noqa: E402


def _anticipy(texts, voice=None):
    return types.SimpleNamespace(
        owner_id="t",
        _voice=voice or (lambda ctx: None),
        notify_owner=lambda m, channel="sms": (texts.append(m), {"ok": True})[1])


def _daytime(monkeypatch, hour=14):
    class FakeDT:
        @staticmethod
        def now(tz=None):
            return datetime(2026, 8, 5, hour, 0, tzinfo=tz)
    monkeypatch.setattr(W, "datetime", FakeDT)


def test_an_overheard_result_texts_one_fyi(monkeypatch):
    _daytime(monkeypatch)
    texts = []
    W.deliver_fyi(_anticipy(texts), "research dinner spots in Vancouver",
                  "Jeju in Mount Pleasant does modern Korean.", overheard=True)
    assert len(texts) == 1 and "Jeju" in texts[0], texts


def test_overheard_fyis_respect_quiet_hours(monkeypatch):
    _daytime(monkeypatch, hour=23)
    texts = []
    W.deliver_fyi(_anticipy(texts), "research dinner spots",
                  "Jeju does modern Korean.", overheard=True)
    assert texts == [], texts


def test_a_held_fyi_says_it_was_not_delivered(monkeypatch):
    """Quiet hours are ten hours long, and "held for morning" used to be the
    same silent None as "sent". The caller took that for delivery, wrote the
    feed record that marks a finding already-raised, and no morning ever came:
    every overheard lookup finishing between 22:00 and 08:00 was destroyed
    rather than deferred. The caller can only know the difference if this
    function tells it."""
    _daytime(monkeypatch, hour=23)
    texts = []
    held = W.deliver_fyi(_anticipy(texts), "research dinner spots",
                         "Jeju does modern Korean.", overheard=True)
    assert held is False, "a held FYI must report that it did not go out"
    assert texts == []
    _daytime(monkeypatch, hour=9)
    sent = W.deliver_fyi(_anticipy(texts), "research dinner spots",
                         "Jeju does modern Korean.", overheard=True)
    assert sent is True and len(texts) == 1, texts


def test_an_asked_for_answer_goes_out_even_at_night(monkeypatch):
    _daytime(monkeypatch, hour=23)
    texts = []
    W.deliver_fyi(_anticipy(texts), "Research: capital of Canada",
                  "Ottawa is the capital of Canada.", overheard=False)
    assert len(texts) == 1 and "Ottawa" in texts[0], texts


def test_her_voice_is_used_when_the_model_answers(monkeypatch):
    _daytime(monkeypatch)
    texts = []
    a = _anticipy(texts, voice=lambda ctx: "caught your dinner hunt — jeju's the move")
    W.deliver_fyi(a, "research dinner spots", "Jeju in Mount Pleasant.",
                  overheard=True)
    assert texts == ["caught your dinner hunt — jeju's the move"]


def test_an_empty_result_never_texts(monkeypatch):
    _daytime(monkeypatch)
    texts = []
    W.deliver_fyi(_anticipy(texts), "research something", "   ", overheard=True)
    assert texts == []
