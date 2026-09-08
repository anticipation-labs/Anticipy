"""Real Conversation/TaskDelivery over local SQLite; meaning/provider are fixtures.

No network or live model. The adapter implements the existing record API's
If-Match contract; Worker tests separately exercise that SQL implementation.
"""
import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from brain import backend
from brain.conversation import Conversation, REPLY_SYSTEM, Turn
from brain.reply_delivery import ReplyDelivery
from brain.task_delivery import TaskDelivery
from brain.workflow import Consequence, from_params, merge, new_plan, put_in_params


OWNER = 'owner0000000001'
PHONE = '+15555550101'


@pytest.fixture
def rig(monkeypatch):
    codec = json
    db = sqlite3.connect(':memory:')
    db.row_factory = sqlite3.Row
    db.execute('CREATE TABLE events (id TEXT PRIMARY KEY, created TEXT, updated TEXT, '
               'owner_ref TEXT, kind TEXT, text TEXT, decision TEXT, goal TEXT, source TEXT, '
               'device_id TEXT, external_event_id TEXT UNIQUE)')
    db.execute('CREATE TABLE jobs (id TEXT PRIMARY KEY, record TEXT)')
    clock = [datetime(2026, 9, 8, 12, tzinfo=timezone.utc)]
    serial = [0]
    patches = []
    hooks = SimpleNamespace(before_patch=None, after_classify=None, read_error=False)
    def stamp():
        return clock[0].isoformat(timespec='milliseconds').replace('T', ' ')
    def tick():
        clock[0] += timedelta(seconds=1)
    def response(body, status=200, headers=None):
        def raise_for_status():
            if status >= 400:
                raise RuntimeError(f'fixture HTTP {status}')
        return SimpleNamespace(json=lambda: body, ok=status < 400, status_code=status,
                               headers=headers or {}, raise_for_status=raise_for_status)
    def read_job():
        return json.loads(db.execute('SELECT record FROM jobs WHERE id="job1"').fetchone()[0])
    def save_job(row):
        db.execute('INSERT OR REPLACE INTO jobs VALUES (?,?)', ('job1', json.dumps(row)))
    def etag(row):
        return '"' + hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest() + '"'
    def post(url, json, **kw):
        assert url.startswith('http://fixture/'), 'network escape'
        if url.endswith('/worker/reply-presentations'):
            if hooks.read_error:
                raise TimeoutError('local evidence read unavailable')
            inbound = dict(db.execute('SELECT * FROM events WHERE id=? AND owner_ref=?',
                                     (json['event_id'], json['owner_ref'])).fetchone())
            digest = hashlib.sha256(inbound['goal'].encode()).hexdigest()
            messages, presentations = [], []
            chains = db.execute("""SELECT m.*,o.id AS outbox_id,o.text AS outbox_text,
              o.created AS outbox_created,o.updated AS outbox_updated,
              a.created AS attempt_created,a.updated AS observed_delivered_at,
              a.text AS receipt,a.decision AS delivery_state
              FROM events o JOIN events m ON o.goal=m.id AND o.owner_ref=m.owner_ref
              JOIN events a ON a.goal=m.id AND a.owner_ref=m.owner_ref
              WHERE o.kind='reply_outbox' AND m.kind='anticipy_text' AND a.kind='notification_status'
              AND o.external_event_id=('reply-outbox:' || m.id)
              AND a.external_event_id=('reply-sms:' || m.id) AND o.owner_ref=?""", (OWNER,)).fetchall()
            for row in chains:
                receipt = codec.loads(row['receipt'] or '{}')
                if (row['delivery_state'] != 'sms_delivered' or not receipt.get('provider_id')
                        or receipt.get('recipient_digest') != digest):
                    continue
                message = {key: row[key] for key in ('id', 'text', 'owner_ref', 'created', 'updated', 'observed_delivered_at')}
                messages.append(message)
                meta = codec.loads(row['outbox_text'] or '{}')
                if (meta.get('job_id') == 'job1' and read_job()['status'] in ('awaiting_confirm', 'needs_user', 'queued')):
                    presentations.append({**message, 'message_id': row['id'], 'presentation_id': row['outbox_id'],
                        'snapshot': meta, **{key: row[key] for key in ('outbox_created', 'outbox_updated', 'attempt_created')}})
            return response({'ok': True, 'complete': True, 'owner_ref': OWNER,
                'event_id': inbound['id'], 'inbound_created': inbound['created'],
                'recipient_digest': digest, 'messages': messages, 'presentations': presentations})
        serial[0] += 1
        row = {'id': f'event{serial[0]}', 'created': stamp(), 'updated': stamp(), **json}
        db.execute(f'INSERT INTO events ({",".join(row)}) VALUES ({",".join("?" for _ in row)})', list(row.values()))
        return response(dict(db.execute('SELECT * FROM events WHERE id=?', (row['id'],)).fetchone()))
    def get(url, params=None, **kw):
        assert url.startswith('http://fixture/'), 'network escape'
        if hooks.read_error:
            raise TimeoutError('local evidence read unavailable')
        if '/jobs/records/' in url:
            row = read_job()
            return response(row, headers={'ETag': etag(row)})
        expression = (params or {}).get('filter', '1').replace('&&', 'AND').replace('||', 'OR')
        rows = [dict(r) for r in db.execute('SELECT * FROM events WHERE ' + expression + ' ORDER BY created,id')]
        return response({'items': rows})
    def patch(url, json, headers=None, **kw):
        assert url.startswith('http://fixture/'), 'network escape'
        if '/jobs/records/' in url:
            if hooks.before_patch:
                hook, hooks.before_patch = hooks.before_patch, None
                hook()
            old = read_job()
            patches.append((json, headers or {}))
            if headers and headers.get('If-Match') != etag(old):
                return response({}, 412)
            row = {**old, **json}
            save_job(row)
            return response(row)
        db.execute(f'UPDATE events SET {",".join(k+"=?" for k in json)},updated=? WHERE id=?',
                   [*json.values(), stamp(), url.rsplit('/', 1)[1]])
        return response({})
    monkeypatch.setattr(backend, 'post', post)
    monkeypatch.setattr(backend, 'get', get)
    monkeypatch.setattr(backend, 'patch', patch)
    monkeypatch.setattr('requests.sessions.Session.request', Mock(side_effect=AssertionError('network escape')))
    plan = new_plan(owner_ref=OWNER, lineage_key='source1', goal='Submit the conference RSVP for six',
                    consequence=Consequence.CONSEQUENTIAL, source_event_id='source1',
                    authority_text='Please prepare my conference RSVP for six.', plan_id='plan1', now=clock[0])
    save_job({'id': 'job1', 'owner_ref': OWNER, 'goal': plan.goal, 'result': 'Ready to submit the RSVP for six?',
              **plan.job_fields(), 'params': json.dumps(put_in_params({'source': plan.authority_text}, plan))})
    transport = SimpleNamespace(send=Mock(return_value={'sid': 'provider1', 'delivered': True}))
    delivery = ReplyDelivery('http://fixture', OWNER, transport, lambda: PHONE)
    task = TaskDelivery(delivery)
    model_state = {'intent': 'confirm', 'changes': None, 'selection': None, 'verdict': 'selected'}
    model_calls = []
    def chat(system, payload):
        data = json.loads(payload)
        model_calls.append((system, data))
        if system == REPLY_SYSTEM:
            if hooks.after_classify:
                hook, hooks.after_classify = hooks.after_classify, None
                hook()
            out = {'intent': model_state['intent'], 'pending_id': 'job1', 'pending_ids': ['job1'],
                   'changes': model_state['changes'], 'reply': 'On it.'}
        else:
            out = {'verdict': model_state['verdict'], 'presentation_ids': model_state['selection'] or []}
        return SimpleNamespace(text=json.dumps(out))
    model = SimpleNamespace(live=True, chat=chat)
    owner = SimpleNamespace(owner_ref=OWNER, owner_id='', backend_url='http://fixture', llm=model,
                            memory=SimpleNamespace(recall=lambda *a, **kw: []))
    convo = Conversation(owner, transport, model)
    convo.reply_delivery = delivery.publish
    monkeypatch.setattr(convo, '_remember_about_owner', lambda text: {})
    monkeypatch.setattr(convo, '_pending', lambda: [read_job()] if read_job()['status'] == 'awaiting_confirm' else [])
    monkeypatch.setattr(convo, '_blocked', lambda: [read_job()] if read_job()['status'] == 'needs_user' else [])
    monkeypatch.setattr(convo, '_queued', lambda: [read_job()] if read_job()['status'] == 'queued' else [])
    for name in ('_running', '_recent_outcomes', '_captured_context'):
        monkeypatch.setattr(convo, name, lambda: [])
    monkeypatch.setattr(convo, '_about_pending', lambda *_a: 'detail')
    def present():
        task.publish(read_job(), read_job()['result'])
        outbox = db.execute("SELECT id FROM events WHERE kind='reply_outbox' ORDER BY created DESC,id DESC LIMIT 1").fetchone()[0]
        model_state['selection'] = [outbox]
        tick()
        return outbox
    def revise():
        row = read_job()
        p = from_params(json.loads(row['params']))
        p = merge(p, expected_version=p.version, goal='Submit the conference RSVP for four', facts={'party_size': 4})
        save_job({**row, **p.job_fields(), 'goal': p.goal, 'result': 'Ready to submit the RSVP for four?',
                  'params': json.dumps(put_in_params(json.loads(row['params']), p))})
    def reply(text='Yes, go ahead', app=False):
        event = {'kind': 'sms_reply', 'owner_ref': OWNER, 'goal': PHONE, 'text': text}
        context = None
        if app:
            row = read_job()
            event['kind'] = 'app_reply'
            context = {'reply_to_job_id': 'job1', 'workflow_version': row['workflow_version'],
                       'question': row['result'], 'goal': row['goal']}
        event = post('http://fixture/api/collections/events/records', json=event).json()
        with convo.from_event(event):
            return convo.on_reply(PHONE, text, reply_context=context)
    return SimpleNamespace(db=db, job=read_job, save=save_job, present=present, revise=revise, reply=reply,
                           tick=tick, clock=clock, transport=transport, delivery=delivery, task=task,
                           model=model_state, calls=model_calls, hooks=hooks, convo=convo, patches=patches)


def test_sms_yes_cannot_approve_a_revision_never_presented(rig):
    rig.present()
    rig.revise()
    before = rig.job()
    out = rig.reply()
    assert rig.job() == before, 'SMS approval silently switched to the newest job revision'
    assert not rig.patches
    assert 'changed' in out['reply'].lower() or 'question' in out['reply'].lower()


@pytest.mark.parametrize('state', ['sms_accepted', 'sms_unconfirmed', 'sms_failed', 'reply_pending'])
def test_unreceived_question_is_not_an_approval_candidate(rig, state):
    rig.present()
    rig.db.execute("UPDATE events SET decision=? WHERE kind='notification_status'", (state,))
    before = rig.job()
    rig.reply()
    assert rig.job() == before
    assert not rig.patches


def test_valid_delivered_snapshot_can_be_approved_with_atomic_identity(rig):
    rig.present()
    out = rig.reply('That RSVP is right, please send it')
    assert rig.job()['status'] == 'queued'
    assert out['acted'] == 'released:job1'
    assert rig.patches[0][1].get('If-Match'), 'authority write lost its expected snapshot'


@pytest.mark.parametrize('boundary', ['after_classify', 'before_patch'])
def test_correction_during_an_await_never_releases_or_overwrites_new_scope(rig, boundary):
    rig.present()
    setattr(rig.hooks, boundary, rig.revise)
    rig.reply()
    assert rig.job()['goal'].endswith('four')
    assert rig.job()['status'] == 'awaiting_confirm'
    assert not json.loads(rig.job()['params'])['_workflow'].get('approval')


def test_delayed_receipt_does_not_retroactively_authorize_earlier_reply(rig):
    rig.present()
    future = (rig.clock[0] + timedelta(seconds=10)).isoformat()
    rig.db.execute("UPDATE events SET updated=? WHERE kind='notification_status'", (future,))
    rig.reply()
    assert rig.job()['status'] == 'awaiting_confirm'


def test_receipt_read_uncertainty_does_not_authorize(rig):
    rig.present()
    rig.hooks.read_error = True
    rig.convo.say = Mock(return_value={})  # delivery is separately unavailable too
    out = rig.reply()
    assert rig.job()['status'] == 'awaiting_confirm'
    assert not rig.patches
    assert out['acted'] is None or out['acted'].startswith('failed:')


@pytest.mark.parametrize('verdict', ['none', 'ambiguous', 'unavailable'])
def test_independent_referent_floor_requires_positive_meaning_verdict(rig, verdict):
    rig.present()
    rig.model['verdict'] = verdict
    rig.reply()
    assert rig.job()['status'] == 'awaiting_confirm'
    assert not rig.patches


def test_app_card_context_cannot_race_a_correction_during_classification(rig):
    rig.hooks.after_classify = rig.revise
    rig.reply(app=True)
    assert rig.job()['goal'].endswith('four')
    assert rig.job()['status'] == 'awaiting_confirm'


def test_a_genuine_new_request_does_not_need_a_task_presentation(rig, monkeypatch):
    rig.model['intent'] = 'new_request'
    monkeypatch.setattr(rig.convo, '_about_pending', lambda *_a: 'no')
    think = Mock(return_value='I will look up those opening hours.')
    monkeypatch.setattr(rig.convo, '_think', think)
    rig.reply('Could you look up the library opening hours?')
    think.assert_called_once()
    assert not rig.patches


def test_correction_then_yes_uses_the_new_delivered_question(rig):
    rig.present()
    rig.model.update(intent='modify', changes={'party_size': 4})
    out = rig.reply('Make it four people instead')
    assert out['acted'] == 'amended:job1'
    assert rig.job()['status'] == 'awaiting_confirm'
    assert from_params(json.loads(rig.job()['params'])).facts['party_size'] == 4
    newest = rig.db.execute("SELECT id,text FROM events WHERE kind='reply_outbox' ORDER BY created DESC,id DESC LIMIT 1").fetchone()
    assert json.loads(newest['text'])['version'] == rig.job()['workflow_version']
    rig.model.update(intent='confirm', changes=None, selection=[newest['id']])
    rig.tick()
    rig.reply('Yes, that is right now')
    assert rig.job()['status'] == 'queued'
    assert from_params(json.loads(rig.job()['params'])).facts['party_size'] == 4


@pytest.mark.parametrize('key,value', [('recipient_digest', 'another-phone'), ('provider_id', ''),
                                     ('recipient_digest', None)])
def test_receipt_must_belong_to_the_actual_inbound_sender(rig, key, value):
    rig.present()
    row = rig.db.execute("SELECT id,text FROM events WHERE kind='notification_status'").fetchone()
    meta = json.loads(row['text'])
    meta[key] = value
    rig.db.execute('UPDATE events SET text=? WHERE id=?', (json.dumps(meta), row['id']))
    rig.reply()
    assert rig.job()['status'] == 'awaiting_confirm'
    assert not rig.patches


@pytest.mark.parametrize('key,value', [('binding_version', 0), ('owner_ref', 'someoneelse'),
                                     ('plan_id', 'other-plan'), ('effect_key', 'other-effect'),
                                     ('scope_digest', 'other-scope'), ('goal', 'An unpresented task')])
def test_unbound_or_mismatched_question_metadata_cannot_approve(rig, key, value):
    rig.present()
    row = rig.db.execute("SELECT id,text FROM events WHERE kind='reply_outbox'").fetchone()
    meta = json.loads(row['text'])
    meta[key] = value
    rig.db.execute('UPDATE events SET text=? WHERE id=?', (json.dumps(meta), row['id']))
    rig.reply()
    assert rig.job()['status'] == 'awaiting_confirm'
    assert not rig.patches


def test_legacy_question_metadata_is_not_silently_promoted(rig):
    rig.present()
    row = rig.db.execute("SELECT id,text FROM events WHERE kind='reply_outbox'").fetchone()
    meta = json.loads(row['text'])
    legacy = {key: meta[key] for key in ('purpose', 'job_id', 'version', 'status', 'question')}
    rig.db.execute('UPDATE events SET text=? WHERE id=?', (json.dumps(legacy), row['id']))
    rig.reply()
    assert rig.job()['status'] == 'awaiting_confirm'


def test_unsent_app_message_cannot_poison_a_cached_sms_thread(rig):
    rig.present()
    rig.delivery.phone = lambda: ''
    rig.delivery.publish({'id': 'app-only', 'owner_ref': OWNER}, 'A newer question that never reached SMS')
    rig.convo.threads[PHONE] = [Turn('anticipy', 'A newer question that never reached SMS')]
    rig.tick()
    rig.reply()
    classification = next(data for system, data in rig.calls if system == REPLY_SYSTEM)
    assert all('never reached SMS' not in turn['text'] for turn in classification['thread'])
    assert any('RSVP for six' in turn['text'] for turn in classification['thread'])


def test_equal_delivery_and_inbound_timestamp_is_not_proof_of_order(rig):
    rig.present()
    rig.db.execute("UPDATE events SET updated=? WHERE kind='notification_status'", (rig.clock[0].isoformat(),))
    rig.reply()
    assert rig.job()['status'] == 'awaiting_confirm'


@pytest.mark.parametrize('selection', [['invented'], ['event2', 'event2']])
def test_missing_or_duplicate_model_presentation_ids_never_authorize(rig, selection):
    rig.present()
    rig.model['selection'] = selection
    rig.reply()
    assert rig.job()['status'] == 'awaiting_confirm'


def test_receipt_lookup_mixed_owner_response_fails_closed(rig, monkeypatch):
    rig.present()
    original = backend.post
    def post(url, **kwargs):
        response = original(url, **kwargs)
        if url.endswith('/worker/reply-presentations'):
            rows = response.json()['messages']
            rows.append({**rows[0], 'id': 'foreign', 'owner_ref': 'someoneelse'})
        return response
    monkeypatch.setattr(backend, 'post', post)
    rig.reply()
    assert rig.job()['status'] == 'awaiting_confirm'


def test_missing_etag_is_unknown_not_permission_to_patch(rig, monkeypatch):
    rig.present()
    original = backend.get
    def get(url, **kwargs):
        response = original(url, **kwargs)
        if '/jobs/' in url:
            response.headers.clear()
        return response
    monkeypatch.setattr(backend, 'get', get)
    rig.reply()
    assert rig.job()['status'] == 'awaiting_confirm'
    assert not rig.patches
