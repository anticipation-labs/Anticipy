"""Exercise production delivery through persistence, failure and restart races."""
import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from brain.reply_delivery import ReplyDelivery
from brain.conversation import Conversation


@pytest.fixture
def rig(monkeypatch):
    from brain import backend
    db = sqlite3.connect(':memory:', check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute('CREATE TABLE events (id TEXT PRIMARY KEY, owner_ref TEXT, kind TEXT, '
               'text TEXT, decision TEXT, goal TEXT, source TEXT, device_id TEXT, '
               'created INTEGER, external_event_id TEXT UNIQUE)')
    lock = threading.Lock()
    def response(body):
        return SimpleNamespace(json=lambda: body, raise_for_status=lambda: None)
    def post(url, json, **kw):
        with lock:
            row = {'id': str(db.execute('SELECT count(*) FROM events').fetchone()[0] + 1),
                   'created': 1, **json}
            db.execute(f'INSERT INTO events ({",".join(row)}) VALUES ({",".join("?" for _ in row)})', list(row.values()))
            return response(dict(db.execute('SELECT * FROM events WHERE id=?', (row['id'],)).fetchone()))
    def get(url, params, **kw):
        with lock:
            sql = params['filter'].replace('&&', 'AND').replace('||', 'OR')
            return response({'items': [dict(r) for r in db.execute('SELECT * FROM events WHERE '+sql)]})
    def patch(url, json, **kw):
        with lock:
            db.execute(f'UPDATE events SET {",".join(k+"=?" for k in json)} WHERE id=?',
                       [*json.values(), url.rsplit('/', 1)[1]])
            return response({})
    monkeypatch.setattr(backend, 'post', post)
    monkeypatch.setattr(backend, 'get', get)
    monkeypatch.setattr(backend, 'patch', patch)
    transport = SimpleNamespace(send=Mock(return_value={'sid': 'provider-1', 'delivered': False}))
    delivery = ReplyDelivery('http://fixture', 'owner1', transport, lambda: '+15555550101')
    return SimpleNamespace(db=db, transport=transport, delivery=delivery, post=post)


EVENT = {'id': 'input1', 'owner_ref': 'owner1', 'source': 'typed'}


def test_feed_exists_before_any_provider_effect(rig):
    def send(*a, **kw):
        assert rig.db.execute("SELECT text FROM events WHERE kind='anticipy_text'").fetchone()[0] == 'A saved answer'
        assert rig.db.execute("SELECT decision FROM events WHERE kind='notification_status'").fetchone()[0] == 'sms_unconfirmed'
        return {'sid': 'accepted', 'delivered': False}
    rig.transport.send.side_effect = send
    rig.delivery.publish(EVENT, 'A saved answer')
    assert rig.db.execute("SELECT decision FROM events WHERE kind='reply_outbox'").fetchone()[0] == 'sms_accepted'


def test_timeout_keeps_answer_and_never_blindly_repeats(rig):
    rig.transport.send.side_effect = TimeoutError()
    rig.delivery.publish(EVENT, 'I need one detail')
    restarted = ReplyDelivery('http://fixture', 'owner1', rig.transport, lambda: '+15555550101')
    restarted.publish(EVENT, 'A rephrased duplicate')
    restarted.sweep()
    assert rig.transport.send.call_count == 1
    assert rig.db.execute("SELECT text FROM events WHERE kind='anticipy_text'").fetchone()[0] == 'I need one detail'
    assert rig.db.execute("SELECT decision FROM events WHERE kind='reply_outbox'").fetchone()[0] == 'sms_unconfirmed'


def test_restart_before_send_resumes_without_rethinking(rig):
    rig.delivery.phone = lambda: ''
    rig.delivery.publish(EVENT, 'Still saved')
    assert rig.transport.send.call_count == 0
    ReplyDelivery('http://fixture', 'owner1', rig.transport, lambda: '+15555550101').sweep()
    assert rig.transport.send.call_count == 1


def test_concurrent_publish_only_one_send(rig):
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: rig.delivery.publish(EVENT, 'Same input'), range(2)))
    assert rig.transport.send.call_count == 1
    assert rig.db.execute("SELECT count(*) FROM events WHERE kind='anticipy_text'").fetchone()[0] == 1


def test_foreign_owner_is_refused(rig):
    with pytest.raises(ValueError):
        rig.delivery.publish({**EVENT, 'owner_ref': 'other'}, 'Private')
    assert rig.transport.send.call_count == 0


def test_same_words_on_distinct_events_are_not_semantic_deduplication(rig):
    rig.delivery.publish(EVENT, 'Sure')
    rig.delivery.publish({**EVENT, 'id': 'input2'}, 'Sure')
    assert rig.transport.send.call_count == 2


def test_app_and_sms_use_the_same_publisher_even_in_app_context(rig):
    convo = Conversation(SimpleNamespace(llm=None), rig.transport)
    convo.reply_delivery = rig.delivery.publish
    with convo.from_event(EVENT), convo.reply_in_app():
        convo.say('+15555550101', 'Question from the app')
    assert rig.transport.send.call_count == 1
    assert rig.db.execute("SELECT count(*) FROM events WHERE kind='anticipy_text'").fetchone()[0] == 1


def test_failed_non_durable_transport_does_not_poison_dedupe():
    transport = SimpleNamespace(send=Mock(side_effect=[TimeoutError(), {'sid': 'ok'}]))
    convo = Conversation(SimpleNamespace(llm=None), transport)
    with pytest.raises(TimeoutError):
        convo.say('phone', 'Same answer')
    assert convo.say('phone', 'Same answer') == {'sid': 'ok'}
    assert transport.send.call_count == 2


def test_unconfigured_transport_leaves_no_attempt_fence(rig):
    from brain.conversation import MockTransport
    rig.delivery.transport=MockTransport()
    rig.delivery.publish(EVENT,'Waiting for configuration')
    assert rig.db.execute("SELECT count(*) FROM events WHERE kind='notification_status'").fetchone()[0]==0
    rig.delivery.transport=rig.transport
    rig.delivery.sweep()
    assert rig.transport.send.call_count==1


def test_orphan_outbox_is_retired_and_cannot_starve_later_reply(rig):
    rig.delivery.create(kind='reply_outbox',decision='reply_pending',goal='missing',text='',external_event_id='orphan')
    rig.delivery.phone=lambda:''
    rig.delivery.publish(EVENT,'An actual answer')
    rig.delivery.phone=lambda:'+15555550101'
    rig.delivery.sweep()
    assert rig.transport.send.call_count==1
    assert rig.db.execute("SELECT decision FROM events WHERE external_event_id='orphan'").fetchone()[0]=='reply_missing'


def prepare_receipt(rig, state='delivered'):
    from datetime import datetime, timezone
    rig.delivery.publish(EVENT, 'The saved reply')
    rig.db.execute("UPDATE events SET created=? WHERE kind='notification_status'",
                   (datetime.now(timezone.utc).isoformat().replace('T', ' '),))
    rig.transport.message_status = Mock(return_value={
        'sid': 'provider-1', 'status': state, 'delivered': state in ('delivered', 'read')})


def test_lost_callback_is_reconciled_without_sending_again(rig):
    prepare_receipt(rig)
    rig.delivery.sweep()
    assert rig.transport.send.call_count == 1
    rig.transport.message_status.assert_called_once_with('provider-1')
    assert rig.db.execute("SELECT decision FROM events WHERE kind='notification_status'").fetchone()[0] == 'sms_delivered'
    assert rig.db.execute("SELECT decision FROM events WHERE kind='reply_outbox'").fetchone()[0] == 'sms_delivered'
    rig.delivery.sweep()
    assert rig.transport.send.call_count == 1
    assert rig.transport.message_status.call_count == 1


def test_receipt_timeout_is_throttled_across_restart_and_preserves_uncertainty(rig):
    prepare_receipt(rig)
    rig.db.execute("UPDATE events SET decision='sms_unconfirmed' WHERE kind='notification_status'")
    rig.transport.message_status.side_effect = TimeoutError()
    rig.delivery.sweep()
    ReplyDelivery('http://fixture', 'owner1', rig.transport, lambda: '+15555550101').sweep()
    assert rig.transport.message_status.call_count == 1
    assert rig.transport.send.call_count == 1
    assert rig.db.execute("SELECT decision FROM events WHERE kind='notification_status'").fetchone()[0] == 'sms_unconfirmed'


def test_late_negative_or_queued_observation_cannot_downgrade_delivered_callback(rig):
    prepare_receipt(rig)
    def callback_races_lookup(handle):
        rig.db.execute("UPDATE events SET decision='sms_delivered' WHERE kind='notification_status'")
        return {'sid': handle, 'status': 'error', 'delivered': False}
    rig.transport.message_status.side_effect = callback_races_lookup
    rig.delivery.sweep()
    assert rig.db.execute("SELECT decision FROM events WHERE kind='notification_status'").fetchone()[0] == 'sms_delivered'
    assert rig.transport.send.call_count == 1


@pytest.mark.parametrize('receipt', [None, {}, {'sid': 'foreign', 'status': 'delivered'},
                                    {'sid': 'provider-1', 'status': 'sent', 'delivered': True}])
def test_unproven_receipt_never_promotes_delivery(rig, receipt):
    prepare_receipt(rig)
    rig.transport.message_status.return_value = receipt
    rig.delivery.sweep()
    assert rig.db.execute("SELECT decision FROM events WHERE kind='notification_status'").fetchone()[0] == 'sms_accepted'
    assert rig.transport.send.call_count == 1


@pytest.mark.parametrize('change', ['missing_handle', 'foreign_owner', 'foreign_message', 'old_attempt'])
def test_only_recent_owned_handles_with_owned_replies_are_queried(rig, change):
    prepare_receipt(rig)
    if change == 'missing_handle':
        rig.db.execute("UPDATE events SET text='{}' WHERE kind='notification_status'")
    elif change == 'foreign_owner':
        rig.db.execute("UPDATE events SET owner_ref='owner2' WHERE kind='notification_status'")
    elif change == 'foreign_message':
        rig.db.execute("UPDATE events SET owner_ref='owner2' WHERE kind='anticipy_text'")
    else:
        rig.db.execute("UPDATE events SET created='2000-01-01 00:00:00.000Z' WHERE kind='notification_status'")
    rig.delivery.sweep()
    assert not rig.transport.message_status.called
    assert rig.transport.send.call_count == 1


def test_one_provider_lookup_per_sweep(rig):
    prepare_receipt(rig, 'queued')
    rig.delivery.publish({**EVENT, 'id': 'input2'}, 'Second reply')
    from datetime import datetime, timezone
    rig.db.execute("UPDATE events SET created=? WHERE kind='notification_status'",
                   (datetime.now(timezone.utc).isoformat().replace('T', ' '),))
    rig.delivery.sweep()
    assert rig.transport.message_status.call_count == 1
    assert rig.transport.send.call_count == 2
