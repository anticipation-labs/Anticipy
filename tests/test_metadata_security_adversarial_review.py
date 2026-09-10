"""Independent, offline privacy/authority controls for reply diagnostics."""
import json
import subprocess
import sys
from types import SimpleNamespace

import pytest
import requests

from brain import backend, reply_diagnostics as diagnostics
from brain import sendblue_arm
from brain.sendblue_arm import SendblueSendFailed
from test_reply_diagnostics import rig as classifier_rig  # noqa: F401
from test_reply_delivery import EVENT, rig as delivery_rig  # noqa: F401


class SecretString(str):
    def __str__(self):
        raise AssertionError('must not render custom metadata')


class SecretInteger(int):
    def __str__(self):
        raise AssertionError('must not render custom metadata')


def test_serializer_rejects_primitive_subclasses_even_when_value_is_allowlisted():
    assert diagnostics.diagnostic('sms_send', SecretString('timeout'),
                                  SecretInteger(401), model_role=SecretString('main')) == {
        'version': 1, 'stage': 'sms_send', 'category': 'unexpected_error'}


def test_typed_http_error_with_raising_response_property_is_content_free():
    class BrokenHTTPError(requests.HTTPError):
        def __getattribute__(self, key):
            if key == 'response':
                raise RuntimeError('private fixture body')
            return super().__getattribute__(key)
        def __str__(self):
            raise AssertionError('must not stringify an exception')
    assert diagnostics.exception_diagnostic(BrokenHTTPError()) == {
        'version': 1, 'stage': 'sms_send', 'category': 'unexpected_error'}


def test_rejected_diagnostic_write_still_calls_actual_durable_reply_path(classifier_rig, monkeypatch):
    r = classifier_rig
    calls = []
    r.model.chat.side_effect = TimeoutError('private model text')
    def reject(*args, **kwargs):
        calls.append(kwargs['json'])
        return SimpleNamespace(raise_for_status=lambda: (_ for _ in ()).throw(
            requests.HTTPError('private sink body')))
    monkeypatch.setattr(backend, 'post', reject)
    r.convo.reply_delivery = lambda event, body, media=None, **kwargs: {
        'via': 'durable-reply', 'id': 'reply-fixture', 'body': body}
    event = {'id': 'input1', 'owner_ref': 'owner1', 'kind': 'app_reply'}
    with r.convo.from_event(event):
        result = r.convo.on_reply('app:owner1', 'harmless fixture')
    assert result['intent'] == 'unavailable'
    assert result['acted'] is None
    assert len(calls) == 1
    assert 'private' not in json.dumps(calls)


def test_malformed_sendblue_error_cannot_remove_durable_attempt_or_resend(delivery_rig):
    r = delivery_rig
    error = SendblueSendFailed('private provider body', category='timeout')
    del error.diagnostic_category
    r.transport.send.side_effect = error
    r.delivery.publish(EVENT, 'saved fixture reply')
    r.delivery.sweep()
    assert r.transport.send.call_count == 1
    assert r.db.execute("SELECT decision FROM events WHERE kind='notification_status'").fetchone()[0] == 'sms_unconfirmed'
    assert r.db.execute("SELECT text FROM events WHERE kind='anticipy_text'").fetchone()[0] == 'saved fixture reply'


@pytest.mark.parametrize('first', ['brain.conversation', 'brain.reply_delivery', 'brain.sendblue_arm'])
def test_import_order_has_no_new_cycle(first):
    result = subprocess.run([sys.executable, '-c',
        f'import {first}; import brain.reply_diagnostics; import brain.conversation; import brain.reply_delivery; import brain.sendblue_arm'],
        capture_output=True, text=True, check=False, timeout=15)
    assert result.returncode == 0
    assert result.stdout == ''


@pytest.mark.parametrize('status', ['ERROR', 'declined', 'FaIlEd', 'QUEUED',
    'SENT', 'DELIVERED', 'READ', ' PENDING ', '', None, False, 123,
    {'private': 'fixture'}, ['ERROR']])
@pytest.mark.parametrize('http_ok', [True, False])
def test_followup_preserves_existing_retry_predicate_for_json_values(status, http_ok):
    response = SimpleNamespace(ok=http_ok, json=lambda: {'status': status})
    previous = not http_ok or str(status or '').lower() in sendblue_arm.DEAD_STATES
    assert sendblue_arm._nothing_went_out(response) == previous


@pytest.mark.parametrize('field,value,category', [
    ('message_handle', SecretString('opaque-fixture'), 'provider_response_missing_handle'),
    ('status', SecretString('QUEUED'), 'provider_response_invalid_shape'),
    ('message_handle', SecretInteger(123), 'provider_response_missing_handle'),
], ids=['custom-handle-string', 'custom-status-string', 'custom-handle-integer'])
def test_followup_send_parser_rejects_primitive_subclasses(field, value, category):
    arm = object.__new__(sendblue_arm.SendblueArm)
    payload = {'message_handle': 'valid-fixture-handle', 'status': 'QUEUED', field: value}
    response = SimpleNamespace(ok=True, status_code=200, json=lambda: payload)
    with pytest.raises(SendblueSendFailed) as caught:
        arm._result(response, 'text', 'fixture-destination')
    assert caught.value.diagnostic_category == category
    assert 'fixture-destination' not in str(caught.value)
