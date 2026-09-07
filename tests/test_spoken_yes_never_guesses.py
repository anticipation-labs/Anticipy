"""Consent is contextual, owner-scoped, and bound to unchanged task state."""
import datetime as dt
import json
from copy import deepcopy
from types import SimpleNamespace

import pytest
from brain.anticipy_core import Anticipy
from brain.memory import Memory
from brain.spoken_consent import judge


def row(id='j1', **values):
    return {'id': id, 'owner': 't', 'owner_ref': '', 'goal': 'send the contract to Priya',
            'status': 'awaiting_confirm', 'params': '{}',
            'created': (dt.datetime.now(dt.timezone.utc)-dt.timedelta(seconds=30)).isoformat(),
            **values}


class Model:
    live = True
    def __init__(self, answer):
        self.answer, self.calls = answer, []
    def chat(self, system, user, **kw):
        self.calls.append((json.loads(user), kw))
        return SimpleNamespace(text=json.dumps(self.answer), finish_reason='stop')


def brain(monkeypatch, items, answer=None, *, latest=None, etag='"snapshot"', patch_ok=True):
    a = Anticipy(memory=Memory(':memory:'), llm=None, owner_id='t')
    model = Model(answer or {'verdict': 'approved', 'job_id': items[0]['id']})
    a.brain = SimpleNamespace(strong=model)
    writes = []
    def get(url, **kw):
        if url.endswith('/records'):
            assert 'owner="t"' in kw['params']['filter']
            data = {'items': deepcopy(items), 'totalPages': 1}
        else:
            data = deepcopy(latest if latest is not None else next(j for j in items if url.endswith('/'+j['id'])))
        return SimpleNamespace(ok=True, json=lambda: data, headers={'ETag': etag})
    def patch(url, **kw):
        writes.append((url, kw))
        return SimpleNamespace(ok=patch_ok)
    monkeypatch.setattr('brain.anticipy_core.backend.get', get)
    monkeypatch.setattr('brain.anticipy_core.backend.patch', patch)
    return a, model, writes


@pytest.mark.parametrize('stamp', ['', 'nonsense', '2999-01-01 00:00:00', '2000-01-01 00:00:00'])
def test_invalid_future_and_expired_dates_never_release(monkeypatch, stamp):
    a, _, writes = brain(monkeypatch, [row(created=stamp)])
    assert a._release_freshest_held('go ahead') is None
    assert writes == []


def test_recent_timestamp_is_eligible_but_does_not_supply_consent():
    assert Anticipy._recently_asked(row())
    assert judge(None, line='go ahead', conversation=[], tasks=[row()])['verdict'] == 'unknown'


@pytest.mark.parametrize('verdict', ['refused', 'clarification', 'unknown', 'yes', True, None])
def test_only_positive_verdict_can_release(monkeypatch, verdict):
    a, _, writes = brain(monkeypatch, [row()], {'verdict': verdict, 'job_id': 'j1'})
    assert a._release_freshest_held('go ahead') is None
    assert writes == []


def test_unqualified_approval_between_two_tasks_stays_held(monkeypatch):
    a, m, writes = brain(monkeypatch, [row(), row('j2', goal='book dinner')],
                         {'verdict': 'clarification', 'job_id': None})
    assert a._release_freshest_held('go ahead', context=['Two tasks are waiting']) is None
    assert len(m.calls[0][0]['held_tasks']) == 2
    assert writes == []


def test_context_selects_older_task_not_first_row(monkeypatch):
    a, m, writes = brain(monkeypatch, [row('j2', goal='book dinner'), row()],
                         {'verdict': 'approved', 'job_id': 'j1'})
    context = ['Anticipy: Send the contract to Priya?', 'Owner: Let me check it first.']
    assert a._release_freshest_held('You may proceed with the contract', context=context) == row()['goal']
    assert writes[0][0].endswith('/j1')
    assert m.calls[0][0]['conversation'] == context
    assert m.calls[0][1]['aux'] is False
    assert writes[0][1]['headers']['If-Match'] == '"snapshot"'
    assert json.loads(writes[0][1]['json']['params'])['spoken_consent']['job_id'] == 'j1'


def test_wrong_owner_cannot_be_selected_even_by_model(monkeypatch):
    a, m, writes = brain(monkeypatch, [row(owner='someone-else')])
    assert a._release_freshest_held('go ahead') is None
    assert writes == [] and m.calls == []


def test_invented_task_id_never_releases(monkeypatch):
    a, _, writes = brain(monkeypatch, [row()], {'verdict': 'approved', 'job_id': 'nonexistent'})
    assert a._release_freshest_held('go ahead') is None
    assert writes == []


@pytest.mark.parametrize('changed', [{'goal': 'send to Morgan'}, {'status': 'cancelled'},
                                   {'params': '{"corrections":{"recipient":"Morgan"}}'}])
def test_change_during_model_call_invalidates_approval(monkeypatch, changed):
    original = row()
    a, _, writes = brain(monkeypatch, [original], latest={**original, **changed})
    assert a._release_freshest_held('go ahead') is None
    assert writes == []


def test_old_api_without_atomic_support_never_receives_release(monkeypatch):
    a, _, writes = brain(monkeypatch, [row()], etag=None)
    assert a._release_freshest_held('go ahead') is None
    assert writes == []


def test_rejected_atomic_patch_is_not_reported_as_released(monkeypatch):
    a, _, writes = brain(monkeypatch, [row()], patch_ok=False)
    assert a._release_freshest_held('go ahead') is None
    assert len(writes) == 1


def test_one_word_yes_reaches_judge_before_fragment_filter(monkeypatch):
    a, model, writes = brain(monkeypatch, [row()])
    out = a.hear('Yes', context=['Anticipy: Send the contract to Priya?'])
    assert out['decision'].decision == 'act'
    assert model.calls[0][0]['owner_utterance'] == 'Yes'
    assert len(writes) == 1


def test_prior_correction_is_visible_and_in_approved_authority(monkeypatch):
    a, m, writes = brain(monkeypatch, [row(params=json.dumps({'corrections': {'time': '6pm'}}))])
    a._release_freshest_held('Please proceed')
    assert '6pm' in m.calls[0][0]['held_tasks'][0]['params']
    assert 'They changed: time: 6pm' in json.loads(writes[0][1]['json']['params'])['approved_scope']


@pytest.mark.parametrize('missing_required', [False, True])
def test_canonical_workflow_keeps_its_approval_invariants(monkeypatch, missing_required):
    from brain.workflow import new_plan, Consequence, put_in_params, from_params
    plan = new_plan(owner_ref='t', lineage_key='conversation-1', goal=row()['goal'],
                    consequence=Consequence.CONSEQUENTIAL, source_event_id='event-1',
                    required=('recipient',), facts={} if missing_required else {'recipient':'Priya'})
    job = row(**plan.job_fields(), owner='t', params=json.dumps(put_in_params({}, plan)))
    a, _, writes = brain(monkeypatch, [job])
    result = a._release_freshest_held('Please proceed')
    if missing_required:
        assert result is None and writes == []
    else:
        assert result == job['goal'] and len(writes) == 1
        approved = from_params(json.loads(writes[0][1]['json']['params']))
        assert approved.approved_for_current_version


def test_absent_model_does_not_query_or_release(monkeypatch):
    a, model, writes = brain(monkeypatch, [row()])
    model.live = False
    monkeypatch.setattr('brain.anticipy_core.backend.get', lambda *a, **kw: pytest.fail('no model can authorize'))
    assert a._release_freshest_held('go ahead') is None
    assert writes == []
