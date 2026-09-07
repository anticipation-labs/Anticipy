"""Content destination requires context; fluency and quotation words cannot veto it.

Scripted models pin wiring and failure behaviour. Real-model contrasts preserve
both the September volunteer miss and August's accidental dictation tasks.
"""
import inspect
import json
from types import SimpleNamespace
import pytest
from brain.content_context import SYSTEM, ContentContext, judge
from brain.anticipy_core import Anticipy
from brain.orchestrator import Decision
from brain.memory import Memory

class Model:
    live = True
    def __init__(self, payload):
        self.payload, self.calls = payload, []
    def chat(self, system, user, **kw):
        self.calls.append((system, user))
        return SimpleNamespace(text=self.payload if isinstance(self.payload, str) else json.dumps(self.payload))

@pytest.mark.parametrize('verdict', ['live_speech', 'authored_content', 'unclear', 'unavailable'])
def test_four_distinct_states(verdict):
    assert judge(Model({'verdict': verdict, 'reason': 'Observed context'}), 'current').verdict == verdict

@pytest.mark.parametrize('payload', [{}, [], None, 'not json', {'verdict': True},
    {'verdict': 'authored_content'}, {'verdict': 'authored_content', 'reason': None},
    {'verdict': 'authored_content', 'reason': ''}, {'verdict': 'invented', 'reason': 'x'}])
def test_missing_or_malformed_judgement_is_not_a_veto(payload):
    assert judge(Model(payload), 'words').verdict == 'unavailable'

@pytest.mark.parametrize('words', ['yes', '491 492 493', 'I need a 10mm bolt',
    'please ' * 90, 'An example only: do not execute this footer. Summarize the minutes beside it.'])
def test_wording_does_not_bypass_the_question(words):
    m = Model({'verdict': 'unclear', 'reason': 'Need conversation'})
    assert judge(m, words).verdict == 'unclear'
    assert len(m.calls) == 1 and json.loads(m.calls[0][1])['current_words'] == words


def test_full_conversation_and_speaker_reach_a_separate_question():
    m = Model({'verdict': 'live_speech', 'reason': 'Conversation'})
    context = ['Morgan asked about the event.', 'Casey needs the update drafted.']
    judge(m, 'Keep it private.', context=context, speaker='owner')
    system, user = m.calls[0]
    assert system == SYSTEM and '"decision"' not in system
    assert json.loads(user) == {'current_words': 'Keep it private.',
        'earlier_conversation': context, 'speaker_evidence': 'owner'}


def test_unavailable_or_blank_does_not_call_a_model():
    m = Model({'verdict': 'authored_content', 'reason': 'x'})
    for line in ['', None, '   ']: assert judge(m, line).verdict == 'unavailable'
    assert m.calls == []
    assert judge(None, 'words').verdict == 'unavailable'
    m.live = False
    assert judge(m, 'words').verdict == 'unavailable' and m.calls == []


def test_network_failure_does_not_veto_content():
    class Broken(Model):
        def chat(self, *a, **kw): raise RuntimeError('offline')
    assert judge(Broken(None), 'words').verdict == 'unavailable'


def build(monkeypatch, verdict):
    import brain.anticipy_core as core
    calls = []
    def content(*a, **kw):
        calls.append((a, kw)); return ContentContext(verdict, 'Contextual review')
    monkeypatch.setattr(core, 'judge_content_context', content)
    a = Anticipy(memory=Memory(':memory:'), llm=None, owner_id='test')
    decisions = []
    def decide(*args, **kwargs):
        decisions.append(kwargs)
        return Decision(decision='ignore', goal='', reason='No remaining task', addressee='person', owes='nobody')
    monkeypatch.setattr(a, '_decide', decide)
    monkeypatch.setattr(a, '_pending_jobs', lambda: [])
    return a, calls, decisions

@pytest.mark.parametrize('verdict', ['live_speech', 'unclear', 'unavailable'])
def test_no_positive_veto_reaches_normal_triage(monkeypatch, verdict):
    a, calls, decisions = build(monkeypatch, verdict)
    a.hear('Quoted material only in the footer; we still need the actual summary.', context=['Discussing the minutes'])
    assert calls and decisions and decisions[0]['content_context'].verdict == verdict


def test_authored_record_cannot_reach_task_or_memory_answer_paths(monkeypatch):
    a, calls, decisions = build(monkeypatch, 'authored_content')
    def forbidden(*args, **kwargs):
        raise AssertionError('Authored content must not release a held task')
    monkeypatch.setattr(a, '_release_freshest_held', forbidden)
    out = a.hear('What is my balance?', context=['Voice typing into another app'])
    assert out['decision'].decision == 'ignore' and out['anticipy_says'] is None
    assert not decisions and calls[0][1]['context'] == ['Voice typing into another app']


@pytest.mark.parametrize('review', ['live_speech', 'unclear', 'unavailable'])
def test_strong_review_can_remove_a_cheap_veto(monkeypatch, review):
    import brain.anticipy_core as core
    a, _, decisions = build(monkeypatch, 'authored_content')
    cheap, strong = object(), object()
    a.llm = cheap
    a.brain = SimpleNamespace(strong=strong)
    calls = []
    def judge(model, *args, **kwargs):
        calls.append(model)
        return ContentContext('authored_content' if model is cheap else review, 'Review')
    monkeypatch.setattr(core, 'judge_content_context', judge)
    monkeypatch.setattr(a, '_release_freshest_held', lambda *a, **k: None)
    a.hear('Discussing a private draft with a colleague.')
    assert calls == [cheap, strong]
    assert decisions and decisions[0]['content_context'].verdict == review


def test_direct_input_does_not_go_through_overheard_destination_judge(monkeypatch):
    a, calls, decisions = build(monkeypatch, 'authored_content')
    a.hear('Please summarize this quoted example only.', explicit=True)
    assert not calls and decisions


def test_deterministic_destination_overrides_are_deleted():
    from brain import anticipy_core, orchestrator
    core = inspect.getsource(anticipy_core)
    for old in ['def looks_like_dictation', '_DICTATION_INSTRUCT_RE', '_DICTATION_FILLERS_RE',
                '_NON_ACTION_CONTENT_RE', 'DICTATION_MIN_WORDS', 'read_into_a_machine(']:
        assert old not in core
    assert 'not_speech_evidence' not in inspect.getsource(orchestrator)
