"""Every parked API reply names the clause that parked it -- and nothing else.

Until 2026-09-14 `Conversation._flip_reply` had five refusal sites that all
returned the same silent `failed:<job>`; a reply that never moved a job could
not be attributed from the live log. Now each refusal prints exactly one
`api reply replan refused: job=<id> reason=<token>` line. The token is a
program state: the owner's words, the question, the job's result, the ETag,
the verdict and any exception MESSAGE must never reach stdout.
"""
import json
from types import SimpleNamespace

import pytest

from brain import backend, hands
from brain.conversation import Conversation
from brain.workflow import Consequence, new_plan, put_in_params

OWNER = 'owner-1'
ETAG = '"' + 'a' * 64 + '"'
ANSWER = 'the work calendar, the one with the dentist on it'
QUESTION = 'Which calendar should I read, work or personal?'
SECRET = 'provider said: key sk-live-000 rejected'
PREFIX = f'api reply replan refused: job=job-1 reason='


def _plan(owner=OWNER, goal='read my calendar for tomorrow'):
    return new_plan(owner_ref=owner, lineage_key='lineage-1', goal=goal,
                    consequence=Consequence.READ_ONLY, source_event_id='event-1')


def _note(**over):
    note = {'hand': hands.HAND_API, 'effect': hands.EFFECT_READ, 'app': 'googlecalendar',
            'alias': '', 'outcome': None}
    note.update(over)
    return note


def _verdict(**over):
    base = dict(hand=hands.HAND_API, reason='one usable row', app='googlecalendar',
                effect=hands.EFFECT_READ, tool='GOOGLECALENDAR_FIND_EVENT',
                args={'query': ANSWER}, alias='')
    base.update(over)
    return hands.HandVerdict(**base)


def _context():
    return hands.HandContext(connections=(hands.ConnectedApp('googlecalendar', alias='work'),),
                             owner_ref=OWNER)


class Rig:
    def __init__(self, monkeypatch, spec):
        self.spec = spec
        plan = _plan(owner=spec.get('plan_owner', OWNER))
        previous = put_in_params({'_hand': spec.get('note', _note())}, plan)
        proposed = put_in_params({'_hand': spec.get('note', _note())}, plan)
        if 'workflow_patch' in spec:
            proposed['_workflow'].update(spec['workflow_patch'])
        if spec.get('drop_workflow'):
            proposed.pop('_workflow')
        self.job = {'id': 'job-1', 'lane': 'api', 'owner_ref': OWNER, 'status': 'awaiting_confirm',
                    'goal': plan.goal, 'workflow_id': plan.plan_id, 'result': QUESTION,
                    'params': json.dumps(previous), **spec.get('job', {})}
        self.fields = {'status': 'queued', 'params': json.dumps(proposed), **spec.get('fields', {})}
        self.anticipy = SimpleNamespace(owner_ref=spec.get('owner', OWNER),
                                        backend_url='http://backend.test', llm=None, brain=None)
        self.convo = Conversation(self.anticipy)
        self.flips = []
        self.convo._flip = lambda job_id, fields, verb, expected_headers=None: (
            self.flips.append((job_id, fields, verb, expected_headers)) or f'{verb}:{job_id}')
        monkeypatch.setattr(backend, 'patch',
                            lambda *a, **k: pytest.fail('a refused replan must not PATCH'))
        monkeypatch.setattr(backend, 'get', lambda *a, **k: self._response())
        monkeypatch.setattr(hands, 'gather_context', self._gather)
        monkeypatch.setattr(hands, 'choose_hand', self._choose)

    def _response(self):
        shape = self.spec.get('reread', 'same')
        if shape == 'down':
            # A real failed re-read is an error PAGE, not JSON. Returning a
            # usable body here made `reread_failed` reachable whether or not
            # `fresh.ok` short-circuits before `.json()` -- so the one lazy
            # guarantee the docstring claims was the one nothing could pin.
            def explode():
                raise json.JSONDecodeError('Expecting value', '<html>502</html>', 0)
            return SimpleNamespace(ok=False, headers={'ETag': ETAG}, json=explode)
        body = dict(self.job) if shape != 'changed' else {**self.job, 'status': 'cancelled'}
        headers = {'ETag': ETAG}
        if shape == 'no_etag':
            headers = {}
        if shape == 'bad_etag':
            headers = {'ETag': '"not-a-sha"'}
        return SimpleNamespace(ok=True, headers=headers, json=lambda: body)

    def _gather(self, params, owner_ref='', backend_url=''):
        if self.spec.get('gather_raises'):
            raise RuntimeError(SECRET)
        return _context()

    def _choose(self, goal, context=None, llm=None):
        if self.spec.get('rotate_owner'):
            self.anticipy.owner_ref = 'someone-else'
        return _verdict(**self.spec.get('verdict', {}))

    def run(self):
        return self.convo._flip_reply(self.job, self.fields, 'resumed',
                                      self.spec.get('owner_text', ANSWER))

    def flip_fails(self):
        """The conditional write loses its If-Match race: `_flip`'s own refusal."""
        self.convo._flip = lambda *a, **k: f'failed:{self.job["id"]}'


SCENARIOS = [
    # site 1: owner / answer / status / fields
    ('owner_missing', {'owner': ''}),
    ('owner_mismatch', {'job': {'owner_ref': 'someone-else'}}),
    ('answer_empty', {'owner_text': '   '}),
    ('status_not_parked', {'job': {'status': 'queued'}}),
    ('fields_not_queued', {'fields': {'status': 'running'}}),
    # site 2: fresh read and ETag
    ('reread_failed', {'reread': 'down'}),
    ('reread_changed', {'reread': 'changed'}),
    ('etag_missing', {'reread': 'no_etag'}),
    ('etag_malformed', {'reread': 'bad_etag'}),
    # site 3: the old note and the proposed workflow
    ('note_not_dict', {'note': 'api'}),
    ('note_not_api_hand', {'note': _note(hand='browser')}),
    ('note_not_read', {'note': _note(effect='write')}),
    ('workflow_missing', {'drop_workflow': True}),
    ('workflow_owner_mismatch', {'plan_owner': 'someone-else'}),
    ('workflow_plan_mismatch', {'job': {'workflow_id': 'another-plan'}}),
    ('workflow_goal_mismatch', {'job': {'goal': 'a different goal'}}),
    ('workflow_not_queued', {'workflow_patch': {'state': 'needs_user'}}),
    ('workflow_not_read_only', {'workflow_patch': {'consequence': 'reversible_local'}}),
    # site 4: the verdict
    ('verdict_not_api_hand', {'verdict': {'hand': 'browser'}}),
    ('verdict_not_read', {'verdict': {'effect': 'write'}}),
    ('verdict_app_changed', {'verdict': {'app': 'gmail'}}),
    ('verdict_no_tool', {'verdict': {'tool': ''}}),
    ('verdict_args_invalid', {'verdict': {'args': None}}),
    ('alias_required', {'note': _note(alias='work'), 'verdict': {'alias': ''}}),
    ('account_not_connected', {'verdict': {'alias': 'personal'}}),
    ('owner_changed', {'rotate_owner': True}),
    # site 5: the except
    ('exception:RuntimeError', {'gather_raises': True}),
    # site 6: the conditional write's own refusal, AFTER the model call
    ('write_refused', {'flip_fails': True}),
]


def test_every_scenario_has_its_own_token():
    tokens = [token for token, _ in SCENARIOS]
    assert len(set(tokens)) == len(tokens)


@pytest.mark.parametrize('token,spec', SCENARIOS, ids=[t for t, _ in SCENARIOS])
def test_refusal_names_exactly_one_clause_and_nothing_private(monkeypatch, capsys, token, spec):
    rig = Rig(monkeypatch, spec)
    if spec.get('flip_fails'):
        rig.flip_fails()
    assert rig.run() == 'failed:job-1'
    assert rig.flips == []
    out = capsys.readouterr().out
    lines = [line for line in out.splitlines() if line.startswith('api reply replan refused:')]
    assert lines == [PREFIX + token]
    for private in (ANSWER, QUESTION, SECRET, 'a' * 64, 'sk-live'):
        assert private not in out


def test_control_replan_flips_with_the_etag_and_says_nothing(monkeypatch, capsys):
    rig = Rig(monkeypatch, {})
    assert rig.run() == 'resumed:job-1'
    assert len(rig.flips) == 1
    job_id, fields, verb, headers = rig.flips[0]
    assert (job_id, verb, headers) == ('job-1', 'resumed', {'If-Match': ETAG})
    note = json.loads(fields['params'])['_hand']
    assert (note['hand'], note['effect'], note['tool'], note['lane']) == (
        hands.HAND_API, hands.EFFECT_READ, 'GOOGLECALENDAR_FIND_EVENT', hands.LANE_API)
    assert 'refused' not in capsys.readouterr().out
