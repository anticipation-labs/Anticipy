"""Persist structural failure facts, never private prose or resend authority.

The existing SQLite publisher fixture executes real delivery code with every
backend call doubled. SendBlue response parsing below never makes a request.
"""
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

from brain import backend, sendblue_arm as sb
from brain.reply_delivery import ReplyDelivery
from test_reply_delivery import EVENT, rig  # noqa: F401 -- shared offline fixture


PRIVATE = 'TOXIC_PRIVATE_BODY_PHONE_KEY_URL_SENTINEL'


class UnprintableFailure(RuntimeError):
    def __str__(self):
        raise AssertionError('Exception prose must not be read')

    def __repr__(self):
        raise AssertionError('Exception representation must not be read')


def http_error(status):
    return requests.HTTPError(PRIVATE, response=SimpleNamespace(
        status_code=status, text=PRIVATE, headers={'Authorization': PRIVATE}))


@pytest.mark.parametrize('error,category,http', [
    (TimeoutError(PRIVATE), 'timeout', None),
    (requests.ReadTimeout(PRIVATE), 'timeout', None),
    (requests.ConnectTimeout(PRIVATE), 'timeout', None),
    (requests.ConnectionError(PRIVATE), 'connection_error', None),
    (http_error(401), 'provider_auth_error', 401),
    (http_error(402), 'provider_payment_error', 402),
    (http_error(429), 'provider_rate_limit', 429),
    (http_error(503), 'provider_server_error', 503),
    (http_error(400), 'provider_http_error', 400),
    (UnprintableFailure({'nested': PRIVATE}), 'unexpected_error', None),
])
def test_send_failure_persists_only_structural_diagnosis_and_never_resends(rig, error, category, http):
    rig.transport.send.side_effect = error
    rig.delivery.publish(EVENT, 'Saved in-app reply')

    attempt = dict(rig.db.execute("SELECT * FROM events WHERE kind='notification_status'").fetchone())
    metadata = json.loads(attempt['text'])
    expected = {'version': 1, 'stage': 'sms_send', 'category': category}
    if http is not None:
        expected['http_status'] = http
    assert metadata.get('diagnostic') == expected
    assert PRIVATE not in attempt['text']
    assert metadata['recipient_digest']
    assert metadata['provider_id'] == ''
    assert attempt['decision'] == 'sms_unconfirmed'

    restarted = ReplyDelivery('http://fixture', 'owner1', rig.transport, lambda: '+15555550101')
    restarted.publish(EVENT, 'Must not replace the saved reply')
    restarted.sweep()
    restarted.sweep()
    assert rig.transport.send.call_count == 1
    assert rig.db.execute("SELECT text FROM events WHERE kind='anticipy_text'").fetchone()[0] == 'Saved in-app reply'
    assert rig.db.execute("SELECT decision FROM events WHERE kind='reply_outbox'").fetchone()[0] == 'sms_unconfirmed'


class Response:
    def __init__(self, payload, status=200, invalid_json=False):
        self.payload = payload
        self.status_code = status
        self.ok = 200 <= status < 300
        self.invalid_json = invalid_json

    def json(self):
        if self.invalid_json:
            raise ValueError(PRIVATE)
        return self.payload


def parser_arm():
    # Bypass only constructor credential loading; _result itself is real.
    arm = object.__new__(sb.SendblueArm)
    arm._secret = 'fixture-not-a-credential'
    arm.credential = 'fixture-key'
    return arm


@pytest.mark.parametrize('response,category,http', [
    (Response({'error_message': PRIVATE, 'nested': {'token': PRIVATE}}, 401), 'provider_http_error', 401),
    (Response(None, invalid_json=True), 'provider_response_invalid_json', 200),
    (Response([{'nested': PRIVATE}]), 'provider_response_invalid_shape', 200),
    (Response({'status': 'QUEUED', 'body': PRIVATE}), 'provider_response_missing_handle', 200),
    (Response({'message_handle': 'fixture-handle', 'status': 'DECLINED', 'error_message': PRIVATE}), 'provider_response_rejected', 200),
    (Response({'message_handle': 'fixture-handle', 'status': 'QUEUED', 'error_code': {'private': PRIVATE}}), 'provider_response_error', 200),
])
def test_actual_sendblue_response_failures_gain_safe_metadata_without_changing_attempt_state(rig, response, category, http):
    arm = parser_arm()
    rig.transport.send.side_effect = lambda *a, **kw: arm._result(response, 'text', '+15555550101')
    rig.delivery.publish(EVENT, 'Saved in-app reply')
    attempt = dict(rig.db.execute("SELECT * FROM events WHERE kind='notification_status'").fetchone())
    assert json.loads(attempt['text']).get('diagnostic') == {
        'version': 1, 'stage': 'sms_send', 'category': category, 'http_status': http}
    assert PRIVATE not in attempt['text']
    assert attempt['decision'] == 'sms_unconfirmed'
    rig.delivery.sweep()
    assert rig.transport.send.call_count == 1


@pytest.mark.parametrize('status', [True, False, '401', {'private': PRIVATE}, 99, 600])
def test_non_numeric_or_out_of_range_http_status_is_never_persisted(rig, status):
    rig.transport.send.side_effect = http_error(status)
    rig.delivery.publish(EVENT, 'Saved in-app reply')
    meta = json.loads(rig.db.execute("SELECT text FROM events WHERE kind='notification_status'").fetchone()[0])
    # The known HTTPError type is a fact even when its numeric status is not.
    assert meta.get('diagnostic') == {'version': 1, 'stage': 'sms_send', 'category': 'provider_http_error'}
    assert PRIVATE not in json.dumps(meta)


@pytest.mark.parametrize('delivered,state', [(False, 'sms_accepted'), (True, 'sms_delivered')])
def test_normal_transport_outcomes_remain_unchanged_and_are_not_failures(rig, delivered, state):
    rig.transport.send.return_value = {'sid': 'fixture-handle', 'delivered': delivered}
    rig.delivery.publish(EVENT, 'Saved in-app reply')
    attempt = dict(rig.db.execute("SELECT * FROM events WHERE kind='notification_status'").fetchone())
    assert attempt['decision'] == state
    assert 'diagnostic' not in json.loads(attempt['text'])


def test_lost_diagnostic_write_cannot_remove_attempt_fence_or_resend(rig, monkeypatch):
    rig.transport.send.side_effect = TimeoutError(PRIVATE)
    original_patch = backend.patch
    def unavailable(url, json, **kwargs):
        if 'diagnostic' in str(json.get('text', '')):
            raise ConnectionError('fixture write unavailable')
        return original_patch(url, json=json, **kwargs)
    monkeypatch.setattr(backend, 'patch', unavailable)
    rig.delivery.publish(EVENT, 'Saved in-app reply')
    rig.delivery.sweep()
    assert rig.transport.send.call_count == 1
    assert rig.db.execute("SELECT decision FROM events WHERE kind='notification_status'").fetchone()[0] == 'sms_unconfirmed'


def test_foreign_owner_cannot_create_diagnostics_or_send(rig):
    rig.transport.send.side_effect = TimeoutError(PRIVATE)
    with pytest.raises(ValueError):
        rig.delivery.publish({**EVENT, 'owner_ref': 'other-owner'}, 'Not ours')
    assert rig.db.execute('SELECT count(*) FROM events').fetchone()[0] == 0
    assert rig.transport.send.call_count == 0


def test_recent_unconfirmed_attempt_without_handle_never_looks_up_or_resends(rig):
    rig.transport.send.side_effect = TimeoutError(PRIVATE)
    rig.transport.message_status = Mock(side_effect=AssertionError('No saved handle authorizes a lookup'))
    rig.delivery.publish(EVENT, 'Saved in-app reply')
    rig.db.execute("UPDATE events SET created=? WHERE kind='notification_status'",
                   (datetime.now(timezone.utc).isoformat().replace('T', ' '),))
    rig.delivery.sweep()
    assert rig.transport.send.call_count == 1
    rig.transport.message_status.assert_not_called()


@pytest.mark.parametrize('category,status', [
    (PRIVATE, True), ({'nested': PRIVATE}, {'nested': PRIVATE}),
    ([PRIVATE], '401'), (PRIVATE, 600),
])
def test_structured_sendblue_error_still_passes_closed_serializer(rig, category, status):
    rig.transport.send.side_effect = sb.SendblueSendFailed(
        PRIVATE, category=category, http_status=status)
    rig.delivery.publish(EVENT, 'Saved in-app reply')
    meta = json.loads(rig.db.execute("SELECT text FROM events WHERE kind='notification_status'").fetchone()[0])
    assert meta.get('diagnostic') == {'version': 1, 'stage': 'sms_send', 'category': 'unexpected_error'}
    assert PRIVATE not in json.dumps(meta)


def test_unknown_exception_cannot_smuggle_structured_lookalike_fields(rig):
    error = UnprintableFailure(PRIVATE)
    error.diagnostic_category = 'provider_response_rejected'
    error.http_status = 401
    rig.transport.send.side_effect = error
    rig.delivery.publish(EVENT, 'Saved in-app reply')
    meta = json.loads(rig.db.execute("SELECT text FROM events WHERE kind='notification_status'").fetchone()[0])
    assert meta.get('diagnostic') == {'version': 1, 'stage': 'sms_send', 'category': 'unexpected_error'}


@pytest.mark.parametrize('provider_status,decision', [
    ('SENT', 'sms_accepted'), ('DELIVERED', 'sms_delivered'), ('READ', 'sms_delivered'),
])
def test_sendblue_response_reaches_durable_state_without_claiming_sent_is_delivered(rig, provider_status, decision):
    arm = parser_arm()
    rig.transport.send.side_effect = lambda *a, **kw: arm._result(
        Response({'message_handle': 'fixture-handle', 'status': provider_status}),
        'text', '+15555550101')
    rig.delivery.publish(EVENT, 'Saved in-app reply')
    assert rig.db.execute("SELECT decision FROM events WHERE kind='notification_status'").fetchone()[0] == decision
    assert rig.db.execute("SELECT decision FROM events WHERE kind='reply_outbox'").fetchone()[0] == decision
    meta = json.loads(rig.db.execute("SELECT text FROM events WHERE kind='notification_status'").fetchone()[0])
    assert meta['provider_id'] == 'fixture-handle'
    assert 'diagnostic' not in meta
    rig.delivery.sweep()
    assert rig.transport.send.call_count == 1


@pytest.mark.parametrize('payload,category', [
    ({'message_handle': {'private': PRIVATE}, 'status': 'QUEUED'}, 'provider_response_missing_handle'),
    ({'message_handle': [PRIVATE], 'status': 'QUEUED'}, 'provider_response_missing_handle'),
    ({'message_handle': True, 'status': 'QUEUED'}, 'provider_response_missing_handle'),
    ({'message_handle': 123, 'status': 'QUEUED'}, 'provider_response_missing_handle'),
    ({'message_handle': 'fixture-handle', 'status': {'private': PRIVATE}}, 'provider_response_invalid_shape'),
    ({'message_handle': 'fixture-handle', 'status': None}, 'provider_response_invalid_shape'),
])
def test_malformed_success_response_never_creates_fake_handle_or_delivery_claim(rig, payload, category):
    arm = parser_arm()
    rig.transport.send.side_effect = lambda *a, **kw: arm._result(Response(payload), 'text', '+15555550101')
    rig.delivery.publish(EVENT, 'Saved in-app reply')
    attempt = dict(rig.db.execute("SELECT * FROM events WHERE kind='notification_status'").fetchone())
    assert attempt['decision'] == 'sms_unconfirmed'
    meta = json.loads(attempt['text'])
    assert meta['provider_id'] == ''
    assert meta['diagnostic']['category'] == category
    assert PRIVATE not in attempt['text']
    rig.delivery.sweep()
    assert rig.transport.send.call_count == 1
